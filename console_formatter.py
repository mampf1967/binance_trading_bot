"""
console_formatter.py - Console output formatting with ANSI colors

Provides consistent console output formatting across the application.
"""

# ANSI Color Codes
ANSI_RESET = "\033[0m"
ANSI_BLACK = "\033[30m"
ANSI_RED = "\033[31m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_BLUE = "\033[34m"
ANSI_MAGENTA = "\033[35m"
ANSI_CYAN = "\033[36m"
ANSI_WHITE = "\033[37m"
ANSI_BRIGHT_BLACK = "\033[90m"
ANSI_BRIGHT_RED = "\033[91m"
ANSI_BRIGHT_GREEN = "\033[92m"
ANSI_BRIGHT_YELLOW = "\033[93m"
ANSI_BRIGHT_BLUE = "\033[94m"
ANSI_BRIGHT_MAGENTA = "\033[95m"
ANSI_BRIGHT_CYAN = "\033[96m"
ANSI_BRIGHT_WHITE = "\033[97m"

# Convenience aliases (for backward compatibility)
ANSI_LIGHT_BLUE = ANSI_BRIGHT_CYAN


def format_colored_pnl(pnl_percent: float, text: str) -> str:
    """
    Format text with color based on PnL
    
    Args:
        pnl_percent: PnL percentage value
        text: Text to color
        
    Returns:
        Colored text string
    """
    color = ANSI_GREEN if pnl_percent >= 0 else ANSI_RED
    return f"{color}{text}{ANSI_RESET}"


def format_colored_icon(pnl_percent: float) -> str:
    """Get colored icon based on PnL"""
    if pnl_percent >= 0:
        return f"{ANSI_GREEN}✅{ANSI_RESET}"
    else:
        return f"{ANSI_RED}❌{ANSI_RESET}"


def format_pattern_alert(message: str) -> str:
    """Format pattern detection alert message"""
    return f"{ANSI_BLUE}{message}{ANSI_RESET}"


def format_buy_monitor(message: str) -> str:
    """Format buy monitor message"""
    return f"{ANSI_LIGHT_BLUE}{message}{ANSI_RESET}"


def format_sell_monitor(message: str) -> str:
    """Format sell monitor message"""
    return f"{ANSI_CYAN}{message}{ANSI_RESET}"


def print_separator(length: int = 50):
    """Print separator line"""
    print("=" * length)


def print_header(title: str, length: int = 50):
    """Print formatted header"""
    print_separator(length)
    print(title)
    print_separator(length)


def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI color codes from text
    
    Used for file logging to keep logs clean.
    """
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)
