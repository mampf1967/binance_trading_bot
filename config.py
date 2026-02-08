"""
config.py - DUAL TIMEFRAME Configuration (Fully Configurable Edition)
VERSION 3.1 - GRADUATED HIGH_WAVE SEVERITY THRESHOLDS

Every abort condition, filter, and logic decision now has a dedicated config flag.
Defaults match current behavior (all enabled).

CHANGELOG:
- v3.1: Added graduated HIGH_WAVE severity (2x-4x-6x thresholds)
"""

# Base Intervals
INTERVAL_1MIN = "1m"
INTERVAL_5MIN = "5m"
INITIAL_CANDLES = 500

# WebSocket & Connection
WEBSOCKET_URL = "wss://stream.binance.com:443/stream"
MAX_RETRIES = 20
RETRY_DELAY = 10

# =============================================================================
# COMMISSION CONFIGURATION
# =============================================================================
# Binance spot trading fee per side (0.075% = 0.00075)
# Round-trip cost = 2 x COMMISSION_PERCENT (buy + sell)
COMMISSION_PERCENT = 0.075  # Per side commission (0.075%)

# =============================================================================
# CANDLE SIZE ANALYZER CONFIG
# =============================================================================
CANDLE_ANALYZER = {
    "bullish_lookback_candles": 50,
    "bearish_lookback_candles": 50,
    "general_lookback_candles": 100,
    "enable_structure_logging": True,  # Enable 4-line structure comparison logging
}

# =============================================================================
# 1MIN - 3BULL PATTERN DETECTION
# =============================================================================
PATTERN_3BULL = {
    "enabled": True,
    
    # === CORE PATTERN REQUIREMENTS ===
    "require_consecutive_candles": True,    # Candles must be consecutive minutes (handles daily rollover)
    "require_all_bullish": True,            # C1, C2, C3 must all be bullish (or doji if allowed)
    "require_ascending_closes": True,       # C2.close > C1.close AND C3.close > C2.close
    
    # === THRESHOLD FILTERS ===
    "min_gain_percent": 0.8,                # Minimum total gain across 3 candles
    "min_volume": 5000.0,                    # Minimum total turnover (USDC)
    "min_trades": 50,                       # Minimum total trade count
    "min_candle_volume": 30.0,              # Minimum volume per individual candle
    
    # === TECHNICAL INDICATOR FILTERS ===
    "filter_ema300": False,                 # Require price > EMA300
    "filter_ema9_above_ema20": True,        # Require EMA9 > EMA20
    "filter_dif_positive": False,           # Require MACD DIF > 0
    "filter_macd_positive": False,          # Require MACD histogram > 0
    "filter_dea_positive": False,           # Require MACD DEA > 0
    
    # === DOJI C1 SUPPORT ===
    "allow_doji_c1": True,                  # Allow C1 to be doji with gap to C2
    "doji_gap_min_percent": 0.1,            # Minimum gap required after doji C1
    "doji_tolerance_percent": 0.0,          # Max body size to qualify as doji
    
    # === VOLUME SURGE FILTER ===
    "filter_volume_surge": False,           # Require volume surge vs recent average
    "volume_surge_multiplier": 1.5,         # Pattern volume must be X times recent average
    "volume_surge_lookback": 20,            # Number of candles for baseline average
    
    # === MACD ACCELERATION FILTER ===
    "filter_macd_acceleration": False,      # Require non-decreasing MACD histogram
    "macd_acceleration_min_growth": 0.0,    # Minimum growth between consecutive values
    "macd_acceleration_lookback": 5,        # Number of candles to check
    
    # === EMA CROSSOVER FILTER ===
    "filter_ema_crossover": False,          # Require recent EMA9 cross above EMA20
    "ema_crossover_lookback": 5,            # Must have crossed within N candles
    
    # === CANDLE SIZE FILTER ===
    "filter_candle_size": False,            # Require pattern candles larger than average
    "min_pattern_candle_ratio": 1.2,        # Pattern candles must be X times avg bullish
}

# =============================================================================
# 5MIN - 2BULL PATTERN DETECTION
# =============================================================================
PATTERN_2BULL = {
    "enabled": False,
    
    # === CORE PATTERN REQUIREMENTS ===
    "require_consecutive_candles": True,    # Candles must be consecutive 5min intervals
    "require_all_bullish": True,            # C1, C2 must both be bullish
    "require_ascending_closes": True,       # C2.close > C1.close
    
    # === THRESHOLD FILTERS ===
    "min_gain_percent": 1.0,                # Minimum total gain across 2 candles
    "min_volume": 15000.0,                   # Minimum total turnover (USDC)
    "min_trades": 100,                      # Minimum total trade count
    "min_candle_volume": 100.0,             # Minimum volume per individual candle
    
    # === TECHNICAL INDICATOR FILTERS ===
    "filter_ema300": False,                 # Require price > EMA300
    "filter_ema9_above_ema20": True,        # Require EMA9 > EMA20
    "filter_dif_positive": False,           # Require MACD DIF > 0
    "filter_macd_positive": False,          # Require MACD histogram > 0
    "filter_dea_positive": False,           # Require MACD DEA > 0
    
    # === DOJI C1 SUPPORT ===
    "allow_doji_c1": True,                  # Allow C1 to be doji with gap to C2
    "doji_gap_min_percent": 0.1,            # Minimum gap required after doji C1
    "doji_tolerance_percent": 0.0,          # Max body size to qualify as doji
    
    # === VOLUME SURGE FILTER ===
    "filter_volume_surge": False,           # Require volume surge vs recent average
    "volume_surge_multiplier": 1.8,         # Pattern volume must be X times recent average
    "volume_surge_lookback": 20,            # Number of candles for baseline average
    
    # === MACD ACCELERATION FILTER ===
    "filter_macd_acceleration": False,      # Require non-decreasing MACD histogram
    "macd_acceleration_min_growth": 0.0,    # Minimum growth between consecutive values
    "macd_acceleration_lookback": 5,        # Number of candles to check
    
    # === EMA CROSSOVER FILTER ===
    "filter_ema_crossover": False,          # Require recent EMA9 cross above EMA20
    "ema_crossover_lookback": 3,            # Must have crossed within N candles
    
    # === CANDLE SIZE FILTER ===
    "filter_candle_size": False,            # Require pattern candles larger than average
    "min_pattern_candle_ratio": 1.2,        # Pattern candles must be X times avg bullish
}

# =============================================================================
# EMA MOMENTUM PATTERN DETECTION (1MIN & 5MIN)
# =============================================================================
EMA_MOMENTUM = {
    "enabled": True,
    
    # === CORE PATTERN REQUIREMENTS ===
    "threshold_percent": 1.0,           # EMA9 must increase by this % to trigger
    "lookback_window": 10,              # Check EMA9 gain over last N candles
    "min_lookback_candles": 6,          # Minimum window size to check (e.g., 6-10)
    
    # === VOLUME FILTERS ===
    "min_candle_volume_1min": 50.0,     # Minimum turnover (USDC) per 1min candle
    "min_candle_volume_5min": 100.0,    # Minimum turnover (USDC) per 5min candle
    
    # === RECENCY FILTER ===
    "recency_filter_enabled": True,     # Skip if pattern detected recently
    "recency_filter_candles": 60,       # Skip if detected within last N candles
    
    # === POSITION LIMITS ===
    "max_positions_1min": 2,            # Max concurrent EMA positions on 1min timeframe
    "max_positions_5min": 2,            # Max concurrent EMA positions on 5min timeframe
}

# =============================================================================
# 1MIN BUY MONITOR - ENTRY DECISION LOGIC
# =============================================================================
BUY_MONITOR = {
    # === MONITORING PARAMETERS ===
    "volume_threshold_factor": 1.1,         # Multiplier for volume threshold (avg_volume × factor)
    "max_monitor_candles": 3,               # Maximum candles to wait for entry
    
    # === WICK REJECTION (BEARISH SIGNAL) ===
    "wick_rejection_enabled": True,         # Abort if upper wick indicates rejection
    "wick_rejection_ratio": 2.0,            # Upper wick must be > ratio × body to trigger
    
    # === BULLISH MARUBOZU (IMMEDIATE BUY TRIGGER) ===
    "marubozu_enabled": True,               # Enable almost-marubozu detection
    "marubozu_min_gain_percent": 0.5,       # Minimum gain for marubozu immediate buy
    "marubozu_lower_wick_tolerance": 0.02,  # Lower wick must be ≤ this fraction of body
    
    # === BEARISH MARUBOZU (ABORT TRIGGER) ===
    "bearish_marubozu_abort_enabled": True, # Abort if bearish marubozu detected
    "marubozu_min_loss_percent": 0.4,       # Minimum loss for bearish marubozu abort
    "bearish_marubozu_upper_wick_tolerance": 0.02,  # Upper wick tolerance for bearish
    
    # === PERFECT BEAUTY SCORE (IMMEDIATE BUY TRIGGER) ===
    "perfect_beauty_buy_enabled": True,     # Buy immediately on beauty score = 100
    
    # === RECURSIVE PATTERN DETECTION ===
    "recursive_pattern_enabled": True,      # Restart monitoring on new 3BULL pattern
    
    # === IMMEDIATE BUY MASTER SWITCH ===
    "immediate_buy_enabled": True,          # Master switch for all immediate buy triggers
    
    # === LIMIT ORDER CONDITIONS (BEARISH C1) ===
    "require_low_volume_for_limit": True,   # Volume must be < threshold for limit order
    "require_macd_positive_for_limit": True,# MACD histogram must be > 0 for limit order
    "high_volume_dip_abort_enabled": True,  # Abort if bearish C1 has high volume
    
    # === HAMMER PATTERN ABORT ===
    "hammer_abort_enabled": True,           # Abort if hammer weakness detected
    # Hammer thresholds from REVERSAL_DETECTION config
    
    # === HIGH WAVE DOJI ABORT ===
    "high_wave_abort_enabled": False,       # Abort if high wave exhaustion detected
    "high_wave_max_body_percent": 20.0,     # Body must be < this % of total range
    "high_wave_min_wick_ratio": 2.0,        # Both wicks must be ≥ this × body
    
    # === LARGE BEARISH ABORT ===
    "abort_large_bearish": False,           # Abort if large bearish candle detected
    "large_bearish_threshold": 1.5,         # Bearish body must be > threshold × avg bearish
    
    # === WEAK BULLISH WARNING ===
    "require_strong_bullish": False,        # Warn if bullish candle is weak
    "min_bullish_ratio": 0.8,               # Bullish body must be ≥ ratio × avg bullish
    
    # === CANDLE SIZE ANALYZER ===
    "candle_size_lookback": 50,             # Lookback for historical size comparison
}

# =============================================================================
# 5MIN BUY MONITOR - ENTRY DECISION LOGIC
# =============================================================================
BUY_MONITOR_5MIN = {
    # === MONITORING PARAMETERS ===
    "volume_threshold_factor": 1.2,         # Multiplier for volume threshold
    "max_monitor_candles": 2,               # Maximum candles to wait for entry (5min shorter)
    
    # === WICK REJECTION (BEARISH SIGNAL) ===
    "wick_rejection_enabled": True,         # Abort if upper wick indicates rejection
    "wick_rejection_ratio": 2.0,            # Upper wick must be > ratio × body to trigger
    
    # === BULLISH MARUBOZU (IMMEDIATE BUY TRIGGER) ===
    "marubozu_enabled": True,               # Enable almost-marubozu detection
    "marubozu_min_gain_percent": 1.0,       # Higher threshold for 5min
    "marubozu_lower_wick_tolerance": 0.02,  # Lower wick must be ≤ this fraction of body
    
    # === BEARISH MARUBOZU (ABORT TRIGGER) ===
    "bearish_marubozu_abort_enabled": True, # Abort if bearish marubozu detected
    "marubozu_min_loss_percent": 0.4,       # Minimum loss for bearish marubozu abort
    "bearish_marubozu_upper_wick_tolerance": 0.02,  # Upper wick tolerance
    
    # === PERFECT BEAUTY SCORE (IMMEDIATE BUY TRIGGER) ===
    "perfect_beauty_buy_enabled": True,     # Buy immediately on beauty score = 100
    
    # === RECURSIVE PATTERN DETECTION ===
    "recursive_pattern_enabled": True,      # Restart monitoring on new 2BULL pattern
    
    # === IMMEDIATE BUY MASTER SWITCH ===
    "immediate_buy_enabled": True,          # Master switch for all immediate buy triggers
    
    # === LIMIT ORDER CONDITIONS (BEARISH C1) ===
    "require_low_volume_for_limit": True,   # Volume must be < threshold for limit order
    "require_macd_positive_for_limit": True,# MACD histogram must be > 0 for limit order
    "high_volume_dip_abort_enabled": True,  # Abort if bearish C1 has high volume
    
    # === HAMMER PATTERN ABORT ===
    "hammer_abort_enabled": True,           # Abort if hammer weakness detected
    
    # === HIGH WAVE DOJI ABORT ===
    "high_wave_abort_enabled": False,       # Abort if high wave exhaustion detected
    "high_wave_max_body_percent": 20.0,     # Body must be < this % of total range
    "high_wave_min_wick_ratio": 2.0,        # Both wicks must be ≥ this × body
    
    # === LARGE BEARISH ABORT ===
    "abort_large_bearish": False,           # Abort if large bearish candle detected
    "large_bearish_threshold": 1.5,         # Bearish body must be > threshold × avg bearish
    
    # === WEAK BULLISH WARNING ===
    "require_strong_bullish": False,        # Warn if bullish candle is weak
    "min_bullish_ratio": 0.8,               # Bullish body must be ≥ ratio × avg bullish
}

# =============================================================================
# 1MIN SELL MONITOR - EXIT DECISION LOGIC
# =============================================================================
SELL_MONITOR = {
    # === PROFIT TARGETS ===
    "tp_percent_orig": 5.0,                 # Original take profit target (%)
    "sl_percent_orig": 3.0,                 # Stop loss threshold (%)
    
    # === RECOVERY MODE ===
    "recovery_mode_enabled": True,          # Enable recovery mode at stagnation
    "recovery_tp": 0.25,                    # Recovery mode take profit target (%)
    "spike_trigger": 1.5,                   # Profit % to revert from recovery to original TP
    "stagnation_candles": 15,               # Candles before entering recovery mode
    
    # === QUICK EXIT AT STAGNATION ===
    "quick_exit_enabled": True,             # Enable quick exit if profitable at stagnation
    "quick_exit_threshold": 0.25,           # Minimum profit (%) for quick exit
    
    # === TIME LIMITS ===
    "max_candles": 30,                      # Force exit after this many candles
    
    # === ADAPTIVE STOP LOSS ===
    "adaptive_stop_loss": False,            # Use adaptive SL based on avg bearish size
    "sl_bearish_multiplier": 2.0,           # SL = avg_bearish_body × multiplier
    "min_sl_percent": 2.0,                  # Minimum SL (%)
    "max_sl_percent": 5.0,                  # Maximum SL (%)
    
    # === DANGER BEARISH EXIT ===
    "auto_exit_large_bearish": False,       # Auto-exit if large bearish while profitable
    "exit_bearish_threshold": 2.0,          # Bearish body must be > threshold × avg
    "exit_min_profit": 0.5,                 # Minimum profit (%) required to trigger exit
}

# =============================================================================
# 5MIN SELL MONITOR - EXIT DECISION LOGIC
# =============================================================================
SELL_MONITOR_5MIN = {
    # === PROFIT TARGETS ===
    "tp_percent_orig": 6.0,                 # Original take profit target (%)
    "sl_percent_orig": 3.0,                 # Stop loss threshold (%)
    
    # === RECOVERY MODE ===
    "recovery_mode_enabled": True,          # Enable recovery mode at stagnation
    "recovery_tp": 0.25,                    # Recovery mode take profit target (%)
    "spike_trigger": 1.5,                   # Profit % to revert from recovery to original TP
    "stagnation_candles": 5,                # Candles before entering recovery (25 min)
    
    # === QUICK EXIT AT STAGNATION ===
    "quick_exit_enabled": True,             # Enable quick exit if profitable at stagnation
    "quick_exit_threshold": 0.25,           # Minimum profit (%) for quick exit
    
    # === TIME LIMITS ===
    "max_candles": 12,                      # Force exit after this many candles (60 min)
    
    # === ADAPTIVE STOP LOSS ===
    "adaptive_stop_loss": False,            # Use adaptive SL based on avg bearish size
    "sl_bearish_multiplier": 2.0,           # SL = avg_bearish_body × multiplier
    "min_sl_percent": 2.0,                  # Minimum SL (%)
    "max_sl_percent": 5.0,                  # Maximum SL (%)
    
    # === DANGER BEARISH EXIT ===
    "auto_exit_large_bearish": False,       # Auto-exit if large bearish while profitable
    "exit_bearish_threshold": 2.0,          # Bearish body must be > threshold × avg
    "exit_min_profit": 0.5,                 # Minimum profit (%) required to trigger exit
}

# =============================================================================
# REVERSAL DETECTION - PATTERN-BASED EXIT TRIGGERS
# =============================================================================
REVERSAL_DETECTION = {
    "enabled": True,                        # Master switch for reversal detection
    
    # === SHOOTING STAR ===
    "shooting_star_enabled": True,          # Bullish candle with long upper wick
    "shooting_star_min_wick_ratio": 3.0,    # Upper wick must be ≥ ratio × body
    "shooting_star_danger_ratio": 4.0,      # Ratio for severity 3 (abort) vs 1 (caution)
    "shooting_star_max_lower_wick_ratio": 0.5,  # Lower wick must be ≤ ratio × body
    
    # === HIGH WAVE DOJI (GRADUATED SEVERITY) ===
    "high_wave_enabled": True,              # Small body with long wicks both sides
    "high_wave_body_percent": 0.1,          # Body must be ≤ this % of price
    "high_wave_severity1_ratio": 2.0,       # Severity 1: 2x-4x ratio (caution)
    "high_wave_severity2_ratio": 4.0,       # Severity 2: 4x-6x ratio (danger)
    "high_wave_severity3_ratio": 6.0,       # Severity 3: >6x ratio (abort)
    
    # === GRAVESTONE DOJI ===
    "gravestone_enabled": True,             # Small body with long upper wick only
    "gravestone_body_percent": 0.1,         # Body must be ≤ this % of price
    "gravestone_min_wick_ratio": 5.0,       # Upper wick must be ≥ ratio × body
    "gravestone_max_lower_wick_ratio": 0.3, # Lower wick must be ≤ ratio × body
    
    # === BEARISH MARUBOZU ===
    "bearish_marubozu_enabled": True,       # Large bearish with minimal wicks
    "bearish_marubozu_min_loss": 0.3,       # Minimum loss (%) to qualify
    "bearish_marubozu_upper_wick_tolerance": 0.02,  # Upper wick ≤ this fraction of range
    "bearish_marubozu_no_lower_wick": True, # Require no lower wick
    
    # === BEARISH ENGULFING ===
    "bearish_engulfing_enabled": True,      # Bearish candle engulfs previous bullish
    "bearish_engulfing_min_body_ratio": 1.0,# Current body must be ≥ ratio × prev body
    
    # === DARK CLOUD COVER ===
    "dark_cloud_enabled": True,             # Gap up then close below midpoint
    "dark_cloud_min_penetration": 0.5,      # Must penetrate ≥ this fraction of prev body
    
    # === HAMMER ===
    "hammer_enabled": True,                 # Long lower wick (potential reversal after gains)
    "hammer_min_lower_wick_ratio": 2.0,     # Lower wick must be ≥ ratio × body
    "hammer_max_upper_wick_ratio": 0.5,     # Upper wick must be ≤ ratio × body
    "hammer_min_profit_threshold": 0.5,     # Only check hammer if profit ≥ this %
    
    # === ACTIONS ===
    "auto_exit_on_danger": True,            # Auto-exit on severity 3 patterns
    "reduce_tp_on_warning": False,          # Enter recovery mode on severity 2+ patterns
    "warning_cooldown_candles": 3,          # Minimum candles between duplicate warnings
}

# Alias for backward compatibility
REVERSAL_PATTERNS = REVERSAL_DETECTION.copy()

# =============================================================================
# PORTFOLIO & CAPITAL ALLOCATION
# =============================================================================
TRADING = {
    "mode": "SIMULATION",
    "total_capital": 1000.0,
    "max_positions_1min": 2,
    "max_positions_5min": 2,
    "allocation_percent_1min": 50,
    "allocation_percent_5min": 50,
    "cooldown_enabled": False,
    "cooldown_1min_candles": 2,
    "cooldown_5min_candles": 1,
}

# =============================================================================
# DUAL TIMEFRAME SETTINGS
# =============================================================================
DUAL_TIMEFRAME = {
    "allow_same_asset_both_timeframes": False,  # Can trade same asset on both timeframes
}

# =============================================================================
# BEAUTY SCORE CONFIGURATION
# =============================================================================
BEAUTY_SCORE = {
    "enabled": True,
    "weights": {
        "volatility": 30,  # Wick analysis
        "volume": 25,      # Volume progression
        "gapless": 25,     # Gap-free continuity
        "gain": 20         # Price gain brackets
    },
    "gain_range": {
        "min": 0.5,   # Below this = 0 pts
        "max": 2.5    # Above this = 0 pts (too extreme)
    },
    "gain_brackets": {
        # Documentation for the bracket system
        # 0 pts:  gain ≤ 0.5% OR gain > 2.5%
        # 5 pts:  0.5% < gain ≤ 0.75%
        # 10 pts: 0.75% < gain ≤ 1.0%
        # 20 pts: gain > 1.0% (up to 2.5%)
        "threshold_low": 0.5,
        "bracket_1": 0.75,
        "bracket_2": 1.0,
        "threshold_high": 2.5
    }
}

# =============================================================================
# SYSTEM LOGGING
# =============================================================================
LOG_TO_FILE = True
LOG_TO_CONSOLE = True
DEBUG_MODE = False