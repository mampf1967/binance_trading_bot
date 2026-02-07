"""
candle_size_analyzer.py - Historical Context for Pattern Quality

CALCULATION RULES:
- AB (Body %): Calculated as % of Open (can be +/-)
- AH, AL, AT: Calculated as % of |Body| (always positive)
- DOJI (Open == Close): Uses Total Range as basis for wicks

VERSION: Final - Percentage-based structure comparison
MAJOR REWRITE: format_structure_comparison() now outputs clean 4-line percentage format

NEW OUTPUT FORMAT:
    C:    AB:+0.87% / AH:+4.55% / AL:+0.00% / AT:+104.55%
    ABuC: AB:+0.12% / AH:+41.67% / AL:+41.67% / AT:+183.33%
    ABeC: AB:-0.15% / AH:+33.33% / AL:+33.33% / AT:+166.67%
    AC:   AB:-0.02% / AH:+37.50% / AL:+37.50% / AT:+175.00%

LEGEND:
    C    = Current Candle
    ABuC = Average Bullish Candle
    ABeC = Average Bearish Candle
    AC   = Average Candle (combined)
    
    AB = Body % (of Open price)
    AH = Upper Wick % (of Body)
    AL = Lower Wick % (of Body)
    AT = Total Range % (of Body)

SPECIAL DOJI HANDLING:
    When Open == Close:
    - AB displays as "DOJI"
    - AH, AL, AT calculated as % of Total Range
    - Special messages for edge cases:
      * "DOJI NO WICKS" (total range = 0)
      * "DOJI NO UPPER WICK" (upper wick = 0)
      * "DOJI NO LOWER WICK" (lower wick = 0)
"""

import time
from typing import Dict, List, Optional


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


class CandleSizeAnalyzer:
    """Analyzes candle sizes and structure in historical context"""
    
    def __init__(self, database, lookback_config: Optional[Dict] = None):
        """
        Initialize the analyzer
        
        Args:
            database: Database instance with get_recent_candles() method
            lookback_config: Dictionary containing lookback settings.
                Expected keys:
                - 'bullish_lookback_candles': int (default 50)
                - 'bearish_lookback_candles': int (default 50)
                - 'general_lookback_candles': int (default 100)
        """
        self.db = database
        
        # Handle both old and new style config
        if lookback_config is None:
            self.lookback = 50
            self.config = {
                'bullish_lookback_candles': 50,
                'bearish_lookback_candles': 50,
                'general_lookback_candles': 50
            }
            self._is_legacy_mode = True
        elif isinstance(lookback_config, dict):
            self.config = lookback_config
            self.lookback = max(
                lookback_config.get('bullish_lookback_candles', 50),
                lookback_config.get('bearish_lookback_candles', 50),
                lookback_config.get('general_lookback_candles', 50)
            )
            self._is_legacy_mode = False
        elif isinstance(lookback_config, int):
            self.lookback = lookback_config
            self.config = {
                'bullish_lookback_candles': lookback_config,
                'bearish_lookback_candles': lookback_config,
                'general_lookback_candles': lookback_config
            }
            self._is_legacy_mode = True
        else:
            self.lookback = 50
            self.config = {
                'bullish_lookback_candles': 50,
                'bearish_lookback_candles': 50,
                'general_lookback_candles': 50
            }
            self._is_legacy_mode = True
        
        self._cache = {}
        self._cache_time = 0
        self._cache_duration = 60
    
    def _get_candle_stats(self, candles: List[Dict]) -> Dict:
        """Calculate average statistics for a list of candles."""
        count = len(candles)
        if count == 0:
            return {
                'avg_open': 0.0, 'avg_high': 0.0, 'avg_low': 0.0, 'avg_close': 0.0,
                'avg_body_size': 0.0, 'avg_total_range': 0.0, 
                'avg_top_wick_size': 0.0, 'avg_bottom_wick_size': 0.0,
                'count': 0
            }

        stats = {
            'sum_open': 0.0, 'sum_high': 0.0, 'sum_low': 0.0, 'sum_close': 0.0,
            'sum_body_size': 0.0, 'sum_total_range': 0.0, 
            'sum_top_wick_size': 0.0, 'sum_bottom_wick_size': 0.0,
        }

        for candle in candles:
            body_size = abs(candle['close'] - candle['open'])
            
            if candle['close'] > candle['open']:
                top_wick = candle['high'] - candle['close']
                bottom_wick = candle['open'] - candle['low']
            else:
                top_wick = candle['high'] - candle['open']
                bottom_wick = candle['close'] - candle['low']

            stats['sum_open'] += candle['open']
            stats['sum_high'] += candle['high']
            stats['sum_low'] += candle['low']
            stats['sum_close'] += candle['close']
            stats['sum_body_size'] += body_size
            stats['sum_total_range'] += (candle['high'] - candle['low'])
            stats['sum_top_wick_size'] += top_wick
            stats['sum_bottom_wick_size'] += bottom_wick

        return {
            'avg_open': stats['sum_open'] / count,
            'avg_high': stats['sum_high'] / count,
            'avg_low': stats['sum_low'] / count,
            'avg_close': stats['sum_close'] / count,
            'avg_body_size': stats['sum_body_size'] / count,
            'avg_total_range': stats['sum_total_range'] / count,
            'avg_top_wick_size': stats['sum_top_wick_size'] / count,
            'avg_bottom_wick_size': stats['sum_bottom_wick_size'] / count,
            'count': count
        }

    def get_historical_averages(self, force_refresh: bool = False) -> Dict:
        """Get average bullish and bearish candle statistics"""
        current_time = time.time()
        if not force_refresh and self._cache and (current_time - self._cache_time < self._cache_duration):
            return self._cache
        
        if self._is_legacy_mode:
            return self._get_legacy_averages(current_time)
        else:
            return self._get_enhanced_averages(current_time)
    
    def _get_legacy_averages(self, current_time: float) -> Dict:
        """Legacy method for backward compatibility"""
        candles = self.db.get_recent_candles(self.lookback * 3)
        
        if not candles:
            result = {
                'avg_bullish': 0,
                'avg_bearish': 0,
                'bullish_count': 0,
                'bearish_count': 0,
                'timestamp': current_time
            }
            self._cache = result
            self._cache_time = current_time
            return result
        
        bullish_bodies = []
        bearish_bodies = []
        
        for candle in candles:
            open_price = float(candle.get('open', 0))
            close_price = float(candle.get('close', 0))
            body_size = abs(close_price - open_price)
            
            if close_price >= open_price:
                bullish_bodies.append(body_size)
            else:
                bearish_bodies.append(body_size)
            
            if len(bullish_bodies) >= self.lookback and len(bearish_bodies) >= self.lookback:
                break
        
        bullish_subset = bullish_bodies[:self.lookback]
        bearish_subset = bearish_bodies[:self.lookback]
        
        result = {
            'avg_bullish': sum(bullish_subset) / len(bullish_subset) if bullish_subset else 0,
            'avg_bearish': sum(bearish_subset) / len(bearish_subset) if bearish_subset else 0,
            'bullish_count': len(bullish_subset),
            'bearish_count': len(bearish_subset),
            'timestamp': current_time
        }
        
        self._cache = result
        self._cache_time = current_time
        
        return result
    
    def _get_enhanced_averages(self, current_time: float) -> Dict:
        """Enhanced method with 8 metrics for each candle type"""
        bull_lb = self.config.get('bullish_lookback_candles', 50)
        bear_lb = self.config.get('bearish_lookback_candles', 50)
        gen_lb = self.config.get('general_lookback_candles', 50)
        
        max_lookback = max(bull_lb, bear_lb, gen_lb) * 2

        all_candles = self.db.get_recent_candles(max_lookback)
        
        bullish_candles = [c for c in all_candles if c['close'] > c['open']][:bull_lb]
        bearish_candles = [c for c in all_candles if c['open'] > c['close']][:bear_lb]
        
        bullish_stats = self._get_candle_stats(bullish_candles)
        bearish_stats = self._get_candle_stats(bearish_candles)
        general_stats = self._get_candle_stats(all_candles[:gen_lb])

        result = {
            'bullish': bullish_stats,
            'bearish': bearish_stats,
            'general': general_stats,
            'timestamp': current_time
        }
        self._cache = result
        self._cache_time = current_time
        return result
    
    def check_pattern_size(self, pattern_candles: List[Dict], min_ratio: float = 1.2) -> Dict:
        """Check if pattern candles are significant vs historical average"""
        if self._is_legacy_mode:
            history = self.get_historical_averages()
            avg_bullish = history['avg_bullish']
        else:
            history = self.get_historical_averages()
            avg_bullish = history['bullish']['avg_body_size']
        
        if avg_bullish == 0:
            return {
                'passed': True,
                'ratio': 0,
                'pattern_avg': 0,
                'historical_avg': 0,
                'details': 'insufficient_history'
            }
        
        pattern_bodies = []
        for candle in pattern_candles:
            open_price = float(candle.get('open', 0))
            close_price = float(candle.get('close', 0))
            body_size = abs(close_price - open_price)
            pattern_bodies.append(body_size)
        
        if not pattern_bodies:
            return {
                'passed': False,
                'ratio': 0,
                'pattern_avg': 0,
                'historical_avg': avg_bullish,
                'details': 'no_pattern_candles'
            }
        
        pattern_avg = sum(pattern_bodies) / len(pattern_bodies)
        ratio = pattern_avg / avg_bullish
        passed = ratio >= min_ratio
        
        return {
            'passed': passed,
            'ratio': ratio,
            'pattern_avg': pattern_avg,
            'historical_avg': avg_bullish,
            'details': f'ratio={ratio:.2f}x (need {min_ratio:.2f}x)'
        }
    
    def check_bearish_size(self, candle: Dict, threshold: float = 1.5) -> Dict:
        """Check if a bearish candle is unusually large"""
        open_price = float(candle.get('open', 0))
        close_price = float(candle.get('close', 0))
        
        if close_price >= open_price:
            return {
                'is_large': False,
                'ratio': 0,
                'body_size': 0,
                'avg_bearish': 0,
                'details': 'not_bearish'
            }
        
        if self._is_legacy_mode:
            history = self.get_historical_averages()
            avg_bearish = history['avg_bearish']
        else:
            history = self.get_historical_averages()
            avg_bearish = history['bearish']['avg_body_size']
        
        if avg_bearish == 0:
            return {
                'is_large': False,
                'ratio': 0,
                'body_size': 0,
                'avg_bearish': 0,
                'details': 'insufficient_history'
            }
        
        body_size = abs(close_price - open_price)
        ratio = body_size / avg_bearish
        is_large = ratio >= threshold
        
        return {
            'is_large': is_large,
            'ratio': ratio,
            'body_size': body_size,
            'avg_bearish': avg_bearish,
            'details': f'{ratio:.2f}x avg (threshold {threshold:.2f}x)'
        }
    
    def check_bullish_size(self, candle: Dict, min_ratio: float = 0.8) -> Dict:
        """Check if a bullish candle is strong enough"""
        open_price = float(candle.get('open', 0))
        close_price = float(candle.get('close', 0))
        
        if close_price < open_price:
            return {
                'is_strong': False,
                'ratio': 0,
                'body_size': 0,
                'avg_bullish': 0,
                'details': 'not_bullish'
            }
        
        if self._is_legacy_mode:
            history = self.get_historical_averages()
            avg_bullish = history['avg_bullish']
        else:
            history = self.get_historical_averages()
            avg_bullish = history['bullish']['avg_body_size']
        
        if avg_bullish == 0:
            return {
                'is_strong': True,
                'ratio': 0,
                'body_size': 0,
                'avg_bullish': 0,
                'details': 'insufficient_history'
            }
        
        body_size = abs(close_price - open_price)
        ratio = body_size / avg_bullish
        is_strong = ratio >= min_ratio
        
        return {
            'is_strong': is_strong,
            'ratio': ratio,
            'body_size': body_size,
            'avg_bullish': avg_bullish,
            'details': f'{ratio:.2f}x avg (need {min_ratio:.2f}x)'
        }
    
    def calculate_adaptive_stop_loss(self, entry_price: float, 
                                     multiplier: float = 2.0,
                                     min_percent: float = 2.0,
                                     max_percent: float = 5.0) -> Dict:
        """Calculate adaptive stop loss based on typical bearish size"""
        if self._is_legacy_mode:
            history = self.get_historical_averages()
            avg_bearish = history['avg_bearish']
        else:
            history = self.get_historical_averages()
            avg_bearish = history['bearish']['avg_body_size']
        
        if avg_bearish == 0 or entry_price == 0:
            sl_percent = min_percent
            sl_price = entry_price * (1 - sl_percent / 100)
            return {
                'sl_price': sl_price,
                'sl_percent': sl_percent,
                'raw_percent': 0,
                'avg_bearish': 0,
                'details': f'insufficient_history_using_min_{min_percent}%'
            }
        
        avg_bearish_percent = (avg_bearish / entry_price) * 100
        raw_sl_percent = avg_bearish_percent * multiplier
        
        sl_percent = max(min_percent, min(raw_sl_percent, max_percent))
        sl_price = entry_price * (1 - sl_percent / 100)
        
        return {
            'sl_price': sl_price,
            'sl_percent': sl_percent,
            'raw_percent': raw_sl_percent,
            'avg_bearish': avg_bearish,
            'details': f'{sl_percent:.2f}% (raw={raw_sl_percent:.2f}%, bounded {min_percent}-{max_percent}%)'
        }
    
    def get_statistics_summary(self) -> str:
        """Get a human-readable summary of current statistics"""
        history = self.get_historical_averages()
        
        if self._is_legacy_mode:
            if history['avg_bullish'] == 0:
                return "Candle Size Statistics: No historical data available"
            
            volatility_ratio = history['avg_bearish'] / history['avg_bullish'] if history['avg_bullish'] > 0 else 0
            
            summary = f"""Candle Size Statistics (last {self.lookback} of each type):
  Avg Bullish Body: ${history['avg_bullish']:.2f} (n={history['bullish_count']})
  Avg Bearish Body: ${history['avg_bearish']:.2f} (n={history['bearish_count']})
  Bearish/Bullish Ratio: {volatility_ratio:.2f}x
  Cache Age: {time.time() - history['timestamp']:.0f}s"""
            
            return summary
        else:
            bull_stats = history['bullish']
            bear_stats = history['bearish']
            
            if bull_stats['count'] == 0 and bear_stats['count'] == 0:
                return "Candle Size Statistics: No historical data available"
            
            volatility_ratio = bear_stats['avg_body_size'] / bull_stats['avg_body_size'] if bull_stats['avg_body_size'] > 0 else 0
            
            summary = f"""Candle Size Statistics (Bull={bull_stats['count']}, Bear={bear_stats['count']}):
  Avg Bullish Body: ${bull_stats['avg_body_size']:.4f} (Avg Range: ${bull_stats['avg_total_range']:.4f})
  Avg Bearish Body: ${bear_stats['avg_body_size']:.4f} (Avg Range: ${bear_stats['avg_total_range']:.4f})
  Bear/Bull Body Ratio: {volatility_ratio:.2f}"""
            
            return summary
    
    def format_structure_comparison(self, candle: Dict, symbol: str, timestamp: str, log_writer) -> None:
        """
        Format and log 4-line percentage-based comparison
        
        NEW FORMAT (Version 2.0):
        - AB (Body %): ((Close - Open) / Open) * 100 ← Can be +/- based on Open price
        - AH (Upper Wick %): (Upper_Wick / |Body|) * 100 ← Always positive, based on Body
        - AL (Lower Wick %): (Lower_Wick / |Body|) * 100 ← Always positive, based on Body
        - AT (Total Range %): (Total_Range / |Body|) * 100 ← Always positive, based on Body
        
        DOJI Handling (Open == Close):
        - AB = "DOJI"
        - AH, AL, AT calculated as % of Total Range
        - Special cases: "DOJI NO WICKS", "DOJI NO UPPER WICK", "DOJI NO LOWER WICK"
        
        OUTPUT FORMAT:
            C:    AB:+0.87% / AH:+4.55% / AL:+0.00% / AT:+104.55%
            ABuC: AB:+0.12% / AH:+41.67% / AL:+41.67% / AT:+183.33%
            ABeC: AB:-0.15% / AH:+33.33% / AL:+33.33% / AT:+166.67%
            AC:   AB:-0.02% / AH:+37.50% / AL:+37.50% / AT:+175.00%
        """
        history = self.get_historical_averages()
        
        open_price = candle['open']
        high_price = candle['high']
        low_price = candle['low']
        close_price = candle['close']
        
        if open_price == 0:
            open_price = 0.0001
        
        body_dollars = close_price - open_price
        total_range = high_price - low_price
        
        is_doji = (open_price == close_price)
        is_bullish = close_price > open_price
        
        if is_bullish:
            upper_wick = high_price - close_price
            lower_wick = open_price - low_price
        else:
            upper_wick = high_price - open_price
            lower_wick = close_price - low_price
        
        # ============================================================
        # CURRENT CANDLE (C)
        # ============================================================
        
        if is_doji:
            ab_str = "DOJI"
            
            if total_range == 0:
                c_line = f"  C:    AB:DOJI / DOJI NO WICKS"
                log_writer.write(f"{symbol} {c_line}", timestamp)
            else:
                ah_pct = (upper_wick / total_range) * 100
                al_pct = (lower_wick / total_range) * 100
                at_pct = 100.0
                
                if upper_wick == 0:
                    ah_str = "DOJI NO UPPER WICK"
                else:
                    ah_str = format_percentage(ah_pct, 2)
                
                if lower_wick == 0:
                    al_str = "DOJI NO LOWER WICK"
                else:
                    al_str = format_percentage(al_pct, 2)
                
                c_line = f"  C:    AB:DOJI / AH:{ah_str} / AL:{al_str} / AT:{format_percentage(at_pct, 2)}"
                log_writer.write(f"{symbol} {c_line}", timestamp)
        else:
            ab_pct = (body_dollars / open_price) * 100
            
            body_abs = abs(body_dollars)
            if body_abs == 0:
                body_abs = 0.0001
            
            ah_pct = (upper_wick / body_abs) * 100
            al_pct = (lower_wick / body_abs) * 100
            at_pct = (total_range / body_abs) * 100
            
            c_line = (
                f"  C:    "
                f"AB:{format_percentage(ab_pct, 2)} / "
                f"AH:{format_percentage(ah_pct, 2)} / "
                f"AL:{format_percentage(al_pct, 2)} / "
                f"AT:{format_percentage(at_pct, 2)}"
            )
            log_writer.write(f"{symbol} {c_line}", timestamp)
        
        # ============================================================
        # HISTORICAL AVERAGES (ABuC, ABeC, AC)
        # ============================================================
        
        if self._is_legacy_mode:
            abuc_line = f"  ABuC: [Legacy mode - limited data]"
            abec_line = f"  ABeC: [Legacy mode - limited data]"
            ac_line = f"  AC:   [Legacy mode - limited data]"
            
            log_writer.write(f"{symbol} {abuc_line}", timestamp)
            log_writer.write(f"{symbol} {abec_line}", timestamp)
            log_writer.write(f"{symbol} {ac_line}", timestamp)
            return
        
        bull_stats = history['bullish']
        bear_stats = history['bearish']
        
        if bull_stats['count'] == 0 or bear_stats['count'] == 0:
            abuc_line = f"  ABuC: [Insufficient data]"
            abec_line = f"  ABeC: [Insufficient data]"
            ac_line = f"  AC:   [Insufficient data]"
            
            log_writer.write(f"{symbol} {abuc_line}", timestamp)
            log_writer.write(f"{symbol} {abec_line}", timestamp)
            log_writer.write(f"{symbol} {ac_line}", timestamp)
            return
        
        # ABuC (Average Bullish Candle)
        bull_open = bull_stats['avg_open']
        if bull_open == 0:
            bull_open = 0.0001
        
        bull_body = bull_stats['avg_body_size']
        if bull_body == 0:
            bull_body = 0.0001
        
        abuc_ab_pct = (bull_body / bull_open) * 100
        abuc_ah_pct = (bull_stats['avg_top_wick_size'] / bull_body) * 100
        abuc_al_pct = (bull_stats['avg_bottom_wick_size'] / bull_body) * 100
        abuc_at_pct = (bull_stats['avg_total_range'] / bull_body) * 100
        
        abuc_line = (
            f"  ABuC: "
            f"AB:{format_percentage(abuc_ab_pct, 2)} / "
            f"AH:{format_percentage(abuc_ah_pct, 2)} / "
            f"AL:{format_percentage(abuc_al_pct, 2)} / "
            f"AT:{format_percentage(abuc_at_pct, 2)}"
        )
        
        # ABeC (Average Bearish Candle)
        bear_open = bear_stats['avg_open']
        if bear_open == 0:
            bear_open = 0.0001
        
        bear_body = bear_stats['avg_body_size']
        if bear_body == 0:
            bear_body = 0.0001
        
        abec_ab_pct = -(bear_body / bear_open) * 100
        abec_ah_pct = (bear_stats['avg_top_wick_size'] / bear_body) * 100
        abec_al_pct = (bear_stats['avg_bottom_wick_size'] / bear_body) * 100
        abec_at_pct = (bear_stats['avg_total_range'] / bear_body) * 100
        
        abec_line = (
            f"  ABeC: "
            f"AB:{format_percentage(abec_ab_pct, 2)} / "
            f"AH:{format_percentage(abec_ah_pct, 2)} / "
            f"AL:{format_percentage(abec_al_pct, 2)} / "
            f"AT:{format_percentage(abec_at_pct, 2)}"
        )
        
        # AC (Average Candle)
        ac_ab_pct = (abuc_ab_pct + abec_ab_pct) / 2
        
        ac_body = (bull_stats['avg_body_size'] + bear_stats['avg_body_size']) / 2
        if ac_body == 0:
            ac_body = 0.0001
        
        ac_upper_dollars = (bull_stats['avg_top_wick_size'] + bear_stats['avg_top_wick_size']) / 2
        ac_ah_pct = (ac_upper_dollars / ac_body) * 100
        
        ac_lower_dollars = (bull_stats['avg_bottom_wick_size'] + bear_stats['avg_bottom_wick_size']) / 2
        ac_al_pct = (ac_lower_dollars / ac_body) * 100
        
        ac_range_dollars = (bull_stats['avg_total_range'] + bear_stats['avg_total_range']) / 2
        ac_at_pct = (ac_range_dollars / ac_body) * 100
        
        ac_line = (
            f"  AC:   "
            f"AB:{format_percentage(ac_ab_pct, 2)} / "
            f"AH:{format_percentage(ac_ah_pct, 2)} / "
            f"AL:{format_percentage(ac_al_pct, 2)} / "
            f"AT:{format_percentage(ac_at_pct, 2)}"
        )
        
        log_writer.write(f"{symbol} {abuc_line}", timestamp)
        log_writer.write(f"{symbol} {abec_line}", timestamp)
        log_writer.write(f"{symbol} {ac_line}", timestamp)
    
    @staticmethod
    def _get_candle_body_size(candle: Dict) -> float:
        """Helper to get absolute body size of a candle"""
        return abs(candle['close'] - candle['open'])


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    """
    Example usage of CandleSizeAnalyzer
    
    This demonstrates how to use the analyzer with a mock database.
    In production, you would use your actual Database instance.
    """
    
    print("=" * 70)
    print("CANDLE SIZE ANALYZER - EXAMPLE USAGE")
    print("=" * 70)
    print()
    
    # Mock database class for demonstration
    class MockDatabase:
        def get_recent_candles(self, limit):
            # Return some example candles
            return [
                {'open': 100.0, 'high': 102.0, 'low': 99.0, 'close': 101.5},
                {'open': 101.5, 'high': 103.0, 'low': 101.0, 'close': 102.5},
                {'open': 102.5, 'high': 104.0, 'low': 102.0, 'close': 103.0},
            ] * (limit // 3)
    
    # Mock log writer
    class MockLogWriter:
        def write(self, message, timestamp=None):
            print(f"[{timestamp or 'LOG'}] {message}")
    
    # Initialize analyzer
    db = MockDatabase()
    config = {
        'bullish_lookback_candles': 50,
        'bearish_lookback_candles': 50,
        'general_lookback_candles': 100,
        'enable_structure_logging': True
    }
    
    analyzer = CandleSizeAnalyzer(db, lookback_config=config)
    
    print("1. Getting historical averages...")
    print("-" * 70)
    stats = analyzer.get_statistics_summary()
    print(stats)
    print()
    
    print("2. Structure comparison for a sample candle...")
    print("-" * 70)
    sample_candle = {
        'open': 100.0,
        'high': 102.5,
        'low': 99.5,
        'close': 101.8
    }
    
    log_writer = MockLogWriter()
    analyzer.format_structure_comparison(
        candle=sample_candle,
        symbol="BTC",
        timestamp="14:30",
        log_writer=log_writer
    )
    print()
    
    print("3. Checking pattern size...")
    print("-" * 70)
    pattern = [sample_candle, sample_candle, sample_candle]
    result = analyzer.check_pattern_size(pattern, min_ratio=1.2)
    print(f"Pattern size check: {result}")
    print()
    
    print("=" * 70)
    print("EXAMPLE COMPLETE")
    print("=" * 70)
