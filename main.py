import os
import time
import speech_recognition as sr
import pyttsx3
import json
import requests
from datetime import datetime
import pytz
from dotenv import load_dotenv
import google.generativeai as genai
import pyautogui

# Import from your utils file 
from utils import preprocess_spoken_text

# Configuration and Setup 

# Load API keys from .env
load_dotenv()
gemini_api_key = os.getenv("GEMINI_API_KEY")

if not gemini_api_key:
    raise ValueError("GEMINI_API_KEY not found. Please set it in .env")

# Configure the Gemini model
genai.configure(api_key=gemini_api_key)
model = genai.GenerativeModel("") # Select Model

# Initialize Text-to-Speech engine globally
engine = pyttsx3.init()
engine.setProperty('rate', 180) # Optional: Set a faster speaking rate

# Memory file path
MEMORY_FILE = "conversation_memory.json"

# Global variable to hold memory state, initialized once
# This will be passed around or accessed by functions that need it.
# It's better to pass it explicitly to functions that modify it.
_current_memory_state = {}

# --- Geolocation Functions ---

def get_ip_based_location():
    """Attempts to get approximate city/region/country based on IP address."""
    try:
        response = requests.get('https://ipinfo.io/json', timeout=5)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        data = response.json()
        city = data.get('city', 'Unknown City')
        region = data.get('region', 'Unknown Region')
        country = data.get('country', 'Unknown Country')
        timezone = data.get('timezone', 'UTC') # Get timezone for time operations

        location_str = f"{city}, {region}, {country}"
        print(f"🌍 Retrieved IP-based location: {location_str} (Timezone: {timezone})")
        return location_str, timezone
    except requests.exceptions.ConnectionError:
        print("⚠️ Network error: Could not connect to ipinfo.io. Please check your internet connection.")
    except requests.exceptions.Timeout:
        print("⚠️ Network error: Request to ipinfo.io timed out. Your internet might be slow or unstable.")
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Network error: An unexpected error occurred while fetching location: {e}")
    except json.JSONDecodeError:
        print("⚠️ Data error: Could not decode location data from ipinfo.io. Response was not valid JSON.")
    return "Unknown Location", "UTC" # Default to UTC if location cannot be found

def get_current_time_in_timezone(timezone_str):
    """Returns the current formatted time for a given timezone string."""
    try:
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)
        return now.strftime('%A, %B %d, %Y at %I:%M:%S %p %Z')
    except pytz.exceptions.UnknownTimeZoneError:
        return f"Unknown timezone: {timezone_str}. Cannot determine local time."
    except Exception as e:
        return f"Error getting time for {timezone_str}: {e}"

# --- Calculation Function ---

def perform_calculation(expression):
    """
    Safely evaluates a mathematical expression.
    Returns (result_string, is_success).
    """
    allowed_chars = "0123456789.+-*/() "
    # Basic check for non-allowed characters for simple prevention of arbitrary code.
    # The preprocessing now handles many common spoken symbols into actual characters.
    for char in expression:
        if char not in allowed_chars:
            return "The calculation contains unsupported characters or symbols.", False

    try:
        result = eval(expression)
        return str(result), True
    except (SyntaxError, TypeError, NameError, ZeroDivisionError) as e:
        return f"I couldn't perform that calculation due to an error: {e}. Please ensure it's a valid mathematical expression.", False
    except Exception as e:
        return f"An unexpected error occurred during calculation: {e}", False

# --- Memory Management Functions ---

def load_memory():
    """Loads the conversation memory from the JSON file."""
    initial_memory_structure = {
        "accumulated_user_input": [],
        "last_gemini_question": None,
        "needs_clarification": False,
        "user_defined_location": None,
        "last_retrieved_ip_location": None
    }
    if not os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'w') as f:
            json.dump(initial_memory_structure, f, indent=4)
        return initial_memory_structure

    try:
        with open(MEMORY_FILE, 'r') as f:
            memory = json.load(f)
            # Ensure the loaded memory has all expected keys, add if missing (for robust updates)
            for key, default_val in initial_memory_structure.items():
                if key not in memory:
                    memory[key] = default_val
            return memory
    except json.JSONDecodeError:
        print(f"Warning: Corrupted {MEMORY_FILE}. Resetting memory.")
        # If corrupted, clear and return initial structure
        clear_all_memory_and_reset_file() # This will also save the initial structure
        return initial_memory_structure

def save_memory(data):
    """Saves the current conversation memory to the JSON file."""
    with open(MEMORY_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def reset_memory_for_new_turn(memory_data):
    """Resets conversational memory flags and accumulated input for a new turn."""
    memory_data["accumulated_user_input"] = []
    memory_data["last_gemini_question"] = None
    memory_data["needs_clarification"] = False
    # Do NOT reset user_defined_location or last_retrieved_ip_location here
    # as these persist across turns.
    return memory_data

def clear_all_memory_and_reset_file():
    """Clears all conversation memory and resets the file to initial state."""
    initial_memory = {
        "accumulated_user_input": [],
        "last_gemini_question": None,
        "needs_clarification": False,
        "user_defined_location": None,
        "last_retrieved_ip_location": None
    }
    save_memory(initial_memory)
    print("✨ All conversation memory cleared and file reset.")
    return initial_memory

# --- Voice and Speech Functions ---

def get_speech_input():
    """Captures speech input from the microphone and converts it to text."""
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("\n🎤 Listening... (Speak your question)")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=8)
        except sr.WaitTimeoutError:
            print("🕒 No speech detected within the timeout period.")
            return None
    try:
        text = recognizer.recognize_google(audio)
        print(f"🗣️ You said: {text}")
        return text
    except sr.UnknownValueError:
        print("❌ Could not understand audio. Please try speaking more clearly.")
    except sr.RequestError as e:
        print(f"❌ Could not request results from Google Speech Recognition service; check your internet connection or API limits: {e}")
    return None

def speak_response(response):
    """Speaks the given text response aloud."""
    engine.say(response)
    engine.runAndWait()

def write_response(text):
    """
    Types the given text using pyautogui.
    Adds a small delay before typing to allow user to switch focus.
    """
    speak_response("Okay, I will type that for you. Please switch to the desired application now.")
    time.sleep(2) # Give user 2 seconds to switch to notepad, word doc, etc.
    try:
        # Use pyautogui.write with a slight interval for better reliability
        pyautogui.write(text, interval=0.01)
        print(f"✍️ Typed: {text[:50]}...") # Print first 50 chars for log
    except Exception as e:
        speak_response(f"I encountered an error trying to type: {e}")
        print(f"❌ Error typing: {e}")

# --- Gemini Interaction Logic ---

def ask_gemini(full_prompt):
    """
    Sends the prompt to Gemini and returns its response.
    Includes error handling for network issues with Gemini API.
    """
    try:
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        # More specific error handling for Gemini API
        if "google.api_core.exceptions.InternalServerError" in str(e) or "google.api_core.exceptions.ServiceUnavailable" in str(e):
            return "Error: The Gemini service is currently unavailable. Please try again later."
        elif "google.api_core.exceptions.BlockedPromptException" in str(e):
            return "Error: Your request was blocked due to content policy. Please try rephrasing."
        elif "google.api_core.exceptions.ResourceExhausted" in str(e):
            return "Error: You've sent too many requests to Gemini. Please wait a moment."
        elif "requests.exceptions.ConnectionError" in str(e) or "urllib3.exceptions.NewConnectionError" in str(e):
            return "Error: I cannot connect to the Gemini service. Please check your internet connection."
        elif "google.api_core.exceptions.InvalidArgument" in str(e):
            return "Error: The request sent to Gemini was invalid. This might be a prompt issue."
        else:
            return f"Error communicating with Gemini: {e}"

# --- Main Application Logic ---

def main():
    global _current_memory_state # Declare intent to use global variable

    print("🎙️ Gemini Voice Assistant with Calculations, Dynamic Location & Writing Capabilities (Speak 'exit' to quit)")
    speak_response("Hello, I am your Gemini voice assistant. How can I help you today?")

    # Load initial memory at startup - only once
    _current_memory_state = load_memory()

    # Get initial IP-based location and timezone - only once at startup
    ip_location, ip_timezone = get_ip_based_location()
    _current_memory_state["last_retrieved_ip_location"] = ip_location
    save_memory(_current_memory_state) # Save after initial IP location update

    if _current_memory_state["needs_clarification"] and _current_memory_state["last_gemini_question"]:
        speak_response(f"Welcome back! Last time, I was trying to understand your request. {_current_memory_state['last_gemini_question']}")
        print(f"Resuming incomplete command. Gemini asked: {_current_memory_state['last_gemini_question']}")

    while True:
        user_input = get_speech_input()
        if user_input:
            # --- Preprocess user input using the function from utils.py ---
            processed_user_input = preprocess_spoken_text(user_input)
            print(f"Preprocessed input: {processed_user_input}") # For debugging

            if processed_user_input.lower() in ['exit', 'quit', 'stop', 'goodbye']:
                speak_response("Goodbye! Have a great day.")
                print("👋 Exiting. Bye!")
                clear_all_memory_and_reset_file() # Clear memory on exit
                break

            # --- Prepare context for Gemini ---
            # Use the most recent timezone information
            current_timezone_for_prompt = ip_timezone # Default to IP-based
            if _current_memory_state["user_defined_location"]:
                # You might need logic here to derive a timezone from user_defined_location
                # For simplicity, if a user-defined location is set, we might
                # assume the IP-based timezone is still the best available,
                # or require a more robust location-to-timezone mapping service.
                # For now, we'll keep using ip_timezone for actual time calculation,
                # but pass user_defined_location in prompt for context.
                pass # No change to current_timezone_for_prompt yet

            current_time = get_current_time_in_timezone(current_timezone_for_prompt)

            prompt_parts = []
            prompt_parts.append(f"Current time is {current_time}.")
            prompt_parts.append(f"Current approximate location (from IP) is {_current_memory_state['last_retrieved_ip_location']}.")
            if _current_memory_state["user_defined_location"]:
                prompt_parts.append(f"User has explicitly set their location as: {_current_memory_state['user_defined_location']}. Use this if relevant.")

            prompt_parts.append("Your goal is to understand and execute commands. You can perform mathematical calculations.")
            prompt_parts.append("You DO NOT have access to real-time information such as current weather, live news updates, real-time stock prices, or specific events happening right now. If the user asks for such information, respond with 'I do not have access to real-time information for that.' or 'I can't provide live updates for that.'")

            prompt_parts.append("You can either SPEAK a response or WRITE a response. You MUST use one of the following prefixes for your final output:")
            prompt_parts.append("- If the user asks you to write something, generate the text and prepend it with 'WRITE_RESPONSE:' (e.g., 'WRITE_RESPONSE:This is the text I will type for you.'). After typing, the conversation turn ends.")
            prompt_parts.append("- If the user asks you a question for which you have an answer, generate the answer and prepend it with 'SPEAK_RESPONSE:' (e.g., 'SPEAK_RESPONSE:The capital of France is Paris.').")
            prompt_parts.append("- If the user asks for a calculation, extract ONLY the mathematical expression (e.g., '5 + 3', '10 * (2 + 3)', '8 / 4'). Do not include any text, just the expression. You MUST prepend this expression with 'CALCULATE:'. If the calculation expression is ambiguous or missing numbers/operators, use 'CLARIFICATION_NEEDED:' instead.")
            prompt_parts.append("- If a command is incomplete or ambiguous (and not a calculation), you MUST respond by starting your reply with 'CLARIFICATION_NEEDED:' followed by the specific question you need answered to complete the command. Do not give a final answer if you need more information.")
            prompt_parts.append("- If a question requires location information (e.g., current time, nearby places) AND the user's provided location or IP-based location is insufficient or missing for the query, you MUST ask the user for their specific location by starting your question with 'LOCATION_NEEDED:'. Once the user provides it, remember it for the current session.")
            prompt_parts.append("Consider the following as a continuous conversation.")
            prompt_parts.append("IMPORTANT: Always choose between SPEAK_RESPONSE, WRITE_RESPONSE, CALCULATE, CLARIFICATION_NEEDED, or LOCATION_NEEDED for your direct response based on user intent. Ensure any numerical expressions or text meant for writing uses standard symbols (e.g., *, @, +, /, #).")


            # Build the internal chat history for Gemini
            chat_history_for_gemini = []

            if _current_memory_state["needs_clarification"] and _current_memory_state["accumulated_user_input"]:
                for i, prev_input in enumerate(_current_memory_state["accumulated_user_input"]):
                    chat_history_for_gemini.append(f"User (part {i+1}): {prev_input}")

                if _current_memory_state["last_gemini_question"]:
                    chat_history_for_gemini.append(f"Assistant: {_current_memory_state['last_gemini_question']}")

                # Pass the processed_user_input to Gemini
                chat_history_for_gemini.append(f"User (clarification): {processed_user_input}")

                full_prompt = "\n".join(prompt_parts) + "\n\n" + "\n".join(chat_history_for_gemini)
            else:
                # Pass the processed_user_input to Gemini
                full_prompt = "\n".join(prompt_parts) + f"\n\nUser command: {processed_user_input}"

            # Debugging: print the full prompt sent to Gemini (optional)
            # print("\n--- PROMPT SENT TO GEMINI ---")
            # print(full_prompt)
            # print("-----------------------------\n")

            gemini_response = ask_gemini(full_prompt)

            # --- Process Gemini's Response ---
            CLARIFICATION_PREFIX = "CLARIFICATION_NEEDED:"
            LOCATION_PREFIX = "LOCATION_NEEDED:"
            CALCULATE_PREFIX = "CALCULATE:"
            SPEAK_PREFIX = "SPEAK_RESPONSE:"
            WRITE_PREFIX = "WRITE_RESPONSE:"

            memory_changed = False # Flag to track if memory needs saving

            if gemini_response.startswith(CALCULATE_PREFIX):
                expression = gemini_response[len(CALCULATE_PREFIX):].strip()
                print(f"Gemini requested calculation: {expression}")

                calculation_output, is_success = perform_calculation(expression)

                speak_response(calculation_output)
                print(f"Calculation result: {calculation_output}")

                # Reset memory for a new turn after successful calculation
                _current_memory_state = reset_memory_for_new_turn(_current_memory_state)
                memory_changed = True

            elif gemini_response.startswith(WRITE_PREFIX):
                text_to_write = gemini_response[len(WRITE_PREFIX):].strip()
                print(f"Gemini requested typing: {text_to_write[:50]}...")
                write_response(text_to_write)
                # Reset memory for a new turn after successful write
                _current_memory_state = reset_memory_for_new_turn(_current_memory_state)
                memory_changed = True

            elif gemini_response.startswith(LOCATION_PREFIX):
                location_question = gemini_response[len(LOCATION_PREFIX):].strip()
                speak_response(location_question)
                print(f"Gemini asked for location: {location_question}")

                _current_memory_state["accumulated_user_input"].append(user_input) # Original user_input saved (for debugging/context)
                _current_memory_state["last_gemini_question"] = location_question
                _current_memory_state["needs_clarification"] = True
                memory_changed = True # Memory state has changed

            elif gemini_response.startswith(CLARIFICATION_PREFIX):
                clarification_question = gemini_response[len(CLARIFICATION_PREFIX):].strip()
                speak_response(clarification_question)
                print(f"Gemini asked for clarification: {clarification_question}")

                _current_memory_state["accumulated_user_input"].append(user_input) # Original user_input saved
                _current_memory_state["last_gemini_question"] = clarification_question
                _current_memory_state["needs_clarification"] = True
                memory_changed = True # Memory state has changed

            elif gemini_response.startswith(SPEAK_PREFIX):
                final_spoken_response = gemini_response[len(SPEAK_PREFIX):].strip()
                speak_response(final_spoken_response)
                print(f"Gemini provided a spoken response.")

                # If this SPEAK_RESPONSE was a follow-up to a LOCATION_NEEDED question
                if _current_memory_state["needs_clarification"] and \
                   _current_memory_state["last_gemini_question"] and \
                   _current_memory_state["last_gemini_question"].startswith(LOCATION_PREFIX):
                    _current_memory_state["user_defined_location"] = user_input # Store the user's provided location
                    # No need to set memory_changed=True here, as the reset below will trigger a save anyway.

                # Reset memory for a new turn after providing a final spoken response
                _current_memory_state = reset_memory_for_new_turn(_current_memory_state)
                memory_changed = True

            else:
                # Fallback for unexpected responses or if Gemini doesn't use a prefix (shouldn't happen with strict prompting)
                print("⚠️ Unexpected response from Gemini (no recognized prefix). Speaking raw response.")
                speak_response(gemini_response)
                print(f"Raw Gemini response: {gemini_response}")
                # Reset memory for a new turn in case of unexpected response
                _current_memory_state = reset_memory_for_new_turn(_current_memory_state)
                memory_changed = True

            # Save memory only if a change occurred during this turn
            if memory_changed:
                save_memory(_current_memory_state)
        time.sleep(0.5)

if __name__ == "__main__":
    main()
