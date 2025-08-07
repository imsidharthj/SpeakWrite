#!/usr/bin/env python3
"""
Typing Automation Tool - Universal Input Text Sender with Voice Input
Works with any application (native, web, built-in) on Wayland/X11
"""

import subprocess
import sys
import time
import random
import threading
import logging

# Voice input dependencies
try:
    import sounddevice as sd
    import numpy as np
    from transformers import pipeline as hf_pipeline
    from pynput import keyboard
    VOICE_AVAILABLE = True
except ImportError as e:
    VOICE_AVAILABLE = False
    print(f"Voice input not available: {e}")
    print("Install with: pip install sounddevice transformers torch pynput")

# Initialize Whisper if available
if VOICE_AVAILABLE:
    try:
        logging.basicConfig(level=logging.ERROR)  # Suppress transformers warnings
        print("Initializing Whisper-tiny ASR model...")
        asr_pipeline = hf_pipeline(
            "automatic-speech-recognition",
            model="openai/whisper-tiny",
            device=-1  # Use CPU
        )
        print("✓ Whisper ASR model loaded successfully")
    except Exception as e:
        print(f"Failed to load Whisper model: {e}")
        VOICE_AVAILABLE = False

# Global voice recording state
recording_active = False
audio_data = []
SAMPLE_RATE = 16000

# ============================================================================
# WINDOW MANAGEMENT FUNCTIONS
# ============================================================================

def get_windows():
    """Get list of all open windows using wmctrl"""
    try:
        result = subprocess.run(['wmctrl', '-l'], capture_output=True, text=True, check=True)
        windows = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split(None, 3)  # Split into max 4 parts
                if len(parts) >= 4:
                    window_id = parts[0]
                    title = parts[3]
                    windows.append((window_id, title))
        return windows
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

def display_window_menu(windows, text_preview):
    """Display numbered menu of windows and get user selection"""
    print(f"\nText to type: '{text_preview[:50]}{'...' if len(text_preview) > 50 else ''}'")
    print("\nAvailable Windows:")
    for i, (window_id, title) in enumerate(windows, 1):
        print(f"{i}. {title}")
    
    try:
        raw_input = input(f"\nSelect window (1-{len(windows)}) or 'q' to quit: ")
        
        # Debug: Show exactly what we received
        print(f"Debug: Raw input received: {repr(raw_input)}")
        
        # Enhanced input cleaning - remove all control characters and whitespace
        choice = ''.join(c for c in raw_input if c.isprintable()).strip()
        
        # Debug: Show cleaned input
        print(f"Debug: Cleaned input: {repr(choice)}")
        
        if choice.lower() in ['q', 'quit', 'exit']:
            return None
        
        choice_num = int(choice)
        if 1 <= choice_num <= len(windows):
            return windows[choice_num - 1][0]  # Return window_id
        else:
            print(f"Invalid selection! Please enter a number between 1 and {len(windows)}")
            return None
    except ValueError:
        print(f"Invalid input! Please enter a number between 1 and {len(windows)} or 'q' to quit")
        return None
    except KeyboardInterrupt:
        print("\nExiting...")
        return None

def focus_window(window_id):
    """Focus the selected window using wmctrl"""
    try:
        subprocess.run(['wmctrl', '-i', '-a', window_id], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        print(f"Error: Failed to focus window {window_id}")
        return False

# ============================================================================
# TYPING FUNCTIONS
# ============================================================================

def init_pydotool():
    """Initialize pydotool connection"""
    try:
        import pydotool
        pydotool.init("/run/user/1000/.ydotool_socket")
        return True
    except Exception:
        return False

def type_with_human_speed(text, use_pydotool=True):
    """Type text with human-like timing"""
    if use_pydotool:
        try:
            import pydotool
            # Calculate human-like delays
            delays = []
            for char in text:
                base_delay = random.randint(50, 150)
                if char in '.,!?;:':
                    base_delay += random.randint(100, 200)  # Longer pause after punctuation
                delays.append(base_delay)
            
            # Type character by character with delays
            for i, char in enumerate(text):
                pydotool.type_string(char)
                if i < len(text) - 1:
                    time.sleep(delays[i] / 1000.0)
            return True
        except Exception:
            return False
    else:
        try:
            # Subprocess fallback with character-by-character timing
            for char in text:
                subprocess.run(['ydotool', 'type', char], check=True, capture_output=True)
                delay = random.randint(50, 150) / 1000.0
                if char in '.,!?;:':
                    delay += random.randint(100, 200) / 1000.0
                time.sleep(delay)
            return True
        except subprocess.CalledProcessError:
            return False

def type_text(text):
    """Main typing function with fallback"""
    # Try pydotool first
    if pydotool_available:
        if type_with_human_speed(text, use_pydotool=True):
            return True
    
    # Fallback to subprocess
    if type_with_human_speed(text, use_pydotool=False):
        return True
    
    print("Error: Both pydotool and subprocess typing methods failed")
    return False

# ============================================================================
# VOICE INPUT FUNCTIONS
# ============================================================================

# def transcribe_input_to_text():
#     """Real-time voice transcription with Ctrl+Space hotkey control"""
#     if not VOICE_AVAILABLE:
#         print("Error: Voice input not available")
#         sys.exit(1)
    
#     global recording_active, audio_data
#     recording_active = False
#     audio_data = []
#     transcribed_text = ""
    
#     print("🎤 Hold Ctrl+alt and speak...")
#     print("Release Ctrl+alt when done speaking")
    
#     def on_hotkey_press():
#         global recording_active, audio_data
#         if not recording_active:
#             recording_active = True
#             audio_data = []
#             print("\r🔴 Recording... ", end='', flush=True)
    
#     def on_hotkey_release():
#         global recording_active
#         if recording_active:
#             recording_active = False
#             print("\r⏹️  Processing... ", end='', flush=True)
    
#     # Setup hotkey listener
#     hotkey = keyboard.HotKey(
#         keyboard.HotKey.parse('<ctrl>+<alt>'),
#         on_hotkey_press
#     )
    
#     hotkey_release = keyboard.HotKey(
#         keyboard.HotKey.parse('<ctrl>+<alt>'),
#         on_hotkey_release
#     )
    
#     # Audio recording thread
#     def audio_recorder():
#         global audio_data
#         try:
#             with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32') as stream:
#                 while True:
#                     if recording_active:
#                         chunk, _ = stream.read(int(SAMPLE_RATE * 0.5))  # 0.5 second chunks
#                         audio_data.extend(chunk.flatten())
#                     else:
#                         time.sleep(0.1)
#         except Exception as e:
#             print(f"\nAudio recording error: {e}")
    
#     # Real-time transcription thread
#     def real_time_transcriber():
#         nonlocal transcribed_text
#         last_transcription = ""
        
#         while True:
#             if recording_active and len(audio_data) > SAMPLE_RATE:  # At least 1 second of audio
#                 try:
#                     # Get recent audio for transcription
#                     recent_audio = np.array(audio_data[-int(SAMPLE_RATE * 2):])  # Last 2 seconds
                    
#                     # Transcribe
#                     result = asr_pipeline({"array": recent_audio, "sampling_rate": SAMPLE_RATE})
#                     current_text = result.get("text", "").strip()
                    
#                     if current_text and current_text != last_transcription:
#                         transcribed_text = current_text
#                         last_transcription = current_text
#                         # Clear line and show current transcription
#                         print(f"\r🎤 Transcribing: {transcribed_text[:60]}{'...' if len(transcribed_text) > 60 else ''}", end='', flush=True)
                
#                 except Exception as e:
#                     print(f"\nTranscription error: {e}")
            
#             elif not recording_active and len(audio_data) > 0:
#                 # Final transcription when recording stops
#                 try:
#                     final_audio = np.array(audio_data)
#                     result = asr_pipeline({"array": final_audio, "sampling_rate": SAMPLE_RATE})
#                     transcribed_text = result.get("text", "").strip()
#                     break
#                 except Exception as e:
#                     print(f"\nFinal transcription error: {e}")
#                     break
            
#             time.sleep(0.5)
    
#     # Keyboard listener
#     def keyboard_listener():
#         with keyboard.Listener(
#             on_press=lambda key: hotkey.press(key) or hotkey_release.press(key),
#             on_release=lambda key: hotkey.release(key) or hotkey_release.release(key)
#         ) as listener:
#             listener.join()
    
#     # Start threads
#     audio_thread = threading.Thread(target=audio_recorder, daemon=True)
#     transcribe_thread = threading.Thread(target=real_time_transcriber, daemon=True)
#     keyboard_thread = threading.Thread(target=keyboard_listener, daemon=True)
    
#     audio_thread.start()
#     transcribe_thread.start()
#     keyboard_thread.start()
    
#     # Wait for user to finish recording
#     try:
#         while True:
#             time.sleep(0.1)
#             if not recording_active and len(audio_data) > 0 and transcribed_text:
#                 break
            
#             # Check for quit command
#             if not recording_active and len(audio_data) == 0:
#                 # Allow manual quit
#                 try:
#                     user_input = input("\nOr type 'q' to quit: ")
#                     if user_input.lower() in ['q', 'quit', 'exit']:
#                         return None
#                 except:
#                     pass
    
#     except KeyboardInterrupt:
#         print("\nExiting...")
#         return None
    
#     print(f"\n✓ Final transcription: '{transcribed_text}'")
#     return transcribed_text if transcribed_text else None

# ============================================================================

def transcribe_input_to_text():
    """Manual voice transcription: press 's' to start, 'q' to stop"""
    if not VOICE_AVAILABLE:
        print("Error: Voice input not available")
        sys.exit(1)

    global recording_active, audio_data
    recording_active = False
    audio_data = []
    transcribed_text = ""
    print("🎤 Press 's' then Enter to start recording, 'q' then Enter to stop and transcribe.")

    def audio_recorder():
        global audio_data, recording_active
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32') as stream:
                while recording_active:
                    chunk, _ = stream.read(int(SAMPLE_RATE * 0.5))
                    audio_data.extend(chunk.flatten())
        except Exception as e:
            print(f"\nAudio recording error: {e}")

    while True:
        cmd = input("Press 's' to start recording, or 'q' to quit: ").strip().lower()
        if cmd == 'q':
            return None
        if cmd == 's':
            recording_active = True
            audio_data = []
            print("🔴 Recording... Press 'q' then Enter to stop.")
            rec_thread = threading.Thread(target=audio_recorder)
            rec_thread.start()
            while True:
                stop_cmd = input()
                if stop_cmd.strip().lower() == 'q':
                    recording_active = False
                    rec_thread.join()
                    print("⏹️ Processing... ")
                    break
            break

    try:
        if len(audio_data) > 0:
            final_audio = np.array(audio_data)
            result = asr_pipeline({"array": final_audio, "sampling_rate": SAMPLE_RATE})
            transcribed_text = result.get("text", "").strip()
    except Exception as e:
        print(f"\nFinal transcription error: {e}")
        return None

    print(f"\n✓ Final transcription: '{transcribed_text}'")
    return transcribed_text if transcribed_text else None

# ============================================================================
# USER INPUT FUNCTIONS  
# ============================================================================

def get_user_text():
    """Get text input via voice transcription"""
    if VOICE_AVAILABLE:
        return transcribe_input_to_text()
    else:
        # Fallback to manual input if voice not available  
        try:
            raw_input = input("\nEnter text to type (or 'q' to quit): ")
            text = ''.join(c if c.isprintable() or c == ' ' else '' for c in raw_input).strip()
            
            if text.lower() in ['q', 'quit', 'exit']:
                return None
            if not text:
                print("Please enter some text!")
                return get_user_text()
            return text
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            return None

def countdown_timer(seconds=2):
    """Give user time to prepare after window selection"""
    print(f"\nFocusing target window and typing in...")
    for i in range(seconds, 0, -1):
        print(f"{i}...", end=' ', flush=True)
        time.sleep(1)
    print("Typing now!")
    time.sleep(0.5)  # Small pause before typing

# ============================================================================
# MAIN PROGRAM
# ============================================================================

def main():
    """Main program flow"""
    print("=== Universal Typing Automation Tool with Voice Input ===")
    
    # Show voice input status
    if VOICE_AVAILABLE:
        print("✓ Voice input enabled (Ctrl+Space to record)")
    else:
        print("⚠ Voice input disabled, using manual input fallback")
    
    # Initialize typing method
    global pydotool_available
    pydotool_available = init_pydotool()
    if pydotool_available:
        print("✓ pydotool initialized successfully")
    else:
        print("⚠ pydotool failed, will use subprocess fallback")
    
    while True:
        # 1. Get windows
        windows = get_windows()
        if not windows:
            print("Error: No windows found or wmctrl not available")
            print("Make sure wmctrl is installed: sudo apt install wmctrl")
            sys.exit(1)
        
        # 2. Get text to type via voice input
        text = get_user_text()
        if text is None:
            break
        
        # 3. User selects target window (showing text preview)
        selected_window = display_window_menu(windows, text)
        if not selected_window:
            if selected_window is None:
                break
            continue
        
        # 4. Focus window and type immediately
        print(f"\nAttempting to focus target window...")
        if focus_window(selected_window):
            countdown_timer(2)
            if type_text(text):
                print("✓ Text typed successfully!\n")
            else:
                print("✗ Failed to type text\n")
        else:
            print("✗ Failed to focus window. Please try selecting a different window.\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExiting...")
        sys.exit(0)