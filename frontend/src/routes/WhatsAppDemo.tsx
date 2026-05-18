import { useEffect, useRef, useState } from "react";
import {
  CheckCheck,
  FileText,
  Loader2,
  LogOut,
  MessageCircle,
  Mic,
  Pencil,
  PhoneOutgoing,
  QrCode,
  RefreshCw,
  Send,
  Smartphone,
  Square,
  Volume2,
  Wifi,
  WifiOff,
} from "lucide-react";
import { toast } from "sonner";
import { StickerButton } from "@/components/sticker/StickerButton";
import { StickerCard } from "@/components/sticker/StickerCard";
import { Textarea } from "@/components/ui/textarea";
import {
  postQuery,
  postQueryStream,
  connectWhatsApp,
  getVoiceProviders,
  getWhatsAppQr,
  getWhatsAppStatus,
  logoutWhatsApp,
  sendWhatsApp,
  synthesizeVoice,
  transcribeVoice,
  type ChatHistoryTurn,
  type QueryResponse,
  type QuerySource,
  type QueryStreamMeta,
  type VoiceProvidersResponse,
  type WhatsAppQr,
  type WhatsAppStatus,
} from "@/lib/api";

type DemoMessage =
  | { kind: "user"; text: string; via?: "voice" | "typed" }
  | { kind: "assistant"; data: QueryResponse; streaming?: boolean; id?: string }
  | { kind: "outreach"; text: string; sent: boolean }
  | { kind: "error"; text: string };

const EXAMPLES = [
  "जिरिहेल्पडेष्क फोन नम्बर",
  "birth certificate in Jiri",
  "who to contact when i got cheated by manpower agency?",
  "What is the official process for a Mars residence certificate in Jiri?",
];

const OUTREACH_TARGET = "Jiri Municipality contact officer";

function emptyQueryResponse(patch: Partial<QueryResponse> = {}): QueryResponse {
  return {
    answer: "",
    citations: [],
    sources: [],
    did_refuse: false,
    retrieved_tacit: 0,
    retrieved_gov: 0,
    detected_lang: "",
    latency_ms: { retrieval: 0, generation: 0, total: 0, ...patch.latency_ms },
    ...patch,
  };
}

function historyFrom(messages: DemoMessage[]): ChatHistoryTurn[] {
  return messages
    .filter((m) => !(m.kind === "assistant" && m.streaming))
    .flatMap((m): ChatHistoryTurn[] => {
      if (m.kind === "user") return [{ role: "user", content: m.text.slice(0, 400) }];
      if (m.kind === "assistant" && m.data.answer) {
        return [{ role: "assistant", content: m.data.answer.slice(0, 700) }];
      }
      return [];
    })
    .slice(-6);
}

function supportedMime() {
  const options = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  return options.find((m) => MediaRecorder.isTypeSupported(m)) || "";
}

function fileExt(mime: string) {
  if (mime.startsWith("audio/mp4")) return "m4a";
  if (mime.startsWith("audio/ogg")) return "ogg";
  return "webm";
}

function sourceHosts(sources: QuerySource[]) {
  const hosts = sources
    .map((s) => {
      try {
        return s.url ? new URL(s.url).host : "";
      } catch {
        return "";
      }
    })
    .filter(Boolean);
  return Array.from(new Set(hosts)).slice(0, 3);
}

function shouldOfferOutreach(resp: QueryResponse) {
  const answer = resp.answer.toLowerCase();
  return (
    resp.did_refuse ||
    answer.includes("not have") ||
    answer.includes("missing") ||
    answer.includes("भेटिन") ||
    resp.sources.length === 0
  );
}

function ttsSegment(text: string) {
  const sentences = text
    .split(/(?<=[।.!?])\s+/)
    .map((part) => part.trim())
    .filter((part) => /[\u0900-\u097F]/.test(part));
  const selected: string[] = [];
  for (const sentence of sentences.length ? sentences : [text.trim()]) {
    if (!/[\u0900-\u097F]/.test(sentence)) continue;
    const candidate = [...selected, sentence].join(" ");
    if (candidate.length > 230) break;
    selected.push(sentence);
  }
  return selected.join(" ").trim();
}

export function WhatsAppDemo() {
  const [messages, setMessages] = useState<DemoMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [transcript, setTranscript] = useState("");
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [ttsLoading, setTtsLoading] = useState(false);
  const [autoSpeak, setAutoSpeak] = useState(true);
  const [voiceProviders, setVoiceProviders] = useState<VoiceProvidersResponse | null>(null);
  const [whatsappStatus, setWhatsappStatus] = useState<WhatsAppStatus | null>(null);
  const [whatsappQr, setWhatsappQr] = useState<WhatsAppQr | null>(null);
  const [bridgeBusy, setBridgeBusy] = useState(false);
  const [manualTo, setManualTo] = useState("");
  const [manualText, setManualText] = useState("");
  const [manualSending, setManualSending] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const activeAudioUrlRef = useRef<string | null>(null);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (scroller && shouldAutoScrollRef.current) scroller.scrollTop = scroller.scrollHeight;
  }, [messages, loading, transcript, transcribing]);

  useEffect(() => {
    void getVoiceProviders()
      .then(setVoiceProviders)
      .catch(() => setVoiceProviders(null));
    return () => {
      activeAudioRef.current?.pause();
      if (activeAudioUrlRef.current) URL.revokeObjectURL(activeAudioUrlRef.current);
    };
  }, []);

  useEffect(() => {
    void refreshWhatsApp(true);
    const id = window.setInterval(() => {
      void refreshWhatsApp(true);
    }, whatsappStatus?.connected ? 10000 : 3000);
    return () => window.clearInterval(id);
  }, [whatsappStatus?.connected]);

  async function refreshWhatsApp(quiet = false) {
    try {
      const status = await getWhatsAppStatus();
      setWhatsappStatus(status);
      if (status.hasQr || status.status === "qr" || status.status === "connecting") {
        setWhatsappQr(await getWhatsAppQr());
      } else if (status.connected) {
        setWhatsappQr(null);
      }
    } catch (error) {
      setWhatsappStatus(null);
      setWhatsappQr(null);
      if (!quiet) toast.error(error instanceof Error ? error.message : "WhatsApp bridge unavailable");
    }
  }

  async function connectBridge() {
    setBridgeBusy(true);
    try {
      const status = await connectWhatsApp();
      setWhatsappStatus(status);
      setWhatsappQr(await getWhatsAppQr());
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not start WhatsApp bridge");
    } finally {
      setBridgeBusy(false);
    }
  }

  async function logoutBridge() {
    if (!window.confirm("Disconnect this WhatsApp account from the bridge?")) return;
    setBridgeBusy(true);
    try {
      const status = await logoutWhatsApp();
      setWhatsappStatus(status);
      setWhatsappQr(null);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not logout WhatsApp");
    } finally {
      setBridgeBusy(false);
    }
  }

  async function sendManualWhatsApp(text: string) {
    if (!manualTo.trim()) {
      toast.error("Enter phone number with country code.");
      return false;
    }
    const body = text.trim();
    if (!body) return false;
    setManualSending(true);
    try {
      await sendWhatsApp(manualTo, body);
      toast.success("WhatsApp message sent.");
      setManualText("");
      await refreshWhatsApp(true);
      return true;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "WhatsApp send failed");
      return false;
    } finally {
      setManualSending(false);
    }
  }

  function handleScroll() {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const distanceFromBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom < 120;
  }

  async function startRecording() {
    if (recording || transcribing || loading) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      toast.error("This browser cannot record audio.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = supportedMime();
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        setRecording(false);
        stream.getTracks().forEach((track) => track.stop());
        const finalMime = recorder.mimeType || mime || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: finalMime });
        void transcribeBlob(blob, finalMime);
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Microphone unavailable");
    }
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      setRecording(false);
      return;
    }
    recorder.stop();
    setRecording(false);
  }

  async function transcribeBlob(blob: Blob, mime: string) {
    if (!blob.size) return;
    setTranscribing(true);
    try {
      const result = await transcribeVoice(blob, `whatsapp-demo.${fileExt(mime)}`);
      const text = result.transcript.trim();
      setTranscript(text);
      setDraft(text);
      if (!text) toast.warning("ASR returned an empty transcript.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "ASR failed");
    } finally {
      setTranscribing(false);
    }
  }

  async function speak(text: string, options: { quietUnsupported?: boolean } = {}) {
    const speakable = ttsSegment(text);
    if (!speakable) {
      if (!options.quietUnsupported) toast.error("Model TTS is currently Nepali-script only.");
      return;
    }
    if (ttsLoading) return;
    if (voiceProviders && !voiceProviders.tts_enabled) {
      toast.error("Model TTS is not configured on the server.");
      return;
    }
    setTtsLoading(true);
    try {
      activeAudioRef.current?.pause();
      if (activeAudioUrlRef.current) URL.revokeObjectURL(activeAudioUrlRef.current);
      const result = await synthesizeVoice(speakable);
      const url = URL.createObjectURL(result.audio);
      const audio = new Audio(url);
      activeAudioRef.current = audio;
      activeAudioUrlRef.current = url;
      audio.onended = () => {
        if (activeAudioUrlRef.current === url) {
          URL.revokeObjectURL(url);
          activeAudioUrlRef.current = null;
          activeAudioRef.current = null;
        }
      };
      await audio.play();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Model TTS failed");
    } finally {
      setTtsLoading(false);
    }
  }

  async function send(text: string, via: "voice" | "typed" = "typed") {
    const question = text.trim();
    if (!question || loading) return;
    const history = historyFrom(messages);
    setMessages((prev) => [...prev, { kind: "user", text: question, via }]);
    setDraft("");
    setTranscript("");
    setLoading(true);

    const streamId =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random()}`;

    const updateAssistant = (patch: Partial<QueryResponse>, streaming = true) => {
      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.kind === "assistant" && m.id === streamId);
        const base =
          idx >= 0 && prev[idx].kind === "assistant"
            ? prev[idx].data
            : emptyQueryResponse();
        const next: DemoMessage = {
          kind: "assistant",
          id: streamId,
          streaming,
          data: emptyQueryResponse({
            ...base,
            ...patch,
            latency_ms: { ...base.latency_ms, ...patch.latency_ms },
          }),
        };
        if (idx < 0) return [...prev, next];
        const copy = [...prev];
        copy[idx] = next;
        return copy;
      });
    };

    const appendAssistantText = (chunk: string) => {
      if (!chunk) return;
      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.kind === "assistant" && m.id === streamId);
        const base =
          idx >= 0 && prev[idx].kind === "assistant"
            ? prev[idx].data
            : emptyQueryResponse();
        const next: DemoMessage = {
          kind: "assistant",
          id: streamId,
          streaming: true,
          data: emptyQueryResponse({
            ...base,
            answer: `${base.answer}${chunk}`,
          }),
        };
        if (idx < 0) return [...prev, next];
        const copy = [...prev];
        copy[idx] = next;
        return copy;
      });
    };

    try {
      await postQueryStream(question, history, {
        onMeta: (meta: QueryStreamMeta) =>
          updateAssistant({
            sources: meta.sources,
            retrieved_tacit: meta.retrieved_tacit,
            retrieved_gov: meta.retrieved_gov,
            detected_lang: meta.detected_lang,
            latency_ms: {
              retrieval: meta.latency_ms.retrieval,
              generation: 0,
              total: 0,
            },
          }),
        onToken: appendAssistantText,
        onFinal: (response) => {
          updateAssistant(response, false);
          if (autoSpeak) void speak(response.answer, { quietUnsupported: true });
          if (shouldOfferOutreach(response)) addOutreachDraft(question, response);
        },
      });
    } catch {
      try {
        const response = await postQuery(question, history);
        setMessages((prev) => [...prev, { kind: "assistant", data: response }]);
        if (autoSpeak) void speak(response.answer, { quietUnsupported: true });
        if (shouldOfferOutreach(response)) addOutreachDraft(question, response);
      } catch (error) {
        setMessages((prev) => [
          ...prev,
          { kind: "error", text: error instanceof Error ? error.message : String(error) },
        ]);
      }
    } finally {
      setLoading(false);
    }
  }

  function addOutreachDraft(question: string, response: QueryResponse) {
    const hosts = sourceHosts(response.sources);
    const sourceLine = hosts.length ? `Checked sources: ${hosts.join(", ")}.` : "No reliable source surfaced.";
    const text = `Namaste ${OUTREACH_TARGET}, citizen asked: "${question}". ${sourceLine} Can you confirm the responsible contact/process?`;
    setMessages((prev) => [...prev, { kind: "outreach", text, sent: false }]);
  }

  async function sendOutreach(index: number) {
    const message = messages[index];
    if (message?.kind !== "outreach") return;
    const sent = await sendManualWhatsApp(message.text);
    if (!sent) return;
    setMessages((prev) =>
      prev.map((m, i) => (i === index && m.kind === "outreach" ? { ...m, sent: true } : m)),
    );
  }

  return (
    <div className="h-[calc(100svh-4rem)] bg-[#e8f5e9] flex flex-col">
      <header className="border-b border-emerald-950/15 bg-[#075e54] text-white">
        <div className="mx-auto max-w-4xl px-4 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-white/15">
              <MessageCircle className="size-5" />
            </span>
            <div className="min-w-0">
              <h1 className="text-base font-display font-bold truncate">PreVillage WhatsApp Demo</h1>
              <p className="text-xs text-white/75 truncate">
                {voiceProviders
                  ? `ASR ${voiceProviders.asr_provider} · TTS ${voiceProviders.tts_provider}`
                  : "ASR/TTS provider loading"}
              </p>
            </div>
          </div>
          <label className="flex items-center gap-2 text-xs font-semibold whitespace-nowrap">
            <input
              type="checkbox"
              checked={autoSpeak}
              onChange={(e) => setAutoSpeak(e.target.checked)}
              className="size-4 accent-emerald-300"
            />
            Model TTS
          </label>
        </div>
      </header>

      <main ref={scrollerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-3 sm:px-4 py-5 space-y-4">
          <WhatsAppBridgePanel
            status={whatsappStatus}
            qr={whatsappQr}
            busy={bridgeBusy}
            manualTo={manualTo}
            manualText={manualText}
            manualSending={manualSending}
            onManualTo={setManualTo}
            onManualText={setManualText}
            onConnect={connectBridge}
            onRefresh={() => refreshWhatsApp(false)}
            onLogout={logoutBridge}
            onSendManual={() => sendManualWhatsApp(manualText)}
          />
          {messages.length === 0 && (
            <StickerCard tone="soft" className="p-4 sm:p-5">
              <div className="flex items-start gap-3">
                <Mic className="mt-1 size-5 text-emerald-700" />
                <div>
                  <h2 className="text-lg font-display font-extrabold text-ink">Speak like a citizen would.</h2>
                  <p className="mt-1 text-sm text-ink/70">
                    Record Nepali, Roman Nepali, English, or mixed speech. Review the transcript, send it, then play the answer.
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {EXAMPLES.map((example) => (
                  <button
                    key={example}
                    onClick={() => setDraft(example)}
                    className="rounded-full border border-emerald-900/20 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-950 hover:bg-emerald-100"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </StickerCard>
          )}

          {messages.map((message, index) => (
            <MessageRow
              key={index}
              message={message}
              onSpeak={speak}
              onSendOutreach={() => void sendOutreach(index)}
              ttsLoading={ttsLoading}
            />
          ))}

          {transcribing && (
            <div className="flex justify-start">
              <div className="rounded-2xl bg-white px-4 py-3 text-sm shadow-sm flex items-center gap-2">
                <Loader2 className="size-4 animate-spin" />
                ASR transcribing...
              </div>
            </div>
          )}
        </div>
      </main>

      <footer className="border-t border-emerald-950/15 bg-[#f0f2f5]">
        <div className="mx-auto max-w-4xl px-3 sm:px-4 py-3">
          {transcript && (
            <div className="mb-2 flex items-center gap-2 rounded-lg border border-emerald-900/15 bg-white px-3 py-2 text-xs text-emerald-950">
              <Pencil className="size-3.5" />
              <span className="font-semibold">ASR transcript ready. Edit if needed before sending.</span>
            </div>
          )}
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void send(draft, transcript ? "voice" : "typed");
            }}
            className="flex items-end gap-2"
          >
            <StickerButton
              type="button"
              tone={recording ? "pink" : "mint"}
              size="icon"
              disabled={transcribing || loading}
              onClick={recording ? stopRecording : startRecording}
              aria-label={recording ? "Stop recording" : "Record voice"}
              title={recording ? "Stop recording" : "Record voice"}
            >
              {recording ? <Square className="size-5" /> : <Mic className="size-5" />}
            </StickerButton>
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={1}
              placeholder="Type or record a WhatsApp-style question..."
              disabled={loading}
              className="min-h-11 max-h-32 resize-none rounded-2xl border border-emerald-900/20 bg-white shadow-none focus-visible:ring-emerald-700"
            />
            <StickerButton
              type="submit"
              tone="mint"
              size="icon"
              disabled={!draft.trim() || loading || transcribing || recording}
              aria-label="Send"
              title="Send"
            >
              {loading ? <Loader2 className="size-5 animate-spin" /> : <Send className="size-5" />}
            </StickerButton>
          </form>
        </div>
      </footer>
    </div>
  );
}

function WhatsAppBridgePanel({
  status,
  qr,
  busy,
  manualTo,
  manualText,
  manualSending,
  onManualTo,
  onManualText,
  onConnect,
  onRefresh,
  onLogout,
  onSendManual,
}: {
  status: WhatsAppStatus | null;
  qr: WhatsAppQr | null;
  busy: boolean;
  manualTo: string;
  manualText: string;
  manualSending: boolean;
  onManualTo: (value: string) => void;
  onManualText: (value: string) => void;
  onConnect: () => void;
  onRefresh: () => void;
  onLogout: () => void;
  onSendManual: () => Promise<boolean>;
}) {
  const connected = Boolean(status?.connected);
  const stateLabel = status?.status || "offline";
  const showQr = Boolean(qr?.qrDataUrl && !connected);

  return (
    <StickerCard tone="soft" className="p-4 sm:p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex size-9 items-center justify-center rounded-full ${
                connected ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
              }`}
            >
              {connected ? <Wifi className="size-4" /> : <WifiOff className="size-4" />}
            </span>
            <div className="min-w-0">
              <h2 className="text-sm font-extrabold text-ink">Real WhatsApp bridge</h2>
              <p className="truncate text-xs text-ink/60">
                {connected
                  ? `Connected as ${status?.connectedJid || "WhatsApp Web"}`
                  : `Status: ${stateLabel}`}
              </p>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onConnect}
              disabled={busy || connected}
              className="inline-flex items-center gap-2 rounded-full bg-[#25d366] px-3 py-1.5 text-xs font-bold text-emerald-950 disabled:opacity-50"
            >
              {busy ? <Loader2 className="size-3.5 animate-spin" /> : <QrCode className="size-3.5" />}
              {connected ? "Connected" : "Connect / QR"}
            </button>
            <button
              type="button"
              onClick={onRefresh}
              disabled={busy}
              className="inline-flex items-center gap-2 rounded-full border border-emerald-900/15 bg-white px-3 py-1.5 text-xs font-bold text-emerald-900"
            >
              <RefreshCw className="size-3.5" />
              Refresh
            </button>
            {connected && (
              <button
                type="button"
                onClick={onLogout}
                disabled={busy}
                className="inline-flex items-center gap-2 rounded-full border border-red-900/15 bg-red-50 px-3 py-1.5 text-xs font-bold text-red-800"
              >
                <LogOut className="size-3.5" />
                Logout
              </button>
            )}
          </div>

          {status?.lastError && <p className="mt-2 text-xs text-red-700">{status.lastError}</p>}

          <form
            className="mt-4 grid gap-2 sm:grid-cols-[minmax(180px,240px)_1fr_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              void onSendManual();
            }}
          >
            <input
              value={manualTo}
              onChange={(event) => onManualTo(event.target.value)}
              placeholder="97798..."
              className="h-10 rounded-lg border border-emerald-900/20 bg-white px-3 text-sm outline-none focus:border-emerald-700"
            />
            <input
              value={manualText}
              onChange={(event) => onManualText(event.target.value)}
              placeholder="Manual WhatsApp message"
              className="h-10 rounded-lg border border-emerald-900/20 bg-white px-3 text-sm outline-none focus:border-emerald-700"
            />
            <button
              type="submit"
              disabled={!connected || manualSending || !manualText.trim()}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-emerald-700 px-3 text-xs font-bold text-white disabled:opacity-50"
            >
              {manualSending ? <Loader2 className="size-3.5 animate-spin" /> : <Send className="size-3.5" />}
              Send
            </button>
          </form>
        </div>

        <div className="flex min-h-36 w-full shrink-0 items-center justify-center rounded-lg border border-emerald-900/15 bg-white p-3 lg:w-44">
          {showQr ? (
            <img src={qr?.qrDataUrl || ""} alt="WhatsApp pairing QR" className="h-36 w-36" />
          ) : connected ? (
            <div className="text-center text-xs font-semibold text-emerald-800">
              <Smartphone className="mx-auto mb-2 size-7" />
              Paired
            </div>
          ) : (
            <div className="text-center text-xs font-semibold text-ink/55">
              <QrCode className="mx-auto mb-2 size-7" />
              Start QR
            </div>
          )}
        </div>
      </div>
    </StickerCard>
  );
}

function MessageRow({
  message,
  onSpeak,
  onSendOutreach,
  ttsLoading,
}: {
  message: DemoMessage;
  onSpeak: (text: string) => Promise<void>;
  onSendOutreach: () => void;
  ttsLoading: boolean;
}) {
  if (message.kind === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[82%] rounded-2xl rounded-tr-sm bg-[#dcf8c6] px-4 py-2 text-sm text-emerald-950 shadow-sm">
          <p className="whitespace-pre-wrap break-words">{message.text}</p>
          <div className="mt-1 flex justify-end gap-1 text-[10px] text-emerald-950/55">
            {message.via === "voice" ? "voice" : "typed"} <CheckCheck className="size-3" />
          </div>
        </div>
      </div>
    );
  }
  if (message.kind === "error") {
    return (
      <div className="flex justify-start">
        <div className="max-w-[82%] rounded-2xl bg-red-50 px-4 py-2 text-sm text-red-700 shadow-sm">
          {message.text}
        </div>
      </div>
    );
  }
  if (message.kind === "outreach") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[86%] rounded-2xl rounded-tr-sm border border-emerald-900/20 bg-emerald-100 px-4 py-3 text-sm text-emerald-950 shadow-sm">
          <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-emerald-800">
            <PhoneOutgoing className="size-4" />
            Officer outreach {message.sent ? "sent" : "draft"}
          </div>
          <p className="whitespace-pre-wrap break-words">{message.text}</p>
          {!message.sent && (
            <button
              onClick={onSendOutreach}
              className="mt-3 inline-flex items-center gap-2 rounded-full bg-[#25d366] px-3 py-1.5 text-xs font-bold text-emerald-950"
            >
              <Send className="size-3.5" />
              Send demo message
            </button>
          )}
        </div>
      </div>
    );
  }

  const hosts = sourceHosts(message.data.sources);
  return (
    <div className="flex justify-start">
      <div className="max-w-[88%] rounded-2xl rounded-tl-sm bg-white px-4 py-3 text-sm text-ink shadow-sm">
        {message.data.answer ? (
          <p className="whitespace-pre-wrap break-words leading-relaxed">{message.data.answer}</p>
        ) : (
          <p className="text-ink/50">Thinking...</p>
        )}
        {!message.streaming && message.data.answer && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              onClick={() => void onSpeak(message.data.answer)}
              disabled={ttsLoading}
              className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-900"
            >
              {ttsLoading ? <Loader2 className="size-3.5 animate-spin" /> : <Volume2 className="size-3.5" />}
              Model TTS
            </button>
            {hosts.map((host) => (
              <span
                key={host}
                className="inline-flex items-center gap-1 rounded-full bg-sky/10 px-2.5 py-1 text-[11px] font-semibold text-ink/70"
              >
                <FileText className="size-3" />
                {host}
              </span>
            ))}
          </div>
        )}
        <div className="mt-2 text-[10px] text-ink/45">
          {message.streaming
            ? "streaming"
            : `${message.data.latency_ms.total} ms · ${message.data.retrieved_tacit} tacit · ${message.data.retrieved_gov} gov`}
        </div>
      </div>
    </div>
  );
}
