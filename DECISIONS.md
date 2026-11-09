# Project Decisions

This document records product and architecture decisions made during planning.
It is intentionally separate from the feature backlog in `readme.md`.

## Scope

- The bot is personal software for one Discord server.
- There will be no cross-guild functionality for wisdom, gold, items, dungeons,
  or user-created content.
- The data model may still use guild identifiers where doing so is inexpensive
  and improves portability, but multi-guild behavior is not a requirement.

## Wisdom as a cross-system reward

- Wisdom is the bot's interaction reward and should be available throughout
  the system, not only in the message-karma subsystem.
- Wisdom is an unbounded, nonnegative floating-point total. Quality-normalized
  message rewards and the shared reward service add points; inactivity decay
  subtracts points lazily without imposing an upper cap.
- Meaningful interactions across subsystems should award a very small amount of
  wisdom, including item use, crafting, games, dungeon play, dungeon growth,
  and other intentional participation.
- Wisdom rewards should be granted through a centralized reward service and
  event vocabulary rather than being calculated independently by each command.
- Every reward source needs anti-abuse rules, cooldowns, diminishing returns,
  or activity limits appropriate to that source.
- The reward service should record the source and context of wisdom gains so
  rewards can be audited and tuned later.
- Dungeon players should receive wisdom for playing dungeons.
- Dungeon owners should receive wisdom when other players play their dungeons.
- Dungeon runs should support broader player and owner reward bundles, such as
  wisdom, gold, or items, with exact values tuned later.
- Ingredients, materials, crafted goods, potions, and dungeon objects are all
  items and should not receive separate reward or inventory concepts.
- Growing a dungeon should provide a passive progression benefit, inspired by
  tending a garden.
- Dedicated dungeon tiles may boost wisdom earned from specific activities,
  such as daily claims, messaging, or raiding other dungeons.
- Worship rooms should provide incentives for players to reach them.
- Dungeon owners should receive incentives for stopping or defeating a raiding
  player before the player reaches a worship room.

## Inventory and item behavior

- Items stack by default.
- Items should transfer immediately when a gift or trade is completed.
- Transfers must be atomic so a failure cannot duplicate or destroy items.
- The codebase should model potions as ordinary items, not as a separate
  subsystem or runtime type.
- Crafting should produce items through recipes; recipes are not limited to
  potion-like items.
- Crafted items should use the same item definitions, inventory transactions,
  effects, stacking rules, and sale values as every other item.
- Dungeon tiles, traps, monsters, treasures, and future dungeon equipment
  should also be ordinary items rather than a separate item system.
- Dungeon content should use stable item identifiers so the dungeon system can
  be expanded without replacing its item model.
- The first dungeon implementation should be a basic port of DungeonMakerV2.
- Dungeon expansions should not be added until the basic port is complete and
  playable.
- Successful raids should award random items from a dungeon-specific reward
  pool.
- Most raid reward-pool items will be ordinary crafting ingredients or other
  useful items, with a chance for rare artifacts.
- Dungeon gear is a later expansion consisting of two item behavior classes:
  tools and trinkets. Armor is intentionally out of scope for now.
- Tools have active effects that trigger when the player uses the tool on their
  turn in combat.
- Trinkets have passive effects that respond to game events and state changes.
- Passive trinkets may trigger every turn, when an enemy attacks, or when a
  status ailment would be applied.
- Passive trinkets may prevent status ailments such as poison.
- Passive trinkets may modify initiative, damage, map visibility, and other
  player capabilities.
- The item-effect system must support explicit triggers, ordering, prevention,
  and stat modifiers before dungeon gear is implemented.
- The previously noted "instance only" item alteration mode is not currently a
  committed requirement. `alter item` should initially modify the global item
  definition.
- Item behavior should be configurable so new items can be created without
  changing the core item system.
- The preferred item behavior design is a safe, data-driven action system,
  supplemented by controlled handlers for complex effects.
- Arbitrary Python code or unrestricted import paths should not be executable
  from item data.
- Unique item instances are still appropriate for items that contain their own
  state, such as projection stones.

## Timers and downtime

- Delayed effects must survive bot restarts.
- Scheduled effects must be persisted rather than kept only in memory.
- Downtime should not silently consume a user's waiting period.
- The timer system should support pausing or extending timers after downtime,
  including possible administrator-provided compensation.

## Dungeons

- The dungeon system will be ported from
  https://github.com/alexbatesdev/DungeonMakerV2 rather than designed from
  scratch.
- The port should preserve the source game's useful domain concepts and rules
  where practical, while expanding the game beyond the original V2 design.
- The dungeon architecture should be extensible for additional room types,
  tile behaviors, traps, monsters, treasures, encounters, and future gameplay
  systems.
- Dungeon owners can create, edit, publish, and play their own dungeons.
- Moderators can condemn a dungeon by replacing it with a one-room preset and
  disabling the owner's ability to edit it.
- Condemnation should record the moderator, reason, and timestamp.
- Condemnation does not retain a copy of the original dungeon.
- A condemned dungeon is not restorable; only its one-room replacement remains.

## Shop and dungeon item acquisition

- Dungeon-related items should be purchasable from the shop.
- The shop should support randomized card packs that award items from a
  configured item pool.
- Card packs should use the normal item, inventory, and transaction systems.
- Pack contents should be generated server-side and recorded for auditability.
- Pack definitions should support configurable item pools, weights, and
  quantities.
- The exact pack odds, duplicate handling, and possible pity/protection rules
  remain pending decisions.

## Dungeon progression and wisdom

- Dungeon growth should be a persistent progression system separate from the
  dungeon's basic layout.
- Growth may use passive timers, care/actions, or other garden-like mechanics,
  but the exact growth model is not yet fixed.
- Wisdom-boosting tiles should modify reward calculations through the shared
  wisdom service rather than directly editing wisdom.
- Worship-room rewards and raid-defense rewards should be resolved as part of
  a dungeon run and recorded with the relevant dungeon and player context.

## User-created content moderation

- Moderators can deactivate user-created content. Deactivation is reversible
  and makes the content unavailable or hidden from normal use.
- Moderators can destroy user-created content permanently.
- Moderators can list all custom content submitted by a specified user.
- Moderator actions should be auditable, including the action, target, actor,
  reason, and timestamp.
- Initial moderation scope includes:
  - Dungeons and their names/descriptions
  - Projection stones and their stored text or media
  - Auto-reply rules
  - Auto-reaction rules
  - Other future content that is stored and shown to other users
- Moderators should be able to restore deactivated content, but not destroyed
  content.
- Normal users can list active global projection stones and equivalent content
  that is intentionally published for public use.
- Public listing commands should exclude deactivated and destroyed content.
- Global projection stones do not require a separate moderation action or
  approval workflow. Their existing globalization mechanism is sufficient.

## Pending decisions

- The exact data-driven action vocabulary for item effects.
- The exact Discord commands and pagination behavior for moderator content
  listings and public content listings.
