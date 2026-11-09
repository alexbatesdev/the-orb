# Phase 2 Agent Handoff: Item and Inventory Core

## Objective

Implement Phase 2 from [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md),
following [DECISIONS.md](./DECISIONS.md) and the item backlog in
[readme.md](./readme.md). Deliver working inventory, item operations,
crafting, migrations, tests, and directly related documentation.

Phase 2 provides the common item foundation for later spells, shops, trades,
user-created content, and dungeons. Do not implement those later systems as
part of this handoff. The project is pre-release: do not introduce legacy
aliases or compatibility shims solely to preserve unreleased behavior.

## Existing foundation and integration requirements

- Startup and shared services live in `wisest_wizard/app.py`; commands belong
  in cogs. Preserve both `python bot.py` and `python -m wisest_wizard`.
- `wisest_wizard/phrases.py` supports multiword command names and aliases.
  Declare intended phrases directly on commands; use existing cast prefixes,
  parsing, checks, error handling, and help.
- The Core cog owns the `check` command group. Register feature-specific checks
  as subcommands under that group from their owning cogs, so `help check` lists
  checks from loaded modules; remove those subcommands when their cog unloads.
- Put all Discord-facing copy, including help and validation messages, in
  `wisest_wizard/locales/en.json`. Use `translate` and existing duration
  formatting where appropriate.
- Use `Database` in `wisest_wizard/database.py`. Add ordered migrations after
  `0002_wisdom.sql` rather than editing applied migrations. Inventory and
  crafting services, not Discord callbacks, should own state changes.
- `Database.transaction()` serializes writes on the shared connection. Do not
  nest it or call a helper that opens another transaction while holding it.
  Add transaction-aware service methods where operations must commit together.
- Use the existing permission checks for administrative commands and
  `AuditService.record_in_transaction` for administrative state changes.
  Maintain a separate item transaction history suitable for inventory actions.
- Reuse `PersistentCooldowns` for applicable cooldowns, including its
  transaction-aware operation when consumption must be atomic with item state.
- `WisdomRewardService` and typed `ITEM_USED` / `ITEM_CRAFTED` events exist,
  but rewards are not automatically wired to item actions. Any integration
  must use stable event IDs, the supported identifier-only context, and
  existing limits; do not directly update wisdom. Its current `grant` opens
  its own transaction, so do not invoke it inside an inventory transaction.
- `ScheduledEffects` persists and retries jobs, but `schedule()` currently
  opens its own transaction and handlers may run more than once. If timed
  crafting uses it, make ingredient consumption and scheduling atomic through
  a transaction-aware API, and make completion idempotent. Verify restart and
  failure recovery; do not assume the scheduler already pauses timers during
  downtime.

## Functional requirements

### Definitions and inventory

- Define global item definitions with stable identifiers, names, descriptions,
  categories, stacking behavior, effect configuration, and value where
  appropriate. Preserve identifiers independently of display names.
- Items stack by default. Support unique instances with independent persistent
  state for items that need it; do not model potions, ingredients, or future
  dungeon objects as separate inventory systems.
- Support future dungeon tiles, traps, monsters, treasures, and equipment as
  item categories, without implementing dungeon combat or dungeon gameplay.
- Show the caller's inventory, including useful quantities and a way to
  distinguish individual instances. Handle empty inventories and Discord
  message-size limits.
- Implement giving, tossing, and using items, with validation for ownership,
  quantities, recipients, and unavailable or unsupported actions. Transfers
  are immediate and atomic. A failed operation must not consume, duplicate,
  or silently lose items.
- Implement basic permission-checked administrative spawn and destroy
  operations. Log actor, affected owner, item identity, quantity or instance,
  operation, and outcome as appropriate; combine successful state changes and
  audit/transaction records atomically.
- Support explicit item cooldown and consumption rules. Check and consume
  cooldowns in the same transaction as the corresponding persistent operation.
  Validate invalid quantities and configuration rather than silently defaulting.

### Effects and initial items

- Provide an extensible, bounded effect-trigger model and safe data-driven
  actions, with explicit handlers for effects that require code. Item data
  must not execute arbitrary Python, imports, or unrestricted code paths.
- Implement enough concrete, testable behavior to exercise the item-use flow.
  The planned initial items are an orb, a fortune item, a security scroll, a
  wisdom-granting item, and a basic spell tome. Confirm the intended effect and
  consumption semantics where the existing plans do not define them; do not
  quietly substitute a no-op and report the item as used successfully.
- Orb visions, security mechanics, spell unlocks, role effects, and other
  Phase 3 features must not be presented as complete unless actually
  implemented and tested. If an initial item depends on those features,
  explicitly agree its Phase 2 behavior or defer it transparently.
- Design the trigger interface for later dungeon effects, but do not implement
  combat, passive trinkets, conflict resolution, or a full dungeon engine now.

### Crafting

- Define recipes using stable item identifiers, ingredient quantities,
  output quantities, and optional duration. Start with a small useful recipe
  set including potion-like items; crafted outputs are ordinary items.
- Consume all ingredients atomically. Reject missing ingredients, invalid
  quantities, unavailable recipes, or impossible outputs without partial
  changes. Support both stackable and unique outputs.
- Immediate crafting must commit ingredient consumption, output creation, and
  item transaction history together. Timed crafting must persist pending work
  and complete it safely after restart without duplicating output or consuming
  ingredients twice.
- Store crafted item values without implementing gold balances, selling, shops,
  or a gold ledger in this phase.
- The daily wisdom, gold, and card-pack claim is planned for Phase 4, after gold
  and randomized card packs exist. Do not implement the daily claim in Phase 2.

## Decisions to resolve before implementation

The existing plans do not specify exact command syntax, initial item and recipe
effects, or the effect-action vocabulary. Ask the user when these choices
change gameplay or scope; record the answers in the relevant documentation.
In particular, resolve:

1. Command phrases, how users identify items and unique instances, quantities,
   recipient lookup, and what admin permissions authorize spawn and destroy.
2. Initial items and recipes, their effects and values, whether use consumes
   each item, and per-item cooldown behavior. Identify which Phase 3-dependent
   behavior is deferred rather than inventing it.
3. Timed-crafting UX and downtime behavior: how users start and inspect jobs,
   when outputs become available, and whether waiting time pauses or is
   compensated during downtime. The project decisions say downtime should not
   silently consume waiting periods.
4. Whether Phase 2 item use and crafting grant wisdom immediately. The project
   calls for cross-system rewards, while Phase 5 explicitly lists small item
   and crafting rewards; decide timing and failure/retry behavior with the
   user rather than assuming either interpretation.

Choose practical details such as table names and internal types in the
implementation; document decisions and avoid adding speculative general
frameworks beyond the stated needs.

## Test and acceptance checklist

- Definitions: stable IDs, valid categories and effects, duplicate IDs,
  malformed metadata, disabled or unsupported actions, and migration/restart.
- Inventory: empty and populated displays, long output, stack quantities,
  independent instance state, valid and invalid quantities, ownership and
  guild isolation, and recipient validation.
- Transfers and administration: exact balances before and after each operation,
  permission denial, self/invalid targets, concurrent attempts, ledger/audit
  contents, and rollback on injected failures.
- Item use: supported effects, consumption and non-consumption, cooldown
  boundaries, invalid effects, concurrent use, and rollback of persistent
  state and cooldown on failure. Test external Discord effects and persistence
  failures explicitly; do not claim atomicity across Discord and SQLite.
- Crafting: missing ingredients, repeated ingredient types, quantity
  validation, stackable and unique outputs, concurrent requests, rollback,
  and transaction history. For timed jobs, test restart, downtime policy,
  retries, duplicate completion, and scheduling/creation failure.
- If wisdom rewards are included, test typed event/source attribution,
  cooldowns, duplicate event IDs, failure/retry behavior, and no nested
  transaction deadlocks. Otherwise document the deferral explicitly.
- Exercise the real Discord command parser, aliases, checks, errors, localized
  responses, and help. Existing wisdom, reputation, health, and startup behavior
  must remain intact.
- Run focused tests during development, then the existing full suite with
  `python -m unittest discover -s tests -v` using the project's environment.

## Delivery

- Update user-facing setup, commands, item behavior, and any new configuration
  documentation. Update the implementation plan or decisions when product
  choices or deferrals are resolved.
- Report the resolved questions, schema and atomicity choices, known
  limitations, and exact test results. Do not commit unless explicitly asked.
