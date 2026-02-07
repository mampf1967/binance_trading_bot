"""
data_downloader.py - Historical data fetching from Binance

Supports both sequential and parallel downloading of historical candles.
Handles rate limits and converts kline format to candle format.
"""

import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple


class DataDownloader:
    """Fetches historical candles from Binance API"""
    
    BINANCE_API = "https://api.binance.com/api/v3/klines"
    
    def __init__(self, interval: str = '1m'):
        """
        Initialize data downloader
        
        Args:
            interval: Candle interval (e.g., '1m', '5m')
        """
        self.interval = interval
    
    def fetch_candles(self, symbol: str, limit: int = 500, start_time: int = None, interval: str = None) -> List[Dict]:
        """
        Fetch closed candles for a single symbol
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDC')
            limit: Number of candles to fetch
            start_time: Start timestamp in ms (optional)
        
        Returns:
            List of candle dicts
        """
        try:
            params = {
                'symbol': symbol,
                'interval': self.interval,
                'limit': limit + 1  # Fetch one extra to remove current candle
            }
            
            if start_time:
                params['startTime'] = start_time
            
            response = requests.get(self.BINANCE_API, params=params, timeout=10)
            response.raise_for_status()
            
            klines = response.json()
            
            # Remove last candle (current incomplete one)
            if len(klines) > 0:
                klines = klines[:-1]
            
            # Convert to candle format
            candles = [self._kline_to_candle(k) for k in klines[:limit]]
            
            return candles
            
        except Exception as e:
            print(f"Error fetching candles for {symbol}: {e}")
            return []
    
    def fetch_parallel(self, symbols: List[str], limit: int = 500, max_workers: int = 50, interval: str = None) -> Dict[str, List[Dict]]:
        """
        Fetch candles for multiple symbols in parallel
        
        Args:
            symbols: List of trading symbols
            limit: Number of candles per symbol
            max_workers: Number of parallel workers
        
        Returns:
            Dict mapping symbol to list of candles
        """
        results = {}
        errors = []
        
        print(f"📥 Fetching {limit} candles for {len(symbols)} assets...")
        print(f"⚡ Using {max_workers} parallel workers")
        
        start_time = time.time()
        completed = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_symbol = {
                executor.submit(self.fetch_candles, symbol, limit, None, interval): symbol
                for symbol in symbols
            }
            
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                completed += 1
                
                try:
                    candles = future.result()
                    if candles:
                        results[symbol] = candles
                    else:
                        errors.append((symbol, "No data returned"))
                except Exception as e:
                    errors.append((symbol, str(e)))
                
                if completed % 50 == 0 or completed == len(symbols):
                    elapsed = time.time() - start_time
                    print(f"   Progress: {completed}/{len(symbols)} ({elapsed:.1f}s)")
        
        elapsed = time.time() - start_time
        
        print(f"\n✅ Completed in {elapsed:.1f} seconds")
        print(f"   Successful: {len(results)} assets")
        print(f"   Failed: {len(errors)} assets")
        
        if errors:
            print(f"\n⚠️  Failed assets:")
            for symbol, error in errors[:5]:
                print(f"   {symbol}: {error}")
            if len(errors) > 5:
                print(f"   ... and {len(errors) - 5} more")
        
        return results
    
    def _kline_to_candle(self, kline: List) -> Dict:
        """Convert Binance kline format to candle dict"""
        return {
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
