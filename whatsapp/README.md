# SpeakGov WhatsApp Bridge

Real WhatsApp bridge built on Baileys. It supports text messages, audio
download/transcription, optional voice replies, per-chat short history, and a
QR/status manager for linking an account.

Run locally:

```bash
npm install
HELP_DESK_BASE_URL=http://127.0.0.1:8000 npm start
```

Useful environment variables:

- `AUTO_REPLY=false` to observe inbound messages without answering.
- `SEND_VOICE_REPLIES=false` to disable TTS/voice replies for all inbound messages.
- `SEND_VOICE_FOR_TEXT_REPLIES=false` to keep typed-message replies text-only while still allowing voice replies to audio messages.
- `FORCE_FIRST_REPLY_NEPALI=false` to stop forcing the first auto-reply in a chat to Nepali Devanagari.
- `ALLOW_GROUPS=true` to permit group chats.
- `API_TOKEN=...` to protect bridge admin/send endpoints.
- `AUTH_DIR=...` to store Baileys auth state outside the repo.

The proactive officer-outreach demo path is disabled by default. Do not enable
it for real contacts without operator consent, rate limits, and an audit trail.
