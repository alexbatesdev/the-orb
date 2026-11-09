from __future__ import annotations

import json
from importlib.resources import files


_catalog: dict[str, str] = json.loads(
    files("wisest_wizard").joinpath("locales", "en.json").read_text(encoding="utf-8")
)


def translate(key: str, **values: object) -> str:
    return _catalog[key].format(**values)
