# Nepal Gov Helpdesk — Android (v0.1)

Tiny Compose app that talks to the gemma-god RAG server. Single Activity,
two screens: Chat + Settings. Server URL and bearer token are configurable
at runtime — no rebuild needed to point at a different server.

## What it does

- Chat: type a question in Nepali / Roman-Nepali / English → answer with
  citation cards.
- Each citation is tappable: opens the gov.np page in a browser, or for
  tacit-corpus sources shows the office attribution.
- If the model refuses (no authoritative source), the answer surfaces a
  one-tap **Call Hello Sarkar 1111** action.
- Settings: change `Server URL` and `Bearer Token`. "Test connection" calls
  `/health` and confirms the server + adapter are reachable.

## Build

Open the `android/` folder in Android Studio (Hedgehog 2023.1.1 or later).
Android Studio will:
1. Resolve the Gradle wrapper (run `./gradlew` once on the command line if
   it's slow to download — this fetches Gradle 8.2).
2. Sync dependencies.
3. Let you Run on a connected device or emulator.

Min SDK 24 (Android 7.0), target 34. AGP 8.2.2, Kotlin 1.9.22, Compose
BOM 2024.02.00.

CLI build (after `gradle wrapper` once):

```bash
cd android
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

## Configure

On first launch, open the gear icon → **Settings**:
- **Server URL**: e.g. `https://k2.your-tailnet.ts.net` (Tailscale Funnel) or
  `http://100.x.y.z:8000` if you're on the same tailnet.
- **Bearer token**: paste whatever you set in `BEARER_TOKEN` on the server.
  Leave blank if the server doesn't require auth.
- Tap **Test connection** to verify.

The default URL placeholder is a tailnet IP — change it before you Send.

## What the server expects

The app POSTs to `<serverUrl>/query`:

```json
{
  "question": "...",
  "top_k_tacit": 3,
  "top_k_gov": 3,
  "max_new_tokens": 600
}
```

…with optional `Authorization: Bearer <token>`. Response is the
`QueryResponse` schema in `server/main.py`.

## Roadmap (not in v0.1)

- Push-to-talk voice input via Android `SpeechRecognizer`
- TTS playback of responses via `TextToSpeech`
- Streaming responses (SSE/WebSocket — server work first)
- Multi-turn conversation memory
- "Was this helpful?" feedback loop into the tacit corpus
- Tool-calling actions (send WhatsApp, schedule reminder, open Maps)
- Offline mode that caches recent answers

## Why no Tailscale Android client embed?

The app speaks plain HTTPS. If your demo network has Tailscale routing,
install the official Tailscale Android client first, log into your
tailnet, then the app's `100.x.y.z:8000` URL works. If the demo network
doesn't have Tailscale, set the URL to the public Tailscale Funnel
(`https://<host>.ts.net`) — the Funnel relay handles transit.

## Files

```
android/
  build.gradle.kts                       project-level Gradle (versions only)
  settings.gradle.kts                    repos + module list
  gradle.properties
  app/
    build.gradle.kts                     module config + dependencies
    src/main/
      AndroidManifest.xml                permissions + activity
      java/np/gov/helpdesk/
        MainActivity.kt                  entry + Chat + Settings composables
        Prefs.kt                         SharedPreferences wrapper
        RagClient.kt                     Ktor HTTP + DTOs
      res/values/
        strings.xml
        themes.xml
```

12 files, ~600 lines of Kotlin. Easy to read, easy to extend.
