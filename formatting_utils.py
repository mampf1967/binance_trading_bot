"""
formatting_utils.py - Formatting utilities for prices, volumes, and percentages

Provides clean, consistent formatting for display across the application.
"""


def format_price(price: float) -> str:
    """
    Format price for display - significant digits ONLY for small prices
    
    Examples:
        0.00001234 -> "1234"
        0.123 -> "123"
        1.5 -> "1.5"
        100.0 -> "100"
    """
    if price == 0:
        return "0"
    
    # For very small prices (< 0.01), show only significant digits
    if price < 0.01:
        price_str = f"{price:.10f}"
        decimal_pos = price_str.find('.')
        if decimal_pos == -1:
            return price_str
        
        digits_after_decimal = price_str[decimal_pos+1:]
        significant_digits = digits_after_decimal.lstrip('0')
        
        if not significant_digits:
            return "0"
        
        return significant_digits
    
    # For prices >= 0.01: native formatting (no trailing zeros)
    else:
        formatted = f"{price}"
        if '.' in formatted:
            formatted = formatted.rstrip('0').rstrip('.')
        return formatted


def format_volume(volume: float) -> str:
    """
    Format volume/turnover with K/M/B notation
    
    Examples:
        1234 -> "1.2K"
        1234567 -> "1.2M"
        1234567890 -> "1.2B"
    """
    if volume >= 1_000_000_000:
        result = f"{volume/1_000_000_000:.1f}B"
        return result.replace(".0B", "B")
    elif volume >= 1_000_000:
        result = f"{volume/1_000_000:.1f}M"
        return result.replace(".0M", "M")
    elif volume >= 1_000:
        result = f"{volume/1_000:.1f}K"
        return result.replace(".0K", "K")
    else:
        return f"{volume:.0f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """
    Format percentage value with sign
    
    Examples:
        3.0 -> "+3.00%"
        -1.5 -> "-1.50%"
        0.75 -> "+0.75%"
    """
    sign = "+" if value >= 0 else ""
    formatted = f"{value:.{decimals}f}"
    
    if '.' in formatted:
        formatted = formatted.rstrip('0')
        if formatted.endswith('.'):
            formatted = formatted[:-1]
    return f"{sign}{formatted}%"
