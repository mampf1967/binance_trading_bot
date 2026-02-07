"""
signal_handler.py - Graceful shutdown handling

Handles SIGINT (Ctrl+C) and SIGTERM signals for graceful bot shutdown.
"""

import signal
import sys


class SignalHandler:
    """Handles shutdown signals gracefully"""
    
    def __init__(self, bot_instance):
        """
        Initialize signal handler
        
        Args:
            bot_instance: BotOrchestrator instance
        """
        self.bot_instance = bot_instance
        self.shutdown_initiated = False
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
    
    def _handle_signal(self, signum, frame):
        """Handle shutdown signal"""
        if self.shutdown_initiated:
            print("\n⚠️  Force exit (second signal)")
            sys.exit(1)
        
        self.shutdown_initiated = True
        
        print()
        print("=" * 50)
        print("⚠️  GRACEFUL SHUTDOWN INITIATED (Ctrl+C)")
        print("=" * 50)
        print()
        
        if self.bot_instance:
            try:
                print("🛑 Stopping bot components...")
                self.bot_instance.stop()
                
                print()
                print("📊 Generating trade summary...")
                self.bot_instance.print_trade_summary()
                
                if hasattr(self.bot_instance, 'cleanup_enabled') and self.bot_instance.cleanup_enabled:
                    self.bot_instance.cleanup()
                
            except Exception as e:
                print(f"⚠️  Error during shutdown: {e}")
                try:
                    self.bot_instance.print_trade_summary()
                except:
                    pass
                sys.exit(1)
        
        print("✅ Shutdown complete")
        sys.exit(0)
