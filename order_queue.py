"""
order_queue.py - Limit order collision management

Tracks pending limit orders and resolves collisions when multiple
assets want to place orders simultaneously. Uses beauty score for priority.

VERSION 2.1 - Added add_order() method for simple order tracking
"""

import threading
from typing import Dict, Optional, List
from dataclasses import dataclass


@dataclass
class PendingOrder:
    """Represents a pending limit order"""
    symbol: str
    price: float
    timestamp: str
    beauty_score: float
    candle: Dict


@dataclass
class ExecutedOrder:
    """Represents an executed market order (for tracking/logging)"""
    symbol: str
    side: str  # 'BUY' or 'SELL'
    price: float
    quantity: float
    timestamp: str
    pattern_type: Optional[str] = None


class OrderQueue:
    """
    Manages limit orders and detects collisions
    
    Collision occurs when multiple assets ready to place limit simultaneously.
    Resolution: Highest beauty score wins.
    
    Also tracks executed market orders for logging purposes.
    """
    
    def __init__(self, logger=None):
        """
        Initialize order queue
        
        Args:
            logger: Optional logger instance
        """
        self.logger = logger
        self.pending_orders: Dict[str, PendingOrder] = {}
        self.executed_orders: List[ExecutedOrder] = []
        self.lock = threading.Lock()
    
    def add_order(self, order: Dict):
        """
        Add an executed order to the tracking list
        
        This is used by buy monitors when they execute market orders
        (especially for EMA patterns that enter immediately).
        
        Args:
            order: Dict containing order details
                - symbol: str
                - side: str ('BUY' or 'SELL')
                - price: float
                - quantity: float
                - timestamp: str
                - pattern_type: str (optional)
        """
        with self.lock:
            executed_order = ExecutedOrder(
                symbol=order['symbol'],
                side=order['side'],
                price=order['price'],
                quantity=order['quantity'],
                timestamp=order['timestamp'],
                pattern_type=order.get('pattern_type')
            )
            self.executed_orders.append(executed_order)
            
            # Optional: Log the order if logger exists
            if self.logger:
                self.logger.write(
                    f"📝 Order tracked: {order['side']} {order['symbol']} @ "
                    f"{order['price']:.8f} qty:{order['quantity']:.4f} [{order.get('pattern_type', 'N/A')}]",
                    order['timestamp']
                )
    
    def request_order(self, symbol: str, price: float, timestamp: str,
                     beauty_score: float, candle: Dict) -> str:
        """
        Request to place a limit order
        
        Checks for collisions with other pending orders.
        If collision, compares beauty scores.
        
        Args:
            symbol: Asset symbol
            price: Limit price
            timestamp: Current timestamp
            beauty_score: Beauty score of this pattern
            candle: Current candle
        
        Returns:
            'APPROVED' - Place limit order
            'REJECTED_COLLISION' - Lost beauty competition
            'REJECTED_EXISTS' - Already have limit for this symbol
        """
        with self.lock:
            # Check if this symbol already has a pending order
            if symbol in self.pending_orders:
                return 'REJECTED_EXISTS'
            
            # Check for collisions with other pending orders
            if len(self.pending_orders) > 0:
                winner_symbol = symbol
                winner_score = beauty_score
                losers = []
                
                for existing_symbol, existing_order in self.pending_orders.items():
                    if existing_order.beauty_score > winner_score:
                        losers.append(symbol)
                        winner_symbol = existing_symbol
                        winner_score = existing_order.beauty_score
                    else:
                        losers.append(existing_symbol)
                
                # Remove losers
                for loser in losers:
                    if loser in self.pending_orders:
                        del self.pending_orders[loser]
                
                # Check if current request won
                if symbol in losers:
                    return 'REJECTED_COLLISION'
            
            # No collision or won the collision - add to pending
            order = PendingOrder(
                symbol=symbol,
                price=price,
                timestamp=timestamp,
                beauty_score=beauty_score,
                candle=candle
            )
            
            self.pending_orders[symbol] = order
            return 'APPROVED'
    
    def mark_filled(self, symbol: str):
        """Mark order as filled (remove from pending)"""
        with self.lock:
            if symbol in self.pending_orders:
                del self.pending_orders[symbol]
    
    def cancel_order(self, symbol: str):
        """Cancel a pending order"""
        with self.lock:
            if symbol in self.pending_orders:
                del self.pending_orders[symbol]
    
    def has_pending(self, symbol: str) -> bool:
        """Check if symbol has pending order"""
        with self.lock:
            return symbol in self.pending_orders
    
    def get_order(self, symbol: str) -> Optional[PendingOrder]:
        """Get pending order info"""
        with self.lock:
            return self.pending_orders.get(symbol)
    
    def get_all_pending(self) -> List[PendingOrder]:
        """Get all pending orders"""
        with self.lock:
            return list(self.pending_orders.values())
    
    def get_executed_orders(self) -> List[ExecutedOrder]:
        """Get all executed orders"""
        with self.lock:
            return list(self.executed_orders)
    
    def clear_executed_orders(self):
        """Clear executed orders history"""
        with self.lock:
            self.executed_orders.clear()
    
    def clear_all(self):
        """Clear all pending orders"""
        with self.lock:
            self.pending_orders.clear()
