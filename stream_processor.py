"""
stream_processor.py - Routes klines by interval

VERSION 2.6 - NULL-SAFE HANDLING FOR DISABLED TIMEFRAMES
Handles cases where databases_1min or databases_5min may be None
"""

from typing import Dict, Optional


class StreamProcessor:
    """Processes kline data from WebSocket and routes by interval"""
    
    def __init__(self, databases_1min: Optional[Dict], databases_5min: Optional[Dict],
                 pattern_detectors_1min: Optional[Dict], pattern_detectors_5min: Optional[Dict]):
        """
        Initialize stream processor
        
        Args:
            databases_1min: Dict of symbol_base -> Database (1min) or None if disabled
            databases_5min: Dict of symbol_base -> Database5Min (5min) or None if disabled
            pattern_detectors_1min: Dict of symbol_base -> PatternDetector (1min) or None if disabled
            pattern_detectors_5min: Dict of symbol_base -> PatternDetector5Min (5min) or None if disabled
        """
        self.databases_1min = databases_1min
        self.databases_5min = databases_5min
        self.pattern_detectors_1min = pattern_detectors_1min
        self.pattern_detectors_5min = pattern_detectors_5min
        
        # Determine active timeframes
        self.timeframe_1min_active = databases_1min is not None
        self.timeframe_5min_active = databases_5min is not None
    
    def process_kline(self, symbol: str, kline: Dict):
        """
        Process a kline message and route by interval
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDC')
            kline: Kline data from WebSocket
        """
        # Only process closed candles
        if not kline.get('x', False):
            return
        
        # Extract interval ('1m' or '5m')
        interval = kline.get('i')
        
        # Extract base symbol
        symbol_base = symbol.replace('USDC', '')
        
        # Convert kline to candle format
        candle = {
            'open_time': int(kline['t']),
            'close_time': int(kline['T']),
            'open': float(kline['o']),
            'high': float(kline['h']),
            'low': float(kline['l']),
            'close': float(kline['c']),
            'volume': float(kline['v']),
            'turnover': float(kline['q']),
            'trades': int(kline['n'])
        }
        
        # Route by interval with null checks
        if interval == '1m' and self.timeframe_1min_active:
            db = self.databases_1min.get(symbol_base)
            detector = self.pattern_detectors_1min.get(symbol_base)
            
            if db and detector:
                # Add to database (calculates indicators automatically)
                db.add_candle(candle)
                
                # Get candle back with indicators
                recent = db.get_recent_candles(1)
                if recent:
                    stored_candle = recent[0]
                    # Check 1min pattern
                    detector.check_pattern(stored_candle)
        
        elif interval == '5m' and self.timeframe_5min_active:
            db = self.databases_5min.get(symbol_base)
            detector = self.pattern_detectors_5min.get(symbol_base)
            
            if db and detector:
                # Add to database (calculates indicators automatically)
                db.add_candle(candle)
                
                # Get candle back with indicators
                recent = db.get_recent_candles(1)
                if recent:
                    stored_candle = recent[0]
                    # Check 5min pattern
                    detector.check_pattern(stored_candle)
