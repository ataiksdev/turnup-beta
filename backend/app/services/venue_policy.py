"""Refund presets (docs/venues-spec.md 4.3).

Each preset is a list of (days_before_start, percent_refunded) steps, checked from the
longest notice down. Admins can override them with PlatformSettings.refund_presets (JSON of
the same shape).
"""
import json
from datetime import datetime

DEFAULT_PRESETS: dict[str, list[tuple[float, int]]] = {
    "flexible": [(7, 100), (2, 50), (0, 0)],
    "moderate": [(30, 100), (7, 50), (0, 0)],
    "strict": [(60, 100), (30, 50), (0, 0)],
}
PRESET_LABELS = {
    "flexible": "Flexible: full refund 7+ days before, 50% from 2 to 7 days, nothing within 48 hours",
    "moderate": "Moderate: full refund 30+ days before, 50% from 7 to 30 days, nothing within 7 days",
    "strict": "Strict: full refund 60+ days before, 50% from 30 to 60 days, nothing within 30 days",
}


def presets(override_json: str | None = None) -> dict[str, list[tuple[float, int]]]:
    if override_json:
        try:
            data = json.loads(override_json)
            return {k: [(float(d), int(p)) for d, p in v] for k, v in data.items()} | {
                k: v for k, v in DEFAULT_PRESETS.items() if k not in data}
        except (ValueError, TypeError):
            pass
    return DEFAULT_PRESETS


def refund_percent(preset: str, starts_at: datetime, now: datetime,
                   override_json: str | None = None) -> int:
    days_before = (starts_at - now).total_seconds() / 86400
    for min_days, pct in presets(override_json).get(preset, DEFAULT_PRESETS["moderate"]):
        if days_before >= min_days:
            return pct
    return 0


def refund_amount(paid_kobo: int, preset: str, starts_at: datetime, now: datetime,
                  override_json: str | None = None) -> tuple[int, int]:
    pct = refund_percent(preset, starts_at, now, override_json)
    return pct, paid_kobo * pct // 100
