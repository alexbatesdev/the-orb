from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from wisest_wizard.config import WisdomSettings

MAX_CHARS = 192
_PUNCTUATION = ".?!"
_TRIGRAM_SPLIT = re.compile(r"[\s.,!?]")
_REPEATED_LETTER = re.compile(r"([A-Za-z])\1\1")
_DATA_PATH = Path(__file__).parent / "data" / "trigrams_bugged.txt"

# Reproduced with permission from Hunter R.'s AC Letter Scorer.
def load_trigrams(path: Path = _DATA_PATH) -> tuple[str, ...]:
    """Load the attributed in-game trigram table once for scoring."""
    return tuple(path.read_text(encoding="utf-8").splitlines())


TRIGRAM_TABLE = load_trigrams()


def get_all_trigrams(text: str) -> tuple[str, ...]:
    trigrams: list[str] = []
    index = 0
    while index < len(text):
        while index < len(text) and _TRIGRAM_SPLIT.fullmatch(text[index]):
            index += 1
        if index < len(text):
            trigrams.append(text[index : index + 3])
            while index < len(text) and not _TRIGRAM_SPLIT.fullmatch(text[index]):
                index += 1
    return tuple(trigrams)


def check_punctuation(text: str, max_chars: int = MAX_CHARS) -> int:
    trimmed = text.strip(" \t")
    score = 20 if len(trimmed) < max_chars and trimmed.endswith(tuple(_PUNCTUATION)) else 0
    index = 0
    while index < len(text):
        punctuation_index = next(
            (position for position in range(index, len(text)) if text[position] in _PUNCTUATION),
            None,
        )
        if punctuation_index is None:
            break
        if not re.search(r"\S", text[punctuation_index + 1 :]):
            break
        if punctuation_index + 3 >= len(text):
            break
        lookahead = text[punctuation_index + 1 : punctuation_index + 4]
        capital_index = re.search(r"[A-Z]", lookahead)
        if capital_index:
            score += 10
            index = punctuation_index + 2 + capital_index.start()
        else:
            score -= 10
            index = punctuation_index + 4
    return score


def check_trigrams(text: str, trigram_table: Iterable[str] = TRIGRAM_TABLE) -> int:
    lines = tuple(trigram_table)
    score = 0
    for trigram in get_all_trigrams(text.ljust(MAX_CHARS)):
        if len(trigram) < 3:
            break
        header = f"~{trigram[0].upper()}~"
        try:
            start = next(index for index, line in enumerate(lines) if line.startswith(header))
        except StopIteration:
            continue
        ending = trigram[1:3]
        for line in lines[start + 1 :]:
            if line.startswith("~"):
                continue
            if ending in line:
                score += 3
                break
    return score


def check_leading_capital(text: str) -> int:
    first = re.search(r"\S", text)
    if first is None:
        return 0
    return 20 if "A" <= first.group() <= "Z" else -10


def check_repeated_letters(text: str) -> int:
    trimmed = text.strip(" \t").replace(" ", "")
    return -50 if _REPEATED_LETTER.search(trimmed) else 0


def check_space_ratio(text: str) -> int:
    spaces = text.count(" ")
    non_spaces = len(text) - spaces
    return 20 if non_spaces > 0 and spaces * 100 / non_spaces >= 20 else -20


def check_run_on(text: str) -> int:
    sentence_start = 0
    for index, character in enumerate(text):
        if character in _PUNCTUATION:
            if index - sentence_start >= 75:
                return -150
            sentence_start = index + 1
    return -150 if len(text) - sentence_start >= 75 else 0


def check_32_character_groups(text: str) -> int:
    trimmed = text.strip(" \t")
    score = 0
    for start in range(0, len(trimmed) // 32 * 32, 32):
        if " " not in trimmed[start : start + 32]:
            score -= 20
    return score


def raw_score(text: str, *, max_chars: int = MAX_CHARS) -> int:
    scored_text = text[:max_chars]
    return sum(
        (
            check_punctuation(scored_text, max_chars),
            check_trigrams(scored_text),
            check_leading_capital(scored_text),
            check_repeated_letters(scored_text),
            check_space_ratio(scored_text),
            check_run_on(scored_text),
            check_32_character_groups(scored_text),
        )
    )


def quality(raw: int, settings: WisdomSettings) -> float:
    normalized = min(
        1.0, max(0.0, (raw - settings.score_floor) / (settings.score_ceil - settings.score_floor))
    )
    return normalized**settings.quality_curve
