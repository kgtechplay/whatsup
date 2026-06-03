import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import makeWASocket, {
  Browsers,
  DisconnectReason,
  useMultiFileAuthState,
} from '@whiskeysockets/baileys'
import { Boom } from '@hapi/boom'
import pino from 'pino'
import qrcode from 'qrcode-terminal'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT_DIR = path.dirname(__dirname)
const AUTH_DIR = path.join(__dirname, 'auth')
const DATA_DIR = path.join(__dirname, 'data')
const MESSAGE_STORE_PATH = path.join(DATA_DIR, 'messages.json')

function loadEnvFile() {
  const envPath = path.join(ROOT_DIR, '.env')
  if (!fs.existsSync(envPath)) {
    return
  }

  const raw = fs.readFileSync(envPath, 'utf8')
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) {
      continue
    }

    const separatorIndex = trimmed.indexOf('=')
    if (separatorIndex === -1) {
      continue
    }

    const key = trimmed.slice(0, separatorIndex).trim()
    const value = trimmed.slice(separatorIndex + 1).trim()

    if (!(key in process.env)) {
      process.env[key] = value
    }
  }
}

loadEnvFile()

const PORT = Number(process.env.BAILEYS_PORT || 3001)
const HOST = process.env.BAILEYS_HOST || '127.0.0.1'
const PYTHON_WEBHOOK_URL =
  process.env.PYTHON_WEBHOOK_URL || 'http://127.0.0.1:8000/webhook/messages'
const PAIRING_PHONE_NUMBER = process.env.WHATSAPP_PHONE_NUMBER || ''
const USE_PAIRING_CODE = process.env.USE_PAIRING_CODE === 'true'
const MAX_STORED_MESSAGES = Number(process.env.MAX_STORED_MESSAGES || 200)

fs.mkdirSync(AUTH_DIR, { recursive: true })
fs.mkdirSync(DATA_DIR, { recursive: true })

let sock = null
let isConnecting = false
let isConnected = false
let lastConnectionUpdate = null
let pairingCode = null
let messages = loadMessages()
let lastQrValue = null

function loadMessages() {
  if (!fs.existsSync(MESSAGE_STORE_PATH)) {
    return []
  }

  try {
    return JSON.parse(fs.readFileSync(MESSAGE_STORE_PATH, 'utf8'))
  } catch (error) {
    console.warn('Failed to load message store:', error.message)
    return []
  }
}

function saveMessages() {
  fs.writeFileSync(MESSAGE_STORE_PATH, JSON.stringify(messages, null, 2))
}

function rememberMessage(entry) {
  messages.unshift(entry)
  messages = messages.slice(0, MAX_STORED_MESSAGES)
  saveMessages()
}

function normalizeJid(recipient) {
  if (!recipient || typeof recipient !== 'string') {
    throw new Error('Recipient is required')
  }

  const trimmed = recipient.trim()
  if (trimmed.includes('@')) {
    return trimmed
  }

  const digits = trimmed.replace(/\D/g, '')
  if (!digits) {
    throw new Error('Recipient must be a phone number or WhatsApp JID')
  }

  return `${digits}@s.whatsapp.net`
}

function normalizeStoredJid(jid) {
  if (!jid || typeof jid !== 'string') {
    return jid || null
  }

  const trimmed = jid.trim()
  const atIndex = trimmed.indexOf('@')
  if (atIndex === -1) {
    return trimmed
  }

  const user = trimmed.slice(0, atIndex)
  const domain = trimmed.slice(atIndex + 1)
  const normalizedUser = user.includes(':') ? user.split(':')[0] : user
  return `${normalizedUser}@${domain}`
}

function extractText(message) {
  if (!message) {
    return ''
  }

  return (
    message.conversation ||
    message.extendedTextMessage?.text ||
    message.imageMessage?.caption ||
    message.videoMessage?.caption ||
    message.documentMessage?.caption ||
    message.buttonsResponseMessage?.selectedButtonId ||
    message.listResponseMessage?.title ||
    message.templateButtonReplyMessage?.selectedId ||
    ''
  )
}

function getPrimaryMessageContent(message) {
  if (!message) {
    return null
  }

  if (message.ephemeralMessage?.message) {
    return getPrimaryMessageContent(message.ephemeralMessage.message)
  }

  if (message.viewOnceMessage?.message) {
    return getPrimaryMessageContent(message.viewOnceMessage.message)
  }

  return message
}

function getMessageType(message) {
  const content = getPrimaryMessageContent(message)
  return Object.keys(content || {})[0] || 'unknown'
}

function getContextInfo(message) {
  const content = getPrimaryMessageContent(message)
  const messageType = getMessageType(content)
  return content?.[messageType]?.contextInfo || {}
}

function extractMediaDetails(message) {
  const content = getPrimaryMessageContent(message)
  const messageType = getMessageType(content)
  const media = content?.[messageType]
  const mediaTypes = new Set([
    'imageMessage',
    'videoMessage',
    'documentMessage',
    'audioMessage',
    'stickerMessage',
  ])

  if (!mediaTypes.has(messageType) || !media) {
    return {
      has_media: false,
      media_mime_type: null,
      media_filename: null,
      media_size_bytes: null,
      media_sha256: null,
    }
  }

  return {
    has_media: true,
    media_mime_type: media.mimetype || null,
    media_filename: media.fileName || null,
    media_size_bytes: media.fileLength ? Number(media.fileLength) : null,
    media_sha256: media.fileSha256 ? Buffer.from(media.fileSha256).toString('base64') : null,
  }
}

function buildMessageEntry(incoming, selfJid = null) {
  const content = getPrimaryMessageContent(incoming.message)
  const messageType = getMessageType(content)
  const contextInfo = getContextInfo(content)
  const media = extractMediaDetails(content)
  const reaction = content?.reactionMessage
  const fromMe = Boolean(incoming.key.fromMe)
  const remoteJid = normalizeStoredJid(incoming.key.remoteJid)
  const participantJid = normalizeStoredJid(incoming.key.participant || null)
  const senderJid = normalizeStoredJid(fromMe ? selfJid || remoteJid : participantJid || remoteJid)

  return {
    message_id: incoming.key.id,
    chat_jid: remoteJid,
    sender_jid: senderJid,
    participant_jid: participantJid,
    from_me: fromMe,
    message_timestamp: incoming.messageTimestamp
      ? Number(incoming.messageTimestamp) * 1000
      : Date.now(),
    message_type: messageType,
    message_text: extractText(content),
    has_media: media.has_media,
    media_mime_type: media.media_mime_type,
    media_path: null,
    media_url: null,
    media_filename: media.media_filename,
    media_size_bytes: media.media_size_bytes,
    media_sha256: media.media_sha256,
    message_status: fromMe ? 'sent' : 'received',
    is_forwarded: Boolean(contextInfo?.isForwarded),
    is_ephemeral: Boolean(incoming.message?.ephemeralMessage),
    quoted_message_id: contextInfo?.stanzaId || null,
    quoted_sender_jid: normalizeStoredJid(contextInfo?.participant || null),
    quoted_text: contextInfo?.quotedMessage
      ? extractText(contextInfo.quotedMessage)
      : null,
    reaction_emoji: reaction?.text || null,
    reaction_to_message_id: reaction?.key?.id || null,
    is_deleted: false,
    deleted_at: null,
    is_edited: false,
    edited_at: null,
    profile_name: incoming.verifiedBizName || null,
    push_name: incoming.pushName || null,
    raw_json: incoming,
  }
}

async function sendWebhook(entry) {
  try {
    await fetch(PYTHON_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(entry),
    })
  } catch (error) {
    console.warn('Webhook delivery failed:', error.message)
  }
}

async function ensureSocket() {
  if (sock || isConnecting) {
    return
  }

  isConnecting = true

  try {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR)

    sock = makeWASocket({
      auth: state,
      logger: pino({ level: 'silent' }),
      browser: Browsers.windows('Desktop'),
      printQRInTerminal: !USE_PAIRING_CODE,
      syncFullHistory: false,
    })

    sock.ev.on('creds.update', saveCreds)

    sock.ev.on('connection.update', async (update) => {
      lastConnectionUpdate = update

      if (update.qr) {
        if (update.qr !== lastQrValue) {
          lastQrValue = update.qr
          console.log('Scan this QR code with WhatsApp on your phone:')
          qrcode.generate(update.qr, { small: true })
        }
        console.log('Scan the QR code shown in this terminal with WhatsApp on your phone.')
      }

      if (
        USE_PAIRING_CODE &&
        !state.creds.registered &&
        !pairingCode &&
        PAIRING_PHONE_NUMBER
      ) {
        try {
          pairingCode = await sock.requestPairingCode(PAIRING_PHONE_NUMBER)
          console.log(`Pairing code: ${pairingCode}`)
        } catch (error) {
          console.error('Failed to request pairing code:', error.message)
        }
      }

      if (update.connection === 'open') {
        isConnected = true
        pairingCode = null
        lastQrValue = null
        console.log('WhatsApp connected')
      }

      if (update.connection === 'close') {
        isConnected = false
        const statusCode = new Boom(update.lastDisconnect?.error)?.output?.statusCode
        const shouldReconnect = statusCode !== DisconnectReason.loggedOut
        console.log('Connection closed. Reconnect:', shouldReconnect)
        sock = null

        if (shouldReconnect) {
          setTimeout(() => {
            ensureSocket().catch((error) => {
              console.error('Reconnect failed:', error)
            })
          }, 3000)
        } else {
          console.log('Logged out. Delete the auth folder to pair again.')
        }
      }
    })

    sock.ev.on('messages.upsert', async ({ messages: upserted, type }) => {
      if (type !== 'notify') {
        return
      }

      for (const incoming of upserted) {
        const entry = buildMessageEntry(incoming, sock?.user?.id || null)

        rememberMessage(entry)
        console.log(
          `${entry.from_me ? 'Outgoing' : 'Incoming'} message ${entry.from_me ? 'to' : 'from'} ${entry.chat_jid}: ${entry.message_text || ''}`
        )
        await sendWebhook(entry)
      }
    })
  } finally {
    isConnecting = false
  }
}

function getStatusPayload() {
  return {
    connected: isConnected,
    connecting: isConnecting,
    me: sock?.user || null,
    pairingCode,
    lastConnectionUpdate,
    storedMessages: messages.length,
  }
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let body = ''

    req.on('data', (chunk) => {
      body += chunk
    })

    req.on('end', () => {
      if (!body) {
        resolve({})
        return
      }

      try {
        resolve(JSON.parse(body))
      } catch (error) {
        reject(new Error('Invalid JSON body'))
      }
    })

    req.on('error', reject)
  })
}

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify(payload))
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host}`)

    if (req.method === 'GET' && url.pathname === '/health') {
      sendJson(res, 200, { status: 'ok', service: 'baileys-gateway' })
      return
    }

    if (req.method === 'GET' && url.pathname === '/status') {
      sendJson(res, 200, getStatusPayload())
      return
    }

    if (req.method === 'GET' && url.pathname === '/messages') {
      const limit = Number(url.searchParams.get('limit') || 20)
      sendJson(res, 200, { messages: messages.slice(0, limit) })
      return
    }

    if (req.method === 'POST' && url.pathname === '/send') {
      const { to, text } = await readJsonBody(req)

      if (!sock || !isConnected) {
        sendJson(res, 503, { error: 'WhatsApp is not connected yet' })
        return
      }

      if (!text || typeof text !== 'string') {
        sendJson(res, 400, { error: 'Text is required' })
        return
      }

      const jid = normalizeJid(to)
      const result = await sock.sendMessage(jid, { text })

      sendJson(res, 200, {
        ok: true,
        to: jid,
        id: result?.key?.id || null,
        me: sock?.user
          ? {
              ...sock.user,
              id: normalizeStoredJid(sock.user.id),
            }
          : null,
        messageType: 'conversation',
        messageStatus: 'sent',
        messageTimestamp: Date.now(),
        raw: result || null,
      })
      return
    }

    if (req.method === 'POST' && url.pathname === '/pairing-code') {
      const { phoneNumber } = await readJsonBody(req)

      if (!sock) {
        sendJson(res, 503, { error: 'Socket is not ready yet' })
        return
      }

      const requestedPhone = (phoneNumber || PAIRING_PHONE_NUMBER || '').replace(/\D/g, '')
      if (!requestedPhone) {
        sendJson(res, 400, {
          error: 'Provide phoneNumber or set WHATSAPP_PHONE_NUMBER in the environment',
        })
        return
      }

      pairingCode = await sock.requestPairingCode(requestedPhone)
      sendJson(res, 200, { pairingCode })
      return
    }

    sendJson(res, 404, { error: 'Not found' })
  } catch (error) {
    sendJson(res, 500, { error: error.message || 'Internal server error' })
  }
})

server.listen(PORT, HOST, () => {
  console.log(`Baileys gateway listening on http://${HOST}:${PORT}`)
  ensureSocket().catch((error) => {
    console.error('Failed to start Baileys socket:', error)
    process.exit(1)
  })
})
