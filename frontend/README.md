# SpeakGov Frontend

React/Vite frontend for the PreVillage/SpeakGov demo.

Routes:

- `/` public landing and entry point.
- `/chat` source-backed web chat.
- `/interview` practical-source interview collection.
- `/admin` local/tailnet admin review surface.
- `/whatsapp` WhatsApp bridge QR/status manager.
- `/kiosk` live voice kiosk mode.

Run locally:

```bash
pnpm install
VITE_API_BASE=http://127.0.0.1:8000 pnpm dev
```

Build:

```bash
pnpm build
```
