# SpeakGov Demo

SpeakGov is a Nepal government-service navigator. It combines a resolver-first
RAG backend, a React chat/admin interface, and an optional WhatsApp bridge.

The core product rule is:

> Resolve the user's case first, retrieve sources based on that case, ask compact
> follow-up questions when needed, include official contacts and uncertainty, and
> avoid generic unsupported answers.

## Components

- `server/`: FastAPI backend for retrieval, answer generation, voice endpoints,
  admin tools, and operator-reviewed outreach drafts.
- `frontend/`: React/Vite UI for chat, admin, WhatsApp manager, and kiosk mode.
- `whatsapp/`: Baileys bridge for WhatsApp text/audio messages.
- `scripts/start_k2_*.sh`: deployment helpers used by the demo machine. They are
  parameterized by environment variables and should not contain secrets.
- `scripts/open_whatsapp_outreach_demo_tmux.sh`: local filming layout for the
  proactive outreach demo.

## Safe WhatsApp Outreach Demo

Production behavior should be operator-reviewed. For filming only, the WhatsApp
bridge supports an explicit demo mode:

```bash
export K2_HOST="<host-or-tailnet-ip>"
export K2_USER="<ssh-user>"
# Optional. Prefer SSH keys. Set K2_PASS only for a throwaway demo machine.
export K2_PASS=""

export PROACTIVE_OUTREACH_DEMO=true
export PROACTIVE_OUTREACH_AUTO_SEND=true
export PROACTIVE_OUTREACH_USER_ALLOWLIST="<tester-jid-1>,<tester-jid-2>"

scripts/open_whatsapp_outreach_demo_tmux.sh
```

The demo flow logs:

1. incoming WhatsApp prompt;
2. route/skip decision;
3. outreach draft target and message preview;
4. sent confirmation.

The outreach message is sanitized and does not forward private citizen details.

## Local Checks

```bash
python3 -m py_compile server/main.py server/navigator.py
node --check whatsapp/src/server.mjs
cd frontend && npm run build
```
