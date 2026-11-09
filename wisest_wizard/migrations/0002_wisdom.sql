CREATE TABLE wisdom (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    value REAL NOT NULL DEFAULT 0 CHECK (value >= 0),
    last_active REAL NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE wisdom_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    amount REAL NOT NULL,
    source TEXT NOT NULL,
    event_type TEXT,
    event_id TEXT UNIQUE,
    context_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE INDEX wisdom_ledger_user_idx
    ON wisdom_ledger (guild_id, user_id, created_at);

CREATE TABLE reputation_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    giver_id TEXT NOT NULL,
    recipient_id TEXT NOT NULL,
    direction INTEGER NOT NULL CHECK (direction IN (-1, 1)),
    amount REAL NOT NULL CHECK (amount >= 0),
    created_at REAL NOT NULL
);

CREATE INDEX reputation_ledger_recipient_idx
    ON reputation_ledger (guild_id, recipient_id, created_at);
CREATE INDEX reputation_ledger_giver_idx
    ON reputation_ledger (guild_id, giver_id, created_at);
