import logging
import tempfile
import numpy as np
import soundfile as sf
import sounddevice as sd
from pynput import keyboard
from pynput.keyboard import Controller
import subprocess
import os
import threading
import time
from transformers import pipeline as hf_pipeline
import pyautogui
import atexit
import shutil

logging.debug("Checking audio devices...")
print(sd.query_devices())

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Whisper pipeline
try:
    asr = hf_pipeline(
        "automatic-speech-recognition",
        model="openai/whisper-tiny",
        device=-1  # CPU; use 0 for GPU if available
    )
except Exception as e:
    logging.error(f"Failed to load Whisper model: {e}")
    pyautogui.alert("Failed to load Whisper model. Check dependencies and try again.")
    raise

# Initialize keyboard controller
keyboard_controller = Controller()
is_dictating = False
audio_buffer = []
sample_rate = 16000  # Whisper requires 16kHz


YDOTOOL_SOCKET = os.path.expanduser("~/.ydotool_socket")
ydotool_process = None

def ensure_ydotoold_running():
    """Ensure ydotoold (the uinput daemon) is running and the socket exists."""
    global ydotool_process
    # If it's already running, do nothing
    if ydotool_process and ydotool_process.poll() is None:
        return

    # Prepare the socket directory
    os.makedirs(os.path.dirname(YDOTOOL_SOCKET), exist_ok=True)
    if os.path.exists(YDOTOOL_SOCKET):
        try:
            os.unlink(YDOTOOL_SOCKET)
        except OSError:
            pass

    # Start ydotoold (not ydotool), with proper ownership
    try:
        ydotool_process = subprocess.Popen([
            "sudo", "ydotoold",
            "--socket-path", YDOTOOL_SOCKET,
            "--socket-own", f"{os.getuid()}:{os.getgid()}"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logging.debug("Started ydotoold daemon")

        # Wait for the socket to appear
        for _ in range(20):
            if os.path.exists(YDOTOOL_SOCKET):
                logging.debug("ydotool socket is ready")
                return
            time.sleep(0.1)
        logging.error("ydotool socket did not appear in time")
    except Exception as e:
        logging.error(f"Failed to start ydotoold: {e}")

def stop_ydotoolId():
    """Stop the ydotool socket process."""
    global ydotool_process
    if ydotool_process and ydotool_process.poll() is None:
        ydotool_process.terminate()
        try:
            ydotool_process.wait(timeout=2.0)
            logging.debug("Stopped ydotool socket process")
        except Exception as e:
            logging.error(f"Failed to stop ydotool socket: {e}")
        ydotool_process = None

atexit.register(stop_ydotoolId)

def is_wayland():
    """Check if running on Wayland (Linux)."""
    return os.environ.get("WAYLAND_DISPLAY") is not None or os.environ.get("XDG_SESSION_TYPE") == "wayland"

def type_text(text):
    """Inject text into the active input field on Wayland via ydotool."""
    try:
        focused_window = pyautogui.getActiveWindow()
        if not focused_window:
            logging.error("No active window found for text injection")
            pyautogui.alert("No active window found. Please focus an input field.")
            return

        if os.name == "posix" and is_wayland() and shutil.which("ydotool"):
            # Ensure the daemon is up
            ensure_ydotoold_running()
            logging.debug(f"Typing via ydotool: {text}")
            subprocess.run([
                "ydotool",
                "--socket-path", YDOTOOL_SOCKET,
                "type", "--key-delay", "1", text
            ], check=True)
        else:
            # Fallback to pynput (X11/macOS)
            logging.debug(f"Typing via pynput: {text}")
            keyboard_controller.type(text)

        logging.info(f"Typed text: {text}")
    except subprocess.CalledProcessError as e:
        logging.error(f"ydotool command failed: {e}")
        use_clipboard_fallback(text)
    except Exception as e:
        logging.error(f"Text injection error: {e}")
        pyautogui.alert(f"Failed to type text: {e}")

def use_clipboard_fallback(text):
    """Fallback to clipboard for text injection."""
    try:
        import pyperclip
        pyperclip.copy(text)
        logging.debug(f"Copied to clipboard: {text}")

        with keyboard_controller.pressed(keyboard.Key.ctrl):
            keyboard_controller.press('v')
            keyboard_controller.release('v')
        logging.info("Used clipboard fallback for text injection")
    except Exception as e:
        logging.error(f"Clipboard fallback failed: {e}")
        pyautogui.alert(f"Failed to use clipboard fallback: {e}")

def transcribe_audio(audio_input) -> str:
    """Transcribe audio (file path or numpy array) using Whisper."""
    logging.debug(f"Transcribe audio: input type={type(audio_input)}")
    temp_file = None
    try:
        if isinstance(audio_input, str):
            audio_path = audio_input
        else:
            arr = np.array(audio_input, dtype=np.float32)
            if arr.ndim > 1:
                arr = arr[:, 0]  # Use first channel for mono
            temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            sf.write(temp_file.name, arr, sample_rate)
            audio_path = temp_file.name
            logging.debug(f"Wrote temp WAV: {audio_path}")

        result = asr(audio_path)
        text = result.get("text", "").strip()
        logging.debug(f"Transcription result: {text}")
        return text
    except Exception as e:
        logging.error(f"Transcription error: {e}")
        return ""
    finally:
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
                logging.debug(f"Deleted temp file: {temp_file.name}")
            except Exception as e:
                logging.warning(f"Failed to delete temp file: {e}")
    logging.debug(f"transcribing {len(arr)/sample_rate:.2f}s audio")

def record_audio():
    """Record audio while dictating and transcribe in chunks."""
    global audio_buffer
    audio_buffer = []
    try:
        with sd.InputStream(samplerate=sample_rate, channels=1, dtype='float32') as stream:
            logging.debug("Started audio recording")
            while is_dictating:
                data, overflowed = stream.read(sample_rate // 5)  # Read 0.5s chunks
                if overflowed:
                    logging.warning("Audio buffer overflow")
                audio_buffer.append(data)
                # Process 5-second chunks (or when dictation stops)
                if len(audio_buffer) * 0.5 >= 2:
                    # audio_chunk = np.concatenate(audio_buffer, axis=0)
                    # audio_buffer = []
                    # text = transcribe_audio(audio_chunk)
                    # if text:
                    #     type_text(text + " ")
                    process_audio_buffer()
    except Exception as e:
        logging.error(f"Audio capture error: {e}")
        # pyautogui.alert(f"Audio capture failed: {e}")

pressed_keys = set()

def on_press(key):
    """Handle hotkey press (Ctrl+Alt+1 to start)."""
    global is_dictating, pressed_keys
    try:
        pressed_keys.add(key)

        logging.debug(f"Key pressed: {key}, pressed_keys: {pressed_keys}")

        if key == keyboard.KeyCode.from_char("1") and {keyboard.Key.ctrl, keyboard.Key.alt}.issubset(pressed_keys):
            if not is_dictating:
                is_dictating = True
                logging.debug("Dictation started")
                # Start recording in a separate thread
                threading.Thread(target=record_audio, daemon=True).start()
    except Exception as e:
        logging.error(f"Hotkey press error: {e}")
        pyautogui.alert(f"Hotkey error: {e}")

def on_release(key):
    """Handle hotkey release (stop on 1)."""
    global is_dictating, pressed_keys
    try:
        if key in pressed_keys:
            pressed_keys.remove(key)
        
        logging.debug(f"Key released: {key}, pressed_keys: {pressed_keys}")
        if key == keyboard.KeyCode.from_char("1"):
            if is_dictating:
                is_dictating = False
                logging.debug("Dictation stopped")

                if audio_buffer:
                    process_audio_buffer()
    
    except Exception as e:
        logging.error(f"Hotkey release error: {e}")

def process_audio_buffer():
    """Process and transcribe accumulated audio"""
    global audio_buffer
    if not audio_buffer:
        return
        
    try:
        audio_chunk = np.concatenate(audio_buffer, axis=0)
        logging.debug(f"Processing audio chunk: {len(audio_chunk)/sample_rate:.2f}s")
        
        # Verify audio content
        if np.max(np.abs(audio_chunk)) < 0.01:  # Threshold for silence
            logging.warning("Audio buffer appears silent")
            
        text = transcribe_audio(audio_chunk)
        audio_buffer = []
        
        if text:
            logging.debug(f"Transcription: '{text}'")
            type_text(text + " ")
        else:
            logging.warning("Empty transcription result")
            
    except Exception as e:
        logging.error(f"Audio processing error: {e}")

# Track pressed keys for hotkey detection
pressed_keys = set()
def track_keys(key):
    if key in (keyboard.Key.ctrl, keyboard.Key.alt, keyboard.KeyCode.from_char("1")):
        pressed_keys.add(key)
    return True

def untrack_keys(key):
    pressed_keys.discard(key)

# Check dependencies
if os.name == "posix" and is_wayland() and os.system("which ydotool > /dev/null") != 0:
    logging.warning("ydotool not found; Wayland text injection may fail")
    pyautogui.alert("Install ydotool for Wayland support: sudo apt install ydotool")

# Start keyboard listener
# try:
#     with keyboard.Listener(on_press=on_press, on_release=on_release, on_press_callback=track_keys, on_release_callback=untrack_keys) as listener:
#         logging.info("VoxType started. Press Ctrl+Alt+1 to dictate.")
#         listener.join()
# except Exception as e:
#     logging.error(f"Keyboard listener error: {e}")
#     pyautogui.alert(f"Failed to start VoxType: {e}. Check accessibility permissions on macOS.")

try:
    logging.info("VoxType starting...")
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        logging.info("VoxType started. Press Ctrl+Alt+1 to dictate.")
        listener.join()
except Exception as e:
    logging.error(f"Keyboard listener error: {e}")
    pyautogui.alert(f"Failed to start VoxType: {e}. Check accessibility permissions.")