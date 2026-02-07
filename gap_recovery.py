"""
gap_recovery.py - Missing candle recovery

Detects and recovers gaps in candle data with proper sequential
indicator calculation to maintain EMA accuracy.
"""

import requests
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor


class GapRecovery:
    """Handles gap detection and recovery"""
    
    BINANCE_API = "https://api.binance.com/api/v3/klines"
    
    def __init__(self, interval: str, max_gap_minutes: int = 10):
        """
        Initialize gap recovery
        
        Args:
            interval: Candle interval (e.g., '1m')
            max_gap_minutes: Maximum gap to recover (minutes)
        """
        self.interval = interval
        self.max_gap_minutes = max_gap_minutes
    
    def detect_gap(self, symbol: str, current_time_ms: int, db) -> tuple:
        """
        Detect gap for a specific symbol
        
        Returns:
            (has_gap: bool, gap_minutes: int, last_candle_time: int)
        """
        try:
            recent = db.get_recent_candles(1)
            if not recent:
                return False, 0, 0
            
            last_close_time = recent[0]['close_time']
            time_diff_ms = current_time_ms - last_close_time
            gap_minutes = max(0, (time_diff_ms // 60000) - 1)
            
            has_gap = 0 < gap_minutes <= self.max_gap_minutes
            
            return has_gap, gap_minutes, last_close_time
            
        except Exception as e:
            print(f"Gap detection error for {symbol}: {e}")
            return False, 0, 0
    
    def fetch_missing_candles(self, symbol: str, start_time: int, gap_minutes: int) -> List[Dict]:
        """Fetch missing candles from Binance"""
        try:
            limit = min(gap_minutes + 5, 1000)
            
            params = {
                'symbol': symbol,
                'interval': self.interval,
                'limit': limit,
                'startTime': start_time
            }
            
            response = requests.get(self.BINANCE_API, params=params, timeout=10)
            response.raise_for_status()
            
            klines = response.json()
            
            candles = []
            for kline in klines:
                candle = {
                    'open_time': int(kline[0]),
                    'close_time': int(kline[6]),
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5]),
                    'turnover': float(kline[7]),
                    'trades': int(kline[8])
                }
                candles.append(candle)
            
            return candles
            
        except Exception as e:
            print(f"Failed to fetch missing candles for {symbol}: {e}")
            return []
    
    def recover_gap(self, symbol: str, current_time_ms: int, db, pattern_detector) -> bool:
        """
        Recover gap with proper sequential indicator calculation
        
        Args:
            symbol: Trading symbol
            current_time_ms: Current timestamp
            db: Database instance
            pattern_detector: Pattern detector instance
        
        Returns:
            True if successful
        """
        try:
            has_gap, gap_minutes, last_close_time = self.detect_gap(symbol, current_time_ms, db)
            
            if not has_gap:
                return True
            
            print(f"🔄 {symbol}: Recovering {gap_minutes} minutes...")
            
            missing_candles = self.fetch_missing_candles(symbol, last_close_time + 60000, gap_minutes)
            
            if not missing_candles:
                return False
            
            # Sort oldest first (critical for sequential indicator calculation)
            missing_candles.sort(key=lambda x: x['open_time'])
            
            # Get last known indicators
            recent = db.get_recent_candles(1)
            if not recent:
                return False
            
            last_candle = recent[0]
            
            # Initialize EMA chain
            ema_chain = {
                'ema9': last_candle['ema9'],
                'ema20': last_candle['ema20'],
                'ema300': last_candle['ema300'],
                'ema12': last_candle['ema12'],
                'ema26': last_candle['ema26'],
                'dea': last_candle['dea']
            }
            
            # Process each missing candle sequentially
            for candle_data in missing_candles:
                # Calculate indicators
                indicators = self._calculate_indicators_sequential(
                    candle_data['close'], ema_chain
                )
                
                # Update candle with indicators
                candle_data.update(indicators)
                
                # Update EMA chain for next candle
                ema_chain.update({
                    'ema9': indicators['ema9'],
                    'ema20': indicators['ema20'],
                    'ema300': indicators['ema300'],
                    'ema12': indicators['ema12'],
                    'ema26': indicators['ema26'],
                    'dea': indicators['dea']
                })
                
                # Insert into database
                db.add_candle_with_indicators(candle_data)
                
                # Process through pattern detection
                pattern_detector.check_pattern(candle_data)
            
            print(f"✅ {symbol}: Recovered {len(missing_candles)} candles")
            return True
            
        except Exception as e:
            print(f"Gap recovery failed for {symbol}: {e}")
            return False
    
    def _calculate_indicators_sequential(self, current_close: float, ema_chain: Dict) -> Dict:
        """Calculate indicators using previous EMA values"""
        ema9 = self._update_ema(ema_chain['ema9'], current_close, 9)
        ema20 = self._update_ema(ema_chain['ema20'], current_close, 20)
        ema300 = self._update_ema(ema_chain['ema300'], current_close, 300)
        ema12 = self._update_ema(ema_chain['ema12'], current_close, 12)
        ema26 = self._update_ema(ema_chain['ema26'], current_close, 26)
        
        dif = ema12 - ema26
        dea = self._update_ema(ema_chain['dea'], dif, 9)
        macd_hist = dif - dea
        
        return {
            'ema9': ema9, 'ema20': ema20, 'ema300': ema300,
            'ema12': ema12, 'ema26': ema26, 'dif': dif,
            'dea': dea, 'macd_hist': macd_hist
        }
    
    def _update_ema(self, prev_ema: float, price: float, period: int) -> float:
        """EMA calculation"""
        alpha = 2.0 / (period + 1.0)
        return alpha * price + (1.0 - alpha) * prev_ema
