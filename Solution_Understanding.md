# Solution Understanding

## Overview

This project is a local two-service setup that lets you:

- connect a phone to WhatsApp using `Baileys` in Node.js
- receive WhatsApp messages locally
- forward those messages to a Python app
- send WhatsApp messages from Python through the Node gateway

The solution is split into:

1. a `Node.js` gateway that talks to WhatsApp Web through Baileys
2. a `FastAPI` app in Python that reads incoming messages and sends outgoing ones
3. a local PostgreSQL table that stores both inbound and outbound WhatsApp messages

The Node service is the only part that speaks directly to WhatsApp.  
The Python service speaks to the Node service over local HTTP.

## Folder Structure

At a high level, the important folders and files are:

- `baileys_gateway/`
- `fastapi_agent/`
- `.env`
- `.env.example`
- `package.json`
- `requirements.txt`
- `.gitignore`

## How The Solution Works

## 1. Baileys Gateway

File: [baileys_gateway/index.js](</C:/KG Files/Tech/Cursor/Whatsup/baileys_gateway/index.js:1>)

This is the WhatsApp integration layer.

Its responsibilities are:

- start a Baileys socket session
- create or reuse WhatsApp auth files in `baileys_gateway/auth/`
- show a QR code in the terminal for phone pairing
- optionally support pairing-code mode through environment variables
- detect connection state changes
- listen for incoming WhatsApp messages
- store a recent message history in `baileys_gateway/data/messages.json`
- forward incoming messages to the Python webhook
- expose a local HTTP API for status, message history, and sending messages

Important endpoints exposed by the gateway:

- `GET /health`
- `GET /status`
- `GET /messages`
- `POST /send`
- `POST /pairing-code`

### What happens when a WhatsApp message arrives

1. Baileys receives the message from WhatsApp.
2. The gateway extracts a simple text payload.
3. The message is stored locally in `baileys_gateway/data/messages.json`.
4. The same message is posted to the Python webhook at:
   `http://127.0.0.1:8000/webhook/messages`

### What happens when Python wants to send a message

1. Python calls the gateway’s `POST /send` endpoint.
2. The gateway converts the phone number into a WhatsApp JID if needed.
3. Baileys sends the text message to WhatsApp.

## 2. FastAPI Python App

File: [fastapi_agent/main.py](</C:/KG Files/Tech/Cursor/Whatsup/fastapi_agent/main.py:1>)

This is the Python-facing application layer.

Its responsibilities are:

- expose local HTTP endpoints you can call from Python tools or other apps
- receive incoming message webhooks from the Node gateway
- keep a recent in-memory buffer of received messages
- provide endpoints to read messages
- provide an endpoint to send messages through the Node gateway
- write both incoming and outgoing messages into PostgreSQL
- expose gateway health and status for debugging

## 3. PostgreSQL Persistence

Database:

- `whatsapp_db`

Table:

- `msg_schema.whatsapp_messages`

File: [fastapi_agent/database.py](</C:/KG Files/Tech/Cursor/Whatsup/fastapi_agent/database.py:1>)

This file handles database persistence.

Its responsibilities are:

- connect to local PostgreSQL
- normalize timestamps into timezone-aware values
- insert incoming and outgoing WhatsApp messages
- fetch recent saved messages from the database

The FastAPI app writes to this table in two places:

- when the gateway posts an incoming message webhook
- when Python sends an outgoing message through `POST /messages/send`

Important endpoints exposed by FastAPI:

- `GET /health`
- `GET /gateway/health`
- `GET /gateway/status`
- `GET /messages`
- `POST /messages/send`
- `POST /webhook/messages`

### Message sources in FastAPI

The `GET /messages` endpoint supports two views:

- `source=buffer`
  Returns the recent messages buffered in Python memory from webhook deliveries.
- `source=gateway`
  Fetches recent messages directly from the Node gateway store.

This gives you two useful ways to work:

- use the Python buffer for quick “what just arrived” logic
- use the gateway store when you want the Node-side saved history

## 4. Reusable Python Gateway Client

File: [fastapi_agent/whatsapp_client.py](</C:/KG Files/Tech/Cursor/Whatsup/fastapi_agent/whatsapp_client.py:1>)

This file contains a small reusable Python client class:

- `WhatsAppGatewayClient`

It wraps the Node gateway HTTP calls for:

- health checks
- status checks
- reading messages
- sending text messages

This is helpful if you later want to:

- build another Python script
- add automation logic
- create a bot workflow
- integrate with another FastAPI route or background worker

## File-by-File Role

### Root files

File: [package.json](</C:/KG Files/Tech/Cursor/Whatsup/package.json:1>)

- defines local helper scripts
- `npm run start:gateway` starts the Baileys service
- `npm run start:python` starts the FastAPI app

File: [requirements.txt](</C:/KG Files/Tech/Cursor/Whatsup/requirements.txt:1>)

- lists Python dependencies required by the FastAPI app

File: [.env](</C:/KG Files/Tech/Cursor/Whatsup/.env:1>)

- holds your local environment variables
- should remain local/private

File: [.env.example](</C:/KG Files/Tech/Cursor/Whatsup/.env.example:1>)

- sample environment settings
- use this as the reference for expected configuration

File: [.gitignore](</C:/KG Files/Tech/Cursor/Whatsup/.gitignore:1>)

- ignores local runtime files such as:
  - Python virtual environment
  - Node modules
  - Baileys auth files
  - Baileys local message store

### Gateway files

File: [baileys_gateway/index.js](</C:/KG Files/Tech/Cursor/Whatsup/baileys_gateway/index.js:1>)

- the main Node/Baileys service

Folder: `baileys_gateway/auth/`

- stores WhatsApp session/auth files created by Baileys
- this lets you reconnect without pairing every time

Folder: `baileys_gateway/data/`

- stores recent message history in JSON

File: [baileys_gateway/package.json](</C:/KG Files/Tech/Cursor/Whatsup/baileys_gateway/package.json:1>)

- Node dependencies for the gateway itself

### Python files

File: [fastapi_agent/main.py](</C:/KG Files/Tech/Cursor/Whatsup/fastapi_agent/main.py:1>)

- the FastAPI app entry point

File: [fastapi_agent/database.py](</C:/KG Files/Tech/Cursor/Whatsup/fastapi_agent/database.py:1>)

- the PostgreSQL repository used to write and read WhatsApp messages

File: [fastapi_agent/whatsapp_client.py](</C:/KG Files/Tech/Cursor/Whatsup/fastapi_agent/whatsapp_client.py:1>)

- the reusable Python client for talking to the gateway

## Environment Variables

You can configure the solution using `.env`.

Important settings:

- `BAILEYS_HOST`
  Host for the Node gateway, usually `127.0.0.1`

- `BAILEYS_PORT`
  Port for the Node gateway, currently `3001`

- `BAILEYS_GATEWAY_URL`
  Base URL used by Python to talk to the Node gateway

- `PYTHON_WEBHOOK_URL`
  URL the Node gateway calls when a new WhatsApp message arrives

- `USE_PAIRING_CODE`
  `false` means QR login in terminal
  `true` enables pairing-code mode

- `WHATSAPP_PHONE_NUMBER`
  Needed if you want pairing-code mode

- `MAX_STORED_MESSAGES`
  How many recent messages the Node gateway stores on disk

- `MAX_BUFFERED_MESSAGES`
  How many recent messages FastAPI keeps in memory

- `POSTGRES_DB`
  Local database name, default `whatsapp_db`

- `POSTGRES_USER`
  PostgreSQL username

- `POSTGRES_PASSWORD`
  PostgreSQL password

- `POSTGRES_HOST`
  PostgreSQL host, usually `127.0.0.1`

- `POSTGRES_PORT`
  PostgreSQL port, usually `5432`

## How To Run The Program

## Prerequisites

Make sure you have:

- Node.js installed
- Python installed
- Python dependencies installed in your local environment
- Node dependencies installed for the gateway
- a phone with WhatsApp available for pairing

## Start the Python service

From the project root:

```powershell
npm run start:python
```

This starts FastAPI on:

```text
http://127.0.0.1:8000
```

## Start the Baileys gateway

From the project root in a second terminal:

```powershell
npm run start:gateway
```

This starts the Node gateway on:

```text
http://127.0.0.1:3001
```

## Pair the phone

If `USE_PAIRING_CODE=false`:

1. start the gateway
2. watch the terminal for the QR output
3. open WhatsApp on your phone
4. use Linked Devices
5. scan the QR code

If `USE_PAIRING_CODE=true`:

1. set `WHATSAPP_PHONE_NUMBER` in `.env`
2. start the gateway
3. request or use the printed pairing code

## Verify the services

Check FastAPI:

```text
GET http://127.0.0.1:8000/health
```

Check the Node gateway:

```text
GET http://127.0.0.1:3001/health
```

Check WhatsApp connection status through Python:

```text
GET http://127.0.0.1:8000/gateway/status
```

## Read messages

Read messages buffered in Python:

```text
GET http://127.0.0.1:8000/messages
```

Read messages directly from the Node-side store:

```text
GET http://127.0.0.1:8000/messages?source=gateway
```

Read messages from PostgreSQL:

```text
GET http://127.0.0.1:8000/messages?source=db
```

## Send messages

Use the FastAPI endpoint:

```text
POST http://127.0.0.1:8000/messages/send
Content-Type: application/json
```

Example body:

```json
{
  "to": "9198xxxxxxxx",
  "text": "hello from python"
}
```

## Example Python Usage

You can also build directly on the reusable client:

```python
from fastapi_agent.whatsapp_client import WhatsAppGatewayClient

client = WhatsAppGatewayClient("http://127.0.0.1:3001")

print(client.status())
print(client.get_messages(limit=5))
print(client.send_text("9198xxxxxxxx", "hello from python"))
```

## Message Flow Summary

### Incoming messages

1. Phone/WhatsApp sends message
2. Baileys receives it in Node
3. Gateway stores it locally
4. Gateway posts it to Python webhook
5. FastAPI buffers it for Python-side access
6. FastAPI writes it into `msg_schema.whatsapp_messages`

### Outgoing messages

1. Python code or FastAPI route requests a send
2. FastAPI calls the gateway
3. Gateway uses Baileys to send through WhatsApp
4. FastAPI writes the outbound message into `msg_schema.whatsapp_messages`
5. Message is delivered from the paired account

## Notes And Limitations

- This solution is local-only.
- The WhatsApp session is tied to the paired phone/account.
- If you log out of WhatsApp linked devices, you may need to re-pair.
- The FastAPI message buffer is in memory and resets when the Python app restarts.
- The gateway message history is stored locally in JSON and is only a recent-message cache.
- PostgreSQL is the durable message store for both incoming and outgoing records.
- Real WhatsApp behavior depends on the state of the phone, linked-device session, and Baileys compatibility.

## Troubleshooting

### Gateway says not connected

- make sure the phone was paired successfully
- check `GET /gateway/status`
- restart the gateway if needed

### Messages are not reaching Python

- make sure FastAPI is running on port `8000`
- confirm `PYTHON_WEBHOOK_URL` matches the FastAPI webhook route
- check the gateway terminal for webhook warnings

### Send message fails

- make sure WhatsApp is connected first
- verify the phone number format
- try using a full international number without symbols

### Need to pair again

- stop the gateway
- remove the session files inside `baileys_gateway/auth/`
- start the gateway again and re-pair

## In One Sentence

Baileys in Node handles the real WhatsApp connection, and Python uses a local HTTP bridge to read incoming messages and send outgoing ones safely within your machine.
