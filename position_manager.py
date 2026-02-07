"""
position_manager.py - DUAL TIMEFRAME position tracking
"""

import threading
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
import config


@dataclass
class Position:
    symbol: str
    timeframe: str
    entry_price: float
    entry_time: str
    capital_allocated: float
    status: str
    beauty_score: Optional[float] = None
    candles_held: int = 0
    current_pnl: Optional[float] = None
    pattern_type: Optional[str] = None  # '3BULL_1min', '3BULL_5min', 'EMA1min', 'EMA5min'


class PositionManager:
    """Manages active trading positions - DUAL TIMEFRAME"""
    
    def __init__(self):
        self.positions_1min: Dict[str, Position] = {}
        self.positions_5min: Dict[str, Position] = {}
        self.lock = threading.Lock()
    
    def can_add_position(self, symbol: str, timeframe: str) -> Tuple[bool, str]:
        """Check if position can be added"""
        with self.lock:
            # Check if same asset already active
            if not config.DUAL_TIMEFRAME['allow_same_asset_both_timeframes']:
                if symbol in self.positions_1min or symbol in self.positions_5min:
                    return False, "ASSET_ALREADY_ACTIVE"
            
            # Check slot limit
            if timeframe == '1min':
                if len(self.positions_1min) >= config.TRADING['max_positions_1min']:
                    return False, "NO_SLOTS_1MIN"
            else:
                if len(self.positions_5min) >= config.TRADING['max_positions_5min']:
                    return False, "NO_SLOTS_5MIN"
            
            return True, "OK"
    
    def add_position(self, symbol: str, timeframe: str, entry_price: float, 
                    entry_time: str, capital: float, beauty_score: Optional[float] = None,
                    pattern_type: Optional[str] = None) -> bool:
        with self.lock:
            positions = self.positions_1min if timeframe == '1min' else self.positions_5min
            
            if symbol in positions:
                return False
            
            position = Position(
                symbol=symbol,
                timeframe=timeframe,
                entry_price=entry_price,
                entry_time=entry_time,
                capital_allocated=capital,
                status='BUY_MONITORING',
                beauty_score=beauty_score,
                pattern_type=pattern_type
            )
            
            positions[symbol] = position
            return True
    
    def update_status(self, symbol: str, timeframe: str, status: str):
        with self.lock:
            positions = self.positions_1min if timeframe == '1min' else self.positions_5min
            if symbol in positions:
                positions[symbol].status = status
    
    def update_pnl(self, symbol: str, timeframe: str, current_price: float):
        with self.lock:
            positions = self.positions_1min if timeframe == '1min' else self.positions_5min
            if symbol in positions:
                position = positions[symbol]
                pnl = ((current_price - position.entry_price) / position.entry_price) * 100
                position.current_pnl = pnl
    
    def remove_position(self, symbol: str, timeframe: str) -> bool:
        with self.lock:
            positions = self.positions_1min if timeframe == '1min' else self.positions_5min
            if symbol in positions:
                del positions[symbol]
                return True
            return False
    
    def get_position(self, symbol: str, timeframe: str) -> Optional[Position]:
        with self.lock:
            positions = self.positions_1min if timeframe == '1min' else self.positions_5min
            return positions.get(symbol)
    
    def has_position(self, symbol: str, timeframe: str) -> bool:
        with self.lock:
            positions = self.positions_1min if timeframe == '1min' else self.positions_5min
            return symbol in positions
    
    def count_positions(self, timeframe: str) -> int:
        with self.lock:
            positions = self.positions_1min if timeframe == '1min' else self.positions_5min
            return len(positions)
    
    def count_positions_by_pattern(self, timeframe: str, pattern_type: str) -> int:
        """
        Count positions of a specific pattern type
        
        Args:
            timeframe: '1min' or '5min'
            pattern_type: '3BULL_1min', '3BULL_5min', 'EMA1min', 'EMA5min'
        
        Returns:
            Number of active positions with this pattern type
        """
        with self.lock:
            positions = self.positions_1min if timeframe == '1min' else self.positions_5min
            return sum(1 for p in positions.values() if p.pattern_type == pattern_type)
