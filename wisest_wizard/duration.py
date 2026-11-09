from __future__ import annotations

import math

from wisest_wizard.i18n import translate


def format_duration(seconds: float) -> str:
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Duration must be a finite nonnegative number of seconds.")

    total = math.ceil(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, seconds_left = divmod(remainder, 60)
    parts = []
    if hours:
        if hours == 1:
            parts.append(translate("duration.hour.one", count=hours))
        else:
            parts.append(translate("duration.hour.other", count=hours))
    if minutes:
        if minutes == 1:
            parts.append(translate("duration.minute.one", count=minutes))
        else:
            parts.append(translate("duration.minute.other", count=minutes))
    if seconds_left or not parts:
        if seconds_left == 1:
            parts.append(translate("duration.second.one", count=seconds_left))
        else:
            parts.append(translate("duration.second.other", count=seconds_left))
    return translate("duration.separator").join(parts)
