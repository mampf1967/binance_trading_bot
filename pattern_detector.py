"""
pattern_detector.py - 3BULL pattern detection for 1min candles

Detects 3-candle bullish patterns with volume and momentum confirmation.
Supports doji C1 with gap requirement.
Implements synchronized timestamp logging with reorganized sequence.

VERSION 2.3.1 - FIXED EMA LOGGING (log() → write() with timestamps)
"""

from typing import Optional, Dict, List
from beauty_scorer import BeautyScorer
from formatting_utils import format_price, format_volume, format_percentage
from console_formatter import ANSI_BLUE, ANSI_RESET
from time_converter import vienna_str_to_short
from candle_size_analyzer import CandleSizeAnalyzer
import config


class PatternDetector:
    """Detects 3BULL pattern in 1min candle data"""
    
    def __init__(self, database, log_writer, symbol_base: str, buy_monitor,
                 position_manager=None, cooldown_tracker=None, debug_mode=False):
        """
        Initialize pattern detector
        
        Args:
            database: Database instance
            log_writer: LogWriter instance
            symbol_base: Asset symbol
            buy_monitor: BuyMonitor instance
            position_manager: PositionManager instance
            cooldown_tracker: CooldownTracker instance
            debug_mode: Enable debug logging
        """
        self.db = database
        self.log_writer = log_writer
        self.symbol_base = symbol_base
        self.buy_monitor = buy_monitor
        self.position_manager = position_manager
        self.cooldown_tracker = cooldown_tracker
        self.debug_mode = debug_mode
        self.config = config.PATTERN_3BULL
        self.last_alert_timestamp = None
        
        # Initialize candle size analyzer
        self.candle_analyzer = CandleSizeAnalyzer(
            database,
            lookback_config=config.CANDLE_ANALYZER
        )
        
        # EMA momentum pattern tracking
        self.ema_config = config.EMA_MOMENTUM
        self.ema_last_detection_candle = None  # Track last detection for recency filter
    
    def check_pattern(self, candle: Dict) -> Optional[str]:
        """Check for 3BULL pattern, EMA momentum pattern, or process buy monitor"""
        
        # 0. COOLDOWN CHECK
        if self.cooldown_tracker:
            self.cooldown_tracker.process_candle(self.symbol_base, '1min')
            
            if self.cooldown_tracker.is_in_cooldown(self.symbol_base, '1min'):
                if self.buy_monitor.is_monitoring:
                    self.buy_monitor.process_candle(candle)
                return None
        
        # 1. PRIORITY: Check if sell monitor is active
        if self.buy_monitor.sell_monitor.is_monitoring:
            result = self.buy_monitor.sell_monitor.process_candle(candle)
            return f"SELL_MONITOR: {result}" if result else None
        
        # 2. Check if buy monitor is active
        if self.buy_monitor.is_monitoring:
            result = self.buy_monitor.process_candle(candle)
            return f"BUY_MONITOR: {result}" if result else None
        
        # 3. Try 3BULL pattern first
        if self.config['enabled']:
            result = self._check_3bull_pattern(candle)
            if result:
                return result
        
        # 4. Try EMA momentum pattern if 3BULL didn't trigger
        if self.ema_config['enabled']:
            result = self._check_and_start_ema_pattern(candle)
            if result:
                return result
        
        return None
    
    def _check_3bull_pattern(self, candle: Dict) -> Optional[str]:
        """Check for 3BULL pattern - returns detection result or None"""
        # 3. Get last 3 candles for pattern detection
        candles = self.db.get_recent_candles(3)
        if len(candles) < 3:
            return None
        
        c1, c2, c3 = candles[0], candles[1], candles[2]
        
        # CHECK 1: Consecutive minutes (handles daily rollover)
        if not (self._are_consecutive(c1, c2) and self._are_consecutive(c2, c3)):
            return None
        
        # CHECK 2: C2 and C3 must be bullish
        if not (c2['close'] >= c2['open'] and c3['close'] >= c3['open']):
            return None
        
        # CHECK 2b: C1 bullish OR doji with gap
        c1_is_valid = False
        c1_pattern_type = "BULLISH"
        
        # Standard case: C1 is bullish
        if c1['close'] >= c1['open']:
            c1_is_valid = True
            c1_pattern_type = "BULLISH"
        
        # Doji case: C1 is doji with gap to C2
        elif self.config.get('allow_doji_c1', False):
            doji_result = self._check_doji_c1(c1, c2)
            if doji_result['is_valid']:
                c1_is_valid = True
                c1_pattern_type = f"DOJI+GAP({doji_result['gap_percent']:.2f}%)"
                
                # Log doji detection if debug mode
                if self.debug_mode:
                    time_fmt = vienna_str_to_short(c1['timestamp'])
                    doji_msg = f"🎯 DOJI C1 DETECTED | Gap: {doji_result['gap_percent']:.2f}% | Body: {doji_result['body_percent']:.3f}%"
                    print(f"{time_fmt} {self.symbol_base} {ANSI_BLUE}{doji_msg}{ANSI_RESET}")
                    if self.log_writer:
                        self.log_writer.write(f"{self.symbol_base} {doji_msg}", time_fmt)
        
        if not c1_is_valid:
            return None
        
        # CHECK 3: Ascending closes
        if not (c2['close'] > c1['close'] and c3['close'] > c2['close']):
            return None
        
        # Calculate metrics
        total_gain = ((c3['close'] - c1['open']) / c1['open']) * 100
        total_volume = c1['turnover'] + c2['turnover'] + c3['turnover']
        total_trades = c1['trades'] + c2['trades'] + c3['trades']
        
        # CHECK 4-6: Thresholds
        if total_gain < self.config['min_gain_percent']:
            return None
        if c1['turnover'] < self.config.get('min_candle_volume', 100.0):
            return None
        if total_volume < self.config['min_volume']:
            return None
        if total_trades < self.config['min_trades']:
            return None
        
        # CHECK 7: EMA300 filter (price above EMA300)
        if self.config.get('filter_ema300', False):
            if c3['close'] < c3['ema300']:
                return None
        
        # CHECK 8: EMA9 above EMA20 filter
        if self.config.get('filter_ema9_above_ema20', False):
            if c3['ema9'] < c3['ema20']:
                return None
        
        # CHECK 9: MACD positive filter (histogram > 0)
        if self.config.get('filter_macd_positive', False):
            if c3['macd_hist'] <= 0:
                return None
        
        # CHECK 10: DIF positive filter
        if self.config.get('filter_dif_positive', False):
            if c3['dif'] <= 0:
                return None
        
        # CHECK 11: DEA positive filter
        if self.config.get('filter_dea_positive', False):
            if c3['dea'] <= 0:
                return None
        
        # CHECK 12: Volume surge filter
        if self.config.get('filter_volume_surge', False):
            surge_check = self._check_volume_surge([c1, c2, c3])
            if not surge_check['passed']:
                if self.debug_mode:
                    time_fmt = vienna_str_to_short(c3['timestamp'])
                    surge_msg = f"  ❌ Volume surge check failed: {surge_check['details']}"
                    print(f"{time_fmt} {self.symbol_base} {surge_msg}")
                return None
        
        # CHECK 13: MACD acceleration filter
        if self.config.get('filter_macd_acceleration', False):
            accel_check = self._check_macd_acceleration([c1, c2, c3])
            if not accel_check['passed']:
                if self.debug_mode:
                    time_fmt = vienna_str_to_short(c3['timestamp'])
                    accel_msg = f"  ❌ MACD acceleration check failed: {accel_check['details']}"
                    print(f"{time_fmt} {self.symbol_base} {accel_msg}")
                return None
        
        # CHECK 14: EMA crossover filter
        if self.config.get('filter_ema_crossover', False):
            crossover_check = self._check_ema_crossover(c3)
            if not crossover_check['crossed']:
                if self.debug_mode:
                    time_fmt = vienna_str_to_short(c3['timestamp'])
                    cross_msg = f"  ❌ EMA crossover check failed: {crossover_check['details']}"
                    print(f"{time_fmt} {self.symbol_base} {cross_msg}")
                return None
        
        # CHECK 15: Candle size filter
        if self.config.get('filter_candle_size', False):
            min_ratio = self.config.get('candle_size_min_ratio', 1.5)
            
            size_check = self.candle_analyzer.check_pattern_size(
                pattern_candles=[c1, c2, c3],
                min_ratio=min_ratio
            )
            
            if not size_check['passed']:
                if self.debug_mode:
                    time_fmt = vienna_str_to_short(c3['timestamp'])
                    size_msg = f"  ❌ Candle size: {size_check['details']}"
                    print(f"{time_fmt} {self.symbol_base} {size_msg}")
                return None
            
            elif self.debug_mode:
                time_fmt = vienna_str_to_short(c3['timestamp'])
                size_msg = f"  ✅ Candle size: {size_check['details']}"
                print(f"{time_fmt} {self.symbol_base} {size_msg}")
        
        # Duplicate check
        if self.last_alert_timestamp == c3['timestamp']:
            return None
        
        self.last_alert_timestamp = c3['timestamp']
        
        # SYNCHRONIZED TIMESTAMP CAPTURE
        time_fmt = vienna_str_to_short(c3['timestamp'])
        
        # Calculate average volume for monitoring
        avg_volume = (c1['turnover'] + c2['turnover'] + c3['turnover']) / 3
        
        # Format message components
        price = format_price(c3['close']).replace('$', '')
        gain_str = format_percentage(total_gain, 1).replace('+', '').replace('%', '')
        vol_str = format_volume(total_volume)
        
        # Calculate beauty score (first pass - no logging, just get the score)
        beauty_score = BeautyScorer.calculate(
            [c1, c2, c3], 
            symbol=self.symbol_base,
            logger=None,
            timestamp=time_fmt
        )
        beauty_str = BeautyScorer.format_score(beauty_score)
        
        pattern_msg = f"🎯 3BULL {gain_str}/{price}/{vol_str}/{total_trades}/{beauty_str}"
        
        # Check if we can start buy monitoring
        can_monitor = True
        skip_reason = None
        
        if self.position_manager:
            # Count 3BULL positions specifically
            three_bull_count = self.position_manager.count_positions_by_pattern('1min', '3BULL_1min')
            if three_bull_count >= config.TRADING['max_positions_1min']:
                can_monitor = False
                skip_reason = "No 3BULL slots available"
        
        # UNIFIED LOGGING SEQUENCE
        if self.log_writer:
            # 2. CANDLE DATA BLOCK (3 lines) - ALWAYS LOG
            c1_detail = f"  C1: O:{format_price(c1['open'])} H:{format_price(c1['high'])} L:{format_price(c1['low'])} C:{format_price(c1['close'])} | V:{format_volume(c1['turnover'])} T:{c1['trades']}"
            c2_detail = f"  C2: O:{format_price(c2['open'])} H:{format_price(c2['high'])} L:{format_price(c2['low'])} C:{format_price(c2['close'])} | V:{format_volume(c2['turnover'])} T:{c2['trades']}"
            c3_detail = f"  C3: O:{format_price(c3['open'])} H:{format_price(c3['high'])} L:{format_price(c3['low'])} C:{format_price(c3['close'])} | V:{format_volume(c3['turnover'])} T:{c3['trades']}"
            
            self.log_writer.write(f"{self.symbol_base} {c1_detail}", time_fmt)
            
            # Structure comparison for C1
            if config.CANDLE_ANALYZER.get('enable_structure_logging', True):
                self.candle_analyzer.format_structure_comparison(
                    c1, self.symbol_base, time_fmt, self.log_writer
                )
            
            self.log_writer.write(f"{self.symbol_base} {c2_detail}", time_fmt)
            
            # Structure comparison for C2
            if config.CANDLE_ANALYZER.get('enable_structure_logging', True):
                self.candle_analyzer.format_structure_comparison(
                    c2, self.symbol_base, time_fmt, self.log_writer
                )
            
            self.log_writer.write(f"{self.symbol_base} {c3_detail}", time_fmt)
            
            # Structure comparison for C3
            if config.CANDLE_ANALYZER.get('enable_structure_logging', True):
                self.candle_analyzer.format_structure_comparison(
                    c3, self.symbol_base, time_fmt, self.log_writer
                )
            
            # 3. INDICATOR BLOCK - ALWAYS LOG
            c3_indicators = f"  C3 Indicators: EMA9:{format_price(c3['ema9'])} EMA20:{format_price(c3['ema20'])} EMA300:{format_price(c3['ema300'])} MACD:{c3['macd_hist']:+.2f}"
            self.log_writer.write(f"{self.symbol_base} {c3_indicators}", time_fmt)
            
            # 4. BEAUTY BREAKDOWN - ALWAYS LOG
            BeautyScorer.calculate(
                [c1, c2, c3],
                symbol=self.symbol_base,
                logger=self.log_writer,
                timestamp=time_fmt
            )
        
        # NOW handle can_monitor check with appropriate header
        if can_monitor:
            # 1. HEADER ALERT (started)
            print(f"{time_fmt} {self.symbol_base} {ANSI_BLUE}{pattern_msg}{ANSI_RESET}")
            if self.log_writer:
                self.log_writer.write(f"{self.symbol_base} {pattern_msg}", time_fmt)
                
                # 5. START MONITORING MSG
                self.log_writer.write(
                    f"{self.symbol_base} ✓ STARTING BUY MONITORING",
                    time_fmt
                )
            
            # Start buy monitoring
            self.buy_monitor.start_monitoring(
                avg_volume=avg_volume,
                beauty_score=beauty_score,
                pattern_candles=[c1, c2, c3],
                pattern_gain=total_gain,
                pattern_volume=total_volume,
                pattern_trades=total_trades,
                pattern_type='3BULL_1min'
            )
            
            return "3BULL_STARTED"
        
        else:
            # 1. HEADER ALERT (blocked)
            blocked_msg = f"{pattern_msg} | ✗ BLOCKED: {skip_reason}"
            print(f"{time_fmt} {self.symbol_base} {ANSI_BLUE}{blocked_msg}{ANSI_RESET}")
            if self.log_writer:
                self.log_writer.write(f"{self.symbol_base} {blocked_msg}", time_fmt)
            
            return "3BULL_BLOCKED"
    
    def _are_consecutive(self, c1: Dict, c2: Dict) -> bool:
        """Check if two candles are consecutive (1 minute apart)"""
        ts_format = "%Y-%m-%d %H:%M:%S"
        try:
            from datetime import datetime
            t1 = datetime.strptime(c1['timestamp'], ts_format)
            t2 = datetime.strptime(c2['timestamp'], ts_format)
            diff = (t2 - t1).total_seconds()
            return diff == 60
        except:
            return False
    
    def _check_doji_c1(self, c1: Dict, c2: Dict) -> Dict:
        """Check if C1 is a valid doji with gap to C2"""
        body = abs(c1['close'] - c1['open'])
        body_percent = (body / c1['open']) * 100
        
        max_body_percent = self.config.get('doji_max_body_percent', 0.05)
        min_gap_percent = self.config.get('doji_min_gap_percent', 0.10)
        
        # Check if body is small enough to be considered doji
        if body_percent > max_body_percent:
            return {'is_valid': False, 'reason': 'body_too_large', 'body_percent': body_percent}
        
        # Check if there's a gap between C1's close and C2's open
        gap = abs(c2['open'] - c1['close'])
        gap_percent = (gap / c1['close']) * 100
        
        if gap_percent < min_gap_percent:
            return {'is_valid': False, 'reason': 'gap_too_small', 'gap_percent': gap_percent}
        
        return {
            'is_valid': True,
            'body_percent': body_percent,
            'gap_percent': gap_percent
        }
    
    def _check_volume_surge(self, pattern_candles: List[Dict]) -> Dict:
        """Check if pattern volume surges above baseline"""
        lookback = self.config.get('volume_surge_lookback', 20)
        multiplier = self.config.get('volume_surge_multiplier', 2.0)
        
        recent_candles = self.db.get_recent_candles(lookback + len(pattern_candles))
        
        if len(recent_candles) < lookback + len(pattern_candles):
            return {
                'passed': True,
                'pattern_avg': 0,
                'recent_avg': 0,
                'ratio': 0,
                'details': 'insufficient_history'
            }
        
        baseline_candles = recent_candles[:-len(pattern_candles)][-lookback:]
        
        pattern_avg = sum(c['turnover'] for c in pattern_candles) / len(pattern_candles)
        recent_avg = sum(c['turnover'] for c in baseline_candles) / len(baseline_candles)
        
        if recent_avg == 0:
            recent_avg = 1
        
        ratio = pattern_avg / recent_avg
        passed = ratio >= multiplier
        
        return {
            'passed': passed,
            'pattern_avg': pattern_avg,
            'recent_avg': recent_avg,
            'ratio': ratio,
            'details': f'ratio={ratio:.2f}x (need {multiplier}x)'
        }
    
    def _check_macd_acceleration(self, pattern_candles: List[Dict]) -> Dict:
        """Check if MACD histogram is strictly non-decreasing"""
        min_growth = self.config.get('macd_acceleration_min_growth', 0.0)
        
        macd_values = [c.get('macd_hist', 0) for c in pattern_candles]
        
        is_accelerating = True
        for i in range(1, len(macd_values)):
            growth = macd_values[i] - macd_values[i-1]
            if growth < min_growth:
                is_accelerating = False
                break
        
        total_growth = macd_values[-1] - macd_values[0] if len(macd_values) > 1 else 0
        
        return {
            'passed': is_accelerating,
            'growth': total_growth,
            'macd_sequence': macd_values,
            'details': f'growth={total_growth:+.4f}, seq={[f"{v:.3f}" for v in macd_values]}'
        }
    
    def _check_ema_crossover(self, current_candle: Dict) -> Dict:
        """Check if EMA9 crossed above EMA20 within lookback window"""
        lookback = self.config.get('ema_crossover_lookback', 5)
        
        recent_candles = self.db.get_recent_candles(lookback + 2)
        
        if len(recent_candles) < 2:
            return {
                'crossed': False,
                'candles_ago': 0,
                'details': 'insufficient data'
            }
        
        for i in range(len(recent_candles) - 1):
            prev = recent_candles[i]
            curr = recent_candles[i + 1]
            
            if prev['ema9'] <= prev['ema20'] and curr['ema9'] > curr['ema20']:
                candles_ago = len(recent_candles) - 1 - i
                
                if candles_ago <= lookback:
                    return {
                        'crossed': True,
                        'candles_ago': candles_ago,
                        'details': f'crossed {candles_ago}c ago'
                    }
        
        return {
            'crossed': False,
            'candles_ago': 0,
            'details': f'no crossover in last {lookback}c'
        }
    
    def _check_and_start_ema_pattern(self, candle: Dict) -> Optional[str]:
        """Check for EMA momentum pattern and start monitoring if detected"""
        pattern_info = self.check_ema_momentum_pattern(candle)
        if not pattern_info:
            return None
        
        # Pattern detected and passed recency filter
        # Now check position limits and capital
        
        # Get timestamp for consistent logging
        time_fmt = vienna_str_to_short(pattern_info['timestamp'])
        
        if self.position_manager:
            # Count EMA positions specifically
            ema_count = self.position_manager.count_positions_by_pattern('1min', 'EMA1min')
            if ema_count >= self.ema_config['max_positions_1min']:
                self.log_writer.write(
                    f"[EMA1min] {self.symbol_base}: ✗ BLOCKED - "
                    f"Maximum EMA positions ({self.ema_config['max_positions_1min']}) reached",
                    time_fmt
                )
                return None
        
        # Log successful detection
        self.log_writer.write(
            f"[EMA1min] {self.symbol_base}: Pattern detected - "
            f"EMA9 +{pattern_info['ema_gain_pct']:.2f}% over {pattern_info['lookback_candles']} candles "
            f"(close: {format_price(pattern_info['entry_price'])})",
            time_fmt
        )
        
        # Start EMA monitoring (will enter at next candle open)
        self.buy_monitor.start_monitoring_ema(pattern_info)
        
        self.log_writer.write(
            f"[EMA1min] {self.symbol_base}: ✓ STARTING monitoring - Entry at next candle open",
            time_fmt
        )
        
        return "EMA1min DETECTED"
    
    def check_ema_momentum_pattern(self, current_candle: Dict) -> Optional[Dict]:
        """
        Check for EMA9 momentum surge pattern
        
        Returns dict with pattern info if detected, None otherwise
        """
        if not self.ema_config['enabled']:
            return None
        
        threshold = self.ema_config['threshold_percent'] / 100.0
        lookback_max = self.ema_config['lookback_window']
        lookback_min = self.ema_config['min_lookback_candles']
        
        current_ema9 = current_candle.get('ema9')
        if current_ema9 is None:
            return None
        
        # Get historical candles for lookback
        historical = self.db.get_recent_candles(lookback_max + 1)
        if len(historical) < lookback_min + 1:
            return None
        
        # Check EMA9 gain across different lookback windows
        for lookback in range(lookback_min, lookback_max + 1):
            if lookback >= len(historical):
                continue
            
            old_candle = historical[-(lookback + 1)]  # N candles ago
            old_ema9 = old_candle.get('ema9')
            
            if old_ema9 is None or old_ema9 <= 0:
                continue
            
            ema_gain = (current_ema9 - old_ema9) / old_ema9
            
            if ema_gain >= threshold:
                # Pattern detected!
                pattern_info = {
                    'type': 'EMA1min',
                    'ema_gain_pct': ema_gain * 100,
                    'lookback_candles': lookback,
                    'current_ema9': current_ema9,
                    'old_ema9': old_ema9,
                    'entry_price': current_candle['close'],
                    'timestamp': current_candle['timestamp']
                }
                
                # Check recency filter
                if self.ema_config['recency_filter_enabled']:
                    if self.ema_last_detection_candle is not None:
                        total_candles = self.db.get_candle_count()
                        candles_since_last = total_candles - self.ema_last_detection_candle
                        recency_window = self.ema_config['recency_filter_candles']
                        
                        if candles_since_last < recency_window:
                            # Log skipped pattern with timestamp
                            time_fmt = vienna_str_to_short(current_candle['timestamp'])
                            
                            self.log_writer.write(
                                f"[EMA1min] {self.symbol_base}: Pattern detected - "
                                f"EMA9 +{ema_gain*100:.2f}% over {lookback} candles "
                                f"(close: {format_price(current_candle['close'])})",
                                time_fmt
                            )
                            self.log_writer.write(
                                f"[EMA1min] {self.symbol_base}: ✗ SKIPPED - "
                                f"Recency filter ({candles_since_last} candles since last detection)",
                                time_fmt
                            )
                            
                            # Update last detection even for skipped patterns
                            self.ema_last_detection_candle = total_candles
                            return None
                
                # Pattern passes all filters
                # Update last detection
                self.ema_last_detection_candle = self.db.get_candle_count()
                
                return pattern_info      
        return None
