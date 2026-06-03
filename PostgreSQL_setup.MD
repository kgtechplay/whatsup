# PostgreSQL setup for Whatsup

This guide documents the PostgreSQL objects used by the **Whatsup** project so another developer can recreate the same database on a fresh machine.

The FastAPI agent reads connection settings from `.env` (see `.env.example`). **Do not commit real credentials**; use your own database user and password locally.

| Variable | Purpose | Example value |
|----------|---------|---------------|
| `POSTGRES_DB` | Database name | `whatsapp_db` |
| `POSTGRES_HOST` | Server host | `127.0.0.1` |
| `POSTGRES_PORT` | Server port | `5432` |
| `POSTGRES_USER` | Login user | *(your choice)* |
| `POSTGRES_PASSWORD` | Login password | *(your choice)* |

---

## Overview

| Object | Name | Used by |
|--------|------|---------|
| Database | `whatsapp_db` | `fastapi_agent/database.py` |
| Schema | `msg_schema` | All app tables |
| Table | `msg_schema.whatsapp_messages` | Webhook + send persistence |
| Table | `msg_schema.message_analysis` | Analysis UI (`/analysis/*`) |
| Trigger | `trg_sync_message_analysis_from_whatsapp_messages` | Keeps `message_analysis` in sync on insert |
| Function | `msg_schema.sync_message_analysis_from_whatsapp_messages()` | Trigger body |

**Application references:** [fastapi_agent/database.py](fastapi_agent/database.py), [fastapi_agent/main.py](fastapi_agent/main.py)

---

## 1. Create database and schema

Connect as a PostgreSQL superuser (or a role that can create databases), then run:

```sql
-- Create the application database (name must match POSTGRES_DB in .env)
CREATE DATABASE whatsapp_db
    WITH ENCODING 'UTF8'
         LC_COLLATE 'en_US.UTF-8'
         LC_CTYPE 'en_US.UTF-8'
         TEMPLATE template0;
```

On Windows, locale names may differ; a minimal alternative:

```sql
CREATE DATABASE whatsapp_db;
```

Connect to `whatsapp_db` and create the schema:

```sql
\c whatsapp_db

CREATE SCHEMA IF NOT EXISTS msg_schema;
```

Grant your application role access (replace `your_app_role` with the user from `POSTGRES_USER`):

```sql
GRANT USAGE ON SCHEMA msg_schema TO your_app_role;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA msg_schema TO your_app_role;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA msg_schema TO your_app_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA msg_schema
    GRANT ALL ON TABLES TO your_app_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA msg_schema
    GRANT ALL ON SEQUENCES TO your_app_role;
```

---

## 2. Table: `msg_schema.whatsapp_messages`

Durable store for inbound and outbound WhatsApp messages (webhook + `POST /messages/send`).

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | `BIGINT` | NO | `nextval(...)` | Surrogate primary key |
| `message_id` | `VARCHAR(255)` | NO | — | WhatsApp message id (unique) |
| `chat_jid` | `VARCHAR(255)` | NO | — | Chat JID (e.g. `9198...@s.whatsapp.net`) |
| `sender_jid` | `VARCHAR(255)` | YES | — | Sender JID |
| `participant_jid` | `VARCHAR(255)` | YES | — | Group participant JID |
| `from_me` | `BOOLEAN` | NO | `false` | Outbound from linked device |
| `message_timestamp` | `TIMESTAMPTZ` | NO | — | Message time from WhatsApp |
| `received_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | When gateway/Python received it |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Row created |
| `updated_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Row last updated |
| `message_type` | `VARCHAR(50)` | NO | — | e.g. `conversation`, `imageMessage` |
| `message_text` | `TEXT` | YES | — | Text body when applicable |
| `has_media` | `BOOLEAN` | NO | `false` | Media flag |
| `media_mime_type` | `VARCHAR(100)` | YES | — | MIME type |
| `media_path` | `TEXT` | YES | — | Local path |
| `media_url` | `TEXT` | YES | — | URL |
| `media_filename` | `TEXT` | YES | — | Filename |
| `media_size_bytes` | `BIGINT` | YES | — | Size in bytes |
| `media_sha256` | `VARCHAR(255)` | YES | — | Media hash |
| `message_status` | `VARCHAR(30)` | YES | — | e.g. `sent`, `delivered` |
| `is_forwarded` | `BOOLEAN` | YES | `false` | Forwarded flag |
| `is_ephemeral` | `BOOLEAN` | YES | `false` | Ephemeral flag |
| `quoted_message_id` | `VARCHAR(255)` | YES | — | Quoted message id |
| `quoted_sender_jid` | `VARCHAR(255)` | YES | — | Quoted sender |
| `quoted_text` | `TEXT` | YES | — | Quoted snippet |
| `reaction_emoji` | `VARCHAR(20)` | YES | — | Reaction emoji |
| `reaction_to_message_id` | `VARCHAR(255)` | YES | — | Target message for reaction |
| `is_deleted` | `BOOLEAN` | NO | `false` | Deleted flag |
| `deleted_at` | `TIMESTAMPTZ` | YES | — | Deletion time |
| `is_edited` | `BOOLEAN` | NO | `false` | Edited flag |
| `edited_at` | `TIMESTAMPTZ` | YES | — | Edit time |
| `profile_name` | `VARCHAR(255)` | YES | — | Profile display name |
| `push_name` | `VARCHAR(255)` | YES | — | Push name from contact |
| `raw_json` | `JSONB` | NO | `'{}'::jsonb` | Full payload snapshot |
| `phone_number` | `TEXT` | YES | — | E.164-style number derived from JID |

The app can also add `phone_number` on an existing DB (idempotent):

```sql
ALTER TABLE msg_schema.whatsapp_messages
    ADD COLUMN IF NOT EXISTS phone_number TEXT;
```

### Create table SQL

```sql
CREATE TABLE msg_schema.whatsapp_messages (
    id                  BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    message_id          VARCHAR(255) NOT NULL,
    chat_jid            VARCHAR(255) NOT NULL,
    sender_jid          VARCHAR(255),
    participant_jid     VARCHAR(255),
    from_me             BOOLEAN NOT NULL DEFAULT false,
    message_timestamp   TIMESTAMPTZ NOT NULL,
    received_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    message_type        VARCHAR(50) NOT NULL,
    message_text        TEXT,
    has_media           BOOLEAN NOT NULL DEFAULT false,
    media_mime_type     VARCHAR(100),
    media_path          TEXT,
    media_url           TEXT,
    media_filename      TEXT,
    media_size_bytes    BIGINT,
    media_sha256        VARCHAR(255),
    message_status      VARCHAR(30),
    is_forwarded        BOOLEAN DEFAULT false,
    is_ephemeral        BOOLEAN DEFAULT false,
    quoted_message_id   VARCHAR(255),
    quoted_sender_jid   VARCHAR(255),
    quoted_text         TEXT,
    reaction_emoji      VARCHAR(20),
    reaction_to_message_id VARCHAR(255),
    is_deleted          BOOLEAN NOT NULL DEFAULT false,
    deleted_at          TIMESTAMPTZ,
    is_edited           BOOLEAN NOT NULL DEFAULT false,
    edited_at           TIMESTAMPTZ,
    profile_name        VARCHAR(255),
    push_name           VARCHAR(255),
    raw_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    phone_number        TEXT,
    CONSTRAINT whatsapp_messages_message_id_key UNIQUE (message_id),
    CONSTRAINT chk_media_fields CHECK (
        has_media = false
        OR media_mime_type IS NOT NULL
        OR media_path IS NOT NULL
        OR media_url IS NOT NULL
    )
);
```

### Indexes

```sql
CREATE INDEX idx_whatsapp_messages_chat_jid
    ON msg_schema.whatsapp_messages (chat_jid);

CREATE INDEX idx_whatsapp_messages_sender_jid
    ON msg_schema.whatsapp_messages (sender_jid);

CREATE INDEX idx_whatsapp_messages_participant_jid
    ON msg_schema.whatsapp_messages (participant_jid);

CREATE INDEX idx_whatsapp_messages_timestamp
    ON msg_schema.whatsapp_messages (message_timestamp);

CREATE INDEX idx_whatsapp_messages_type
    ON msg_schema.whatsapp_messages (message_type);

CREATE INDEX idx_whatsapp_messages_status
    ON msg_schema.whatsapp_messages (message_status);

CREATE INDEX idx_whatsapp_messages_has_media
    ON msg_schema.whatsapp_messages (has_media);

CREATE INDEX idx_whatsapp_messages_quoted_message_id
    ON msg_schema.whatsapp_messages (quoted_message_id);

CREATE INDEX idx_whatsapp_messages_reaction_to_message_id
    ON msg_schema.whatsapp_messages (reaction_to_message_id);

CREATE INDEX idx_whatsapp_messages_raw_json
    ON msg_schema.whatsapp_messages USING gin (raw_json);
```

---

## 3. Table: `msg_schema.message_analysis`

Per-chat rollup used by the analysis UI. Rows are maintained automatically by the trigger when messages are inserted into `whatsapp_messages`.

### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | `BIGINT` | NO | `nextval(...)` | Primary key |
| `name` | `TEXT` | YES | — | Contact display name |
| `phone_number` | `TEXT` | YES | — | Contact phone |
| `chat_jid` | `TEXT` | YES | — | Chat JID (lookup key) |
| `all_messages` | `TEXT` | YES | — | Newline-separated message log |
| `profile_creation` | `TEXT` | YES | — | Profile notes (manual / future use) |
| `conv_summary` | `TEXT` | YES | — | Conversation summary |
| `actions` | `TEXT` | YES | — | Action items |
| `created_at` | `TIMESTAMPTZ` | NO | `now()` | Row created |
| `updated_at` | `TIMESTAMPTZ` | NO | `now()` | Row last updated |

### Create table SQL

```sql
CREATE TABLE msg_schema.message_analysis (
    id                 BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name               TEXT,
    phone_number       TEXT,
    chat_jid           TEXT,
    all_messages       TEXT,
    profile_creation   TEXT,
    conv_summary       TEXT,
    actions            TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 4. Trigger function and trigger

When a row is inserted into `whatsapp_messages`, the trigger upserts the matching `message_analysis` row (by `chat_jid`) and appends the message text to `all_messages`.

- Inbound messages use `push_name` / `phone_number` on first insert.
- Outbound (`from_me = true`) lines are prefixed with `(me) `.
- Empty `message_text` does not append a line.

### Function

```sql
CREATE OR REPLACE FUNCTION msg_schema.sync_message_analysis_from_whatsapp_messages()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    existing_id BIGINT;
    message_to_append TEXT;
BEGIN
    message_to_append := CASE
        WHEN NEW.message_text IS NULL OR btrim(NEW.message_text) = '' THEN NULL
        WHEN NEW.from_me THEN '(me) ' || NEW.message_text
        ELSE NEW.message_text
    END;

    SELECT id
    INTO existing_id
    FROM msg_schema.message_analysis
    WHERE chat_jid IS NOT DISTINCT FROM NEW.chat_jid
    ORDER BY id
    LIMIT 1;

    IF existing_id IS NULL THEN
        INSERT INTO msg_schema.message_analysis (
            name,
            phone_number,
            chat_jid,
            all_messages,
            conv_summary,
            created_at,
            updated_at
        )
        VALUES (
            CASE WHEN NEW.from_me THEN '' ELSE COALESCE(NEW.push_name, '') END,
            CASE WHEN NEW.from_me THEN '' ELSE COALESCE(NEW.phone_number, '') END,
            NEW.chat_jid,
            message_to_append,
            NULL,
            NOW(),
            NOW()
        );
    ELSE
        UPDATE msg_schema.message_analysis
        SET all_messages = CASE
                WHEN message_to_append IS NULL THEN all_messages
                WHEN all_messages IS NULL OR btrim(all_messages) = '' THEN message_to_append
                ELSE all_messages || E'\n' || message_to_append
            END,
            updated_at = NOW()
        WHERE id = existing_id;
    END IF;

    RETURN NEW;
END;
$function$;
```

### Trigger

```sql
CREATE TRIGGER trg_sync_message_analysis_from_whatsapp_messages
    AFTER INSERT ON msg_schema.whatsapp_messages
    FOR EACH ROW
    EXECUTE FUNCTION msg_schema.sync_message_analysis_from_whatsapp_messages();
```

> **PostgreSQL 14 and older:** use `EXECUTE PROCEDURE` instead of `EXECUTE FUNCTION` in the `CREATE TRIGGER` statement.

---

## 5. Full bootstrap script (run in order)

Run while connected to `whatsapp_db` as a user with DDL rights:

```sql
CREATE SCHEMA IF NOT EXISTS msg_schema;

-- whatsapp_messages (section 2)
-- paste CREATE TABLE + indexes here

-- message_analysis (section 3)
-- paste CREATE TABLE here

-- trigger function + trigger (section 4)
-- paste function + CREATE TRIGGER here
```

Or save sections 2–4 into a single file (e.g. `scripts/init_msg_schema.sql`) and run:

```powershell
psql -h 127.0.0.1 -p 5432 -U your_app_role -d whatsapp_db -f scripts/init_msg_schema.sql
```

You will be prompted for the password; do not store it in the script.

---

## 6. Verify installation

```sql
-- Schemas and tables
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'msg_schema'
ORDER BY table_name;

-- Columns
SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'msg_schema'
ORDER BY table_name, ordinal_position;

-- Triggers
SELECT tgname, tgrelid::regclass AS table_name, pg_get_triggerdef(oid) AS definition
FROM pg_trigger
WHERE tgrelid IN (
    'msg_schema.whatsapp_messages'::regclass,
    'msg_schema.message_analysis'::regclass
)
AND NOT tgisinternal;

-- Row counts (optional)
SELECT 'whatsapp_messages' AS table_name, COUNT(*) FROM msg_schema.whatsapp_messages
UNION ALL
SELECT 'message_analysis', COUNT(*) FROM msg_schema.message_analysis;
```

Expected tables: `whatsapp_messages`, `message_analysis`.  
Expected trigger: `trg_sync_message_analysis_from_whatsapp_messages` on `whatsapp_messages`.

---

## 7. How the application uses the database

| Operation | Table | Notes |
|-----------|-------|-------|
| `POST /webhook/messages` | `whatsapp_messages` | Insert if `message_id` (+ `chat_jid`) not already present |
| `POST /messages/send` | `whatsapp_messages` | Saves outbound message after gateway send |
| `GET /messages?source=db` | `whatsapp_messages` | Recent rows, ordered by `message_timestamp` |
| `GET /analysis/contacts` | `message_analysis` | Contacts with `chat_jid`, excludes gateway’s own number |
| `GET /analysis/conversation` | `message_analysis` | Full row for one `chat_jid` |

**Dedup logic (application):** `get_message_by_message_id` filters by `message_id` and `chat_jid`. The database enforces **unique `message_id` only** (not composite with `chat_jid`).

**Trigger side effect:** Every successful insert into `whatsapp_messages` updates or creates the corresponding `message_analysis` row.

---

## 8. Example queries

```sql
-- Latest 20 messages
SELECT id, message_id, chat_jid, phone_number, from_me, message_timestamp, message_type, message_text
FROM msg_schema.whatsapp_messages
ORDER BY message_timestamp DESC, id DESC
LIMIT 20;

-- Analysis contacts (same idea as the API)
SELECT id, name, phone_number, chat_jid, updated_at
FROM msg_schema.message_analysis
WHERE chat_jid IS NOT NULL
ORDER BY LOWER(COALESCE(NULLIF(name, ''), NULLIF(phone_number, ''), chat_jid)), id;

-- One conversation transcript
SELECT chat_jid, all_messages, conv_summary, actions, updated_at
FROM msg_schema.message_analysis
WHERE chat_jid = '9198xxxxxxxx@s.whatsapp.net'
LIMIT 1;
```

---

## 9. Troubleshooting

| Issue | What to check |
|-------|----------------|
| `relation "msg_schema.whatsapp_messages" does not exist` | Run schema/table DDL in section 5 |
| `permission denied for schema msg_schema` | Run `GRANT` statements in section 1 |
| `function msg_schema.sync_message_analysis_from_whatsapp_messages() does not exist` | Create the function before the trigger |
| Trigger never fires | Confirm trigger exists on `whatsapp_messages` (section 6) |
| FastAPI cannot connect | `.env` host/port/db name; PostgreSQL listening on `POSTGRES_HOST:POSTGRES_PORT` |
| `phone_number` column missing on old DB | Run `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in section 2 |

---

## 10. Security notes

- Keep `.env` out of git (already in `.gitignore`).
- Use a dedicated application role with least privilege on `msg_schema` only.
- `raw_json` may contain personal data; treat backups accordingly.
- Rotating credentials does not require schema changes—only update `.env`.
