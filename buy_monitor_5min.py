"""
buy_monitor_5min.py - Buy decision monitoring for 5min timeframe

KEY FIX: Pass pattern alert data (gain, volume, trades, beauty) to sell monitor
when starting monitoring so it appears in trade summaries.

VERSION 2.2.1 - PATTERN ALERT DATA PASSTHROUGH FIX
"""

from typing import Dict, Optional, List
from formatting_utils import format_price, format_volume, format_percentage
from console_formatter import ANSI_LIGHT_BLUE, ANSI_RESET
from time_converter import vienna_str_to_short
from beauty_scorer import BeautyScorer
from candle_size_analyzer import CandleSizeAnalyzer
import config


class BuyMonitor5Min:
    """Monitors market and determines buy entry for 5min timeframe"""
    
    def __init__(self, log_writer, symbol_base: str, sell_monitor,
                 position_manager=None, order_queue=None, 
                 database=None,
                 debug_mode=False):
        """
        Initialize buy monitor
        
        Args:
            log_writer: LogWriter instance
            symbol_base: Asset symbol
            sell_monitor: SellMonitor instance
            position_manager: PositionManager instance
            order_queue: OrderQueue instance
            database: Database instance for historical analysis
            debug_mode: Enable debug logging
        """
        self.log_writer = log_writer
        self.symbol_base = symbol_base
        self.sell_monitor = sell_monitor
        self.debug_mode = debug_mode
        
        # Managers
        self.position_manager = position_manager
        self.order_queue = order_queue
        
        # Configuration
        self.volume_threshold_factor = config.BUY_MONITOR_5MIN['volume_threshold_factor']
        self.max_monitor = 2
        
        # State
        self.is_monitoring = False
        self.monitor_count = 0
        self.avg_volume = 0.0
        self.beauty_score = 0.0
        
        # Pattern tracking (for recursive detection)
        self.pattern_candles = []  # Stores [C1, C2]
        
        # ===== NEW: Store pattern alert data =====
        self.pattern_gain = None
        self.pattern_volume = None
        self.pattern_trades = None
        self.pattern_type = None  # Track pattern type ('2BULL_5min', 'EMA5min', etc.)
        self.ema_pattern_info = None  # Store EMA pattern details
        # =========================================
        
        self.limit_orders = []
        self.bought = False
        self.buy_price = None
        
        # Missed opportunity tracking
        self.missed_opportunities = []
        
        # Store database and lazy init analyzer
        self.db = database
        self.candle_analyzer = None
    
    def _get_candle_analyzer(self):
        """Lazy initialization of candle analyzer"""
        if self.candle_analyzer is None and self.db is not None:
            lookback = config.BUY_MONITOR_5MIN.get('candle_size_lookback', 50)
            self.candle_analyzer = CandleSizeAnalyzer(self.db, lookback)
        return self.candle_analyzer
    
    def start_monitoring(self, c1: Dict, c2: Dict, beauty_score: float, avg_volume: float, pattern_type: str = '2BULL_5min'):
        """
        Start monitoring with volume context
        
        ===== MODIFIED: Added pattern_type parameter =====
        """
        self.is_monitoring = True
        self.avg_volume = avg_volume
        self.beauty_score = beauty_score
        self.monitor_count = 0
        self.limit_orders = []
        self.bought = False
        self.buy_price = None
        self.pattern_type = pattern_type
        
        # Store pattern candles for recursive detection
        self.pattern_candles = [c1, c2]
        
        # ===== NEW: Calculate and store pattern alert metrics (2BULL = 2 candles) =====
        self.pattern_gain = ((c2['close'] - c1['open']) / c1['open']) * 100
        self.pattern_volume = c1['turnover'] + c2['turnover']
        self.pattern_trades = c1['trades'] + c2['trades']
        # ===============================================================================
        
        time_fmt = vienna_str_to_short(c2['timestamp'])
        if self.log_writer:
            self.log_writer.write(f"{self.symbol_base} 🎯 START BUY MONITORING [{pattern_type}] | AvgVol: {format_volume(avg_volume)} | Threshold: {self.volume_threshold_factor}x", time_fmt)
            self.log_writer.write(f"*{self.symbol_base} 🎯 START BUY MONITORING | AvgVol: {format_volume(avg_volume)} | Threshold: {self.volume_threshold_factor}x", time_fmt)
    
    def process_candle(self, candle: Dict) -> Optional[str]:
        """Process candle during buy monitoring"""
        # Delegate to sell monitor if bought
        if self.bought and self.sell_monitor.is_monitoring:
            return self.sell_monitor.process_candle(candle)
        
        if not self.is_monitoring:
            return None
        
        # EMA pattern: Simple entry at next candle open (first candle we see)
        if self.pattern_type and self.pattern_type.startswith('EMA'):
            return self._execute_ema_entry(candle)
        
        # 2BULL pattern: Continue with existing complex logic
        # Get timestamp for consistent logging
        time_fmt = vienna_str_to_short(candle['timestamp'])
        
        # Log candle OHLCV data first
        if self.log_writer:
            candle_detail = f"C:    O:{format_price(candle['open'])} H:{format_price(candle['high'])} L:{format_price(candle['low'])} C:{format_price(candle['close'])} | V:{format_volume(candle['turnover'])} T:{candle['trades']}"
            self.log_writer.write(f"*{self.symbol_base} {candle_detail}", time_fmt)
        
        # Structure comparison for this candle (ALWAYS log FIRST, before any checks)
        if config.CANDLE_ANALYZER.get('enable_structure_logging', True):
            analyzer = self._get_candle_analyzer()
            if analyzer:
                analyzer.format_structure_comparison(
                    candle, f"*{self.symbol_base}", time_fmt, self.log_writer
                )
        
        # Check limit fill first
        if self.limit_orders:
            if self._check_limit_fill(candle) == "BUY_FILLED":
                return "BUY_FILLED"
        
        # Check timeout
        if self.monitor_count >= self.max_monitor:
            return self._abort_monitoring("TIMEOUT", candle)
        
        # Increment counter
        self.monitor_count += 1
        
        # Market data
        is_bullish = candle['close'] >= candle['open']
        current_volume = candle['turnover']
        volume_threshold = self.avg_volume * self.volume_threshold_factor
        
        # Check for large bearish candle
        if config.BUY_MONITOR_5MIN.get('abort_large_bearish', False):
            open_price = float(candle.get('open', 0))
            close_price = float(candle.get('close', 0))
            
            if close_price < open_price:
                analyzer = self._get_candle_analyzer()
                if analyzer:
                    threshold = config.BUY_MONITOR_5MIN.get('large_bearish_threshold', 1.5)
                    bearish_check = analyzer.check_bearish_size(candle, threshold)
                    
                    if bearish_check['is_large']:
                        time_fmt = vienna_str_to_short(candle['timestamp'])
                        bearish_msg = f"🔻LARGE BEARISH: {bearish_check['details']}"
                        print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{bearish_msg}{ANSI_RESET}")
                        
                        if self.log_writer:
                            self.log_writer.write(
                                f"*{self.symbol_base} {bearish_msg}",
                                time_fmt
                            )
                        
                        return self._abort_monitoring("LARGE_BEARISH", candle)
        
        # Check for weak bullish
        if config.BUY_MONITOR_5MIN.get('require_strong_bullish', False):
            open_price = float(candle.get('open', 0))
            close_price = float(candle.get('close', 0))
            
            if close_price >= open_price:
                analyzer = self._get_candle_analyzer()
                if analyzer:
                    min_ratio = config.BUY_MONITOR_5MIN.get('min_bullish_ratio', 0.8)
                    bullish_check = analyzer.check_bullish_size(candle, min_ratio)
                    
                    if not bullish_check['is_strong']:
                        time_fmt = vienna_str_to_short(candle['timestamp'])
                        weak_msg = f"⚠️ WEAK BULLISH: {bullish_check['details']}"
                        print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{weak_msg}{ANSI_RESET}")
        
        # Check for high wave exhaustion
        if config.BUY_MONITOR_5MIN.get('high_wave_abort_enabled', False):
            high_wave_check = self._check_high_wave_exhaustion(candle)
            
            time_fmt = vienna_str_to_short(candle['timestamp'])
            debug_msg = f"  🔍HIGH_WAVE_CHECK: detected={high_wave_check['detected']}, {high_wave_check['details']}"
            print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{debug_msg}{ANSI_RESET}")
            if self.log_writer:
                self.log_writer.write(f"*{self.symbol_base} {debug_msg}", time_fmt)
            
            if high_wave_check['detected']:
                high_wave_msg = f"  🌪️High wave exhaustion DETECTED: {high_wave_check['details']}"
                print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{high_wave_msg}{ANSI_RESET}")
                if self.log_writer:
                    self.log_writer.write(f"*{self.symbol_base} {high_wave_msg}", time_fmt)
                
                return self._abort_monitoring("HIGH_WAVE_EXHAUSTION", candle)
        
        # Check for hammer weakness on bearish candles
        if not is_bullish and config.BUY_MONITOR_5MIN.get('hammer_abort_enabled', False):
            hammer_check = self._check_hammer_weakness(candle)
            if hammer_check['detected']:
                time_fmt = vienna_str_to_short(candle['timestamp'])
                hammer_msg = f"  🔨Hammer weakness detected: {hammer_check['details']}"
                print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{hammer_msg}{ANSI_RESET}")
                if self.log_writer:
                    self.log_writer.write(f"*{self.symbol_base} {hammer_msg}", time_fmt)
                
                return self._abort_monitoring("HAMMER_WEAKNESS", candle)
        
        # RULE 1: CANDLE 1/3
        if self.monitor_count == 1:
            if is_bullish:
                return self._process_bullish_candle_1(candle)
            else:
                return self._process_bearish_candle_1(candle, current_volume, volume_threshold)
        
        # RULE 2: CANDLE 2/3
        elif self.monitor_count == 2:
            if not self.limit_orders:
                return self._abort_monitoring("NO_LIMIT_ORDER", candle)
            
            current_limit = self.limit_orders[0]['price']
            
            if is_bullish and candle['high'] >= current_limit:
                return self._check_limit_fill(candle)
            
            elif not is_bullish:
                if candle['high'] >= current_limit:
                    return self._check_limit_fill(candle)
                else:
                    new_limit = candle['high']
                    old_limit = current_limit
                    self.limit_orders = [{'price': new_limit, 'candle': candle}]
                    
                    time_fmt = vienna_str_to_short(candle['timestamp'])
                    limit_msg = f"↘️LIMIT UPDATED:{old_limit:.6f}->{new_limit:.6f}"
                    print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{limit_msg}{ANSI_RESET}")
                    if self.log_writer:
                        self.log_writer.write(f"*{self.symbol_base} {limit_msg}", time_fmt)
        
        # RULE 3: CANDLE 3/3
        elif self.monitor_count == 3:
            if not self.limit_orders:
                return self._abort_monitoring("NO_LIMIT_ORDER", candle)
            
            current_limit = self.limit_orders[0]['price']
            
            if is_bullish and candle['high'] >= current_limit:
                return self._check_limit_fill(candle)
            else:
                return self._abort_monitoring("FINAL_CANDLE_FAILED", candle)
        
        # Log status
        time_fmt = vienna_str_to_short(candle['timestamp'])
        close_str = format_price(candle['close'])
        high_str = format_price(candle['high'])
        vol_str = format_volume(candle['turnover'])
        threshold_str = format_volume(volume_threshold)
        
        compact_msg = (
            f"{self.monitor_count}/{self.max_monitor}{'🟢' if is_bullish else '🔴'}"
            f"{close_str}/{high_str}/{vol_str}/Thresh:{threshold_str}"
        )
        
        print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{compact_msg}{ANSI_RESET}")
        if self.log_writer:
            self.log_writer.write(f"*{self.symbol_base} {compact_msg}", time_fmt)
        
        return None
    
    def _process_bullish_candle_1(self, candle: Dict) -> Optional[str]:
        """
        Process bullish Candle 1/3 with new advanced logic
        
        Priority order:
        1. Check rejection (upper_wick > 2× body) → ABORT
        2. Check almost marubozu → IMMEDIATE BUY
        3. Check perfect beauty score → IMMEDIATE BUY
        4. Check recursive 2BULL pattern → RESTART monitoring
        5. Any other bullish → ABORT "WEAK_CONTINUATION"
        """
        
        # Calculate candle metrics
        body_size = abs(candle['close'] - candle['open'])
        upper_wick = candle['high'] - candle['close']
        lower_wick = candle['open'] - candle['low']
        
        time_fmt = vienna_str_to_short(candle['timestamp'])
        
        # RULE 1: Check Rejection First
        if upper_wick > 2 * body_size:
            wick_calc_msg = f"  Wick Reject Calc: Upper={format_price(upper_wick)} Body={format_price(body_size)} Ratio={upper_wick/body_size if body_size > 0 else 0:.2f}x (>2x threshold)"
            if self.log_writer:
                self.log_writer.write(f"*{self.symbol_base} {wick_calc_msg}", time_fmt)
            
            return self._abort_monitoring("WICK_REJECTION", candle)
        
        # RULE 2: Check Almost Marubozu
        if upper_wick == 0 and lower_wick <= 0.02 * body_size:
            gain_percent = ((candle['close'] - candle['open']) / candle['open']) * 100
            min_gain = config.BUY_MONITOR_5MIN.get('marubozu_min_gain_percent', 0.5)
            
            if gain_percent >= min_gain:
                marubozu_msg = f"🔥ALMOST_MARUBOZU DETECTED! No upper wick, lower wick {(lower_wick/body_size*100):.1f}% of body, gain {gain_percent:.2f}%"
                print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{marubozu_msg}{ANSI_RESET}")
                if self.log_writer:
                    self.log_writer.write(f"*{self.symbol_base} {marubozu_msg}", time_fmt)
                
                if config.BUY_MONITOR_5MIN.get('immediate_buy_enabled', True):
                    return self._execute_immediate_buy(candle, "MARUBOZU")
                else:
                    skip_msg = f"⏭️ IMMEDIATE BUY DISABLED - Skipping marubozu buy"
                    print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{skip_msg}{ANSI_RESET}")
                    if self.log_writer:
                        self.log_writer.write(f"*{self.symbol_base} {skip_msg}", time_fmt)
            else:
                insufficient_msg = f"⚠️ MARUBOZU structure but gain {gain_percent:.2f}% < {min_gain}% minimum"
                print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{insufficient_msg}{ANSI_RESET}")
                if self.log_writer:
                    self.log_writer.write(f"*{self.symbol_base} {insufficient_msg}", time_fmt)
        
        # RULE 3: Check Perfect Beauty Score
        beauty_candles = [self.pattern_candles[1], candle]
        beauty_score = BeautyScorer.calculate(beauty_candles)
        
        if beauty_score == 100:
            beauty_msg = f"✨PERFECT BEAUTY SCORE: 100! Beauty on [C2,Candle1]"
            print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{beauty_msg}{ANSI_RESET}")
            if self.log_writer:
                self.log_writer.write(f"*{self.symbol_base} {beauty_msg}", time_fmt)
            
            if config.BUY_MONITOR_5MIN.get('immediate_buy_enabled', True):
                return self._execute_immediate_buy(candle, "PERFECT_BEAUTY")
            else:
                skip_msg = f"⏭️ IMMEDIATE BUY DISABLED - Skipping perfect beauty buy"
                print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{skip_msg}{ANSI_RESET}")
                if self.log_writer:
                    self.log_writer.write(f"*{self.symbol_base} {skip_msg}", time_fmt)
        
        # RULE 4: Check Recursive 2BULL Pattern
        c2_close = self.pattern_candles[1]['close']
        
        if candle['close'] > c2_close:
            momentum_msg = f"🚀STRONG MOMENTUM: Close {format_price(candle['close'])} > C2 close {format_price(c2_close)}"
            print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{momentum_msg}{ANSI_RESET}")
            if self.log_writer:
                self.log_writer.write(f"*{self.symbol_base} {momentum_msg}", time_fmt)
            
            # Create new pattern: [C2, Candle1]
            new_pattern = [self.pattern_candles[1], candle]
            
            # Validate as 2BULL pattern
            if self._validate_2bull_pattern(new_pattern):
                # ============================================================
                # SYNCHRONIZED RECURSIVE PATTERN LOGGING
                # Matches PatternDetector5Min output format exactly
                # ============================================================
                
                c1_new, c2_new = new_pattern
                
                # Calculate metrics
                new_gain = ((c2_new['close'] - c1_new['open']) / c1_new['open']) * 100
                new_vol = c1_new['turnover'] + c2_new['turnover']
                new_trades = c1_new['trades'] + c2_new['trades']
                
                # Calculate beauty score (first pass - no logging)
                new_beauty = BeautyScorer.calculate(new_pattern)
                
                # Format components
                price = format_price(c2_new['close']).replace('$', '')
                gain_str = format_percentage(new_gain, 1).replace('+', '').replace('%', '')
                vol_str = format_volume(new_vol)
                beauty_str = BeautyScorer.format_score(new_beauty)
                
                # 1. HEADER ALERT
                pattern_msg = f"🎯 2BULL {gain_str}/{price}/{vol_str}/{new_trades}/{beauty_str}"
                print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{pattern_msg}{ANSI_RESET}")
                
                if self.log_writer:
                    self.log_writer.write(f"*{self.symbol_base} {pattern_msg}", time_fmt)
                    
                    # 2. CANDLE DATA BLOCK (2 lines for 5min)
                    c1_detail = f"C1: O:{format_price(c1_new['open'])} H:{format_price(c1_new['high'])} L:{format_price(c1_new['low'])} C:{format_price(c1_new['close'])} | V:{format_volume(c1_new['turnover'])} T:{c1_new['trades']}"
                    c2_detail = f"C2: O:{format_price(c2_new['open'])} H:{format_price(c2_new['high'])} L:{format_price(c2_new['low'])} C:{format_price(c2_new['close'])} | V:{format_volume(c2_new['turnover'])} T:{c2_new['trades']}"
                    
                    self.log_writer.write(f"*{self.symbol_base} {c1_detail}", time_fmt)
                    self.log_writer.write(f"*{self.symbol_base} {c2_detail}", time_fmt)
                    
                    # 3. INDICATOR BLOCK (C2 for 5min, not C3)
                    c2_indicators = f"  C2 Indicators: EMA9:{format_price(c2_new['ema9'])} EMA20:{format_price(c2_new['ema20'])} EMA300:{format_price(c2_new['ema300'])} MACD:{c2_new['macd_hist']:+.2f}"
                    self.log_writer.write(f"*{self.symbol_base} {c2_indicators}", time_fmt)
                    
                    # 4. BEAUTY BREAKDOWN (second call with logger triggers breakdown)
                    BeautyScorer.calculate(
                        new_pattern,
                        symbol=f"*{self.symbol_base}",
                        logger=self.log_writer,
                        timestamp=time_fmt
                    )
                    
                    # 5. MONITORING HANDOFF
                    new_avg_volume = (c1_new['turnover'] + c2_new['turnover']) / 2
                    monitor_msg = f"🎯 START BUY MONITORING | Avg Vol: {format_volume(new_avg_volume)}"
                    self.log_writer.write(f"*{self.symbol_base} {monitor_msg}", time_fmt)
                
                # Clear old limit orders
                self.limit_orders = []
                if self.order_queue:
                    self.order_queue.cancel_order(self.symbol_base)
                
                # Restart monitoring with new pattern
                new_avg_volume = (c1_new['turnover'] + c2_new['turnover']) / 2
                self.start_monitoring(c1_new, c2_new, new_beauty, new_avg_volume)
                
                return "RECURSIVE_RESTART"
            else:
                return self._abort_monitoring("RECURSIVE_PATTERN_FAILED", candle)
        
        # RULE 5: Any Other Bullish Case → ABORT
        return self._abort_monitoring("WEAK_CONTINUATION", candle)
    
    def _process_bearish_candle_1(self, candle: Dict, current_volume: float, volume_threshold: float) -> Optional[str]:
        """Process bearish Candle 1/3 - existing limit order logic"""
        
        time_fmt = vienna_str_to_short(candle['timestamp'])
        
        # Calculate candle metrics
        body_size = abs(candle['close'] - candle['open'])
        if body_size == 0:
            body_size = 0.0001
        
        lower_wick = candle['close'] - candle['low']
        upper_wick = candle['high'] - candle['open']
        
        # Check for wick rejection - CONFIGURABLE
        if config.BUY_MONITOR_5MIN.get('wick_rejection_enabled', True):
            wick_ratio_threshold = config.BUY_MONITOR_5MIN.get('wick_rejection_ratio', 2.0)
            if upper_wick > wick_ratio_threshold * body_size:
                wick_calc_msg = f"  Wick Reject Calc: Upper={format_price(upper_wick)} Body={format_price(body_size)} Ratio={upper_wick/body_size:.2f}x (>{wick_ratio_threshold}x threshold)"
                if self.log_writer:
                    self.log_writer.write(f"*{self.symbol_base} {wick_calc_msg}", time_fmt)
                
                return self._abort_monitoring("WICK_REJECTION", candle)
        
        # Check Bearish Marubozu - CONFIGURABLE
        if config.BUY_MONITOR_5MIN.get('bearish_marubozu_abort_enabled', True):
            bearish_marubozu_tolerance = config.BUY_MONITOR_5MIN.get('bearish_marubozu_upper_wick_tolerance', 0.02)
            if lower_wick == 0 and upper_wick <= bearish_marubozu_tolerance * body_size:
                loss_percent = ((candle['close'] - candle['open']) / candle['open']) * 100
                min_loss = config.BUY_MONITOR_5MIN.get('marubozu_min_loss_percent', 0.4)
                
                if loss_percent <= -min_loss:
                    bearish_marubozu_msg = f"🔻BEARISH_MARUBOZU DETECTED! No lower wick, upper wick {(upper_wick/body_size*100):.1f}% of body, loss {loss_percent:.2f}%"
                    print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{bearish_marubozu_msg}{ANSI_RESET}")
                    if self.log_writer:
                        self.log_writer.write(f"*{self.symbol_base} {bearish_marubozu_msg}", time_fmt)
                    
                    return self._abort_monitoring("BEARISH_MARUBOZU", candle)
                else:
                    insufficient_loss_msg = f"⚠️ BEARISH_MARUBOZU structure but loss {loss_percent:.2f}% > -{min_loss}% minimum"
                    print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{insufficient_loss_msg}{ANSI_RESET}")
                    if self.log_writer:
                        self.log_writer.write(f"*{self.symbol_base} {insufficient_loss_msg}", time_fmt)
        
        # Bearish dip logic - CONFIGURABLE
        # Check volume condition
        volume_check_enabled = config.BUY_MONITOR_5MIN.get('require_low_volume_for_limit', True)
        volume_ok = (current_volume < volume_threshold) if volume_check_enabled else True
        
        # Check MACD condition
        macd_check_enabled = config.BUY_MONITOR_5MIN.get('require_macd_positive_for_limit', True)
        macd_ok = (candle.get('macd_hist', 0) > 0) if macd_check_enabled else True
        
        # If both conditions pass, set limit order
        if volume_ok and macd_ok:
            can_commit, rejection_reason = self._check_capital_commitment(candle)
            if not can_commit:
                self._track_missed_opportunity(candle, rejection_reason, "LIMIT_ORDER")
                return self._abort_monitoring(rejection_reason, candle)
            
            # Set limit order
            new_limit = candle['high']
            self.limit_orders = [{'price': new_limit, 'candle': candle}]
            
            if self.position_manager:
                self.position_manager.add_position(
                    symbol=self.symbol_base,
                    timeframe='5min',
                    entry_price=new_limit,
                    entry_time=time_fmt,
                    capital=0.0,
                    beauty_score=self.beauty_score
                )
                self.position_manager.update_status(self.symbol_base, '5min', 'LIMIT_PENDING')
            
            limit_msg = f"✅LIMIT ORDER SET@{new_limit:.6f}"
            print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{limit_msg}{ANSI_RESET}")
            if self.log_writer:
                self.log_writer.write(f"*{self.symbol_base} {limit_msg}", time_fmt)
            
            return None
        
        # Abort based on which condition failed
        if not macd_ok:
            return self._abort_monitoring("MACD_FAILED", candle)
        elif not volume_ok:
            # High volume dip abort - CONFIGURABLE
            if config.BUY_MONITOR_5MIN.get('high_volume_dip_abort_enabled', True):
                return self._abort_monitoring("HIGH_VOLUME_DIP", candle)
            else:
                # Volume high but abort disabled - try to set limit anyway
                can_commit, rejection_reason = self._check_capital_commitment(candle)
                if not can_commit:
                    self._track_missed_opportunity(candle, rejection_reason, "LIMIT_ORDER")
                    return self._abort_monitoring(rejection_reason, candle)
                
                # Set limit order despite high volume
                new_limit = candle['high']
                self.limit_orders = [{'price': new_limit, 'candle': candle}]
                
                if self.position_manager:
                    self.position_manager.add_position(
                        symbol=self.symbol_base,
                        timeframe='5min',
                        entry_price=new_limit,
                        entry_time=time_fmt,
                        capital=0.0,
                        beauty_score=self.beauty_score
                    )
                    self.position_manager.update_status(self.symbol_base, '5min', 'LIMIT_PENDING')
                
                limit_msg = f"✅LIMIT ORDER SET@{new_limit:.6f} (HIGH VOLUME IGNORED)"
                print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{limit_msg}{ANSI_RESET}")
                if self.log_writer:
                    self.log_writer.write(f"*{self.symbol_base} {limit_msg}", time_fmt)
                
                return None
    
    def _check_capital_commitment(self, candle: Dict) -> tuple:
        """
        Check if capital can be committed
        
        Returns:
            (can_commit: bool, reason: str)
        """
        time_fmt = vienna_str_to_short(candle['timestamp'])
        
        if self.position_manager:
            current_positions = self.position_manager.count_positions('5min')
            max_positions = config.TRADING['max_positions_5min']
            
            if current_positions >= max_positions:
                rejection_msg = f"⛔REJECTED: Position limit reached ({current_positions}/{max_positions})"
                print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{rejection_msg}{ANSI_RESET}")
                if self.log_writer:
                    self.log_writer.write(f"*{self.symbol_base} {rejection_msg}", time_fmt)
                
                return False, "POSITION_LIMIT_REACHED"
        
        return True, "APPROVED"
    
    def _track_missed_opportunity(self, candle: Dict, reason: str, opportunity_type: str):
        """Track a missed trading opportunity"""
        time_fmt = vienna_str_to_short(candle['timestamp'])
        
        opportunity = {
            'symbol': self.symbol_base,
            'timestamp': time_fmt,
            'beauty_score': self.beauty_score,
            'type': opportunity_type,
            'reason': reason,
            'price': candle['close']
        }
        
        self.missed_opportunities.append(opportunity)
        
        if self.log_writer:
            missed_msg = f"📊MISSED OPPORTUNITY: {opportunity_type} | Beauty:{self.beauty_score:.0f} | Reason:{reason}"
            self.log_writer.write(f"*{self.symbol_base} {missed_msg}", time_fmt)
    
    def get_missed_opportunities(self):
        """Get list of missed opportunities"""
        return self.missed_opportunities
    
    def _validate_2bull_pattern(self, candles: List[Dict]) -> bool:
        """
        Validate if 2 candles form a valid 2BULL pattern
        
        Checks:
        - All bullish
        - Ascending closes
        - Gain >= min_gain_percent
        - Volume >= min_volume
        - Trades >= min_trades
        - Min candle volume
        """
        if len(candles) != 2:
            return False
        
        c1, c2 = candles
        
        # Check 1: All bullish
        if not (c1['close'] >= c1['open'] and c2['close'] >= c2['open']):
            return False
        
        # Check 2: Ascending closes
        if not (c2['close'] > c1['close']):
            return False
        
        # Calculate metrics
        total_gain = ((c2['close'] - c1['open']) / c1['open']) * 100
        total_volume = c1['turnover'] + c2['turnover']
        total_trades = c1['trades'] + c2['trades']
        
        # Check 3: Gain threshold
        if total_gain < config.PATTERN_2BULL['min_gain_percent']:
            return False
        
        # Check 4: Min candle volume
        if c1['turnover'] < config.PATTERN_2BULL.get('min_candle_volume', 100.0):
            return False
        
        # Check 5: Total volume
        if total_volume < config.PATTERN_2BULL['min_volume']:
            return False
        
        # Check 6: Total trades
        if total_trades < config.PATTERN_2BULL['min_trades']:
            return False
        
        return True
    
    def _check_hammer_weakness(self, candle: Dict) -> Dict:
        """
        Check for hammer pattern indicating weakness during buy monitoring
        
        Hammer structure:
        - Small body at top
        - Long lower wick (sellers tried to push down)
        - Suggests weakness despite recovery
        
        Uses REVERSAL_DETECTION thresholds for consistency
        
        Args:
            candle: Current candle
            
        Returns:
            {
                'detected': bool,
                'lower_ratio': float,
                'details': str
            }
        """
        body_size = abs(candle['close'] - candle['open'])
        
        if body_size == 0:
            body_size = 0.0001
        
        upper_wick = candle['high'] - max(candle['close'], candle['open'])
        lower_wick = min(candle['close'], candle['open']) - candle['low']
        
        lower_ratio = lower_wick / body_size if body_size > 0 else 0
        upper_ratio = upper_wick / body_size if body_size > 0 else 0
        
        min_lower_wick = config.REVERSAL_DETECTION.get('hammer_min_lower_wick_ratio', 2.0)
        max_upper_wick = config.REVERSAL_DETECTION.get('hammer_max_upper_wick_ratio', 0.5)
        
        has_long_lower_wick = lower_ratio >= min_lower_wick
        has_small_upper_wick = upper_ratio <= max_upper_wick
        
        detected = has_long_lower_wick and has_small_upper_wick
        
        return {
            'detected': detected,
            'lower_ratio': lower_ratio,
            'upper_ratio': upper_ratio,
            'details': f'L:{lower_ratio:.1f}x,U:{upper_ratio:.1f}x'
        }
    
    def _check_high_wave_exhaustion(self, candle: Dict) -> Dict:
        """
        Check for high wave candle showing exhaustion/indecision
        
        High wave structure:
        - Very small body (< 20% of total range)
        - Long upper wick (>= 2x body)
        - Long lower wick (>= 2x body)
        - Shows extreme battle between bulls and bears
        - After 2BULL pattern = momentum exhausted
        
        Works on BOTH bullish AND bearish candles
        
        Args:
            candle: Current candle
            
        Returns:
            {
                'detected': bool,
                'body_percent': float,
                'upper_ratio': float,
                'lower_ratio': float,
                'details': str
            }
        """
        body_size = abs(candle['close'] - candle['open'])
        total_range = candle['high'] - candle['low']
        
        if total_range == 0:
            total_range = 0.0001
        if body_size == 0:
            body_size = 0.0001
        
        upper_wick = candle['high'] - max(candle['close'], candle['open'])
        lower_wick = min(candle['close'], candle['open']) - candle['low']
        
        body_percent = (body_size / total_range) * 100
        upper_ratio = upper_wick / body_size if body_size > 0 else 0
        lower_ratio = lower_wick / body_size if body_size > 0 else 0
        
        max_body = config.BUY_MONITOR_5MIN.get('high_wave_max_body_percent', 20.0)
        min_wick = config.BUY_MONITOR_5MIN.get('high_wave_min_wick_ratio', 2.0)
        
        has_small_body = body_percent < max_body
        has_long_upper = upper_ratio >= min_wick
        has_long_lower = lower_ratio >= min_wick
        
        detected = has_small_body and has_long_upper and has_long_lower
        
        return {
            'detected': detected,
            'body_percent': body_percent,
            'upper_ratio': upper_ratio,
            'lower_ratio': lower_ratio,
            'details': f'Body:{body_percent:.1f}%,U:{upper_ratio:.1f}x,L:{lower_ratio:.1f}x'
        }
    
    def _execute_immediate_buy(self, candle: Dict, reason: str) -> str:
        """
        Execute immediate buy
        
        ===== MODIFIED: Pass pattern alert data to sell monitor =====
        """
        can_commit, rejection_reason = self._check_capital_commitment(candle)
        if not can_commit:
            self._track_missed_opportunity(candle, rejection_reason, "IMMEDIATE_BUY")
            return self._abort_monitoring(rejection_reason, candle)
        
        buy_price = candle['close']
        time_fmt = vienna_str_to_short(candle['timestamp'])
        
        buy_msg = f"💰IMMEDIATE_BUY@{buy_price:.6f} ({reason})"
        print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{buy_msg}{ANSI_RESET}")
        if self.log_writer:
            self.log_writer.write(f"*{self.symbol_base} {buy_msg}", time_fmt)
        
        self.bought = True
        self.buy_price = buy_price
        
        if self.position_manager:
            self.position_manager.add_position(
                symbol=self.symbol_base,
                timeframe='5min',
                entry_price=buy_price,
                entry_time=time_fmt,
                capital=0.0,
                beauty_score=self.beauty_score
            )
            self.position_manager.update_status(self.symbol_base, '5min', 'SELL_MONITORING')
        
        # ===== PASS PATTERN ALERT DATA TO SELL MONITOR =====
        self.sell_monitor.start_monitoring(
            self.buy_price, 
            time_fmt,
            pattern_gain=self.pattern_gain,
            pattern_volume=self.pattern_volume,
            pattern_trades=self.pattern_trades,
            beauty_score=self.beauty_score
        )
        # ====================================================
        
        self.is_monitoring = False
        
        return f"IMMEDIATE_BUY_{reason}"
    
    def _abort_monitoring(self, reason: str, candle: Dict) -> str:
        """Abort buy monitoring"""
        time_fmt = vienna_str_to_short(candle['timestamp'])
        
        abort_msg = f"⛔ABORT:{reason}"
        print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{abort_msg}{ANSI_RESET}")
        if self.log_writer:
            self.log_writer.write(f"*{self.symbol_base} {abort_msg}", time_fmt)
        
        self._stop_monitoring()
        return f"ABORT_{reason}"
    
    def _check_limit_fill(self, candle: Dict) -> Optional[str]:
        """
        Check if limit order filled
        
        ===== MODIFIED: Pass pattern alert data to sell monitor =====
        """
        if self.limit_orders and candle['high'] >= self.limit_orders[0]['price']:
            order = self.limit_orders.pop(0)
            self.bought = True
            self.buy_price = order['price']
            
            time_fmt = vienna_str_to_short(candle['timestamp'])
            
            filled_msg = f"💰FILLED@{self.buy_price:.6f}"
            print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{filled_msg}{ANSI_RESET}")
            if self.log_writer:
                self.log_writer.write(f"*{self.symbol_base} {filled_msg}", time_fmt)
            
            entry_msg = f"📄TRADE ENTRY COMPLETE.FILLED@{self.buy_price:.6f}."
            print(f"{time_fmt}*{self.symbol_base} {ANSI_LIGHT_BLUE}{entry_msg}{ANSI_RESET}")
            if self.log_writer:
                self.log_writer.write(f"*{self.symbol_base} {entry_msg}", time_fmt)
            
            if self.position_manager:
                self.position_manager.update_status(self.symbol_base, '5min', 'SELL_MONITORING')
            
            if self.order_queue:
                self.order_queue.mark_filled(self.symbol_base)
            
            # ===== PASS PATTERN ALERT DATA TO SELL MONITOR =====
            self.sell_monitor.start_monitoring(
                self.buy_price, 
                time_fmt,
                pattern_gain=self.pattern_gain,
                pattern_volume=self.pattern_volume,
                pattern_trades=self.pattern_trades,
                beauty_score=self.beauty_score
            )
            # ====================================================
            
            self.is_monitoring = False
            
            return "BUY_FILLED"
        
        return None
    
    def _stop_monitoring(self):
        """Stop buy monitoring"""
        if self.limit_orders and self.order_queue:
            self.order_queue.cancel_order(self.symbol_base)
        
        if self.position_manager and self.position_manager.has_position(self.symbol_base, '5min'):
            position = self.position_manager.get_position(self.symbol_base, '5min')
            if position and position.status == 'LIMIT_PENDING':
                self.position_manager.remove_position(self.symbol_base, '5min')
        
        if not self.sell_monitor.is_monitoring:
            self.is_monitoring = False
            if self.log_writer:
                self.log_writer.write_raw(f"{self.symbol_base} 🛑BUY MONITORING ENDED")
    
    def start_monitoring_ema(self, pattern_info: Dict):
        """
        Start monitoring for EMA momentum pattern entry (5min timeframe)
        
        Simpler than 2BULL - just waits for next candle open to enter
        No limit orders, no recursive pattern detection
        
        Args:
            pattern_info: Dict with keys: type, ema_gain_pct, entry_price, timestamp, etc.
        """
        self.is_monitoring = True
        self.monitor_count = 0
        self.bought = False
        self.buy_price = None
        self.pattern_type = pattern_info['type']  # 'EMA5min'
        self.ema_pattern_info = pattern_info
        
        # EMA patterns don't use volume threshold or beauty score
        self.avg_volume = 0.0
        self.beauty_score = 0.0
        self.pattern_candles = []
        self.limit_orders = []
        
        # Store pattern metrics for sell monitor
        self.pattern_gain = pattern_info['ema_gain_pct']
        self.pattern_volume = 0.0
        self.pattern_trades = 0
        
        time_fmt = vienna_str_to_short(pattern_info['timestamp'])
        if self.log_writer:
            self.log_writer.write(
                f"{self.symbol_base} 🎯 START EMA MONITORING [{pattern_info['type']}] | "
                f"EMA9 +{pattern_info['ema_gain_pct']:.2f}% over {pattern_info['lookback_candles']}c",
                time_fmt
            )
    
    def _execute_ema_entry(self, candle: Dict) -> str:
        """Execute entry for EMA momentum pattern at candle open (5min)"""
        time_fmt = vienna_str_to_short(candle['timestamp'])
        
        # Log candle data
        if self.log_writer:
            candle_detail = f"C:    O:{format_price(candle['open'])} H:{format_price(candle['high'])} L:{format_price(candle['low'])} C:{format_price(candle['close'])} | V:{format_volume(candle['turnover'])} T:{candle['trades']}"
            self.log_writer.write(f"{self.symbol_base} {candle_detail}", time_fmt)
        
        # Enter at candle open
        entry_price = candle['open']
        
        # Check for capital and position management
        if self.position_manager and self.order_queue:
            timeframe = '5min'
            
            # Calculate capital allocation for EMA patterns
            capital_pct = config.TRADING['allocation_percent_5min']
            total_capital = config.TRADING['total_capital']
            max_positions = config.EMA_MOMENTUM['max_positions_5min']
            
            capital_per_position = (total_capital * capital_pct / 100) / max_positions
            
            # Add position
            success = self.position_manager.add_position(
                symbol=self.symbol_base,
                timeframe=timeframe,
                entry_price=entry_price,
                entry_time=candle['timestamp'],
                capital=capital_per_position,
                beauty_score=0.0,  # EMA patterns don't have beauty score
                pattern_type=self.pattern_type
            )
            
            if not success:
                if self.log_writer:
                    self.log_writer.write(f"{self.symbol_base} [{self.pattern_type}] ✗ Failed to add position", time_fmt)
                self.is_monitoring = False
                return "FAILED_TO_ADD_POSITION"
            
            # Create buy order
            order = {
                'symbol': self.symbol_base,
                'side': 'BUY',
                'price': entry_price,
                'quantity': capital_per_position / entry_price,
                'timestamp': candle['timestamp'],
                'pattern_type': self.pattern_type
            }
            self.order_queue.add_order(order)
        
        self.bought = True
        self.buy_price = entry_price
        self.is_monitoring = False
        
        # Start sell monitor with pattern type
        self.sell_monitor.start_monitoring(
            entry_price=entry_price,
            entry_time=candle['timestamp'],
            pattern_gain=self.pattern_gain,
            pattern_volume=self.pattern_volume,
            pattern_trades=self.pattern_trades,
            beauty_score=0.0,
            pattern_type=self.pattern_type
        )
        
        if self.log_writer:
            self.log_writer.write(
                f"{self.symbol_base} [{self.pattern_type}] ✓ BUY EXECUTED at {format_price(entry_price)} | "
                f"Capital: {format_price(capital_per_position)}",
                time_fmt
            )
        
        return "BUY_FILLED"
