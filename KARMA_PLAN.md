# Karma System Plan

Plan only. Nothing here is implemented yet.

## Approach
Track per-guild, per-user karma in SQLite, keyed on Discord user IDs. Each message is graded with the Animal Crossing (GameCube, North American) letter algorithm, the grade is normalized to 0..1, and that nudges the user's karma (also 0..1) upward. Decay is linear after a grace period and computed lazily from timestamps, so no background job is needed. Every tunable number lives in one config block.

## Decisions
- **Identity:** `(guild_id, user_id)` from `message.guild.id` and `message.author.id`. Ignore bots and DMs.
- **Storage:** SQLite via `aiosqlite`. Table `karma(guild_id, user_id, value REAL, last_active REAL, last_scored REAL, PRIMARY KEY(guild_id, user_id))`. `value` is always in 0..1.
- **Scored text:** only the first 192 characters of the message (the in-game letter limit). The rest is ignored.
- **Cooldown:** a message earns karma at most once per 30 seconds per user (`COOLDOWN_SECONDS`).
- **Listener:** `@bot.listen("on_message")`, so commands keep working.
- **Command:** `cast karma` shows the current (decayed) karma.

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

- Data file `data/trigrams_bugged.txt`: lines starting with `~X~` begin the section for first letter `X`. Other lines list the valid 2-character endings.
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
2. **Karma update:** `karma += GAIN * q * (1 - karma)`
   - `GAIN` default 0.02, the fraction of the remaining gap closed by a perfect message.
   - The `(1 - karma)` factor gives diminishing returns, so karma approaches 1 but never exceeds it. A user needs sustained good messages to stay high.

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
- On a new message: apply decay first, then add the gain, then set `last_active = now`.
- Only karma-earning messages reset `last_active` by default. The flag `REFRESH_ON_ANY_MESSAGE` changes that.

## Tunables (single config block, env-overridable)
| Name | Default | Meaning |
|---|---|---|
| `MAX_CHARS` | 192 | Characters of each message that get scored |
| `COOLDOWN_SECONDS` | 30 | Minimum gap between karma-earning messages per user |
| `SCORE_FLOOR` | 0 | Raw score that maps to q = 0 |
| `SCORE_CEIL` | 100 | Raw score that maps to q = 1 |
| `QUALITY_CURVE` | 1.0 | Exponent shaping q |
| `GAIN` | 0.02 | Fraction of the remaining gap closed per perfect message |
| `GRACE_DAYS` | 7 | Idle days before decay starts |
| `DECAY_PER_DAY` | 0.02 | Karma lost per idle day after the grace period |
| `REFRESH_ON_ANY_MESSAGE` | false | Whether non-earning messages reset the idle timer |

## Todos
1. `data/trigrams_bugged.txt` and a loader (table comes from Hunter's repo, with credit).
2. `scoring.py`: `raw_score(text) -> int` (checks A-G with the bugged trigram lookup) and `quality(raw) -> float`. Pure functions, unit-testable.
3. `config.py`: the tunables above, read from env with defaults.
4. `karma.py`: SQLite schema, upsert, lazy decay, gain update, cooldown.
5. `bot.py`: `on_message` listener and `cast karma` command. Add `aiosqlite` with `uv add aiosqlite`.
6. Tests (pytest): each check A-G, the bugged trigram behavior, normalization edges, decay with grace period, cooldown. Cross-check some raw scores against Hunter's web scorer.
7. `.gitignore`: add the `.db` file.

## Notes
- Lazy decay means bot downtime never skips decay.
- A user's stored value is only rewritten when they send a message. Their displayed value is always the decayed one.
- After running for a while, look at the real distribution of raw scores on your server, then tune `SCORE_CEIL`, `GAIN` and `DECAY_PER_DAY` to taste.
