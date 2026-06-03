# Whatsup Local Bridge

This project connects a phone-linked WhatsApp account through `Baileys` and exposes it to Python through a local HTTP bridge.

The setup has two parts:

- `baileys_gateway/`: Node.js service that connects to WhatsApp
- `fastapi_agent/`: Python FastAPI service that reads and sends messages through the gateway

Incoming and outgoing WhatsApp messages are also persisted to a local PostgreSQL table:

- database: `whatsapp_db`
- table: `msg_schema.whatsapp_messages`

For the full architecture and file-by-file explanation, see [Solution_Understanding.md](</C:/KG Files/Tech/Cursor/Whatsup/Solution_Understanding.md:1>).

## Quick Start

## 1. Install dependencies

Python dependencies:

```powershell
pip install -r requirements.txt
```

Node gateway dependencies:

```powershell
cd baileys_gateway
npm install
cd ..
```

## 2. Configure environment

Create or update `.env` using `.env.example` as reference.

Important defaults:

- `BAILEYS_PORT=3001`
- `BAILEYS_GATEWAY_URL=http://127.0.0.1:3001`
- `PYTHON_WEBHOOK_URL=http://127.0.0.1:8000/webhook/messages`
- `USE_PAIRING_CODE=false`
- `POSTGRES_DB=whatsapp_db`
- `POSTGRES_HOST=127.0.0.1`
- `POSTGRES_PORT=5432`
- `POSTGRES_USER=postgres`
- `POSTGRES_PASSWORD=postgres`
- `OPENAI_API_KEY=...`
- `OPENAI_MODEL=gpt-5.5`

## 3. Start the Python service

From the project root:

```powershell
npm run start:python
```

Direct equivalent:

```powershell
uvicorn fastapi_agent.main:app --host 127.0.0.1 --port 8000
```

FastAPI will run on:

```text
http://127.0.0.1:8000
```

UI pages:

- `http://127.0.0.1:8000/analysis`
- `http://127.0.0.1:8000/ai-analyzer`

## 4. Start the Baileys gateway

Open a second terminal in the project root and run:

```powershell
npm run start:gateway
```

Direct equivalent:

```powershell
node baileys_gateway/index.js
```

The gateway will run on:

```text
http://127.0.0.1:3001
```

## 5. Pair WhatsApp

If `USE_PAIRING_CODE=false`, scan the QR shown in the gateway terminal using WhatsApp Linked Devices on your phone.

If `USE_PAIRING_CODE=true`, set `WHATSAPP_PHONE_NUMBER` and use the pairing code flow.

## Common Endpoints

FastAPI:

- `GET /health`
- `GET /gateway/status`
- `GET /messages`
- `GET /messages?source=db`
- `GET /analysis`
- `GET /ai-analyzer`
- `GET /analysis/contacts`
- `GET /analysis/conversation?chat_jid=...`
- `POST /analysis/summary/generate`
- `POST /messages/send`

Gateway:

- `GET /health`
- `GET /status`
- `GET /messages`
- `POST /send`

## Example Send Request

```json
{
  "to": "9198xxxxxxxx",
  "text": "hello from python"
}
```

Send it to:

```text
POST http://127.0.0.1:8000/messages/send
```

## Notes

- This is a local-only setup.
- WhatsApp auth/session files are stored in `baileys_gateway/auth/`.
- Recent gateway messages are stored in `baileys_gateway/data/messages.json`.
- The Python in-memory buffer resets when the FastAPI app restarts.
- The durable message store is PostgreSQL table `msg_schema.whatsapp_messages`.
- Conversation analysis data is read from `msg_schema.message_analysis`.
- AI prompts are stored in `prompts/`. The summary prompt file is `prompts/create_summary.md`.
- The AI Analyzer summary action calls OpenAI server-side, so `OPENAI_API_KEY` must be present in `.env`.
