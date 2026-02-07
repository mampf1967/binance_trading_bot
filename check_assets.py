#!/usr/bin/env python3
"""
check_assets.py - Display all USDC trading pairs from Binance

Fetches all active USDC pairs and analyzes them for:
- Chinese/special characters
- URL encoding issues
- Character types
"""

import requests
import sys
from urllib.parse import quote, unquote


def get_usdc_pairs():
    """Fetch all USDC trading pairs from Binance"""
    BINANCE_API = "https://api.binance.com/api/v3"
    
    EXCLUDED = {
        'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP', 'USDD', 'GUSD', 'USDS',
        'FDUSD', 'PYUSD', 'FRAX', 'LUSD', 'SUSD',
        'USD', 'EUR', 'GBP', 'AUD', 'BRL', 'TRY', 'RUB', 'UAH', '币安人生'
    }
    
    try:
        print("🔍 Fetching USDC trading pairs from Binance...")
        response = requests.get(f"{BINANCE_API}/exchangeInfo", timeout=10)
        response.raise_for_status()
        data = response.json()
        
        pairs = []
        pairs_info = []
        
        for symbol_info in data['symbols']:
            if (symbol_info['symbol'].endswith('USDC') and 
                symbol_info['status'] == 'TRADING' and
                symbol_info['isSpotTradingAllowed']):
                base = symbol_info['symbol'].replace('USDC', '')
                
                if base not in EXCLUDED:
                    pairs.append(base)
                    pairs_info.append({
                        'base': base,
                        'full': symbol_info['symbol'],
                        'status': symbol_info['status']
                    })
        
        print(f"✅ Found {len(pairs)} active USDC trading pairs\n")
        return sorted(pairs), sorted(pairs_info, key=lambda x: x['base'])
    
    except Exception as e:
        print(f"❌ Failed to fetch pairs: {e}")
        return [], []


def analyze_character(char):
    """Analyze a character and return its type"""
    code = ord(char)
    
    if code < 128:
        return "ASCII"
    elif 0x4E00 <= code <= 0x9FFF:
        return "CHINESE"
    elif 0x3040 <= code <= 0x309F:
        return "HIRAGANA"
    elif 0x30A0 <= code <= 0x30FF:
        return "KATAKANA"
    elif 0xAC00 <= code <= 0xD7AF:
        return "KOREAN"
    elif 0x0400 <= code <= 0x04FF:
        return "CYRILLIC"
    elif 0x0600 <= code <= 0x06FF:
        return "ARABIC"
    else:
        return f"UNICODE-{code:04X}"


def check_symbol(base, full):
    """Check if symbol has special characters"""
    has_special = False
    char_types = set()
    details = []
    
    for char in base:
        char_type = analyze_character(char)
        char_types.add(char_type)
        
        if char_type != "ASCII":
            has_special = True
            details.append(f"'{char}' ({char_type}, U+{ord(char):04X})")
    
    return has_special, char_types, details


def print_all_pairs(pairs, pairs_info):
    """Print all pairs with analysis"""
    
    print("=" * 80)
    print("ALL USDC TRADING PAIRS")
    print("=" * 80)
    print()
    
    # Print in columns
    columns = 5
    for i in range(0, len(pairs), columns):
        row = pairs[i:i+columns]
        print("  ".join(f"{p:12}" for p in row))
    
    print()
    print("=" * 80)
    print("CHARACTER ANALYSIS")
    print("=" * 80)
    print()
    
    special_chars = []
    ascii_only = []
    
    for info in pairs_info:
        base = info['base']
        full = info['full']
        has_special, char_types, details = check_symbol(base, full)
        
        if has_special:
            special_chars.append({
                'base': base,
                'full': full,
                'types': char_types,
                'details': details
            })
        else:
            ascii_only.append(base)
    
    # Print special character symbols
    if special_chars:
        print("⚠️  SYMBOLS WITH SPECIAL CHARACTERS:")
        print("-" * 80)
        for item in special_chars:
            print(f"\n{item['base']} ({item['full']}):")
            print(f"  Character types: {', '.join(sorted(item['types']))}")
            for detail in item['details']:
                print(f"    - {detail}")
            
            # Show URL encoding
            encoded = quote(item['full'])
            if encoded != item['full']:
                print(f"  URL encoded: {encoded}")
        
        print()
        print(f"⚠️  Total symbols with special characters: {len(special_chars)}")
    else:
        print("✅ No symbols with special characters found")
    
    print()
    print(f"✅ ASCII-only symbols: {len(ascii_only)}")
    print()
    
    # Print problematic symbols summary
    if special_chars:
        print("=" * 80)
        print("⚠️  POTENTIALLY PROBLEMATIC SYMBOLS (for WebSocket)")
        print("=" * 80)
        print()
        
        for item in special_chars:
            print(f"  {item['base']:15} → {item['full']:20} (types: {', '.join(sorted(item['types']))})")
        
        print()
        print("💡 These symbols may cause WebSocket URL encoding issues.")
        print("   Consider excluding them from the trading bot.")
    
    print()


def main():
    """Main execution"""
    pairs, pairs_info = get_usdc_pairs()
    
    if not pairs:
        print("❌ No pairs found or error occurred")
        sys.exit(1)
    
    print_all_pairs(pairs, pairs_info)
    
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total USDC pairs: {len(pairs)}")
    
    # Count by character type
    special_count = sum(1 for info in pairs_info if check_symbol(info['base'], info['full'])[0])
    ascii_count = len(pairs) - special_count
    
    print(f"  ASCII only: {ascii_count}")
    print(f"  With special chars: {special_count}")
    print()


if __name__ == "__main__":
    main()
