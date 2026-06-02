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


class WhatsAppMessageRepository:
    def __init__(self) -> None:
        self.conninfo = (
            f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} "
            f"host={DB_HOST} port={DB_PORT}"
        )

    def _connect(self):
        return psycopg.connect(self.conninfo, row_factory=dict_row)

    def get_message_by_message_id(
        self, message_id: str, chat_jid: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        query = """
            SELECT
                id,
                message_id,
                chat_jid,
                from_me,
                message_timestamp,
                message_type,
                message_text
            FROM msg_schema.whatsapp_messages
            WHERE message_id = %s
              AND (%s IS NULL OR chat_jid = %s)
            ORDER BY id DESC
            LIMIT 1
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (message_id, chat_jid, chat_jid))
                return cur.fetchone()

    def insert_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        now = utc_now()
        payload = {
            "message_id": message["message_id"],
            "chat_jid": message["chat_jid"],
            "sender_jid": message.get("sender_jid"),
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
            RETURNING id, message_id, chat_jid, from_me, message_timestamp, message_type, message_text
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
        query = """
            SELECT
                id,
                message_id,
                chat_jid,
                sender_jid,
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
