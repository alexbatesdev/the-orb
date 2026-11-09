# Wisest Wizard

## Running the bot

The project requires Python 3.12 or newer. Install dependencies with
`python -m pip install -r requirements.txt`, copy `.env.example` to `.env`, and
set `DISCORD_TOKEN` to the bot token from the Discord Developer Portal. From
a Bash shell, start the bot with `bash start.sh`. The script starts the full
bot in the foreground, preferring the project's `.venv` if present and otherwise
using Python from `PATH`. Install dependencies into the interpreter it will use.
Stop the bot with Ctrl+C. `python bot.py` and `python -m wisest_wizard` also
remain available.

There is no separate development mode yet: running the script locally connects
to Discord using the configured token, just as it does on a server. For safe
local testing, use a separate Discord bot/token and a separate `DATABASE_PATH`
in your local environment. Do not run two bot processes against the same
database.

On startup, the bot validates its environment, opens the SQLite database at
`DATABASE_PATH` (default: `data/wisest-wizard.sqlite3`), and applies any pending
ordered SQL migrations before connecting to Discord. The database directory is
created automatically and is excluded from Git. Back up the database file
while the bot is stopped. Set `AUDIT_RETENTION_DAYS` to a positive number to
enable bounded daily deletion of older audit records; leave it unset to retain
them.

The bot needs the Message Content and Server Members privileged intents enabled
in the Discord Developer Portal. Server Members lets the bot resolve partial
usernames against the full current member list.

## Wisdom

Human messages in servers, including bot commands, are scored with the
Animal Crossing (GameCube, North American) letter rules. Only the first
`WISDOM_MAX_CHARS` characters (default 192) count. Positive-quality messages
add `WISDOM_GAIN * quality` to the sender's unbounded wisdom total; zero-quality
messages do not consume the message cooldown. The default message cooldown is
one second and can be tuned with `WISDOM_MESSAGE_COOLDOWN_SECONDS`.

Wisdom decays lazily after the configured grace period. `i cast check wisdom` shows
the caller's current value as a number, without a percentage or another
member's value. `i cast check wis` and `i cast chwi` are shortcuts for the
same check; all three also work with the `cast` prefix. Use
`i cast +rep username` or `i cast -rep username` to add
or remove one point of wisdom; both commands share a per-giver, per-server
24-hour cooldown by default and only accept current human server members.
Set `WISDOM_REPUTATION_COOLDOWN_SECONDS` to change it. Remaining time is
displayed in hours, minutes, and seconds, rounded up to the next second. Names are
case-insensitive and can be partial usernames or display names. An exact match
takes precedence; ambiguous matches require a more specific name or user ID.
Mentions and user IDs also work without requiring a ping. Wisdom cannot fall
below zero.

The remaining scoring, decay, reputation, and shared reward-service settings
are listed in `.env.example`. The message and reputation cooldowns, score
normalization, gain, decay, and reward limits are validated at startup.

The trigram table in `wisest_wizard/data/trigrams_bugged.txt` is reproduced
with permission and attribution from Hunter R.'s
[AC Letter Scorer](https://github.com/HunterRDev/AC-Letter-Scorer), which
documents the Animal Crossing letter-scoring behavior and game bug.

## Discord copy

Discord-facing text lives in `wisest_wizard/locales/en.json`. Use
`translate("key", name=value)` from `wisest_wizard.i18n` for replies, errors,
and command help rather than embedding copy in Python. Templates use Python
format placeholders, including numeric formats such as `{value:.3f}`.
Missing keys or placeholders raise errors rather than silently displaying a
fallback. Restart the bot after editing the catalog. English is currently the
only catalog; language selection and other translations are not implemented.

## Foundation structure

- `wisest_wizard/app.py` owns startup, bot lifecycle, shared services, and prefix
  behavior.
- `wisest_wizard/phrases.py` resolves command names and aliases as phrases.
- `wisest_wizard/cogs/` contains loadable command cogs.
- `wisest_wizard/migrations/` contains ordered, transactional SQL migrations.
- `wisest_wizard/database.py` owns the shared async SQLite connection and
  transaction boundary.
- `wisest_wizard/services/` contains reusable persistence, cooldown, audit,
  scheduled-effect, interaction-event, and wisdom-reward contracts.

Feature cogs should use shared services instead of issuing ad hoc database
queries. Combine state changes and `AuditService.record_in_transaction` in the
same database transaction when both must succeed together. Scheduled handlers
must be registered by a bounded effect type and be safe to retry: a crash
after a Discord side effect but before its completion is recorded can result
in at-least-once delivery. Run a single bot process against a database; the
scheduler recovers all in-flight rows during startup and is not designed for
multiple active bot processes sharing the same SQLite file. Interaction events
use a bounded event-type enum and unique event IDs so future reward handling
can identify duplicate events without storing generic event payloads now.

Future wisdom grants use `WisdomRewardService` with a typed interaction event,
source enum, unique event ID, and identifier-only context. Each event type has
its own per-user/guild cooldown; the service is available for later phases but
does not award item, crafting, game, or dungeon rewards on its own.

Commands can declare multiword names and aliases directly with
`@commands.command(name="check wisdom", aliases=["check wis", "chwi"])`.
The router matches whole words case-insensitively, accepts whitespace between
words, and selects the longest registered phrase before handing any remaining
arguments to Discord.py. Declare phrases using single spaces between words;
duplicate command names or aliases fail registration. Standard command checks,
cooldowns, and help apply.

## Planned features

- admin commands
  - banish
    - User given the banished role and can only message in the abyss channel
  - unbanish
    - Removes the banished role from a user, allowing them to message normally again
  - create item
    - Allows an admin to create a new item that can be added to the inventory system
    - Admin can specify item name, description, and effects
      - not sure how the effects will be implemented
  - alter item
    - Allows an admin to modify an existing item's properties such as name, description, and effects
  - spawn item
    - Allows an admin to spawn an item into a user's inventory
  - destroy item
    - Allows an admin to permanently remove an item from a user's inventory
  - content moderation
    - Deactivate user-created content, making it unavailable without permanently deleting it
    - Destroy user-created content permanently
    - List all user-created content submitted by a specified user
    - Restore deactivated content when appropriate
    - Record moderator actions and reasons

- karma system branded as "wisdom"
  - linear karma decay on inactive after 1 week
  - karma gain on send messages
    - follows animal crossing gamecube letter grading system
  - "+rep" and "-rep" commands for people to give or remove wisdom from current server members
    - one-per-day cooldown per giver, shared by both commands
- inventory system
  - check inventory
    - shows the users inventory
  - give item
    - Allows a user to give an item from their inventory to another user
  - toss item
    - Allows a user to remove an item from their inventory
  - use item
    - Allows a user to use an item from their inventory, triggering its effect
  - items:
    - dungeon tiles, traps, monsters, etc.
    - colored robes (role color)
    - pocket glitter (makes the current channels text history hidden for a certain duration)
    - spell tomes (fun commands locked behind reading the tomes)
      - uwu, explosion, roll, summon cat
      - The more annoying or intrusive a spell, the more expensive it is in the shop currency (Gold)
    - giant gold statue (birdly statue that gives you a dweeb role)
    - orb (for pondering) 
      - see random visions
    - seance item
      - Creates a thread that acts as a link between any channel and the thread, allowing communication with wizards banished to the void through the seance item
      - This includes the abyss, letting players communicate with wizards banished there
    - projection stone
      - Upon creation user can store a string of text within the stone, which can later be reproduced by casting the stone
      - this can be used for silly image embeds or prompts
      - An emote can be set that globalizes a projection stone once enough users react with it, making it usable by all users who have the projection spell.
      - Users can list all active global projection stones
      - Moderators can deactivate, destroy, or restore projection stones
- shop
  - currency is what? (not wisdom)
    - Gold (G)
  - check gold command
    - Shows the user's current wealth in the shop currency (Gold)
  - pay command
    - Allows a user to give a specified amount of shop currency (Gold) to another user
  - card packs
    - Allows a user to buy randomized packs containing items from a configured pool
    - Dungeon tiles, traps, monsters, treasures, and other dungeon items can be obtained from packs
  - trade offer
    - Allows a user to propose a trade with another user, specifying items and/or shop currency (Gold) to exchange
    - The other user can accept or decline the trade offer
- dungeon maker port
  - Allows users to create, manage, and play ascii/text-based dungeons within Discord
  - Dungeon tiles, traps, monsters, treasures, and equipment are ordinary inventory items
  - First port the basic DungeonMakerV2 gameplay before adding expansions
  - Raid rewards come from randomized item pools, mostly crafting items with rare artifacts possible
  - Later dungeon gear includes tools and trinkets with effects; armor is out of scope for now
  - Later expansions can add additional room types, tile behaviors, encounters, and dungeon systems
  - Players can invade each other's dungeons
  - Maybe integrate with shop?
    - sell dungeon tiles
    - sell dungeon traps
    - sell dungeon monsters
    - sell treasures
      - owner of dungeon gets reward if treasure is not claimed by invaders
- potion brewing
  - allows a user to brew potions using ingredients from their inventory
    - start with the minecraft brewing system as a base
  - sell potions for shop currency (Gold)
  - use them in dungeon invasions
- crafting?
  - ingredient combinations
  - id have to make up a bunch of items and crafting trees
  - could integrate with potion brewing and dungeon maker for ingredients and crafted items
  - could also integrate with the shop for selling crafted items
  - make main money loop be crafting artifacts and selling/high-alch'ing them
- claim daily
  - Allows a user to claim their daily reward of wisdom and gold
  - User must have gained enough karma/wisdom in the past 24 rolling hours to claim the daily reward
  - The daily reward also has a 24 hour cooldown
  - The reward consists of both some wisdom and some gold, not much
    - I think the amount of wisdom and gold should scale with the user's recent activity and karma gain
- pocket dimension
  - Creates a thread in the current channel
- toys/silly spells
  - magic missile
    - Casts explode at the specified user after a random delay from 5 minutes to 2 weeks
    - a wizard can only have one active magic missile at a time
  - dither command
  - ponder command
    - magic 8 ball style responses
  - uwu
    - UWUify text, defaults to previous message in channel
  - explosion/explode
    - Respond with a random explosion gif
    - optionally provide image to overlay explosion gif over the image
    - optionally ping a user to overlay the explosion on their profile picture (and ping them)
  - summon cat
    - Respond with a random cat image, potentially from cataas
  - timestamp
    - convert a human time string input into a discord timestamp
  - games
    - connect 4
    - tictactoe
    - mancala
    - knucklebones
    - guessthenumber
  - roll
    - Roll a number of dice with a specified number of sides, defaults to 6
  - calculate
  - coinflip
  - flame text
    - Converts the input text into a flaming style text effect
  - babel
    - Looks up which book in the libary of babel contains the specified text
    - Returns the book's location and a link to view it
    - I think I want this to be needlessly complex and flexible
    - allow finding books with the title, or containing specific text
  - define
    - Looks up the definition of a specified word
    - Returns the word's meaning, part of speech, and example usage if available
  - up thumber
    - replies with a random thumbs up image
  - down thumber
    - replies with a random thumbs down image
  - read fortune
    - Responds with a random fortune message
  - conjure security scroll
    - Places the "security scroll" item in the user's inventory
    - Using the security scroll item replies with the following message: "You unfurl the security scroll, it reads: 'The secret passkey is: 4'"
  - auto react
    - Automatically reacts to messages with matching content with a specified emoji
  - auto reply
    - Automatically replies to messages with matching content with a specified response
  - whisper to the void
    - sends a message to the abyss
  - listen to the void
    - Casts a 30 second net that returns any messages sent for the next 30 seconds after it is cast
