# Proactive WhatsApp Outreach

## Purpose

When SpeakGov cannot answer a user query from reliable retrieved sources, the next production behavior should be:

1. Admit the source gap to the user.
2. Try to find the responsible office/contact from official sources.
3. Draft a concise WhatsApp question to that contact.
4. Let an operator review/send it.
5. Use the official reply as a named practical source only after verification.

This is an escalation loop for missing knowledge. It is not a replacement for RAG, and it must not become automatic spam to government staff.

## Current Implementation

Backend admin endpoints in `server/main.py`:

- `POST /admin/outreach/draft`
  - Auth: HTTP Basic admin auth.
  - Input: `question`, optional `history`, optional `reason`.
  - Resolves the query with the service navigator.
  - Runs a contact-focused official-source retrieval query.
  - Extracts Nepal mobile numbers only from official retrieved sources.
  - Stores a draft under `OUTREACH_DIR/pending`.

- `GET /admin/outreach?status=pending|sent|failed`
  - Lists stored outreach records.

- `GET /admin/outreach/{id}`
  - Reads one outreach record.

- `POST /admin/outreach/{id}/send`
  - Sends the stored draft through the Baileys bridge (`WHATSAPP_BRIDGE_URL`).
  - Moves the record to `OUTREACH_DIR/sent` on success.
  - Moves the record to `OUTREACH_DIR/failed` if the bridge send fails.

Default storage:

```bash
OUTREACH_DIR=/Volumes/T9/gemma-god/outreach
```

## Safety Rules

- Do not send directly from the public `/query` endpoint.
- Do not message landline numbers; WhatsApp send requires a Nepal mobile number.
- Do not use citizen interview phone numbers as official outreach recipients.
- Do not share private citizen details in the outreach message.
- Prefer information officers, helpdesks, grievance officers, and official contact pages.
- Store the source URL/title/host used to select the contact.
- Operator review is required before sending.

## Draft Example

```bash
curl -u admin:$ADMIN_PASSWORD \
  -H 'Content-Type: application/json' \
  -d '{"question":"How do I get birth certificate in Jiri if the ward page does not list documents?","reason":"no current ward/service source found"}' \
  http://127.0.0.1:8000/admin/outreach/draft
```

Send after review:

```bash
curl -u admin:$ADMIN_PASSWORD \
  -X POST \
  http://127.0.0.1:8000/admin/outreach/<id>/send
```

## Next Integration

The next product step is to surface this from the chat flow:

1. If retrieval quality fails or the composer refuses due to missing sources, show the user a grounded answer:
   - "I do not have a reliable current source for this exact case."
   - "I found this likely office/contact."
   - "I can route a question to the responsible office without sharing private details."
2. Create an outreach draft only after user/operator confirmation.
3. When the official replies, put that answer into the interview/verified practical-source pipeline with the responder name, role, source office, timestamp, and expiry.

For filming/demo only, the WhatsApp bridge can run with:

```bash
PROACTIVE_OUTREACH_DEMO=true
PROACTIVE_OUTREACH_AUTO_SEND=true
PROACTIVE_OUTREACH_USER_ALLOWLIST="<tester-jid>"
```

That path is intentionally gated by environment variables and should stay
limited to tester accounts. It logs incoming prompts, route/skip decisions,
drafts, and sends to the demo JSONL log.
