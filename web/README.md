# Speak Gov — web client

Single-file HTML chat interface to the gemma-god RAG server. Same feature
set as the Android app: chat, citation cards (color-coded for tacit vs
gov.np sources), refusal-with-tap-to-dial, configurable server URL +
bearer token at runtime.

**Zero build, zero deps, zero JS framework.** Drop the `index.html`
anywhere. The whole thing is one file with inline CSS + vanilla JS.

## Deploy

Anywhere that serves static files works:

```
ampixa.com/speakgov/index.html        ← traditional web server
                              or
GitHub Pages, Cloudflare Pages, Vercel, Netlify, S3, etc.
```

For your domain (`ampixa.com/speakgov`), the simplest path is whichever
hosts your site already:

- **If ampixa.com is on a VPS / static server:** rsync this file to
  `/var/www/ampixa.com/speakgov/index.html`. Done.
- **If ampixa.com is on Cloudflare Pages / Vercel:** add `/speakgov/`
  as a route or push the folder to a Pages project.
- **GitHub Pages:** push `web/speakgov/` to the docs branch and enable
  Pages from that path.

## How it talks to the server

Plain `fetch()` to `${serverUrl}/query` and `${serverUrl}/health`. No
proxy, no cookies, no auth dance — bearer token (if configured) goes in
the `Authorization` header.

The server's CORS is wide-open by default (`ALLOW_ORIGINS=*`). For a
production deploy at `ampixa.com/speakgov`, lock it down:

```bash
ALLOW_ORIGINS=https://ampixa.com python -m uvicorn server.main:app
```

## First-use flow for a citizen

1. Open `ampixa.com/speakgov` in any browser (mobile or desktop).
2. The Settings overlay opens automatically since no server URL is saved.
3. Paste the Tailscale Funnel URL of the helpdesk server (e.g.
   `https://k2.your-tailnet.ts.net`).
4. Optionally paste a bearer token if the server requires one.
5. Tap "Test connection" — should show `OK · model=... · adapter=...`.
6. Tap Save → Close.
7. Type a question, tap send.

Settings are stored in `localStorage` so the user only does this once per
device.

## What's in the UI

- Chat bubbles (user right, AI left), markdown-style URL linking in
  bracketed citations.
- **Source cards** below each AI message:
  - 🟢 green = `CITIZEN INTERVIEW` (tacit corpus, priority)
  - 🔵 blue = `GOV.NP` (the official documentation)
  - Each card is tappable to open the source URL.
- Refusal handling: if the model couldn't find a source, a single tap
  dials Hello Sarkar 1111.
- Per-message footer: detected language + latency + source counts.
- Dark mode honored automatically via `prefers-color-scheme: dark`.

## What's NOT in v0.1 (yet)

- Voice input (Web Speech API would work — push-to-talk is one button add)
- Voice output (Web Speech Synthesis API for TTS)
- Streaming responses (server is non-streaming today)
- Multi-turn history persistence (each session is fresh)
- Service worker for offline caching of last N answers

## File layout

```
web/
└── speakgov/
    └── index.html      ← single file, ~530 lines, no build step
```

That's it.
