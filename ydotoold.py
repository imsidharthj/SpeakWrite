"""
Typing Automation Tool - Universal Input Text Sender
Works with any application (native, web, built-in) on Wayland/X11
"""

import subprocess
import sys
import time
import random

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
# USER INPUT FUNCTIONS  
# ============================================================================

def get_user_text():
    """Get text input from user"""
    try:
        raw_input = input("\nEnter text to type (or 'q' to quit): ")
        
        # Debug: Show exactly what we received
        print(f"Debug: Raw text input received: {repr(raw_input)}")
        
        # For text input, we want to preserve spaces but clean control characters
        # Remove only non-printable control characters, keep spaces
        text = ''.join(c if c.isprintable() or c == ' ' else '' for c in raw_input).strip()
        
        # Debug: Show cleaned input
        print(f"Debug: Cleaned text input: {repr(text)}")
        
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
    print("=== Universal Typing Automation Tool ===")
    
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
        
        # 2. Get text to type FIRST (while terminal has focus)
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



# from pydotool import init, type_string

# init("/run/user/1000/.ydotool_socket")
# type_string("Hello!")

# import subprocess

# def type_text(text):
#     subprocess.run(["ydotool", "type", text])

# # Example usage:
# type_text("Hello from Python!")