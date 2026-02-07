"""
capital_allocator.py - DUAL TIMEFRAME capital allocation
"""

import threading
from typing import Dict
import config


class CapitalAllocator:
    """Manages capital allocation - DUAL TIMEFRAME with split pools"""
    
    def __init__(self, total_capital: float, allocation_1min: float, allocation_5min: float):
        self.total_capital = total_capital
        self.capital_1min = (total_capital * allocation_1min) / 100
        self.capital_5min = (total_capital * allocation_5min) / 100
        
        self.allocations_1min: Dict[str, float] = {}
        self.allocations_5min: Dict[str, float] = {}
        self.lock = threading.Lock()
    
    def can_allocate(self, timeframe: str) -> bool:
        with self.lock:
            allocations = self.allocations_1min if timeframe == '1min' else self.allocations_5min
            pool = self.capital_1min if timeframe == '1min' else self.capital_5min
            
            allocated = sum(allocations.values())
            available = pool - allocated
            
            # Check if we have enough for at least one position
            capital_per_position = pool / (config.TRADING[f'max_positions_{timeframe}'])
            return available >= capital_per_position
    
    def allocate(self, symbol: str, timeframe: str) -> float:
        with self.lock:
            allocations = self.allocations_1min if timeframe == '1min' else self.allocations_5min
            pool = self.capital_1min if timeframe == '1min' else self.capital_5min
            
            if symbol in allocations:
                return 0.0
            
            allocated = sum(allocations.values())
            available = pool - allocated
            
            max_positions = config.TRADING[f'max_positions_{timeframe}']
            capital_per_position = pool / max_positions
            
            capital = min(capital_per_position, available)
            
            if capital > 0:
                allocations[symbol] = capital
            
            return capital
    
    def release(self, symbol: str, timeframe: str):
        with self.lock:
            allocations = self.allocations_1min if timeframe == '1min' else self.allocations_5min
            if symbol in allocations:
                del allocations[symbol]
