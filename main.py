"""
main.py - DUAL TIMEFRAME Bot Entry Point
"""

import sys
from bot_orchestrator import BotOrchestrator, fetch_all_usdc_pairs


def main():
    """Main entry point"""
    
    debug_mode = False
    
    for arg in sys.argv[1:]:
        if arg in ['-debug', '--debug', '-d']:
            debug_mode = True
            print("🔧 DEBUG MODE ACTIVATED")
    
    print()
    print("🔍 Fetching all USDC trading pairs...")
    
    symbols = fetch_all_usdc_pairs()
    
    if not symbols:
        print("❌ No symbols found. Exiting.")
        return
    
    print(f"📊 Will monitor: {', '.join(symbols[:10])}{'...' if len(symbols) > 10 else ''}")
    print()
    
    bot = BotOrchestrator(symbols, debug_mode=debug_mode, cleanup_enabled=True)
    bot.run()


if __name__ == "__main__":
    main()
