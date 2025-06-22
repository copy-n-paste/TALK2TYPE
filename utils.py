# utils.py
import re

def preprocess_spoken_text(text):
    """
    Converts common spoken phrases for symbols and numbers into their actual characters.
    This helps the assistant interpret commands more accurately for calculations and typing.
    """
    text = text.lower() # Work with lowercase for consistency

    # Order matters for some replacements (e.g., 'at the rate' before 'at')
    # Longest phrases should come first to prevent partial matches.
    replacements = {
        "at the rate": "@",
        "hash tag": "#",
        "hash": "#",
        "dollar sign": "$",
        "percent sign": "%",
        "ampersand": "&",
        "asterisk": "*",
        "star": "*",
        "plus": "+",
        "minus": "-",
        "hyphen": "-",
        "dash": "-",
        "slash": "/",
        "divided by": "/",
        "backslash": "\\",
        "equals": "=",
        "colon": ":",
        "semicolon": ";",
        "quote": "'",
        "double quote": '"',
        "single quote": "'",
        "open parenthesis": "(",
        "close parenthesis": ")",
        "left parenthesis": "(",
        "right parenthesis": ")",
        "square bracket open": "[",
        "square bracket close": "]",
        "curly bracket open": "{",
        "curly bracket close": "}",
        "less than": "<",
        "greater than": ">",
        "comma": ",",
        "dot": ".",
        "period": ".",
        "question mark": "?",
        "exclamation mark": "!",
        "underscore": "_",
        "tilde": "~",
        "caret": "^",
        "pipe": "|",
        "and": "&", # context-dependent, but often for symbols
        "number sign": "#",
        "exclamation point": "!",
        "full stop": ".", # Common in some English dialects
        "new line": "\n", # For writing commands
        "new paragraph": "\n\n", # For writing commands
        "tab": "\t", # For writing commands
    }

    # Numerals (basic ones, to help with calculations and addresses etc.)
    num_words = {
        "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
        "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
        "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
        "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30",
        "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70",
        "eighty": "80", "ninety": "90", "hundred": "00" # Be careful with "hundred"
    }

    # Apply symbol replacements first (longest phrases first)
    sorted_replacements = sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True)
    for phrase, symbol in sorted_replacements:
        text = text.replace(phrase, symbol)
    
    # Apply number word replacements (using regex for whole words)
    for word, digit in num_words.items():
        # Using word boundaries (\b) to ensure 'one' doesn't replace part of 'phone'
        text = re.sub(r'\b' + re.escape(word) + r'\b', digit, text)

    return text
