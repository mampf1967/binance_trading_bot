"""
sell_monitor_5min.py - Sell decision monitoring for 5min timeframe

Monitors active positions and determines sell points using:
- Standard mode: +3% TP, -3% SL
- Recovery mode: +0.25% TP after 5 candles stagnation
- Time limit: Exit after 12 candles

Phased exit strategy with dynamic target adjustment.

VERSION 2.5 - ADDED COMMISSION TRACKING
"""

from typing import Dict, Optional, List
from formatting_utils import format_price, format_percentage, format_volume
from console_formatter import format_colored_pnl, ANSI_GREEN, ANSI_RED, ANSI_CYAN, ANSI_RESET
from time_converter import vienna_str_to_short
from candle_size_analyzer import CandleSizeAnalyzer
import config


class SellMonitor5Min:
    """Monitors position and determines sell points for 5min timeframe"""
    
    def __init__(self, log_writer, symbol_base: str, position_manager=None,
                 cooldown_tracker=None, 
                 database=None,  # ← ADDED THIS PARAMETER
                 debug_mode=False):
        """
        Initialize sell monitor
        
        Args:
            log_writer: LogWriter instance
            symbol_base: Asset symbol (e.g., 'BTC', 'ETH')
            position_manager: PositionManager instance
            cooldown_tracker: CooldownTracker instance
            database: Database instance for historical analysis (NEW)
            debug_mode: Enable debug logging
        """
        self.log_writer = log_writer
        self.symbol_base = symbol_base
        self.debug_mode = debug_mode
        
        # Managers
        self.position_manager = position_manager
        self.cooldown_tracker = cooldown_tracker
        
        # Configuration
        self.tp_percent_orig = config.SELL_MONITOR_5MIN['tp_percent_orig']
        self.sl_percent_orig = config.SELL_MONITOR_5MIN['sl_percent_orig']
        self.recovery_tp = config.SELL_MONITOR_5MIN['recovery_tp']
        self.spike_trigger = config.SELL_MONITOR_5MIN['spike_trigger']
        self.stagnation_candles = config.SELL_MONITOR_5MIN['stagnation_candles']
        self.max_candles = config.SELL_MONITOR_5MIN['max_candles']
        
        # Commission configuration
        self.commission_percent = getattr(config, 'COMMISSION_PERCENT', 0.075)
        
        # Reversal detection config
        self.reversal_config = config.REVERSAL_DETECTION
        
        # State
        self.is_monitoring = False
        self.entry_price = None
        self.entry_candle_count = 0
        self.tp_price = None
        self.sl_price = None
        self.pattern_type = None  # NEW: Track pattern type
        
        # Trade tracking - store ALL completed trades
        self.completed_trades = []  # List of all trade summaries
        
        # Current trade state
        self.trade_result = None
        self.exit_price = None
        self.exit_reason = None
        self.entry_time = None
        self.exit_time = None
        
        # Mode: False = Standard (3%), True = Recovery (0.25%)
        self.recovery_mode = False
        
        # Reversal detection tracking
        self.prev_candle = None
        self.warning_history = {}  # Track last warning candle by pattern type
        
        # NEW: Store database and lazy init analyzer
        self.db = database
        self.candle_analyzer = None  # Lazy initialization
    
    def _calculate_commission(self, entry_price: float, exit_price: float) -> Dict:
        """
        Calculate commission costs for a round-trip trade.
        
        Commission is charged on top of the trade value:
        - Buy: Pay commission_percent on entry value
        - Sell: Pay commission_percent on exit value
        
        Args:
            entry_price: Entry price per unit
            exit_price: Exit price per unit
            
        Returns:
            Dict with commission details:
            - entry_commission_percent: Commission on buy (% of entry)
            - exit_commission_percent: Commission on sell (% of entry, scaled)
            - total_commission_percent: Total round-trip commission (% of entry)
            - gross_pnl_percent: PnL before commission
            - net_pnl_percent: PnL after commission
        """
        # Gross PnL (before commission)
        gross_pnl_percent = ((exit_price - entry_price) / entry_price) * 100
        
        # Commission on entry (as % of entry value)
        entry_commission_percent = self.commission_percent
        
        # Commission on exit (as % of entry value)
        # exit_commission = exit_price * commission_rate
        # As % of entry: (exit_price * commission_rate) / entry_price * 100
        exit_commission_percent = (exit_price / entry_price) * self.commission_percent
        
        # Total commission (as % of entry value)
        total_commission_percent = entry_commission_percent + exit_commission_percent
        
        # Net PnL (after commission)
        net_pnl_percent = gross_pnl_percent - total_commission_percent
        
        return {
            'entry_commission_percent': entry_commission_percent,
            'exit_commission_percent': exit_commission_percent,
            'total_commission_percent': total_commission_percent,
            'gross_pnl_percent': gross_pnl_percent,
            'net_pnl_percent': net_pnl_percent
        }
    
    def _get_candle_analyzer(self):
        """Lazy initialization of candle analyzer"""
        if self.candle_analyzer is None and self.db is not None:
            self.candle_analyzer = CandleSizeAnalyzer(
                self.db,
                lookback_config=config.CANDLE_ANALYZER
            )
        return self.candle_analyzer
    
    def start_monitoring(self, entry_price: float, entry_time: str,
                         pattern_gain=None, pattern_volume=None, pattern_trades=None, beauty_score=None,
                         pattern_type: str = '2BULL_5min'):
        """Start monitoring after buy"""
        self.is_monitoring = True
        self.entry_price = entry_price
        self.entry_candle_count = 0
        self.recovery_mode = False
        self.entry_time = entry_time
        self.pattern_type = pattern_type  # NEW: Track pattern type
        
        # Store pattern metrics for trade summary
        self.pattern_gain = pattern_gain
        self.pattern_volume = pattern_volume
        self.pattern_trades = pattern_trades
        self.pattern_beauty = beauty_score
        
        # Reset reversal detection state
        self.prev_candle = None
        self.warning_history = {}
        
        # NEW: Calculate adaptive stop loss (optional)
        if config.SELL_MONITOR_5MIN.get('adaptive_stop_loss', False):
            analyzer = self._get_candle_analyzer()
            if analyzer:
                sl_multiplier = config.SELL_MONITOR_5MIN.get('sl_bearish_multiplier', 2.0)
                min_sl = config.SELL_MONITOR_5MIN.get('min_sl_percent', 2.0)
                max_sl = config.SELL_MONITOR_5MIN.get('max_sl_percent', 5.0)
                
                adaptive_sl = analyzer.calculate_adaptive_stop_loss(
                    entry_price,
                    multiplier=sl_multiplier,
                    min_percent=min_sl,
                    max_percent=max_sl
                )
                
                self.sl_price = adaptive_sl['sl_price']
                self.sl_percent = adaptive_sl['sl_percent']
                
                if self.debug_mode:
                    print(f"  📊 Adaptive SL: {adaptive_sl['details']}")
            else:
                # Fallback to existing fixed SL
                self.sl_percent = config.SELL_MONITOR_5MIN.get('sl_percent_orig', 3.0)
                self.sl_price = entry_price * (1 - self.sl_percent / 100)
        else:
            # Use existing fixed SL
            self.sl_percent = config.SELL_MONITOR_5MIN.get('sl_percent_orig', 3.0)
            self.sl_price = entry_price * (1 - self.sl_percent / 100)
        
        # Set Initial TP
        self.tp_price = entry_price * (1 + self.tp_percent_orig / 100)
        
        # Update position manager
        if self.position_manager:
            self.position_manager.update_status(self.symbol_base, '5min', 'SELL_MONITORING')
        
        # Log start
        start_msg = f"📈STARTING SELL MONITORING"
        print(f"{entry_time}*{self.symbol_base} {ANSI_GREEN}{start_msg}{ANSI_RESET}")
        if self.log_writer:
            self.log_writer.write(f"*{self.symbol_base} {start_msg}", entry_time)
        
        details_msg = f"Entry:{format_price(self.entry_price)}|TP:{format_price(self.tp_price)}|SL:{format_price(self.sl_price)}"
        print(f"{entry_time}*{self.symbol_base} {details_msg}")
        if self.log_writer:
            self.log_writer.write(f"*{self.symbol_base} {details_msg}", entry_time)
    
    def process_candle(self, candle: Dict) -> Optional[str]:
        """Process a candle during position monitoring"""
        if not self.is_monitoring:
            return None
        
        # Get timestamp for consistent logging
        time_fmt = vienna_str_to_short(candle['timestamp'])
        
        # Log candle OHLCV data first
        if self.log_writer:
            candle_detail = f"  C:    O:{format_price(candle['open'])} H:{format_price(candle['high'])} L:{format_price(candle['low'])} C:{format_price(candle['close'])} | V:{format_volume(candle['turnover'])} T:{candle['trades']}"
            self.log_writer.write(f"*{self.symbol_base} {candle_detail}", time_fmt)
        
        # Structure comparison for this candle (ALWAYS log FIRST)
        if config.CANDLE_ANALYZER.get('enable_structure_logging', True):
            analyzer = self._get_candle_analyzer()
            if analyzer:
                analyzer.format_structure_comparison(
                    candle, f"*{self.symbol_base}", time_fmt, self.log_writer
                )
                # Add blank line for readability
                print()
        
        self.entry_candle_count += 1
        
        # Market data
        close = candle['close']
        high = candle['high']
        low = candle['low']
        
        # Calculate PnL
        pnl_percent = ((close - self.entry_price) / self.entry_price) * 100
        
        # Update position PnL
        if self.position_manager:
            self.position_manager.update_pnl(self.symbol_base, '5min', close)
        
        # NEW: Check for danger-sized bearish (add before SL check)
        if config.SELL_MONITOR_5MIN.get('auto_exit_large_bearish', False):
            open_price = float(candle.get('open', 0))
            close_price = float(candle.get('close', 0))
            
            # Only check bearish candles when in minimum profit
            if close_price < open_price:
                min_profit = config.SELL_MONITOR_5MIN.get('exit_min_profit', 0.5)
                
                if pnl_percent >= min_profit:
                    analyzer = self._get_candle_analyzer()
                    if analyzer:
                        threshold = config.SELL_MONITOR_5MIN.get('exit_bearish_threshold', 2.0)
                        bearish_check = analyzer.check_bearish_size(candle, threshold)
                        
                        if bearish_check['is_large']:
                            time_fmt = vienna_str_to_short(candle['timestamp'])
                            danger_msg = f"🔴DANGER BEARISH: {bearish_check['details']} - Auto-exit"
                            print(f"{time_fmt}*{self.symbol_base} {ANSI_CYAN}{danger_msg}{ANSI_RESET}")
                            
                            if self.log_writer:
                                self.log_writer.write(
                                    f"*{self.symbol_base} {danger_msg}",
                                    time_fmt
                                )
                            
                            # Execute sell to protect profit
                            return self._execute_sell(
                                candle,
                                "DANGER_BEARISH",
                                pnl_percent,
                                close_price
                            )
        
        # 1. ALWAYS CHECK STOP LOSS
        if low <= self.sl_price:
            loss_pct = -self.sl_percent_orig
            return self._execute_sell(candle, "STOP_LOSS", loss_pct, self.sl_price)
        
        # 2. CHECK MAX CANDLES TIME LIMIT
        if self.entry_candle_count >= self.max_candles:
            return self._execute_sell(candle, "TIME_LIMIT", pnl_percent, close)
        
        # 3. CHECK FOR REVERSAL PATTERNS (NEW)
        if self.reversal_config['enabled']:
            reversal_check = self._detect_reversal_patterns(candle)
            
            if reversal_check['has_warning']:
                self._log_reversal_warning(candle, reversal_check, pnl_percent)
                
                # Optional: Auto-exit on danger
                if reversal_check['severity'] == 3 and self.reversal_config['auto_exit_on_danger']:
                    return self._execute_sell(candle, "REVERSAL_DETECTED", pnl_percent, close)
                
                # Optional: Reduce TP on warning
                if reversal_check['severity'] >= 2 and self.reversal_config['reduce_tp_on_warning']:
                    if not self.recovery_mode:
                        self._trigger_early_recovery_mode(candle)
        
        # 4. HANDLE RECOVERY MODE - CONFIGURABLE
        if config.SELL_MONITOR_5MIN.get('recovery_mode_enabled', True) and self.recovery_mode:
            # Check for spike (revert to original)
            if pnl_percent >= self.spike_trigger:
                self.recovery_mode = False
                self.tp_price = self.entry_price * (1 + self.tp_percent_orig / 100)
                
                time_fmt = vienna_str_to_short(candle['timestamp'])
                spike_msg = f"🚀SPIKE DETECTED(>{self.spike_trigger}%)!Reverting to Original TP(+{self.tp_percent_orig}%)"
                print(f"{time_fmt}*{self.symbol_base} {ANSI_CYAN}{spike_msg}{ANSI_RESET}")
                if self.log_writer:
                    self.log_writer.write(f"*{self.symbol_base} {spike_msg}", time_fmt)
            
            # Check recovery target
            elif high >= self.tp_price:
                return self._execute_sell(candle, "RECOVERY_TP", self.recovery_tp, self.tp_price)
        
        # 5. HANDLE STANDARD MODE
        if not self.recovery_mode:
            if high >= self.tp_price:
                return self._execute_sell(candle, "TAKE_PROFIT", self.tp_percent_orig, self.tp_price)
        
        # 6. HANDLE STAGNATION TRIGGER - CONFIGURABLE
        if self.entry_candle_count == self.stagnation_candles:
            quick_exit_threshold = config.SELL_MONITOR_5MIN.get('quick_exit_threshold', 0.25)
            
            if config.SELL_MONITOR_5MIN.get('quick_exit_enabled', True) and pnl_percent >= quick_exit_threshold:
                return self._execute_sell(candle, "QUICK_EXIT", pnl_percent, close)
            elif config.SELL_MONITOR_5MIN.get('recovery_mode_enabled', True):
                self.recovery_mode = True
                self.tp_price = self.entry_price * (1 + self.recovery_tp / 100)
                
                time_fmt = vienna_str_to_short(candle['timestamp'])
                stag_msg = f"⚠️C{self.stagnation_candles} STAGNATION.Entering Recovery Mode(Target:+{self.recovery_tp}%)"
                print(f"{time_fmt}*{self.symbol_base} {ANSI_CYAN}{stag_msg}{ANSI_RESET}")
                if self.log_writer:
                    self.log_writer.write(f"*{self.symbol_base} {stag_msg}", time_fmt)
        
        # 7. LOG STATUS
        time_fmt = vienna_str_to_short(candle['timestamp'])
        pnl_str = format_percentage(pnl_percent)
        close_str = format_price(close)
        
        mode_str = "REC" if self.recovery_mode else "STD"
        colored_pnl = format_colored_pnl(pnl_percent, pnl_str)
        
        status_msg = f"{str(self.entry_candle_count).zfill(2)}{colored_pnl}/{close_str}/{mode_str}"
        print(f"{time_fmt}*{self.symbol_base} {status_msg}")
        if self.log_writer:
            self.log_writer.write(f"*{self.symbol_base}{str(self.entry_candle_count).zfill(2)}{pnl_str}/{close_str}/{mode_str}", time_fmt)
        
        # Store candle for next iteration
        self.prev_candle = candle
        
        return None
    
    def _execute_sell(self, candle: Dict, reason: str, pnl_percent: float, price: float) -> str:
        """Execute the sell and log results"""
        # Dynamic reason codes based on config
        reason_codes = {
            "TAKE_PROFIT": "TP",
            "STOP_LOSS": "SL",
            "QUICK_EXIT": f"C{self.stagnation_candles}",
            "RECOVERY_TP": "RTP",
            "TIME_LIMIT": f"C{self.max_candles}",
            "DANGER_BEARISH": "DBEAR",
            "REVERSAL_DETECTED": "REV"
        }
        short_reason = reason_codes.get(reason, reason)
        
        time_fmt = vienna_str_to_short(candle['timestamp'])
        
        # Calculate commission and net PnL
        commission_data = self._calculate_commission(self.entry_price, price)
        gross_pnl = commission_data['gross_pnl_percent']
        net_pnl = commission_data['net_pnl_percent']
        total_commission = commission_data['total_commission_percent']
        
        # Use NET PnL for win/loss determination
        color = ANSI_GREEN if net_pnl >= 0 else ANSI_RED
        icon = "✅" if net_pnl >= 0 else "❌"
        
        pnl_str = format_percentage(pnl_percent)
        net_pnl_str = format_percentage(net_pnl)
        price_str = format_price(price)
        
        # Store trade result (use net PnL)
        self.trade_result = net_pnl
        self.exit_price = price
        self.exit_reason = short_reason
        self.exit_time = time_fmt
        
        # Save to completed trades history with commission details
        trade_summary = {
            'symbol': self.symbol_base,
            'entry_time': self.entry_time,
            'exit_time': time_fmt,
            'entry_price': self.entry_price,
            'exit_price': price,
            'exit_reason': short_reason,
            'gross_pnl_percent': gross_pnl,
            'commission_percent': total_commission,
            'net_pnl_percent': net_pnl,
            'pnl_percent': net_pnl,  # Keep for backward compatibility (now shows net)
            'candle_count': self.entry_candle_count,
            'pattern_gain_percent': self.pattern_gain,
            'pattern_volume': self.pattern_volume,
            'pattern_trades': self.pattern_trades,
            'beauty_score': self.pattern_beauty
        }
        self.completed_trades.append(trade_summary)
        
        # Log sell with both gross and net PnL
        colored_icon_pnl = f"{color}{icon}{short_reason}{net_pnl_str}{ANSI_RESET}"
        sell_msg = f"{str(self.entry_candle_count).zfill(2)}{colored_icon_pnl}@{price_str}"
        
        # Add commission info to console output
        commission_info = f"(Gross:{pnl_str} Fee:-{format_percentage(total_commission)})"
        print(f"{time_fmt}*{self.symbol_base} {sell_msg} {commission_info}")
        
        if self.log_writer:
            self.log_writer.write(
                f"*{self.symbol_base}{str(self.entry_candle_count).zfill(2)}{icon}{short_reason}"
                f" Gross:{pnl_str} Fee:-{format_percentage(total_commission)} Net:{net_pnl_str}@{price_str}",
                time_fmt
            )
        
        # Release position
        if self.position_manager:
            self.position_manager.remove_position(self.symbol_base, '5min')
        
        # Start cooldown
        if self.cooldown_tracker and config.TRADING['cooldown_enabled']:
            self.cooldown_tracker.start_cooldown(self.symbol_base, '5min')
            cooldown_candles = config.TRADING['cooldown_5min_candles']
            cooldown_msg = f"⏸️ COOLDOWN: {cooldown_candles} candle{'s' if cooldown_candles > 1 else ''}"
            print(f"{time_fmt}*{self.symbol_base} {cooldown_msg}")
            if self.log_writer:
                self.log_writer.write(f"*{self.symbol_base} {cooldown_msg}", time_fmt)
        
        self._stop_monitoring()
        return reason
    
    def get_trade_summary(self) -> List[Dict]:
        """
        Get all trade summaries for reporting
        
        Returns:
            List of trade summary dicts (may be empty)
        """
        return self.completed_trades
    
    def _detect_reversal_patterns(self, candle: Dict) -> Dict:
        """
        Detect downward reversal patterns
        
        Returns:
            {
                'has_warning': bool,
                'pattern': str,
                'severity': int,  # 1=caution ⚠️, 2=warning 🔶, 3=danger 🔴
                'details': str
            }
        """
        result = {
            'has_warning': False,
            'pattern': None,
            'severity': 0,
            'details': ''
        }
        
        # Calculate candle metrics
        body_size = abs(candle['close'] - candle['open'])
        is_bearish = candle['close'] < candle['open']
        is_bullish = candle['close'] >= candle['open']
        
        if body_size == 0:
            body_size = 0.0001  # Prevent division by zero
        
        upper_wick = candle['high'] - max(candle['close'], candle['open'])
        lower_wick = min(candle['close'], candle['open']) - candle['low']
        body_percent = (body_size / candle['open']) * 100 if candle['open'] > 0 else 0
        
        # Priority 1: Bearish Marubozu (Highest priority)
        if self.reversal_config['bearish_marubozu_enabled'] and is_bearish:
            check = self._check_bearish_marubozu(candle, body_size, upper_wick, lower_wick, body_percent)
            if check['detected']:
                result.update({
                    'has_warning': True,
                    'pattern': 'BEAR_MARU',
                    'severity': 3,
                    'details': check['details']
                })
                return result
        
        # Priority 2: Gravestone Doji
        if self.reversal_config['gravestone_enabled']:
            check = self._check_gravestone_doji(body_size, upper_wick, lower_wick, body_percent)
            if check['detected']:
                result.update({
                    'has_warning': True,
                    'pattern': 'GRAVESTONE',
                    'severity': 3,
                    'details': check['details']
                })
                return result
        
        # Priority 3: Shooting Star
        if self.reversal_config['shooting_star_enabled'] and is_bullish:
            check = self._check_shooting_star(body_size, upper_wick, lower_wick)
            if check['detected']:
                severity = 3 if check['ratio'] >= self.reversal_config['shooting_star_danger_ratio'] else 1
                result.update({
                    'has_warning': True,
                    'pattern': 'SHOOT_STAR',
                    'severity': severity,
                    'details': check['details']
                })
                return result
        
        # Priority 4: Bearish Engulfing (requires prev_candle)
        if self.reversal_config['bearish_engulfing_enabled'] and self.prev_candle and is_bearish:
            check = self._check_bearish_engulfing(candle, self.prev_candle, body_size)
            if check['detected']:
                result.update({
                    'has_warning': True,
                    'pattern': 'BEAR_ENG',
                    'severity': 2,
                    'details': check['details']
                })
                return result
        
        # Priority 5: High Wave Doji (with graduated severity)
        if self.reversal_config['high_wave_enabled']:
            check = self._check_high_wave_doji(body_size, upper_wick, lower_wick, body_percent)
            if check['detected']:
                result.update({
                    'has_warning': True,
                    'pattern': 'HIGH_WAVE',
                    'severity': check['severity'],  # Now returns graduated severity
                    'details': check['details']
                })
                return result
        
        # Priority 6: Dark Cloud Cover (requires prev_candle)
        if self.reversal_config['dark_cloud_enabled'] and self.prev_candle and is_bearish:
            check = self._check_dark_cloud(candle, self.prev_candle)
            if check['detected']:
                result.update({
                    'has_warning': True,
                    'pattern': 'DARK_CLOUD',
                    'severity': 2,
                    'details': check['details']
                })
                return result
        
        # Priority 7: Hammer (potential reversal after gains)
        if self.reversal_config['hammer_enabled'] and is_bullish:
            pnl_percent = ((candle['close'] - self.entry_price) / self.entry_price) * 100
            if pnl_percent >= self.reversal_config['hammer_min_profit_threshold']:
                check = self._check_hammer(body_size, upper_wick, lower_wick)
                if check['detected']:
                    result.update({
                        'has_warning': True,
                        'pattern': 'HAMMER',
                        'severity': 1,
                        'details': check['details']
                    })
                    return result
        
        return result
    
    def _check_bearish_marubozu(self, candle: Dict, body_size: float, 
                                upper_wick: float, lower_wick: float, body_percent: float) -> Dict:
        """Check for bearish marubozu pattern"""
        loss_percent = ((candle['close'] - candle['open']) / candle['open']) * 100
        min_loss = self.reversal_config['bearish_marubozu_min_loss']
        
        # Check loss threshold
        if loss_percent > -min_loss:
            return {'detected': False}
        
        # Check upper wick tolerance
        upper_wick_ratio = upper_wick / body_size if body_size > 0 else 0
        if upper_wick_ratio > self.reversal_config['bearish_marubozu_upper_wick_tolerance']:
            return {'detected': False}
        
        # Check no lower wick
        if self.reversal_config['bearish_marubozu_no_lower_wick'] and lower_wick > 0.0001:
            return {'detected': False}
        
        return {
            'detected': True,
            'details': f'loss:{abs(loss_percent):.2f}%'
        }
    
    def _check_gravestone_doji(self, body_size: float, upper_wick: float, 
                               lower_wick: float, body_percent: float) -> Dict:
        """Check for gravestone doji pattern"""
        # Small body
        if body_percent > self.reversal_config['gravestone_body_percent']:
            return {'detected': False}
        
        # Long upper wick
        wick_ratio = upper_wick / body_size if body_size > 0 else 999
        if wick_ratio < self.reversal_config['gravestone_min_wick_ratio']:
            return {'detected': False}
        
        # Minimal lower wick
        lower_ratio = lower_wick / body_size if body_size > 0 else 0
        if lower_ratio > self.reversal_config['gravestone_max_lower_wick_ratio']:
            return {'detected': False}
        
        return {
            'detected': True,
            'details': f'wick:{wick_ratio:.1f}x'
        }
    
    def _check_shooting_star(self, body_size: float, upper_wick: float, lower_wick: float) -> Dict:
        """Check for shooting star pattern"""
        wick_ratio = upper_wick / body_size if body_size > 0 else 0
        lower_ratio = lower_wick / body_size if body_size > 0 else 0
        
        # Upper wick must be significant
        if wick_ratio < self.reversal_config['shooting_star_min_wick_ratio']:
            return {'detected': False}
        
        # Lower wick should be small
        if lower_ratio > self.reversal_config['shooting_star_max_lower_wick_ratio']:
            return {'detected': False}
        
        return {
            'detected': True,
            'ratio': wick_ratio,
            'details': f'wick:{wick_ratio:.1f}x'
        }
    
    def _check_bearish_engulfing(self, candle: Dict, prev_candle: Dict, body_size: float) -> Dict:
        """Check for bearish engulfing pattern"""
        prev_body_size = abs(prev_candle['close'] - prev_candle['open'])
        
        # Current must open above prev close
        if candle['open'] <= prev_candle['close']:
            return {'detected': False}
        
        # Current must close below prev open
        if candle['close'] >= prev_candle['open']:
            return {'detected': False}
        
        # Check body ratio
        body_ratio = body_size / prev_body_size if prev_body_size > 0 else 0
        if body_ratio < self.reversal_config['bearish_engulfing_min_body_ratio']:
            return {'detected': False}
        
        return {
            'detected': True,
            'details': f'ratio:{body_ratio:.1f}x'
        }
    
    def _check_high_wave_doji(self, body_size: float, upper_wick: float, 
                             lower_wick: float, body_percent: float) -> Dict:
        """
        Check for high wave doji (exhaustion) with graduated severity
        
        Severity levels:
        - 1 (caution): 2x-4x ratio
        - 2 (danger): 4x-6x ratio
        - 3 (abort): >6x ratio
        """
        # Small body
        if body_percent > self.reversal_config['high_wave_body_percent']:
            return {'detected': False}
        
        # Both wicks must be significant
        upper_ratio = upper_wick / body_size if body_size > 0 else 999
        lower_ratio = lower_wick / body_size if body_size > 0 else 999
        
        # Use minimum of both wicks for severity calculation
        min_wick_ratio = min(upper_ratio, lower_ratio)
        
        # Check if meets minimum threshold (severity 1)
        severity1_threshold = self.reversal_config.get('high_wave_severity1_ratio', 2.0)
        if min_wick_ratio < severity1_threshold:
            return {'detected': False}
        
        # Determine severity based on wick ratios
        severity2_threshold = self.reversal_config.get('high_wave_severity2_ratio', 4.0)
        severity3_threshold = self.reversal_config.get('high_wave_severity3_ratio', 6.0)
        
        if min_wick_ratio >= severity3_threshold:
            severity = 3  # Abort
        elif min_wick_ratio >= severity2_threshold:
            severity = 2  # Danger
        else:
            severity = 1  # Caution
        
        return {
            'detected': True,
            'severity': severity,
            'details': f'U:{upper_ratio:.1f}x,L:{lower_ratio:.1f}x'
        }
    
    def _check_dark_cloud(self, candle: Dict, prev_candle: Dict) -> Dict:
        """Check for dark cloud cover pattern"""
        # Must gap up above prev high
        if candle['open'] <= prev_candle['high']:
            return {'detected': False}
        
        # Must close below midpoint of prev candle
        prev_midpoint = (prev_candle['open'] + prev_candle['close']) / 2
        if candle['close'] >= prev_midpoint:
            return {'detected': False}
        
        # Calculate penetration
        prev_body = abs(prev_candle['close'] - prev_candle['open'])
        penetration = (prev_candle['close'] - candle['close']) / prev_body if prev_body > 0 else 0
        
        if penetration < self.reversal_config['dark_cloud_min_penetration']:
            return {'detected': False}
        
        return {
            'detected': True,
            'details': f'pen:{penetration:.1f}x'
        }
    
    def _check_hammer(self, body_size: float, upper_wick: float, lower_wick: float) -> Dict:
        """Check for hammer pattern (potential reversal after gains)"""
        lower_ratio = lower_wick / body_size if body_size > 0 else 0
        upper_ratio = upper_wick / body_size if body_size > 0 else 0
        
        # Long lower wick
        if lower_ratio < self.reversal_config['hammer_min_lower_wick_ratio']:
            return {'detected': False}
        
        # Small upper wick
        if upper_ratio > self.reversal_config['hammer_max_upper_wick_ratio']:
            return {'detected': False}
        
        return {
            'detected': True,
            'details': f'L-wick:{lower_ratio:.1f}x'
        }
    
    def _log_reversal_warning(self, candle: Dict, reversal_check: Dict, pnl_percent: float):
        """Log reversal warning with proper formatting"""
        pattern = reversal_check['pattern']
        
        # Check cooldown
        cooldown = self.reversal_config['warning_cooldown_candles']
        if pattern in self.warning_history:
            last_candle = self.warning_history[pattern]
            if self.entry_candle_count - last_candle < cooldown:
                return  # Skip duplicate warnings
        
        # Update warning history
        self.warning_history[pattern] = self.entry_candle_count
        
        # Severity icons
        severity_icons = {
            1: '⚠️',
            2: '🔶',
            3: '🔴'
        }
        icon = severity_icons.get(reversal_check['severity'], '⚠️')
        
        # Format warning
        time_fmt = vienna_str_to_short(candle['timestamp'])
        pnl_str = format_percentage(pnl_percent)
        close_str = format_price(candle['close'])
        mode_str = "REC" if self.recovery_mode else "STD"
        colored_pnl = format_colored_pnl(pnl_percent, pnl_str)
        
        # Build status with warning
        status_msg = f"{str(self.entry_candle_count).zfill(2)}{colored_pnl}/{close_str}/{mode_str} {icon}{pattern}({reversal_check['details']})"
        
        print(f"{time_fmt}*{self.symbol_base} {status_msg}")
        if self.log_writer:
            self.log_writer.write(f"*{self.symbol_base}{str(self.entry_candle_count).zfill(2)}{pnl_str}/{close_str}/{mode_str} {icon}{pattern}({reversal_check['details']})", time_fmt)
    
    def _trigger_early_recovery_mode(self, candle: Dict):
        """Trigger recovery mode early due to warning"""
        if self.recovery_mode:
            return  # Already in recovery
        
        self.recovery_mode = True
        self.tp_price = self.entry_price * (1 + self.recovery_tp / 100)
        
        time_fmt = vienna_str_to_short(candle['timestamp'])
        warning_msg = f"⚠️REVERSAL WARNING.Entering Recovery Mode(Target:+0.25%)"
        print(f"{time_fmt}*{self.symbol_base} {ANSI_CYAN}{warning_msg}{ANSI_RESET}")
        if self.log_writer:
            self.log_writer.write(f"*{self.symbol_base} {warning_msg}", time_fmt)
    
    def _stop_monitoring(self):
        """Stop monitoring"""
        self.is_monitoring = False
        end_msg = f"🛑SELL MONITORING ENDED"
        print("=" * 25)
        print(end_msg)
        print("=" * 25)
        if self.log_writer:
            self.log_writer.write_separator(25)
            self.log_writer.write_raw(end_msg)
            self.log_writer.write_separator(25)
