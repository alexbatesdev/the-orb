# Karma System Plan

## Approach
Track per-guild, per-user wisdom in SQLite, keyed on Discord user IDs. Each human server message, including command messages, is graded with the Animal Crossing (GameCube, North American) letter algorithm. Its normalized quality is in 0..1 and adds points to an unbounded wisdom total. Decay is linear after a grace period and computed lazily from timestamps, so no background job is needed. Every tunable number lives in one config block.

## Decisions
- **Identity:** `(guild_id, user_id)` from `message.guild.id` and `message.author.id`. Ignore bots and DMs.
- **Storage:** SQLite via `aiosqlite`. Wisdom is stored per `(guild_id, user_id)` with its last activity timestamp. The total is an unbounded, nonnegative float.
- **Scored text:** only the first 192 characters of the message (the in-game letter limit). The rest is ignored.
- **Cooldown:** positive-quality messages earn wisdom at most once per configured interval per guild/user (`WISDOM_MESSAGE_COOLDOWN_SECONDS`, default 1 second). Zero-quality messages do not consume it.
- **Listener:** `@bot.listen("on_message")`, so commands keep working.
- **Command:** `i cast check wisdom` shows the caller's current (decayed) wisdom as a number, not a percentage.

## Letter scoring (raw score)
Source: Hunter R., "How Villagers 'Read' Your Letters in Animal Crossing" (8VbwWVvw-zI) and "Further Exploiting Animal Crossing's Letter System" (mleA6tW_7To), cross-checked against his scorer, https://github.com/HunterRDev/AC-Letter-Scorer (`letter_scorer.js`). The raw score is the sum of seven checks, run on the first 192 characters:

| Check | Rule |
|---|---|
| A. Punctuation | For each `.` `?` `!`, look at the next 3 characters: a capital letter = +10, none = -10 (skipped if nothing follows). Letter ends with `.` `?` `!` = +20. |
| B. Trigrams | Take the first 3 characters of each word (words split on whitespace and `. , ! ?`). Each one in the trigram table = +3. |
| C. Leading capital | First non-space character is capital = +20, otherwise -10. |
| D. Repeats | Any letter A-Z repeated 3 or more times in a row (spaces removed) = -50, once. |
| E. Space ratio | `spaces * 100 / non_spaces >= 20` = +20, otherwise -20 (all spaces = -20). |
| F. Run-on | No punctuation within 75 characters of a sentence start = -150, once. |
| G. 32-character groups | Each full 32-character chunk with no space = -20. |

In the game, 100 or more is a good reply and under 50 is a bad one. The theoretical max is about 936 (spamming `X.` pairs), so the raw range is roughly -300 to 936. Real chat messages mostly land between -100 and 150.

### Trigram table: recreate the bug
The NA game forgot the stop characters in its trigram lists. A lookup that fails scans past the table and keeps reading, so about 23,000 trigrams count as valid instead of the intended 776. We recreate this on purpose.

- Data file `wisest_wizard/data/trigrams_bugged.txt`: lines starting with `~X~` begin the section for first letter `X`. Other lines list the valid 2-character endings.
- Lookup for a word: uppercase its first letter, find that header, then scan every following line, **skipping other headers instead of stopping** (this is the bug), and count a hit if any line contains the word's last two characters.
- Load once at startup into memory.
- Port the behavior exactly from `letter_scorer.js` (`checkB`, `getAllTrigrams`), then cross-check scores against his web tool on a set of sample strings.
- Licensing: his repo has no license file. Credit him in a comment and the README, and consider messaging him before publishing the bot. For a private server this is low risk.

## Normalizing to 0..1
Two steps, both tunable:

1. **Quality** `q` in 0..1 from the raw score `s`:
   - `q = clamp((s - SCORE_FLOOR) / (SCORE_CEIL - SCORE_FLOOR), 0, 1) ** QUALITY_CURVE`
   - `SCORE_FLOOR` default 0 (anything at or below this earns nothing).
   - `SCORE_CEIL` default 100 (the game's "good letter" line earns the full amount).
   - `QUALITY_CURVE` default 1.0 (linear). Above 1 favors really good messages, below 1 is more generous.
2. **Wisdom update:** `wisdom += GAIN * q`
   - `GAIN` default 0.02 points per perfect message.
   - Wisdom accumulates without an upper bound; message quality still scales each addition from zero to `GAIN`.

Knobs to start with: `SCORE_FLOOR`, `SCORE_CEIL`, `GAIN` (and optionally `QUALITY_CURVE`).

## Decay
Linear after a grace period, applied lazily on every read and write:

```
idle_days  = (now - last_active) / 86400
decay_days = max(0, idle_days - GRACE_DAYS)
value      = max(0, value - DECAY_PER_DAY * decay_days)
```

- `GRACE_DAYS` default **7**.
- `DECAY_PER_DAY` default 0.02 (about 50 days to fall from 1.0 to 0 after the grace period). Placeholder value, since we don't know how it will feel yet.
- On an earning message: apply decay first, then add the gain, then set `last_active = now`.
- Only karma-earning messages reset `last_active` by default. The flag `REFRESH_ON_ANY_MESSAGE` changes that.
- Direct reputation and centralized reward grants also apply decay before updating the total and reset the activity timestamp.

## Tunables (single config block, env-overridable)
| Name | Default | Meaning |
|---|---|---|
| `WISDOM_MAX_CHARS` | 192 | Characters of each message that get scored |
| `WISDOM_MESSAGE_COOLDOWN_SECONDS` | 1 | Minimum gap between positive-quality messages per guild/user |
| `WISDOM_SCORE_FLOOR` | 0 | Raw score that maps to q = 0 |
| `WISDOM_SCORE_CEIL` | 100 | Raw score that maps to q = 1 |
| `WISDOM_QUALITY_CURVE` | 1.0 | Exponent shaping q |
| `WISDOM_GAIN` | 0.02 | Points added for a perfect message |
| `WISDOM_GRACE_DAYS` | 7 | Idle days before decay starts |
| `WISDOM_DECAY_PER_DAY` | 0.02 | Wisdom lost per idle day after the grace period |
| `WISDOM_REFRESH_ON_ANY_MESSAGE` | false | Whether non-earning messages reset the idle timer |
| `WISDOM_REPUTATION_COOLDOWN_SECONDS` | 86400 | Shared per-giver rep cooldown |
| `WISDOM_REPUTATION_CHANGE` | 1 | Points changed by `+rep` or `-rep` |
| `WISDOM_REWARD_COOLDOWN_SECONDS` | 86400 | Per-event-type cross-system reward limit |
| `WISDOM_REWARD_GAIN` | 0.02 | Points added by a configured cross-system reward |

## Todos
1. `wisest_wizard/data/trigrams_bugged.txt` and its loader (included with permission and attribution to Hunter R.).
2. `wisest_wizard/scoring.py`: `raw_score(text) -> int` (checks A-G with the bugged trigram lookup) and `quality(raw) -> float`. Pure functions, unit-testable.
3. `wisest_wizard/config.py`: the tunables above, read from env with defaults.
4. `wisest_wizard/services/wisdom.py`: SQLite persistence, lazy decay, additive gains, rep, and centralized rewards.
5. Wisdom cog: `on_message` listener, `i cast check wisdom`, and shared-cooldown `i cast +rep` / `i cast -rep` with member name lookup.
6. Tests: each check A-G, the bugged trigram behavior, normalization edges, decay with grace period, cooldown, reputation, and centralized rewards.

## Notes
- Lazy decay means bot downtime never skips decay.
- A user's stored value is only rewritten when they earn wisdom or `REFRESH_ON_ANY_MESSAGE` is enabled. Their displayed value is always the decayed one.
- After running for a while, look at the real distribution of raw scores on your server, then tune `SCORE_CEIL`, `GAIN` and `DECAY_PER_DAY` to taste.
