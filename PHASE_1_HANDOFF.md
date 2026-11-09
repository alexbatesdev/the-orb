# Phase 1 Agent Handoff: Wisdom / Karma

## Objective

Implement Phase 1 from [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md), using
[KARMA_PLAN.md](./KARMA_PLAN.md) as the detailed message-scoring design and
[DECISIONS.md](./DECISIONS.md) for cross-system requirements. Deliver working
features, migrations, tests, and directly related documentation. Do not start
Phase 2 inventory or economy work.

Phase 1 includes:

- Animal Crossing letter scoring, normalization, persistent per-guild wisdom,
  message cooldown, lazy inactivity decay, and `cast karma`.
- `+rep` / `-rep`, their shared daily cooldown, anti-abuse protections, and an
  auditable reputation ledger.
- A centralized wisdom reward service and typed source/event metadata contract
  that later item, crafting, game, dungeon, and daily-reward features can call.
- Source-specific cooldowns, diminishing returns, or activity limits where
  needed to prevent repeated interactions from farming rewards.

## Existing foundation and integration requirements

- The bot is now a Python package. Keep bot startup in
  `wisest_wizard/app.py`; put commands/listeners in cogs under
  `wisest_wizard/cogs/`. Keep `python bot.py` and `python -m wisest_wizard`
  working.
- Shared settings are in `wisest_wizard/config.py`. Add validated wisdom
  settings there rather than creating a second configuration-loading path.
- SQLite is accessed through `Database` in `wisest_wizard/database.py`. Add
  new schema through a new ordered migration (for example
  `0002_wisdom.sql`); do not edit `0001_foundation.sql`.
- Use `Database.transaction()` for writes that must succeed together. The
  transaction helper serializes work on the current bot process's shared
  connection. The generic persistent cooldown service is in
  `wisest_wizard/services/cooldowns.py`; its current `acquire()` opens its own
  transaction, so it cannot by itself make cooldown acquisition atomic with a
  wisdom update.
- `InteractionEvent` and `InteractionEventType` are in
  `wisest_wizard/services/events.py`. Extend this bounded contract as needed;
  do not add a generic event/outbox table without a concrete reliability need.
- `AuditService` is for general administrative/economy audit records. The
  reputation ledger has its own user-facing domain and should not be conflated
  with, or silently substituted by, the generic audit log.
- Preserve `cast hello`, `i cast hello`, and command processing. Register
  message handling as a listener/cog listener, not an `on_message` override
  that suppresses command processing.
- Do not persist message contents in wisdom, cooldown, event, or ledger records.

## Required design decision: message cooldown and transaction

There must be exactly one source of truth for the message-scoring cooldown.
`KARMA_PLAN.md` currently proposes both `last_scored` on the karma row and a
generic persistent cooldown service. Do not implement both as competing
cooldowns.

Preferred integration: use the shared named-key cooldown (`wisdom.message`,
user scope, including the guild ID) and add a transaction-aware acquisition
operation so cooldown consumption and the karma read/decay/gain/write happen in
one `Database.transaction()`. If a different source of truth is chosen, explain
why and update the schema/design so there is still one atomic operation. A
failure must not consume a cooldown without the corresponding committed
processing result, and concurrent messages must not lose updates.

Positive-quality messages consume the configured message cooldown. A
zero-quality message does not consume it.

## Functional requirements

### Message wisdom

- Ignore direct messages and bot authors.
- Identify users by `(guild_id, user_id)`; constrain message cooldown to the
  same guild/user.
- Score only the first `MAX_CHARS` characters (default 192).
- Implement all seven checks and the documented bug-compatible trigram lookup;
  keep scoring and normalization pure and unit-testable.
- Validate configuration (including impossible ranges, non-finite numbers,
  and non-positive curve/ceiling values) at startup with clear errors.
- Keep stored/displayed wisdom unbounded above and nonnegative; decay lazily on
  reads and writes using the configured grace period and rate. A clock moving
  backwards must never cause negative decay or increase wisdom.
- Only earning messages reset `last_active` unless
  `REFRESH_ON_ANY_MESSAGE` is enabled.
- `cast karma` shows only the caller's current decayed numeric value, with no
  percentage or other-member lookup; a user with no row starts at zero.

### Reputation and shared rewards

- Implement `+rep` and `-rep` with one shared per-giver daily cooldown across
  both commands, as specified in the existing backlog. Persist changes and
  ledger entries atomically.
- Allow reputation only for current server members; prevent self-reputation,
  bot targets, DMs, repeated/invalid targets, and other straightforward abuse
  paths. `+rep` adds one point; `-rep` removes one point without taking wisdom
  below zero.
- Add a centralized reward service for future cross-system grants. Each grant
  must identify its source/context, enforce its configured anti-abuse policy,
  and record the grant in a ledger. Repeated calls/events must not bypass the
  same source limit.
- Do not invent item, crafting, game, or dungeon rewards in Phase 1; expose the
  service/contracts those later phases will use.

## Resolved product decisions

- Score all human server messages, including `cast` commands.
- Only positive-quality messages consume the configurable message cooldown.
  Its initial default is one second for local tuning.
- `+rep` / `-rep` target current human server members only. They share a
  per-giver, per-server 24-hour cooldown.
- `cast karma` displays the caller's unbounded wisdom as a numeric float only.
- Permission to include and attribute the trigram data was confirmed. The
  table is credited in setup documentation; no source JavaScript is copied.

The settings defaults are `MAX_CHARS=192`, `WISDOM_MESSAGE_COOLDOWN_SECONDS=1`,
`SCORE_FLOOR=0`, `SCORE_CEIL=100`, `QUALITY_CURVE=1.0`, `GAIN=0.02`,
`GRACE_DAYS=7`, `DECAY_PER_DAY=0.02`, and
`REFRESH_ON_ANY_MESSAGE=false`. Wisdom uses additive, unbounded gains rather
than the earlier capped 0..1 formula.

## Test and acceptance checklist

Add focused tests alongside implementation. The existing foundation suite
must continue to pass with `uv run python -m unittest discover -v`.

### Scoring and normalization

- Cover every rule A–G independently, plus combinations where checks interact.
- Include empty and whitespace-only text; punctuation at the beginning/end and
  at 3-character lookahead boundaries; lowercase/uppercase after punctuation;
  repeated letters with spaces removed; all-space and zero-space ratios;
  75-character run-on boundaries; exact 32-character groups and multiple
  groups; Unicode input; and text truncation at 192 characters.
- Test trigram section lookup, the intentional cross-section scan behavior,
  missing headers, line endings, and repeated trigram hits according to the
  reference behavior.
- Cross-check a representative set of raw scores against the cited scorer/tool
  where permitted; keep expected score fixtures and provenance in tests/docs.
- Test normalization at/below floor, at/above ceiling, between bounds, and
  invalid configuration; test curve/gain boundaries and assert wisdom can
  exceed 1 while remaining nonnegative.

### Persistence, decay, and cooldown

- Test a new user, a read without row creation (if that is the chosen behavior),
  a successful grant, a zero-quality result, and a transaction rollback.
- Test decay immediately before, exactly at, and immediately after the grace
  boundary; clamp at zero; ensure future timestamps/clock rollback do not
  produce negative decay or increase value.
- Test earning versus non-earning messages with both values of
  `REFRESH_ON_ANY_MESSAGE`.
- Test just-before, exactly-at, and just-after cooldown expiry; isolation
  between users and guilds; and concurrent same-user attempts.
- Prove cooldown and karma are atomic: a failed update cannot consume cooldown,
  and simultaneous events cannot grant twice or overwrite one another.

### Discord and reputation behavior

- Test DMs and bot authors are ignored, and decide/test command-message
  eligibility from the product answer.
- Verify the message listener does not break `cast hello` or `i cast hello`.
- Test `+rep` / `-rep` shared cooldown, self-target and bot-target rejection,
  repeated attempts, ledger correctness, and atomic rollback.
- Test reward-service source limits, duplicate/repeated interactions, and
  ledger attribution without storing message content.

## Delivery

- Update `.env.example` and setup documentation for validated wisdom settings.
- Add migrations and tests; preserve all existing startup and health behavior.
- Report the product questions answered, any unresolved licensing constraint,
  migration/schema choices, and exact test commands/results in the completion
  summary.
- Do not commit unless explicitly requested.
