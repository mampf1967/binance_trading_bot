"""
bot_orchestrator.py - Main bot coordinator

DUAL TIMEFRAME with CONDITIONAL INITIALIZATION
VERSION 2.6 - Supports disabling 1min or 5min timeframes via config
"""

import requests
import shutil
from pathlib import Path
import config
from database import Database
from database_5min import Database5Min
from log_writer import LogWriter
from pattern_detector import PatternDetector
from pattern_detector_5min import PatternDetector5Min
from buy_monitor import BuyMonitor
from buy_monitor_5min import BuyMonitor5Min
from sell_monitor import SellMonitor
from sell_monitor_5min import SellMonitor5Min
from position_manager import PositionManager
from capital_allocator import CapitalAllocator
from order_queue import OrderQueue
from cooldown_tracker import CooldownTracker
from data_downloader import DataDownloader
from websocket_client import WebSocketClient
from stream_processor import StreamProcessor
from trade_reporter import TradeReporter
from signal_handler import SignalHandler
from console_formatter import print_header


class BotOrchestrator:
    """Main bot coordinator - CONDITIONAL DUAL TIMEFRAME"""
    
    def __init__(self, symbols: list, debug_mode: bool = False, cleanup_enabled: bool = True):
        self.symbols = symbols
        self.debug_mode = debug_mode
        self.cleanup_enabled = cleanup_enabled
        
        # Determine active timeframes from config
        self.timeframe_1min_enabled = config.PATTERN_3BULL.get('enabled', True)
        self.timeframe_5min_enabled = config.PATTERN_2BULL.get('enabled', True)
        
        # Validate at least one timeframe is enabled
        if not self.timeframe_1min_enabled and not self.timeframe_5min_enabled:
            raise ValueError("❌ At least one timeframe must be enabled in config.py")
        
        print_header("🤖 CONDITIONAL DUAL TIMEFRAME TRADING BOT", 50)
        if debug_mode:
            print("🔧 DEBUG MODE: ENABLED")
        print()
        
        # Display active timeframes
        print("⏱️  ACTIVE TIMEFRAMES:")
        if self.timeframe_1min_enabled:
            print("   ✅ 1min (3BULL pattern)")
        else:
            print("   ❌ 1min (DISABLED)")
        
        if self.timeframe_5min_enabled:
            print("   ✅ 5min (2BULL pattern)")
        else:
            print("   ❌ 5min (DISABLED)")
        print()
        
        # Initialize global managers
        self.position_manager = PositionManager()
        self.capital_allocator = CapitalAllocator(
            total_capital=config.TRADING['total_capital'],
            allocation_1min=config.TRADING['allocation_percent_1min'] if self.timeframe_1min_enabled else 0,
            allocation_5min=config.TRADING['allocation_percent_5min'] if self.timeframe_5min_enabled else 0
        )
        self.order_queue = OrderQueue()
        self.cooldown_tracker = CooldownTracker()
        
        # Log configuration
        print(f"💰 Capital: {config.TRADING['total_capital']} USDC")
        
        if self.timeframe_1min_enabled:
            print(f"📊 1min pool: ${self.capital_allocator.capital_1min:.0f} ({config.TRADING['allocation_percent_1min']}%)")
            print(f"🎯 Max Positions (1min): {config.TRADING['max_positions_1min']}")
            print(f"⏸️  Cooldown (1min): {config.TRADING['cooldown_1min_candles']}c")
        
        if self.timeframe_5min_enabled:
            print(f"📊 5min pool: ${self.capital_allocator.capital_5min:.0f} ({config.TRADING['allocation_percent_5min']}%)")
            print(f"🎯 Max Positions (5min): {config.TRADING['max_positions_5min']}")
            print(f"⏸️  Cooldown (5min): {config.TRADING['cooldown_5min_candles']}c")
        
        if cleanup_enabled:
            print(f"🧹 Cleanup: Enabled")
        print()
        
        # Initialize components for each asset - CONDITIONAL
        self.databases_1min = {} if self.timeframe_1min_enabled else None
        self.databases_5min = {} if self.timeframe_5min_enabled else None
        self.log_writers = {}
        self.pattern_detectors_1min = {} if self.timeframe_1min_enabled else None
        self.pattern_detectors_5min = {} if self.timeframe_5min_enabled else None
        
        self._init_all_assets()
        
        # WebSocket and processor
        self.websocket_client = None
        self.stream_processor = None
        
        # Signal handler
        self.signal_handler = SignalHandler(self)
    
    def _init_all_assets(self):
        """Initialize databases and detectors for enabled timeframes only"""
        active_timeframes = []
        if self.timeframe_1min_enabled:
            active_timeframes.append("1min")
        if self.timeframe_5min_enabled:
            active_timeframes.append("5min")
        
        print(f"📊 Initializing components for: {', '.join(active_timeframes)}...")
        
        for symbol_base in self.symbols:
            # Log writer (always needed)
            self.log_writers[symbol_base] = LogWriter(
                name=symbol_base,
                log_to_file=config.LOG_TO_FILE
            )
            
            log_writer = self.log_writers[symbol_base]
            
            # ===== 1MIN INITIALIZATION (CONDITIONAL) =====
            if self.timeframe_1min_enabled:
                # 1min Database
                db_path_1min = f"data/{symbol_base.lower()}usdc_1min.db"
                self.databases_1min[symbol_base] = Database(db_path_1min, symbol_base)
                
                # 1min monitors
                sell_monitor_1min = SellMonitor(
                    log_writer, symbol_base,
                    position_manager=self.position_manager,
                    cooldown_tracker=self.cooldown_tracker,
                    database=self.databases_1min[symbol_base],
                    debug_mode=self.debug_mode
                )
                
                buy_monitor_1min = BuyMonitor(
                    log_writer, symbol_base,
                    sell_monitor=sell_monitor_1min,
                    position_manager=self.position_manager,
                    order_queue=self.order_queue,
                    database=self.databases_1min[symbol_base],
                    debug_mode=self.debug_mode
                )
                
                # 1min Pattern detector
                self.pattern_detectors_1min[symbol_base] = PatternDetector(
                    self.databases_1min[symbol_base],
                    log_writer,
                    symbol_base,
                    buy_monitor_1min,
                    position_manager=self.position_manager,
                    cooldown_tracker=self.cooldown_tracker,
                    debug_mode=self.debug_mode
                )
            
            # ===== 5MIN INITIALIZATION (CONDITIONAL) =====
            if self.timeframe_5min_enabled:
                # 5min Database
                db_path_5min = f"data/{symbol_base.lower()}usdc_5min.db"
                self.databases_5min[symbol_base] = Database5Min(db_path_5min, symbol_base)
                
                # 5min monitors
                sell_monitor_5min = SellMonitor5Min(
                    log_writer, symbol_base,
                    position_manager=self.position_manager,
                    cooldown_tracker=self.cooldown_tracker,
                    database=self.databases_5min[symbol_base],
                    debug_mode=self.debug_mode
                )
                
                buy_monitor_5min = BuyMonitor5Min(
                    log_writer, symbol_base,
                    sell_monitor=sell_monitor_5min,
                    position_manager=self.position_manager,
                    order_queue=self.order_queue,
                    database=self.databases_5min[symbol_base],
                    debug_mode=self.debug_mode
                )
                
                # 5min Pattern detector
                self.pattern_detectors_5min[symbol_base] = PatternDetector5Min(
                    self.databases_5min[symbol_base],
                    log_writer,
                    symbol_base,
                    buy_monitor_5min,
                    position_manager=self.position_manager,
                    cooldown_tracker=self.cooldown_tracker,
                    debug_mode=self.debug_mode
                )
        
        timeframe_str = " + ".join(active_timeframes)
        print(f"✅ Initialized {len(self.symbols)} assets ({timeframe_str})")
        print()
    
    def preload_historical_data(self):
        """Preload historical data - ONLY for enabled timeframes"""
        print_header("HISTORICAL DATA LOADING", 50)
        print()
        
        downloader = DataDownloader()
        full_symbols = [f"{base}USDC" for base in self.symbols]
        
        # ===== 5MIN DATA (CONDITIONAL) =====
        if self.timeframe_5min_enabled:
            print(f"📥 Fetching 500 5min candles for {len(self.symbols)} assets...")
            results_5min = downloader.fetch_parallel(
                symbols=full_symbols,
                limit=config.INITIAL_CANDLES,
                max_workers=50,
                interval='5m'
            )
            
            print("💾 Inserting 5min data...")
            total_5min = 0
            for symbol_base in self.symbols:
                symbol = f"{symbol_base}USDC"
                db = self.databases_5min[symbol_base]
                
                if symbol in results_5min:
                    for candle in results_5min[symbol]:
                        db.add_candle(candle)
                    total_5min += len(results_5min[symbol])
            
            print(f"✅ Loaded {total_5min} 5min candles")
            print()
        else:
            print("⏭️  Skipping 5min data (timeframe disabled)")
            print()
        
        # ===== 1MIN DATA (CONDITIONAL) =====
        if self.timeframe_1min_enabled:
            print(f"📥 Fetching 500 1min candles for {len(self.symbols)} assets...")
            results_1min = downloader.fetch_parallel(
                symbols=full_symbols,
                limit=config.INITIAL_CANDLES,
                max_workers=50,
                interval='1m'
            )
            
            print("💾 Inserting 1min data...")
            total_1min = 0
            for symbol_base in self.symbols:
                symbol = f"{symbol_base}USDC"
                db = self.databases_1min[symbol_base]
                
                if symbol in results_1min:
                    for candle in results_1min[symbol]:
                        db.add_candle(candle)
                    total_1min += len(results_1min[symbol])
            
            print(f"✅ Loaded {total_1min} 1min candles")
            print()
        else:
            print("⏭️  Skipping 1min data (timeframe disabled)")
            print()
    
    def start_websocket(self):
        """Start WebSocket collector - ONLY for enabled timeframes"""
        print_header("START WEBSOCKET COLLECTOR", 50)
        print()
        
        full_symbols = [f"{base}USDC" for base in self.symbols]
        
        # Determine active intervals
        active_intervals = []
        if self.timeframe_1min_enabled:
            active_intervals.append('1m')
        if self.timeframe_5min_enabled:
            active_intervals.append('5m')
        
        # Create stream processor
        self.stream_processor = StreamProcessor(
            databases_1min=self.databases_1min,
            databases_5min=self.databases_5min,
            pattern_detectors_1min=self.pattern_detectors_1min,
            pattern_detectors_5min=self.pattern_detectors_5min
        )
        
        # Create WebSocket client with ONLY active intervals
        self.websocket_client = WebSocketClient(
            symbols=full_symbols,
            interval=config.INTERVAL_1MIN,  # Not used anymore
            on_message_callback=self.stream_processor.process_kline,
            max_retries=config.MAX_RETRIES,
            retry_delay=config.RETRY_DELAY,
            active_intervals=active_intervals  # NEW PARAMETER
        )
        
        total_streams = len(self.symbols) * len(active_intervals)
        
        print(f"🚀 Starting stream collector...")
        print(f"📡 Subscribing to {total_streams} streams ({len(self.symbols)} assets × {len(active_intervals)} intervals)")
        print(f"⚡ Active intervals: {', '.join(active_intervals)}")
        
        if self.timeframe_5min_enabled:
            print(f"⚠️  * = 5min candles")
        
        print(f"⚠️  Press Ctrl+C to stop")
        print()
        
        # Connect (blocking)
        self.websocket_client.connect()
    
    def run(self):
        """Run the bot"""
        try:
            self.preload_historical_data()
            self.start_websocket()
        except Exception as e:
            print(f"❌ Bot error: {e}")
            import traceback
            traceback.print_exc()
    
    def stop(self):
        """Stop the bot"""
        print("🛑 Stopping bot...")
        
        if self.websocket_client:
            self.websocket_client.stop()
        
        # Close databases for active timeframes
        if self.databases_1min:
            for db in self.databases_1min.values():
                db.close()
        
        if self.databases_5min:
            for db in self.databases_5min.values():
                db.close()
        
        for log_writer in self.log_writers.values():
            log_writer.close()
        
        print("✅ Bot stopped")
    
    def print_trade_summary(self):
        """Print trade summary"""
        TradeReporter.print_trade_summary(
            self.pattern_detectors_1min if self.pattern_detectors_1min else {},
            self.pattern_detectors_5min if self.pattern_detectors_5min else {}
        )
    
    def cleanup(self):
        """Clean up databases"""
        if not self.cleanup_enabled:
            return
        
        print()
        print("🧹 Cleaning up...")
        
        try:
            data_dir = Path("data")
            if data_dir.exists():
                shutil.rmtree(data_dir)
                print("   → Deleted database files")
        except Exception as e:
            print(f"   → Error deleting databases: {e}")
        
        print("   → Log files preserved")
        print("✅ Cleanup completed")


def fetch_all_usdc_pairs() -> list:
    """Fetch all USDC trading pairs from Binance"""
    BINANCE_API = "https://api.binance.com/api/v3"
    
    EXCLUDED = {
        'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP', 'USDD', 'GUSD', 'USDS',
        'FDUSD', 'PYUSD', 'FRAX', 'LUSD', 'SUSD',
        'USD', 'EUR', 'GBP', 'AUD', 'BRL', 'TRY', 'RUB', 'UAH', '币安人生'
    }
    
    try:
        response = requests.get(f"{BINANCE_API}/exchangeInfo", timeout=10)
        response.raise_for_status()
        data = response.json()
        
        pairs = []
        for symbol_info in data['symbols']:
            if (symbol_info['symbol'].endswith('USDC') and 
                symbol_info['status'] == 'TRADING' and
                symbol_info['isSpotTradingAllowed']):
                base = symbol_info['symbol'].replace('USDC', '')
                
                if base not in EXCLUDED:
                    pairs.append(base)
        
        print(f"✅ Found {len(pairs)} USDC trading pairs")
        return sorted(pairs)
    
    except Exception as e:
        print(f"❌ Failed to fetch pairs: {e}")
        return []
