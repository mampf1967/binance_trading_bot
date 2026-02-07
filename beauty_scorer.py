"""
beauty_scorer.py - Shared Logger & Timestamp Edition
VERSION 2.3 - FIXED GAIN BRACKET SYSTEM

NEW GAIN SCORING:
- 0 pts:  Gain ≤ 0.5% OR Gain > max_gain (default 2.5%)
- 5 pts:  0.5% < Gain ≤ 0.75%
- 10 pts: 0.75% < Gain ≤ 1.0%
- 20 pts: Gain > 1.0% (up to max_gain)
"""

from typing import List, Dict, Any
from log_writer import LogWriter

# Fallback logger if the main bot doesn't pass one
default_logger = LogWriter(name="bot", log_to_file=True)

class ScoreResult(float):
    def __new__(cls, value, details):
        instance = super(ScoreResult, cls).__new__(cls, value)
        instance.details = details
        return instance

class BeautyScorer:
    VOLATILITY_WEIGHT = 30  
    VOLUME_WEIGHT     = 25  
    GAPLESS_WEIGHT    = 25  
    GAIN_WEIGHT       = 20    
    
    # Gain thresholds (configurable via config.py)
    GAIN_MIN = 0.5   # Below this = 0 points
    GAIN_MAX = 2.5   # Above this = 0 points (too extreme)

    @staticmethod
    def calculate(candles: List[Dict[str, Any]], symbol: str = "", logger=None, timestamp: str = None) -> ScoreResult:
        """
        Accepts 'logger' to share the file handle and 'timestamp' to match candle time.
        """
        if not candles or len(candles) < 2:
            return ScoreResult(0.0, "ERROR: Insufficient data.")
        
        v_score, v_log = BeautyScorer._calculate_volatility(candles)
        vol_score, vol_log = BeautyScorer._calculate_volume(candles)
        gap_score, gap_log = BeautyScorer._calculate_gapless(candles)
        gain_score, gain_log = BeautyScorer._calculate_gain(candles)
        
        total_score = round(v_score + vol_score + gap_score + gain_score, 2)
        
        log = logger if logger is not None else default_logger
        label = f"{symbol} " if symbol else ""
        
        # Every line now uses the provided timestamp (e.g., 20:11)
        log.write(f"{label}  [BEAUTY BREAKDOWN]", timestamp=timestamp)
        log.write(f"{label}    - Volatility: {v_score:g}/30 [{v_log}]", timestamp=timestamp)
        log.write(f"{label}    - Volume:     {vol_score:g}/25 [{vol_log}]", timestamp=timestamp)
        log.write(f"{label}    - Gapless:    {gap_score:g}/25 [{gap_log}]", timestamp=timestamp)
        log.write(f"{label}    - Gain:       {gain_score:g}/20 [{gain_log}]", timestamp=timestamp)
        log.write(f"{label}    >> FINAL BEAUTY SCORE: {total_score}/100", timestamp=timestamp)
        
        return ScoreResult(total_score, "Breakdown logged.")

    @staticmethod
    def _calculate_volatility(candles: List[Dict]) -> (float, str):
        points = 0.0
        details = []
        for i, c in enumerate(candles):
            tr = c['high'] - c['low']
            body = abs(c['close'] - c['open'])
            wick_pct = ((tr - body) / tr * 100) if tr > 0 else 0
            pts = 10 if wick_pct <= 20.0 else (5 if wick_pct <= 30.0 else 0)
            points += pts
            details.append(f"C{i+1}:{wick_pct:.1f}%")
        return points, "Wicks: " + " ".join(details)

    @staticmethod
    def _calculate_volume(candles: List[Dict]) -> (float, str):
        pairs = len(candles) - 1
        pts_per_step = BeautyScorer.VOLUME_WEIGHT / pairs
        score = 0.0
        vols = [f"{c['turnover']/1000:.1f}K" for c in candles]
        for i in range(pairs):
            if candles[i+1]['turnover'] >= candles[i]['turnover']:
                score += pts_per_step
        return score, "Vols: " + " < ".join(vols)

    @staticmethod
    def _calculate_gapless(candles: List[Dict]) -> (float, str):
        pairs = len(candles) - 1
        pts_per_step = BeautyScorer.GAPLESS_WEIGHT / pairs
        score = 0.0
        logs = []
        for i in range(pairs):
            if candles[i+1]['open'] >= candles[i]['close']:
                score += pts_per_step
            logs.append(f"C{i}C:{candles[i]['close']}/C{i+1}O:{candles[i+1]['open']}")
        return score, "Gaps: " + " ".join(logs)

    @staticmethod
    def _calculate_gain(candles: List[Dict]) -> (float, str):
        """
        NEW BRACKET SYSTEM:
        - 0 pts:  gain ≤ 0.5% OR gain > max_gain (default 2.5%)
        - 5 pts:  0.5% < gain ≤ 0.75%
        - 10 pts: 0.75% < gain ≤ 1.0%
        - 20 pts: gain > 1.0% (up to max_gain)
        """
        f_open, l_close = candles[0]['open'], candles[-1]['close']
        gain = ((l_close - f_open) / f_open) * 100
        
        score = 0.0
        bracket = "Below threshold"
        
        if gain <= BeautyScorer.GAIN_MIN:
            score = 0.0
            bracket = f"≤{BeautyScorer.GAIN_MIN}%"
        elif gain > BeautyScorer.GAIN_MAX:
            score = 0.0
            bracket = f">{BeautyScorer.GAIN_MAX}% (too extreme)"
        elif gain <= 0.75:
            score = 5.0
            bracket = "0.5-0.75%"
        elif gain <= 1.0:
            score = 10.0
            bracket = "0.75-1.0%"
        else:  # gain > 1.0 and <= GAIN_MAX
            score = 20.0
            bracket = ">1.0%"
        
        return score, f"{gain:.2f}% [{bracket}]"

    @staticmethod
    def format_score(score: Any) -> str:
        try:
            return f"B:{float(score):.0f}"
        except:
            return "B:ERR"
