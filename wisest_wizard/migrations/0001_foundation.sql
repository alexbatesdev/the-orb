CREATE TABLE cooldowns (
    cooldown_key TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('global', 'guild', 'user')),
    guild_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    expires_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (cooldown_key, scope, guild_id, user_id)
);

CREATE INDEX cooldowns_expiration_idx ON cooldowns (expires_at);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    guild_id TEXT,
    target_type TEXT,
    target_id TEXT,
    reason TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE INDEX audit_log_created_at_idx ON audit_log (created_at);
CREATE INDEX audit_log_actor_idx ON audit_log (actor_id, created_at);

CREATE TABLE scheduled_effects (
    id TEXT PRIMARY KEY,
    effect_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    guild_id TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'running', 'retry', 'completed', 'cancelled', 'failed')
    ),
    due_at REAL NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    lease_until REAL,
    last_error TEXT
);

CREATE INDEX scheduled_effects_due_idx
    ON scheduled_effects (status, due_at, lease_until);
CREATE INDEX scheduled_effects_guild_idx ON scheduled_effects (guild_id, due_at);
