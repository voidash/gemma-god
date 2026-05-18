# Hackathon demo runbook - 2026-05-10

Public site: https://helpdesk.ampixa.com

Backend: k2 `<k2-tailnet-ip>:8000`

WhatsApp/voice demo: https://helpdesk.ampixa.com/whatsapp

Live kiosk voice demo:

- Best office-kiosk path on the Mac Studio itself:
  `http://127.0.0.1:8000/kiosk`
- Office/LAN path for viewing only: `http://192.168.10.30:8000/kiosk`.
  Browser mic capture is blocked on plain LAN HTTP unless we add local HTTPS or
  launch the browser with a secure-origin override.
- Tailnet path: `http://<k2-tailnet-ip>:8000/kiosk`
- Public path exists at `https://helpdesk.ampixa.com/kiosk`, but that goes
  through the Finland public route and is not the right latency path for a
  kiosk demo.

Pi edge model demo:

- Runbook: `PI_E2B_LLAMA_CPP_RUNBOOK.md`.
- Target: `cdjk@<pi-tailnet-ip>` on Tailscale. The shorthand `cdjk@pi` does not
  currently resolve from this Mac.
- Runtime: `llama.cpp` `llama-server` on port `8081`.
- Default model: `bartowski/google_gemma-4-E2B-it-GGUF` /
  `google_gemma-4-E2B-it-Q4_K_M.gguf`, about 3.46 GB.
- Current Pi endpoint: `http://<pi-tailnet-ip>:8081/v1/chat/completions`.
- Current footprint: about 3.9 GB under `/home/cdjk/speakgov-pi`; prompt cache
  capped at 256 MiB; short prompt generation measured around 7.5 tok/s.
- This is an edge fallback/story lane, not the main RAG path. Do not claim the
  Pi is serving the full corpus unless retrieval is explicitly wired there.

Temporary operator auth: HTTP Basic Auth on `/whatsapp` and all
`/whatsapp/*` proxy endpoints. On k2 the password is stored in
`/Users/k2/gemma-god/.admin_password`.

Current status:

- Full government directory crawl finished: 899/899 sources.
- FTS rebuilt: 270,509 searchable chunks.
- API smoke: 14/14 pass in `eval/reports/rag_query_audit_demo_ready_20260510.jsonl`.
- Public chat UI manually smoke-tested with Jiri mayor and passport fee.
- Real Baileys WhatsApp bridge is linked to `9779763612645:3@s.whatsapp.net`.
- WhatsApp bridge runs on k2 localhost `127.0.0.1:8787`; FastAPI proxies it.
- WhatsApp auth state lives on the 4 TB SSD:
  `/Volumes/T9/gemma-god/whatsapp-auth`.
- WhatsApp inbound text and audio work. Audio path is:
  Baileys media download -> local warm FastConformer ASR worker on k2 ->
  `/query` -> local warm real Nepali Kala TTS worker on k2 -> Opus OGG voice
  reply.
- Bridge now deduplicates recent inbound message IDs in
  `/Volumes/T9/gemma-god/whatsapp-auth/speakgov-seen-messages.json`.
- Audio replies send full text/sources separately and synthesize only a compact
  answer, so the TTS should not read URLs aloud.
- `/kiosk` is a live voice UI: continuous mic, browser-side silence detection,
  rolling interim ASR every about 2.2 seconds while the user speaks, final ASR on
  utterance end, streamed answer text, then model TTS playback.

Latency measured from the home machine on 2026-05-17:

- k2 public IP ping: 5.3-10.8 ms, average 6.9 ms.
- k2 Tailscale ping: 110.9-275.5 ms, average 160.0 ms.
- k2 direct tailnet `/health`: about 227-229 ms total.
- public `helpdesk.ampixa.com/health`: about 0.95-1.39 s total.
- k2 local loopback `/health`: about 0.7-2.8 ms total.
- Old HF Space ASR on a short TTS sample: 12.9 s server-side.
- Local ASR worker cold first request after start: 4.95 s.
- Local ASR worker warm request: about 498-532 ms server-side.
- Old HF Space TTS on a short Nepali sentence: 11.8 s server-side.
- Local TTS worker cold first request after start: 4.57 s.
- Local TTS worker warm request: 290-310 ms server-side.

Conclusion: network is not the blocker for an office kiosk when opened on the
Mac Studio itself. ASR and TTS are now local warm workers. The next latency
problem is the composer/generation path and the browser security/origin setup
for kiosk mic access. `/kiosk` should run from localhost or local HTTPS.

## WhatsApp run commands

Restart the bridge:

```bash
ssh k2@<k2-tailnet-ip> /Users/k2/gemma-god/scripts/start_k2_whatsapp_bridge.sh
```

Check status:

```bash
curl -u admin:$(ssh k2@<k2-tailnet-ip> 'cat /Users/k2/gemma-god/.admin_password') \
  https://helpdesk.ampixa.com/whatsapp/status
```

Expected status:

- `connected: true`
- `autoReply: true`
- `sendVoiceReplies: true`
- `allowGroups: false`

Current voice providers:

- ASR: local worker `http://127.0.0.1:8789/transcribe`, model
  `voidash/nepali-asr-staging`.
- TTS: local worker `http://127.0.0.1:8788/synthesize`, model
  `ampixa/real-nepali-v0.2-kala`, speaker `kala`.

Restart local ASR worker:

```bash
ssh k2@<k2-tailnet-ip> /Users/k2/gemma-god/scripts/start_k2_voice_asr_worker.sh
```

Restart local TTS worker:

```bash
ssh k2@<k2-tailnet-ip> /Users/k2/gemma-god/scripts/start_k2_voice_tts_worker.sh
```

## WhatsApp demo risks to fix

- Replace the temporary admin password with a proper operator secret before
  showing the manager outside the team.
- Add real process supervision for FastAPI and the Baileys bridge. The restart
  scripts are reproducible, but they are not a full crash-restart supervisor.
- Add structured per-message observability: WhatsApp message ID, ASR latency,
  query latency, TTS latency, and fallback reason.
- Add ASR confirmation for names, wards, municipalities, and phone numbers.
  The current path can transcribe speech, but entity errors still need a
  compact confirmation loop.
- Keep group replies disabled unless we intentionally design moderation and
  privacy behavior for groups.
- For production, persist conversation memory in a bounded store rather than
  only the bridge process memory.

## Kiosk voice next fixes

- Local ASR/TTS workers are done.
- Do not use the TTS script path per request; it reloads the model and takes
  about 5.2 s even after the checkpoint is cached.
- Native streaming ASR is not done yet. The deployed `/kiosk` mode now has
  rolling interim ASR snapshots, but it is not using a token-level streaming
  FastConformer decoder.
- Expose only the office/LAN endpoint for kiosk mode. Do not route kiosk audio
  through `helpdesk.ampixa.com`.
- If the kiosk is not the Mac Studio itself, add local HTTPS for mic access or
  launch Chrome with a secure-origin override for the LAN origin.
- Improve ASR correction/entity confirmation. Latency is now usable, but the
  TTS round-trip sample still misheard parts of `जन्मदर्ताका लागि वडा
  कार्यालयमा सम्पर्क गर्नुहोस्।`.

## Demo order

1. Open landing page.
   Say: "This is an open-weight Nepal government helpdesk grounded in crawled .gov.np sources and citizen-interview knowledge."

2. Open `/chat`.

3. Ask a local-government exact fact:
   `जिरीको नगर प्रमुख को हो?`

   Expected: Mitra Bahadur Jirel with email/phone, cited to `jirimun.gov.np`.

4. Ask a local contact question:
   `जिरिहेल्पडेष्क फोन नम्बर`

   Expected: `+977 071 5555556`, cited to Jiri contact page.

5. Ask a federal procedure:
   `How do I replace a lost citizenship certificate?`

   Expected: duplicate citizenship process, DAO/MoHA source, no hallucinated passport procedure.

6. Ask police:
   `How do I apply for police clearance report in Nepal?`

   Expected: deterministic answer from Nepal Police source, fast.

7. Ask partial-source case:
   `What is the fee for passport renewal?`

   Expected: says retrieved Department of Passports source does not give one fixed amount; fee varies by registration center; cites source. This is good behavior, not a failure.

8. Ask impossible/refusal case:
   `What is the official process for a Mars residence certificate in Jiri?`

   Expected: honest refusal.

## Avoid in live demo

- Do not claim the SFT model is solved. Say the RAG is strong and v5 SFT will train answerability/source-selection explicitly.
- Do not ask arbitrary broad policy questions first. Start with the safe path above.
- Do not promise exact passport fees unless an official fee table is retrieved.
- Do not restart k2 during the demo.

## If something is slow

- Use the deterministic questions above first. They skip generation or have short generation.
- If a generated answer takes too long, refresh and ask one of the deterministic local/contact/procedure questions.
- Backend health check:
  `curl http://<k2-tailnet-ip>:8000/health`

## After demo

1. Build the 500-record v5 RAG-contract distillation set.
2. Human-audit the first 200 records by slice.
3. Train E2B checkpoint sweep only after the audited contract data is clean.
