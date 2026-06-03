import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv()


DB_NAME = os.getenv("POSTGRES_DB", "whatsapp_db")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_timestamp(value: Optional[Any]) -> datetime:
    if value is None:
        return utc_now()

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    if isinstance(value, (int, float)):
        if value > 1_000_000_000_000:
            value = value / 1000
        return datetime.fromtimestamp(value, tz=timezone.utc)

    if isinstance(value, str):
        cleaned = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(cleaned)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    return utc_now()


def extract_phone_number_from_jid(jid: Optional[str]) -> Optional[str]:
    if not jid or not isinstance(jid, str):
        return None

    trimmed = jid.strip()
    if not trimmed:
        return None

    user = trimmed.split("@", 1)[0]
    normalized_user = user.split(":", 1)[0].strip()
    digits_only = "".join(ch for ch in normalized_user if ch.isdigit())
    if not digits_only:
        return None

    return f"+{digits_only}"


def extract_phone_number(message: Dict[str, Any]) -> Optional[str]:
    raw_json = message.get("raw_json")
    if isinstance(raw_json, dict):
        key = raw_json.get("key")
        if isinstance(key, dict):
            remote_jid_alt = key.get("remoteJidAlt")
            phone_number = extract_phone_number_from_jid(remote_jid_alt)
            if phone_number:
                return phone_number

    return extract_phone_number_from_jid(message.get("sender_jid"))


class WhatsAppMessageRepository:
    def __init__(self) -> None:
        self.conninfo = (
            f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} "
            f"host={DB_HOST} port={DB_PORT}"
        )
        self._phone_number_column_checked = False

    def _connect(self):
        return psycopg.connect(self.conninfo, row_factory=dict_row)

    def ensure_phone_number_column(self) -> None:
        if self._phone_number_column_checked:
            return

        query = """
            ALTER TABLE msg_schema.whatsapp_messages
            ADD COLUMN IF NOT EXISTS phone_number TEXT
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
            conn.commit()

        self._phone_number_column_checked = True

    def get_message_by_message_id(
        self, message_id: str, chat_jid: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        self.ensure_phone_number_column()
        query = """
            SELECT
                id,
                message_id,
                chat_jid,
                phone_number,
                from_me,
                message_timestamp,
                message_type,
                message_text
            FROM msg_schema.whatsapp_messages
            WHERE message_id = %s
        """
        params: tuple[Any, ...] = (message_id,)

        if chat_jid is None:
            query += "\n  AND chat_jid IS NULL"
        else:
            query += "\n  AND chat_jid = %s"
            params = (message_id, chat_jid)

        query += "\nORDER BY id DESC\nLIMIT 1"

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchone()

    def insert_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        self.ensure_phone_number_column()
        now = utc_now()
        payload = {
            "message_id": message["message_id"],
            "chat_jid": message["chat_jid"],
            "sender_jid": message.get("sender_jid"),
            "phone_number": extract_phone_number(message),
            "participant_jid": message.get("participant_jid"),
            "from_me": bool(message.get("from_me", False)),
            "message_timestamp": normalize_timestamp(message.get("message_timestamp")),
            "received_at": normalize_timestamp(message.get("received_at")) if message.get("received_at") else now,
            "created_at": normalize_timestamp(message.get("created_at")) if message.get("created_at") else now,
            "updated_at": normalize_timestamp(message.get("updated_at")) if message.get("updated_at") else now,
            "message_type": message.get("message_type", "unknown"),
            "message_text": message.get("message_text"),
            "has_media": bool(message.get("has_media", False)),
            "media_mime_type": message.get("media_mime_type"),
            "media_path": message.get("media_path"),
            "media_url": message.get("media_url"),
            "media_filename": message.get("media_filename"),
            "media_size_bytes": message.get("media_size_bytes"),
            "media_sha256": message.get("media_sha256"),
            "message_status": message.get("message_status"),
            "is_forwarded": bool(message.get("is_forwarded", False)),
            "is_ephemeral": bool(message.get("is_ephemeral", False)),
            "quoted_message_id": message.get("quoted_message_id"),
            "quoted_sender_jid": message.get("quoted_sender_jid"),
            "quoted_text": message.get("quoted_text"),
            "reaction_emoji": message.get("reaction_emoji"),
            "reaction_to_message_id": message.get("reaction_to_message_id"),
            "is_deleted": bool(message.get("is_deleted", False)),
            "deleted_at": normalize_timestamp(message.get("deleted_at")) if message.get("deleted_at") else None,
            "is_edited": bool(message.get("is_edited", False)),
            "edited_at": normalize_timestamp(message.get("edited_at")) if message.get("edited_at") else None,
            "profile_name": message.get("profile_name"),
            "push_name": message.get("push_name"),
            "raw_json": json.dumps(message.get("raw_json", {})),
        }

        query = """
            INSERT INTO msg_schema.whatsapp_messages (
                message_id,
                chat_jid,
                sender_jid,
                phone_number,
                participant_jid,
                from_me,
                message_timestamp,
                received_at,
                created_at,
                updated_at,
                message_type,
                message_text,
                has_media,
                media_mime_type,
                media_path,
                media_url,
                media_filename,
                media_size_bytes,
                media_sha256,
                message_status,
                is_forwarded,
                is_ephemeral,
                quoted_message_id,
                quoted_sender_jid,
                quoted_text,
                reaction_emoji,
                reaction_to_message_id,
                is_deleted,
                deleted_at,
                is_edited,
                edited_at,
                profile_name,
                push_name,
                raw_json
            )
            VALUES (
                %(message_id)s,
                %(chat_jid)s,
                %(sender_jid)s,
                %(phone_number)s,
                %(participant_jid)s,
                %(from_me)s,
                %(message_timestamp)s,
                %(received_at)s,
                %(created_at)s,
                %(updated_at)s,
                %(message_type)s,
                %(message_text)s,
                %(has_media)s,
                %(media_mime_type)s,
                %(media_path)s,
                %(media_url)s,
                %(media_filename)s,
                %(media_size_bytes)s,
                %(media_sha256)s,
                %(message_status)s,
                %(is_forwarded)s,
                %(is_ephemeral)s,
                %(quoted_message_id)s,
                %(quoted_sender_jid)s,
                %(quoted_text)s,
                %(reaction_emoji)s,
                %(reaction_to_message_id)s,
                %(is_deleted)s,
                %(deleted_at)s,
                %(is_edited)s,
                %(edited_at)s,
                %(profile_name)s,
                %(push_name)s,
                %(raw_json)s::jsonb
            )
            RETURNING id, message_id, chat_jid, sender_jid, phone_number, from_me, message_timestamp, message_type, message_text
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, payload)
                row = cur.fetchone()
            conn.commit()
        return row

    def insert_message_if_new(self, message: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.get_message_by_message_id(
            message_id=message["message_id"],
            chat_jid=message.get("chat_jid"),
        )
        if existing:
            return {**existing, "inserted": False}

        created = self.insert_message(message)
        return {**created, "inserted": True}

    def fetch_messages(self, limit: int = 20) -> List[Dict[str, Any]]:
        self.ensure_phone_number_column()
        query = """
            SELECT
                id,
                message_id,
                chat_jid,
                sender_jid,
                phone_number,
                participant_jid,
                from_me,
                message_timestamp,
                received_at,
                message_type,
                message_text,
                message_status,
                push_name,
                profile_name
            FROM msg_schema.whatsapp_messages
            ORDER BY message_timestamp DESC, id DESC
            LIMIT %s
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (limit,))
                return cur.fetchall()

    def fetch_message_analysis_contacts(
        self, excluded_phone_number: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT
                id,
                name,
                phone_number,
                chat_jid,
                updated_at
            FROM msg_schema.message_analysis
            WHERE chat_jid IS NOT NULL
            ORDER BY
                CASE
                    WHEN COALESCE(NULLIF(name, ''), NULLIF(phone_number, ''), chat_jid) IS NULL
                        THEN 1
                    ELSE 0
                END,
                LOWER(COALESCE(NULLIF(name, ''), NULLIF(phone_number, ''), chat_jid)),
                id
        """
        params: tuple[Any, ...] = ()

        if excluded_phone_number is not None:
            query = query.replace(
                "ORDER BY",
                "  AND COALESCE(phone_number, '') <> %s\n            ORDER BY",
                1,
            )
            params = (excluded_phone_number,)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall()

    def get_message_analysis_by_chat_jid(self, chat_jid: str) -> Optional[Dict[str, Any]]:
        query = """
            SELECT
                id,
                name,
                phone_number,
                chat_jid,
                all_messages,
                profile_creation,
                conv_summary,
                actions,
                created_at,
                updated_at
            FROM msg_schema.message_analysis
            WHERE chat_jid = %s
            ORDER BY id
            LIMIT 1
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (chat_jid,))
                return cur.fetchone()

    def update_message_analysis_summary(
        self, chat_jid: str, conv_summary: str
    ) -> Optional[Dict[str, Any]]:
        query = """
            UPDATE msg_schema.message_analysis
            SET conv_summary = %s,
                updated_at = NOW()
            WHERE chat_jid = %s
            RETURNING
                id,
                name,
                phone_number,
                chat_jid,
                all_messages,
                profile_creation,
                conv_summary,
                actions,
                created_at,
                updated_at
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (conv_summary, chat_jid))
                row = cur.fetchone()
            conn.commit()
        return row
