"""
cooldown_tracker.py - DUAL TIMEFRAME cooldown tracking
"""

import threading
from typing import Dict
import config


class CooldownTracker:
    """Tracks cooldown periods - DUAL TIMEFRAME independent cooldowns"""
    
    def __init__(self):
        self.cooldowns_1min: Dict[str, int] = {}
        self.cooldowns_5min: Dict[str, int] = {}
        self.lock = threading.Lock()
    
    def start_cooldown(self, symbol: str, timeframe: str):
        with self.lock:
            if timeframe == '1min':
                self.cooldowns_1min[symbol] = config.TRADING['cooldown_1min_candles']
            else:
                self.cooldowns_5min[symbol] = config.TRADING['cooldown_5min_candles']
    
    def process_candle(self, symbol: str, timeframe: str):
        with self.lock:
            cooldowns = self.cooldowns_1min if timeframe == '1min' else self.cooldowns_5min
            
            if symbol in cooldowns:
                cooldowns[symbol] -= 1
                
                if cooldowns[symbol] <= 0:
                    del cooldowns[symbol]
    
    def is_in_cooldown(self, symbol: str, timeframe: str) -> bool:
        with self.lock:
            cooldowns = self.cooldowns_1min if timeframe == '1min' else self.cooldowns_5min
            return symbol in cooldowns
    
    def get_remaining(self, symbol: str, timeframe: str) -> int:
        with self.lock:
            cooldowns = self.cooldowns_1min if timeframe == '1min' else self.cooldowns_5min
            return cooldowns.get(symbol, 0)
