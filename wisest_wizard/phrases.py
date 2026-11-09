from __future__ import annotations

import re
from collections.abc import Mapping

from discord.ext import commands


def match_phrase(
    content: str, registered: Mapping[str, commands.Command]
) -> tuple[commands.Command, str, int] | None:
    words = list(re.finditer(r"\S+", content))
    if not words or words[0].start() != 0:
        return None

    match = None
    longest = 0
    for phrase, command in registered.items():
        parts = phrase.split()
        if len(parts) <= longest or len(parts) > len(words):
            continue
        if all(part.lower() == word.group().lower() for part, word in zip(parts, words)):
            end = words[len(parts) - 1].end()
            match = command, content[:end], end
            longest = len(parts)
    return match
