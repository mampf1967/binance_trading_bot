"""
database.py - Trading database handler with technical indicators

Handles SQLite storage for candles with automatic indicator calculation.
Features:
- Single table design
- Incremental EMA calculations
- MACD indicators
- Fast indexed queries
"""

import sqlite3
from typing import Dict, List, Optional
from pathlib import Path
from time_converter import timestamp_to_vienna_str


class Database:
    """SQLite database handler for trading data"""
    
    def __init__(self, db_path: str, symbol_base: str):
        """
        Initialize database connection
        
        Args:
            db_path: Path to SQLite database file
            symbol_base: Base symbol name (e.g., 'BTC', 'ETH')
        """
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self.db_path = db_path
        self.symbol_base = symbol_base
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        # Enable WAL mode for better performance
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        
        self._create_table()
    
    def _create_table(self):
        """Create the candles table with all indicator columns"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS candles (
                timestamp TEXT PRIMARY KEY,
                open_time INTEGER NOT NULL,
                close_time INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                turnover REAL NOT NULL,
                trades INTEGER NOT NULL,
                ema9 REAL,
                ema20 REAL,
                ema300 REAL,
                ema12 REAL,
                ema26 REAL,
                dif REAL,
                dea REAL,
                macd_hist REAL
            )
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON candles(timestamp DESC)
        """)
        
        self.conn.commit()
    
    def get_candle_count(self) -> int:
        """Get total number of candles"""
        cursor = self.conn.execute("SELECT COUNT(*) FROM candles")
        return cursor.fetchone()[0]
    
    def get_recent_candles(self, limit: int = 300) -> List[Dict]:
        """
        Get recent candles (oldest first)
        
        Args:
            limit: Number of candles to retrieve
        
        Returns:
            List of candle dicts
        """
        cursor = self.conn.execute("""
            SELECT * FROM candles 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        candles = [dict(row) for row in rows]
        candles.reverse()  # Return oldest first
        
        return candles
    
    def add_candle(self, candle_data: Dict):
        """
        Add a new candle with automatic indicator calculation
        
        Args:
            candle_data: Dict with OHLCV data
        """
        open_time = candle_data.get('open_time')
        if not open_time:
            return
        
        timestamp = timestamp_to_vienna_str(open_time)
        
        # Check if exists
        cursor = self.conn.execute(
            "SELECT 1 FROM candles WHERE timestamp = ?", (timestamp,)
        )
        if cursor.fetchone():
            return
        
        # Calculate indicators
        close = float(candle_data['close'])
        indicators = self._calculate_indicators(close)
        
        # Insert candle
        self.conn.execute("""
            INSERT INTO candles (
                timestamp, open_time, close_time,
                open, high, low, close, volume, turnover, trades,
                ema9, ema20, ema300, ema12, ema26,
                dif, dea, macd_hist
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, open_time, candle_data['close_time'],
            candle_data['open'], candle_data['high'], candle_data['low'], close,
            candle_data['volume'], candle_data['turnover'], candle_data['trades'],
            indicators['ema9'], indicators['ema20'], indicators['ema300'],
            indicators['ema12'], indicators['ema26'],
            indicators['dif'], indicators['dea'], indicators['macd_hist']
        ))
        
        self.conn.commit()
    
    def add_candle_with_indicators(self, candle_data: Dict):
        """
        Add candle with pre-calculated indicators
        Used for gap recovery to maintain correct EMA sequence
        """
        open_time = candle_data.get('open_time')
        if not open_time:
            return
        
        timestamp = timestamp_to_vienna_str(open_time)
        
        # Check if exists
        cursor = self.conn.execute(
            "SELECT 1 FROM candles WHERE timestamp = ?", (timestamp,)
        )
        if cursor.fetchone():
            return
        
        # Insert with provided indicators
        self.conn.execute("""
            INSERT INTO candles (
                timestamp, open_time, close_time,
                open, high, low, close, volume, turnover, trades,
                ema9, ema20, ema300, ema12, ema26,
                dif, dea, macd_hist
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, open_time, candle_data['close_time'],
            candle_data['open'], candle_data['high'], candle_data['low'], candle_data['close'],
            candle_data['volume'], candle_data['turnover'], candle_data['trades'],
            candle_data.get('ema9', candle_data['close']),
            candle_data.get('ema20', candle_data['close']),
            candle_data.get('ema300', candle_data['close']),
            candle_data.get('ema12', candle_data['close']),
            candle_data.get('ema26', candle_data['close']),
            candle_data.get('dif', 0.0),
            candle_data.get('dea', 0.0),
            candle_data.get('macd_hist', 0.0)
        ))
        
        self.conn.commit()
    
    def _calculate_indicators(self, current_close: float) -> Dict:
        """Calculate all indicators incrementally"""
        cursor = self.conn.execute("""
            SELECT close, ema9, ema20, ema300, ema12, ema26, dif, dea
            FROM candles 
            ORDER BY timestamp DESC 
            LIMIT 1
        """)
        
        prev = cursor.fetchone()
        
        if not prev:
            # First candle - initialize with current close
            return {
                'ema9': current_close,
                'ema20': current_close,
                'ema300': current_close,
                'ema12': current_close,
                'ema26': current_close,
                'dif': 0.0,
                'dea': 0.0,
                'macd_hist': 0.0
            }
        
        # Calculate EMAs incrementally
        ema9 = self._update_ema(prev['ema9'], current_close, 9)
        ema20 = self._update_ema(prev['ema20'], current_close, 20)
        ema300 = self._update_ema(prev['ema300'], current_close, 300)
        ema12 = self._update_ema(prev['ema12'], current_close, 12)
        ema26 = self._update_ema(prev['ema26'], current_close, 26)
        
        # Calculate MACD
        dif = ema12 - ema26
        dea = self._update_ema(prev['dea'], dif, 9)
        macd_hist = dif - dea
        
        return {
            'ema9': ema9,
            'ema20': ema20,
            'ema300': ema300,
            'ema12': ema12,
            'ema26': ema26,
            'dif': dif,
            'dea': dea,
            'macd_hist': macd_hist
        }
    
    def _update_ema(self, prev_ema: Optional[float], price: float, period: int) -> float:
        """Update EMA incrementally"""
        if prev_ema is None:
            return price
        
        alpha = 2.0 / (period + 1.0)
        return alpha * price + (1.0 - alpha) * prev_ema
    
    def close(self):
        """Close database connection"""
        self.conn.close()
