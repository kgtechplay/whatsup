from collections import deque
import os
from typing import Any, Deque, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

load_dotenv()

from fastapi_agent.database import WhatsAppMessageRepository, utc_now
from fastapi_agent.whatsapp_client import WhatsAppGatewayClient


class SendMessageRequest(BaseModel):
    to: str = Field(..., description="Phone number or WhatsApp JID")
    text: str = Field(..., min_length=1, description="Message body")


class MessageRecord(BaseModel):
    message_id: str
    chat_jid: str
    sender_jid: Optional[str] = None
    participant_jid: Optional[str] = None
    from_me: bool = False
    message_timestamp: Optional[Any] = None
    received_at: Optional[Any] = None
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None
    message_type: str = "unknown"
    message_text: Optional[str] = None
    has_media: bool = False
    media_mime_type: Optional[str] = None
    media_path: Optional[str] = None
    media_url: Optional[str] = None
    media_filename: Optional[str] = None
    media_size_bytes: Optional[int] = None
    media_sha256: Optional[str] = None
    message_status: Optional[str] = None
    is_forwarded: bool = False
    is_ephemeral: bool = False
    quoted_message_id: Optional[str] = None
    quoted_sender_jid: Optional[str] = None
    quoted_text: Optional[str] = None
    reaction_emoji: Optional[str] = None
    reaction_to_message_id: Optional[str] = None
    is_deleted: bool = False
    deleted_at: Optional[Any] = None
    is_edited: bool = False
    edited_at: Optional[Any] = None
    profile_name: Optional[str] = None
    push_name: Optional[str] = None
    raw_json: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


GATEWAY_URL = os.getenv("BAILEYS_GATEWAY_URL", "http://127.0.0.1:3001")
MAX_BUFFERED_MESSAGES = int(os.getenv("MAX_BUFFERED_MESSAGES", "200"))
gateway = WhatsAppGatewayClient(GATEWAY_URL)
repository = WhatsAppMessageRepository()
recent_messages: Deque[Dict] = deque(maxlen=MAX_BUFFERED_MESSAGES)

app = FastAPI(title="Whatsup Agent")


def save_message_to_db(entry: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return repository.insert_message_if_new(entry)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write WhatsApp message to PostgreSQL: {exc}",
        ) from exc


def fetch_messages_from_db(limit: int) -> Dict[str, Any]:
    try:
        return {"messages": repository.fetch_messages(limit=limit), "source": "db"}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read WhatsApp messages from PostgreSQL: {exc}",
        ) from exc


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "fastapi-agent",
        "gateway_url": GATEWAY_URL,
        "postgres_db": os.getenv("POSTGRES_DB", "whatsapp_db"),
    }


@app.get("/gateway/health")
def gateway_health():
    return gateway.health()


@app.get("/gateway/status")
def gateway_status():
    return gateway.status()


@app.get("/messages")
def list_messages(limit: int = 20, source: str = "buffer"):
    if source == "gateway":
        return {"messages": gateway.get_messages(limit=limit), "source": "gateway"}

    if source == "db":
        return fetch_messages_from_db(limit)

    buffered = list(recent_messages)
    return {"messages": buffered[:limit], "source": "buffer"}


@app.post("/messages/send")
def send_message(payload: SendMessageRequest):
    gateway_response = gateway.send_text(payload.to, payload.text)
    now = utc_now()
    record = MessageRecord(
        message_id=gateway_response.get("id") or f"local-{int(now.timestamp() * 1000)}",
        chat_jid=gateway_response.get("to") or payload.to,
        sender_jid=gateway_response.get("me", {}).get("id") if isinstance(gateway_response.get("me"), dict) else None,
        from_me=True,
        message_timestamp=gateway_response.get("messageTimestamp") or now,
        received_at=now,
        created_at=now,
        updated_at=now,
        message_type=gateway_response.get("messageType", "conversation"),
        message_text=payload.text,
        message_status=gateway_response.get("messageStatus", "sent"),
        push_name=gateway_response.get("me", {}).get("name") if isinstance(gateway_response.get("me"), dict) else None,
        raw_json={
            "request": payload.model_dump(),
            "gateway_response": gateway_response,
        },
    )

    saved = save_message_to_db(record.model_dump())
    recent_messages.appendleft(
        {
            "message_id": record.message_id,
            "chat_jid": record.chat_jid,
            "message_text": record.message_text,
            "from_me": True,
            "message_type": record.message_type,
        }
    )
    return {"gateway": gateway_response, "database": saved}


@app.post("/webhook/messages")
def receive_message(message: MessageRecord):
    entry = message.model_dump()
    recent_messages.appendleft(entry)
    saved = save_message_to_db(entry)
    return {"ok": True, "buffered_messages": len(recent_messages), "database": saved}
