from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import AverageTrueRange


@dataclass
class TechnicalSnapshot:
    market: dict[str, Any]
    missing_data: list[str]


def _latest_number(series: pd.Series) -> float | None:
    clean = series.dropna()
    if clean.empty:
        return None
    return round(float(clean.iloc[-1]), 2)


def _round_or_none(value: float | None) -> float | None:
    return None if value is None else round(float(value), 2)


def normalize_candles(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return raw

    frame = raw.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = [str(column[0]).lower().replace(" ", "_") for column in frame.columns]
    else:
        frame.columns = [str(column).lower().replace(" ", "_") for column in frame.columns]

    rename_map = {"adj_close": "adjusted_close"}
    frame = frame.rename(columns=rename_map)
    if "adjusted_close" not in frame.columns and "close" in frame.columns:
        frame["adjusted_close"] = frame["close"]

    required = ["open", "high", "low", "close", "adjusted_close", "volume"]
    existing = [column for column in required if column in frame.columns]
    frame = frame[existing].dropna(subset=["open", "high", "low", "close"])
    frame.index = pd.to_datetime(frame.index)
    return frame.sort_index()


def candles_to_records(candles: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, row in candles.iterrows():
        records.append(
            {
                "date": index.date().isoformat(),
                "open": round(float(row["open"]), 4),
                "high": round(float(row["high"]), 4),
                "low": round(float(row["low"]), 4),
                "close": round(float(row["close"]), 4),
                "adjusted_close": round(float(row.get("adjusted_close", row["close"])), 4),
                "volume": int(row.get("volume", 0) or 0),
                "source": "yfinance",
            }
        )
    return records


def calculate_technicals(candles: pd.DataFrame) -> TechnicalSnapshot:
    missing_data: list[str] = []
    if candles.empty:
        return TechnicalSnapshot(market={}, missing_data=["No yfinance candles returned"])

    count = len(candles)
    close = candles["close"]
    high = candles["high"]
    low = candles["low"]
    volume = candles["volume"] if "volume" in candles else pd.Series(dtype=float)

    ma_20 = _latest_number(close.rolling(20).mean()) if count >= 20 else None
    ma_50 = _latest_number(close.rolling(50).mean()) if count >= 50 else None
    ma_200 = _latest_number(close.rolling(200).mean()) if count >= 200 else None
    if ma_20 is None:
        missing_data.append("20-day moving average requires at least 20 daily candles")
    if ma_50 is None:
        missing_data.append("50-day moving average requires at least 50 daily candles")
    if ma_200 is None:
        missing_data.append("200-day moving average requires at least 200 daily candles")

    rsi = _latest_number(RSIIndicator(close=close, window=14).rsi()) if count >= 14 else None
    if rsi is None:
        missing_data.append("RSI requires at least 14 candles")

    macd_direction = "unknown"
    if count >= 35:
        macd = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
        macd_line = _latest_number(macd.macd())
        macd_signal = _latest_number(macd.macd_signal())
        if macd_line is not None and macd_signal is not None:
            macd_direction = "positive" if macd_line >= macd_signal else "negative"
    else:
        missing_data.append("MACD requires at least 35 candles")

    atr_percent = None
    if count >= 14:
        atr = _latest_number(AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range())
        latest_close = float(close.iloc[-1])
        atr_percent = round((atr / latest_close) * 100, 2) if atr and latest_close else None

    if count >= 20 and not volume.empty:
        avg_volume = float(volume.tail(20).mean())
        relative_volume = round(float(volume.iloc[-1]) / avg_volume, 2) if avg_volume else 0.0
    else:
        relative_volume = 0.0
        missing_data.append("Relative volume needs at least 20 volume candles")

    if count >= 60:
        recent = candles.tail(60)
        support_levels = sorted([round(float(value), 2) for value in recent["low"].nsmallest(2).tolist()])
        resistance_levels = sorted([round(float(value), 2) for value in recent["high"].nlargest(2).tolist()])
    else:
        support_levels = []
        resistance_levels = []
        missing_data.append("Support and resistance need at least 60 candles")

    recent_gaps: list[str] = []
    gap_window = candles.tail(10)
    for previous, current in zip(gap_window.iloc[:-1].itertuples(), gap_window.iloc[1:].itertuples()):
        previous_close = float(previous.close)
        current_open = float(current.open)
        if previous_close and abs((current_open - previous_close) / previous_close) >= 0.03:
            direction = "higher" if current_open > previous_close else "lower"
            recent_gaps.append(f"Recent gap {direction} of {round(((current_open - previous_close) / previous_close) * 100, 2)}%.")

    previous_close = float(close.iloc[-2]) if count >= 2 else float(close.iloc[-1])
    market = {
        "current_price": round(float(close.iloc[-1]), 2),
        "previous_close": round(previous_close, 2),
        "ma_20": ma_20,
        "ma_50": ma_50,
        "ma_200": ma_200,
        "rsi": rsi,
        "macd_direction": macd_direction,
        "relative_volume": relative_volume,
        "atr_percent": _round_or_none(atr_percent),
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "recent_gaps": recent_gaps,
        "candle_count": count,
        "last_candle_date": candles.index[-1].date().isoformat(),
        "data_source": "yfinance",
    }
    return TechnicalSnapshot(market=market, missing_data=missing_data)

