# Project Decisions

This document records product and architecture decisions made during planning.
It is intentionally separate from the feature backlog in `readme.md`.

## Scope

- The bot is personal software for one Discord server.
- There will be no cross-guild functionality for wisdom, gold, items, dungeons,
  or user-created content.
- The data model may still use guild identifiers where doing so is inexpensive
  and improves portability, but multi-guild behavior is not a requirement.

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
- The port should preserve the source game's domain concepts and rules where
  practical, while adapting input and rendering for Discord.
- Dungeon owners can create, edit, publish, and play their own dungeons.
- Moderators can condemn a dungeon by replacing it with a one-room preset and
  disabling the owner's ability to edit it.
- Condemnation should record the moderator, reason, and timestamp.
- Condemnation does not retain a copy of the original dungeon.
- A condemned dungeon is not restorable; only its one-room replacement remains.

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
- Public listing commands should exclude deactivated, destroyed, and
  unapproved content.
- Global projection stones do not require a separate moderation action or
  approval workflow. Their existing globalization mechanism is sufficient.

## Pending decisions

- The exact data-driven action vocabulary for item effects.
- The exact Discord commands and pagination behavior for moderator content
  listings and public content listings.
