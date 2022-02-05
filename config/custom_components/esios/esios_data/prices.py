"""ESIOS API handler for HomeAssistant. Hourly price attributes."""
from datetime import datetime
from typing import Any, Dict, Tuple
import zoneinfo


def _is_tomorrow_price(ts: datetime, ref: datetime) -> bool:
    return any(map(lambda x: x[0] > x[1], zip(ts.isocalendar(), ref.isocalendar())))


def _split_today_tomorrow_prices(
    current_prices: Dict[datetime, float],
    utc_time: datetime,
    timezone: zoneinfo.ZoneInfo,
) -> Tuple[Dict[datetime, float], Dict[datetime, float]]:
    local_time = utc_time.astimezone(timezone)
    today, tomorrow = {}, {}
    for ts_utc, price_h in current_prices.items():
        ts_local = ts_utc.astimezone(timezone)
        if _is_tomorrow_price(ts_local, local_time):
            tomorrow[ts_utc] = price_h
        else:
            today[ts_utc] = price_h
    return today, tomorrow


def _make_price_tag_attributes(
    prices: Dict[datetime, float], timezone: zoneinfo.ZoneInfo, tomorrow: bool
) -> Dict[str, Any]:
    prefix = "price_next_day_" if tomorrow else "price_"
    attributes = {}
    for ts_utc, price_h in prices.items():
        ts_local = ts_utc.astimezone(timezone)
        attr_key = f"{prefix}{ts_local.hour:02d}h"
        if attr_key in attributes:  # DST change with duplicated hour :)
            attr_key += "_d"
        attributes[attr_key] = price_h
    return attributes


def _make_price_stats_attributes(
    current_price: float,
    current_prices: Dict[datetime, float],
    utc_time: datetime,
    timezone: zoneinfo.ZoneInfo,
) -> Dict[str, Any]:
    attributes: Dict[str, Any] = {}
    better_prices_ahead = [
        (ts, price)
        for ts, price in current_prices.items()
        if ts > utc_time and price < current_price
    ]
    if better_prices_ahead:
        next_better_ts, next_better_price = better_prices_ahead[0]
        delta_better = next_better_ts - utc_time
        attributes["next_better_price"] = next_better_price
        attributes["hours_to_better_price"] = int(delta_better.total_seconds()) // 3600
        attributes["num_better_prices_ahead"] = len(better_prices_ahead)

    prices_sorted = dict(sorted(current_prices.items(), key=lambda x: x[1]))
    try:
        attributes["price_position"] = (
            list(prices_sorted.values()).index(current_price) + 1
        )
    except ValueError:
        pass

    max_price = max(current_prices.values())
    min_price = min(current_prices.values())
    try:
        attributes["price_ratio"] = round(
            (current_price - min_price) / (max_price - min_price), 2
        )
    except ZeroDivisionError:  # pragma: no cover
        pass
    attributes["max_price"] = max_price
    attributes["max_price_at"] = (
        next(iter(reversed(prices_sorted))).astimezone(timezone).hour
    )
    attributes["min_price"] = min_price
    attributes["min_price_at"] = next(iter(prices_sorted)).astimezone(timezone).hour
    attributes["next_best_at"] = list(
        map(
            lambda x: x.astimezone(timezone).hour,
            filter(lambda x: x >= utc_time, prices_sorted.keys()),
        )
    )
    return attributes


def make_price_sensor_attributes(
    current_prices: Dict[datetime, float],
    utc_time: datetime,
    timezone: zoneinfo.ZoneInfo,
) -> Dict[str, Any]:
    """Generate sensor attributes for hourly prices variables."""
    current_price = current_prices[utc_time]
    today, tomorrow = _split_today_tomorrow_prices(current_prices, utc_time, timezone)
    price_attrs = _make_price_stats_attributes(current_price, today, utc_time, timezone)
    price_tags = _make_price_tag_attributes(today, timezone, False)
    if tomorrow:
        tomorrow_prices = {
            f"{key} (next day)": value
            for key, value in _make_price_stats_attributes(
                current_price, tomorrow, utc_time, timezone
            ).items()
        }
        tomorrow_price_tags = _make_price_tag_attributes(tomorrow, timezone, True)
        price_attrs = {**price_attrs, **tomorrow_prices}
        price_tags = {**price_tags, **tomorrow_price_tags}
    return {**price_attrs, **price_tags}
