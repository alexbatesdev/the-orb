# Implementation Plan

This is a planning document. It describes the intended implementation order
without committing to exact command names, schemas, or timelines.

The project is a personal Discord bot for one server. The phases are ordered
around reusable foundations and feature dependencies rather than the order in
the feature backlog.

## Difficulty scale

- **1/5 — Small:** A mostly self-contained command or utility.
- **2/5 — Moderate:** A command with validation, permissions, or a small
  external integration.
- **3/5 — Substantial:** Persistence, multiple commands, or time-dependent
  behavior.
- **4/5 — Complex:** Multiple systems, Discord interaction state, or significant
  abuse/error handling.
- **5/5 — Major subsystem:** A game or system with substantial state, testing,
  and balancing requirements.

## Phase 0: Bot and persistence foundation

**Goal:** Establish the infrastructure that every later phase can use.

**Difficulty: 3/5**

- Organize commands into modules/cogs.
- Add SQLite persistence and migrations.
- Add transaction helpers for atomic updates.
- Add configuration loading and validation.
- Add shared permission checks.
- Add persistent cooldowns.
- Add common command error handling.
- Add audit logging for administrative and economy actions.
- Add a persistent scheduled-effect framework for future delayed spells.

This phase should remain small and should not include user-facing gameplay
beyond basic health/diagnostic commands.

## Phase 1: Wisdom / karma

**Goal:** Implement the first persistent progression system.

**Difficulty: 4/5**

- Port the Animal Crossing letter scoring algorithm.
- Add the bugged trigram table and lookup behavior.
- Add unit tests for each scoring rule.
- Store per-user wisdom.
- Apply cooldowns and lazy inactivity decay.
- Add the wisdom display command.
- Add `+rep` and `-rep`.
- Add abuse protections and an auditable reputation ledger.
- Ignore bots and direct messages.

The detailed technical design lives in
[KARMA_PLAN.md](./KARMA_PLAN.md).

## Phase 2: Item and inventory core

**Goal:** Build the item system early so later spells, rewards, and gameplay can
use it.

**Difficulty: 4/5**

- Define global item definitions.
- Support stackable inventory quantities by default.
- Support unique item instances when an item stores state.
- Add inventory display.
- Add item giving.
- Add item tossing.
- Add item use.
- Add atomic inventory transfers.
- Add item cooldowns and consumption rules.
- Add basic admin spawn and destroy commands.
- Add item transaction logging.
- Define craftable item recipes.
- Consume crafting ingredients atomically.
- Produce stackable or unique crafted items.
- Support optional crafting duration.
- Add crafted item values.
- Start with a small recipe set, including potion-like items.

The first items should be simple and useful for testing:

- Orb
- Fortune item
- Security scroll
- Wisdom-granting item
- Basic spell tome

Item behavior should use safe, data-driven actions where possible, with
controlled handlers for complex effects. Arbitrary Python code must not execute
from item data.

## Phase 3: Purgatory and item-powered fun

**Goal:** Add the bot's core wizard theme and simple entertainment features
around the item system.

**Difficulty: 3/5**

### Purgatory mechanics

- Banish users to the abyss.
- Unbanish users.
- Create and manage the banished role.
- Restrict banished users to the abyss channel.
- Add pocket dimensions as temporary threads.
- Add the giant gold statue and its role effect.
- Add colored robes and role-color handling.

### Item-powered spells

- Spell tomes and command unlocks.
- Orb visions.
- Security scroll.
- Fortune effects.
- Wisdom and gold rewards from item effects.
- Basic role-granting items.

### Simple fun spells and utilities

- Roll
- Coinflip
- Ponder
- Read fortune
- Summon cat
- Explosion
- Uwu
- Timestamp
- Up thumber
- Down thumber
- Dither
- Basic games such as guess-the-number and tic-tac-toe

The most advanced delayed spell, magic missile, should wait until the
persistent scheduler has been exercised by simpler delayed effects.

## Phase 4: Gold economy and daily rewards

**Goal:** Add the second progression currency and the basic reward loop.

**Difficulty: 3/5**

- Add gold balances.
- Add a gold transaction ledger.
- Add the gold balance command.
- Add gold payments.
- Add item sell values.
- Add the daily wisdom and gold reward.
- Require recent wisdom activity for daily claims.
- Add the 24-hour claim cooldown.
- Cap activity-based reward scaling.

The daily reward should be implemented after wisdom and gold both exist, but
before the larger dungeon economy.

## Phase 5: Immediate trades and advanced item administration

**Goal:** Allow users and administrators to manage item economies safely.

**Difficulty: 4/5**

- Add confirmed immediate item/gold trades.
- Validate both sides at confirmation time.
- Exchange all assets in one database transaction.
- Add admin item creation.
- Add global item alteration.
- Add enable/disable state for item definitions.
- Add configurable item-effect actions.
- Add moderator/admin audit history.

Trades should exchange assets immediately. They do not need escrow or pending
inventory reservations.

The previously mentioned instance-only alteration mode is not part of the
current plan.

## Phase 6: Persistent delayed effects and chat relays

**Goal:** Implement communication and timer-heavy features separately from
ordinary items and fun commands.

**Difficulty: 4/5**

- Make delayed effects survive bot restarts.
- Define downtime behavior for timers.
- Add configurable timer extensions or compensation.
- Implement magic missile.
- Implement whisper to the void.
- Implement listen to the void.
- Implement seance threads and channel/thread relays.
- Add relay cleanup, loop prevention, permissions, and rate limits.

This phase is intentionally separate because relays have different risks from
ordinary item effects: privacy, message forwarding, concurrency, cleanup, and
moderation.

## Phase 7: User-generated content and moderation

**Goal:** Introduce persistent content created by users only after the core
systems are stable.

**Difficulty: 4/5**

- Add a shared content status model.
- Support active, deactivated, and destroyed states.
- Add moderator action logging.
- Add moderator content listings by user.
- Add deactivation and permanent destruction.
- Add restoration only for deactivated content.
- Add pagination and permission checks.

Initial content types:

- Projection stones
- Auto-reply rules
- Auto-reaction rules
- Dungeon names and descriptions

Normal users should be able to list active global projection stones and other
content intentionally published for public use. Global projection stones do not
need a separate moderation or approval action; their existing globalization
mechanism is sufficient.

Moderators should be able to deactivate or destroy projection stones and other
stored user content. Destroyed content is not restorable.

## Phase 8: Projection stones and public content

**Goal:** Build the most stateful non-dungeon user-created content.

**Difficulty: 4/5**

- Store text and optional media/embed data in unique projection stone instances.
- Cast a projection stone.
- Configure its globalization reaction.
- Make a stone global after the required reaction threshold.
- List active global projection stones.
- Prevent deactivated or destroyed stones from being cast or listed.
- Add moderator listings and actions.

This phase is separate from the general moderation framework because
projection stones have their own publication and reaction state.

## Phase 9: DungeonMakerV2 port

**Goal:** Port the existing dungeon game as the final major subsystem.

**Difficulty: 5/5**

The source project is
[DungeonMakerV2](https://github.com/alexbatesdev/DungeonMakerV2).

### Domain port

- Port dungeon, room, player, and monster concepts.
- Preserve the source gameplay rules where practical.
- Separate game logic from Discord command/rendering code.
- Add persistent dungeon and run state.

### Discord integration

- Create and edit dungeons.
- Render rooms and dungeon state in Discord.
- Add movement and gameplay commands or controls.
- Add dungeon publishing.
- Add dungeon ownership.
- Validate dungeon layouts.

### Moderation

- Allow moderators to condemn a dungeon.
- Replace a condemned dungeon with a one-room preset.
- Disable the owner's ability to edit it.
- Record the moderator, reason, and timestamp.
- Do not retain a copy of the condemned dungeon.
- Do not restore the original dungeon after condemnation.

### Economy integration

- Sell dungeon tiles.
- Sell traps.
- Sell monsters.
- Sell treasures.
- Add invasion rewards.
- Reward dungeon owners for unclaimed treasure where appropriate.
- Allow potions and other items to affect dungeon runs.

The basic dungeon port should be completed before invasions and economy
integration.

## Deferred or optional features

These are intentionally not assigned to an early phase:

- Library of Babel integration
- Complex games such as Mancala and Knucklebones
- Image compositing for explosion effects
- Fully flexible natural-language calculator behavior
- Large crafting trees
- Additional social automation

## Phase dependency summary

```text
Phase 0 Foundation
    |
    +--> Phase 1 Wisdom
    |        |
    |        +--> Phase 4 Gold and daily rewards
    |
    +--> Phase 2 Items
             |
             +--> Phase 3 Purgatory and fun spells
             |
             +--> Phase 5 Trades and item administration
             +--> Phase 6 Timers and chat relays
             |
             +--> Phase 7 Moderation framework
                      |
                      +--> Phase 8 Projection stones
                      |
                      +--> Phase 9 Dungeon port
```
