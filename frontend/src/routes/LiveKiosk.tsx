import { useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Mic,
  MicOff,
  RotateCcw,
  Settings,
  Volume2,
  Wifi,
} from "lucide-react";
import { toast } from "sonner";
import {
  apiPath,
  getRuntimeApiBase,
  postQueryStream,
  setRuntimeApiBase,
  synthesizeVoice,
  transcribeVoice,
  type ChatHistoryTurn,
  type QueryResponse,
  type QueryStreamMeta,
  type VoiceTranscribeResponse,
} from "@/lib/api";

type Phase = "idle" | "listening" | "speech" | "transcribing" | "thinking" | "speaking" | "error";

type Turn = {
  id: string;
  user: string;
  assistant: string;
  streaming: boolean;
  asr?: VoiceTranscribeResponse;
  response?: QueryResponse;
  error?: string;
};

type Metrics = {
  networkMs?: number;
  partialAsrMs?: number;
  asrMs?: number;
  retrievalMs?: number;
  generationMs?: number;
  totalQueryMs?: number;
  ttsMs?: number;
};

const MIME_OPTIONS = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
const RMS_SPEECH_THRESHOLD = 0.035;
const SILENCE_MS = 850;
const MIN_UTTERANCE_MS = 650;
const PARTIAL_ASR_MS = 2200;

function supportedMime() {
  if (typeof MediaRecorder === "undefined") return "";
  return MIME_OPTIONS.find((mime) => MediaRecorder.isTypeSupported(mime)) || "";
}

function phaseLabel(phase: Phase) {
  if (phase === "idle") return "Idle";
  if (phase === "listening") return "Listening";
  if (phase === "speech") return "Hearing speech";
  if (phase === "transcribing") return "Transcribing";
  if (phase === "thinking") return "Answering";
  if (phase === "speaking") return "Speaking";
  return "Needs attention";
}

function fileExt(mime: string) {
  if (mime.includes("mp4")) return "m4a";
  if (mime.includes("ogg")) return "ogg";
  return "webm";
}

function historyFrom(turns: Turn[]): ChatHistoryTurn[] {
  return turns
    .flatMap((turn) => [
      { role: "user" as const, content: turn.user },
      ...(turn.assistant ? [{ role: "assistant" as const, content: turn.assistant }] : []),
    ])
    .slice(-8);
}

function speakableSegment(text: string) {
  const clean = text.replace(/\n+Sources:[\s\S]*$/i, "").replace(/https?:\/\/\S+/gi, " ");
  const sentences = clean
    .split(/(?<=[।.!?])\s+/)
    .map((part) => part.trim())
    .filter((part) => /[\u0900-\u097F]/.test(part));
  const selected: string[] = [];
  for (const sentence of sentences.length ? sentences : [clean.trim()]) {
    if (!/[\u0900-\u097F]/.test(sentence)) continue;
    const candidate = [...selected, sentence].join(" ");
    if (candidate.length > 230) break;
    selected.push(sentence);
  }
  return selected.join(" ").trim();
}

function formatMs(value?: number) {
  if (value === undefined) return "-";
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

function newId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random()}`;
}

export function LiveKiosk() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [apiBaseInput, setApiBaseInput] = useState(getRuntimeApiBase());
  const [liveEnabled, setLiveEnabled] = useState(false);
  const [autoSpeak, setAutoSpeak] = useState(true);
  const [level, setLevel] = useState(0);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [metrics, setMetrics] = useState<Metrics>({});
  const [lastTranscript, setLastTranscript] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");
  const [statusText, setStatusText] = useState("");

  const phaseRef = useRef<Phase>("idle");
  const liveEnabledRef = useRef(false);
  const processingRef = useRef(false);
  const ignoreStopRef = useRef(false);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const turnsRef = useRef<Turn[]>([]);
  const chunksRef = useRef<BlobPart[]>([]);
  const partialTimerRef = useRef<number | null>(null);
  const partialInFlightRef = useRef(false);
  const partialAbortRef = useRef<AbortController | null>(null);
  const rafRef = useRef<number | null>(null);
  const lastVoiceAtRef = useRef(0);
  const utteranceStartedAtRef = useRef(0);
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const activeAudioUrlRef = useRef<string | null>(null);

  useEffect(() => {
    turnsRef.current = turns;
  }, [turns]);

  useEffect(() => () => stopLive(), []);

  function setPhaseSafe(next: Phase) {
    phaseRef.current = next;
    setPhase(next);
  }

  async function measureBackend() {
    const samples: number[] = [];
    for (let i = 0; i < 5; i += 1) {
      const started = performance.now();
      const response = await fetch(apiPath("/health"), { cache: "no-store" });
      await response.text();
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      samples.push(performance.now() - started);
    }
    samples.sort((a, b) => a - b);
    const median = samples[Math.floor(samples.length / 2)];
    setMetrics((prev) => ({ ...prev, networkMs: median }));
    setStatusText(`Backend ${formatMs(median)}`);
  }

  function saveApiBase() {
    const saved = setRuntimeApiBase(apiBaseInput);
    setApiBaseInput(saved);
    toast.success(saved ? "Kiosk API base saved." : "Using same-origin API.");
    void measureBackend().catch((error) => {
      toast.error(error instanceof Error ? error.message : "Backend check failed");
    });
  }

  async function startLive() {
    if (liveEnabledRef.current) return;
    if (typeof window !== "undefined" && !window.isSecureContext) {
      toast.error("Microphone requires localhost or HTTPS. Open this on the kiosk machine as http://127.0.0.1:8000/kiosk.");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      toast.error("This browser cannot record audio.");
      return;
    }
    try {
      await measureBackend();
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      const context = new AudioContext();
      const source = context.createMediaStreamSource(stream);
      const analyser = context.createAnalyser();
      analyser.fftSize = 1024;
      source.connect(analyser);

      const mime = supportedMime();
      const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        if (ignoreStopRef.current) {
          ignoreStopRef.current = false;
          return;
        }
        const finalMime = recorder.mimeType || mime || "audio/webm";
        stopPartialTranscription();
        const blob = new Blob(chunksRef.current, { type: finalMime });
        chunksRef.current = [];
        if (blob.size < 1200) {
          if (liveEnabledRef.current) setPhaseSafe("listening");
          return;
        }
        void processUtterance(blob, finalMime);
      };

      streamRef.current = stream;
      audioContextRef.current = context;
      analyserRef.current = analyser;
      recorderRef.current = recorder;
      liveEnabledRef.current = true;
      setLiveEnabled(true);
      setPhaseSafe("listening");
      loopVad();
    } catch (error) {
      setPhaseSafe("error");
      toast.error(error instanceof Error ? error.message : "Could not start live mode");
    }
  }

  function stopLive() {
    liveEnabledRef.current = false;
    setLiveEnabled(false);
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    stopPartialTranscription();
    activeAudioRef.current?.pause();
    if (activeAudioUrlRef.current) URL.revokeObjectURL(activeAudioUrlRef.current);
    activeAudioRef.current = null;
    activeAudioUrlRef.current = null;
    const recorder = recorderRef.current;
    if (recorder && recorder.state === "recording") {
      ignoreStopRef.current = true;
      recorder.stop();
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    void audioContextRef.current?.close().catch(() => undefined);
    streamRef.current = null;
    audioContextRef.current = null;
    analyserRef.current = null;
    recorderRef.current = null;
    chunksRef.current = [];
    processingRef.current = false;
    setLevel(0);
    setPhaseSafe("idle");
  }

  function loopVad() {
    const analyser = analyserRef.current;
    if (!analyser || !liveEnabledRef.current) return;
    const data = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (const value of data) {
      const centered = (value - 128) / 128;
      sum += centered * centered;
    }
    const rms = Math.sqrt(sum / data.length);
    setLevel((prev) => prev * 0.7 + rms * 0.3);

    const now = performance.now();
    const recorder = recorderRef.current;
    const currentPhase = phaseRef.current;
    if (!processingRef.current && recorder) {
      if (currentPhase === "listening" && rms > RMS_SPEECH_THRESHOLD && recorder.state === "inactive") {
        chunksRef.current = [];
        setInterimTranscript("");
        utteranceStartedAtRef.current = now;
        lastVoiceAtRef.current = now;
        recorder.start(250);
        startPartialTranscription(recorder.mimeType || supportedMime() || "audio/webm");
        setPhaseSafe("speech");
      } else if (currentPhase === "speech") {
        if (rms > RMS_SPEECH_THRESHOLD) lastVoiceAtRef.current = now;
        const silentFor = now - lastVoiceAtRef.current;
        const utteranceFor = now - utteranceStartedAtRef.current;
        if (silentFor > SILENCE_MS && utteranceFor > MIN_UTTERANCE_MS && recorder.state === "recording") {
          setPhaseSafe("transcribing");
          recorder.stop();
        }
      }
    }
    rafRef.current = requestAnimationFrame(loopVad);
  }

  function startPartialTranscription(mime: string) {
    stopPartialTranscription();
    partialTimerRef.current = window.setInterval(() => {
      void transcribePartial(mime);
    }, PARTIAL_ASR_MS);
  }

  function stopPartialTranscription() {
    if (partialTimerRef.current !== null) {
      window.clearInterval(partialTimerRef.current);
      partialTimerRef.current = null;
    }
    partialAbortRef.current?.abort();
    partialAbortRef.current = null;
    partialInFlightRef.current = false;
  }

  async function transcribePartial(mime: string) {
    if (partialInFlightRef.current || phaseRef.current !== "speech") return;
    const blob = new Blob(chunksRef.current, { type: mime });
    if (blob.size < 3000) return;
    partialInFlightRef.current = true;
    const controller = new AbortController();
    partialAbortRef.current = controller;
    const started = performance.now();
    try {
      const asr = await transcribeVoice(blob, `partial.${fileExt(mime)}`, controller.signal);
      const transcript = asr.transcript.trim();
      if (transcript && phaseRef.current === "speech") {
        setInterimTranscript(transcript);
        setMetrics((prev) => ({ ...prev, partialAsrMs: performance.now() - started }));
      }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        // Interim ASR is best-effort; final ASR still runs at end of utterance.
        console.warn("partial ASR failed", error);
      }
    } finally {
      if (partialAbortRef.current === controller) partialAbortRef.current = null;
      partialInFlightRef.current = false;
    }
  }

  async function processUtterance(blob: Blob, mime: string) {
    if (processingRef.current) return;
    processingRef.current = true;
    setPhaseSafe("transcribing");
    const turnId = newId();
    try {
      const asrStarted = performance.now();
      const asr = await transcribeVoice(blob, `kiosk.${fileExt(mime)}`);
      const asrElapsed = performance.now() - asrStarted;
      const transcript = asr.transcript.trim();
      setMetrics((prev) => ({ ...prev, asrMs: asrElapsed }));
      setLastTranscript(transcript);
      setInterimTranscript("");
      if (!transcript) {
        setStatusText("No speech recognized");
        if (liveEnabledRef.current) setPhaseSafe("listening");
        return;
      }

      const history = historyFrom(turnsRef.current);
      setTurns((prev) => [...prev, { id: turnId, user: transcript, assistant: "", streaming: true, asr }]);
      setPhaseSafe("thinking");
      let finalAnswer = "";

      const updateTurn = (patch: Partial<Turn>) => {
        setTurns((prev) => prev.map((turn) => (turn.id === turnId ? { ...turn, ...patch } : turn)));
      };

      const queryStarted = performance.now();
      await postQueryStream(transcript, history, {
        onMeta: (meta: QueryStreamMeta) => {
          setMetrics((prev) => ({ ...prev, retrievalMs: meta.latency_ms.retrieval }));
        },
        onToken: (text) => {
          setTurns((prev) =>
            prev.map((turn) =>
              turn.id === turnId ? { ...turn, assistant: `${turn.assistant}${text}` } : turn,
            ),
          );
        },
        onFinal: (response) => {
          finalAnswer = response.answer;
          updateTurn({ assistant: response.answer, response, streaming: false });
          setMetrics((prev) => ({
            ...prev,
            retrievalMs: response.latency_ms.retrieval,
            generationMs: response.latency_ms.generation,
            totalQueryMs: performance.now() - queryStarted,
          }));
        },
      });

      if (autoSpeak && finalAnswer) {
        await playAnswer(finalAnswer);
      }
      if (liveEnabledRef.current) setPhaseSafe("listening");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setTurns((prev) => [...prev, { id: turnId, user: lastTranscript || "(audio)", assistant: "", streaming: false, error: message }]);
      setPhaseSafe("error");
      toast.error(message);
    } finally {
      processingRef.current = false;
      if (liveEnabledRef.current && phaseRef.current === "error") setPhaseSafe("listening");
    }
  }

  async function playAnswer(answer: string) {
    const text = speakableSegment(answer);
    if (!text) return;
    setPhaseSafe("speaking");
    const ttsStarted = performance.now();
    activeAudioRef.current?.pause();
    if (activeAudioUrlRef.current) URL.revokeObjectURL(activeAudioUrlRef.current);
    const result = await synthesizeVoice(text);
    setMetrics((prev) => ({ ...prev, ttsMs: result.latencyMs || performance.now() - ttsStarted }));
    const url = URL.createObjectURL(result.audio);
    activeAudioUrlRef.current = url;
    const audio = new Audio(url);
    activeAudioRef.current = audio;
    await new Promise<void>((resolve, reject) => {
      audio.onended = () => resolve();
      audio.onerror = () => reject(new Error("audio playback failed"));
      audio.play().catch(reject);
    });
    if (activeAudioUrlRef.current === url) {
      URL.revokeObjectURL(url);
      activeAudioUrlRef.current = null;
      activeAudioRef.current = null;
    }
  }

  function resetConversation() {
    setTurns([]);
    setLastTranscript("");
    setInterimTranscript("");
    setMetrics((prev) => ({ networkMs: prev.networkMs }));
  }

  const meterWidth = `${Math.min(100, Math.round(level * 600))}%`;
  const liveUrl = getRuntimeApiBase() || "same-origin";

  return (
    <div className="min-h-screen bg-[#f7f8f4] text-slate-900">
      <header className="border-b border-slate-300 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <h1 className="text-xl font-display font-extrabold">PreVillage Kiosk</h1>
            <p className="text-xs font-semibold text-slate-500">{liveUrl}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-slate-50 px-3 py-1.5 text-sm font-bold">
              <Activity className="size-4" />
              {phaseLabel(phase)}
            </span>
            <button
              onClick={liveEnabled ? stopLive : startLive}
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-extrabold text-white ${
                liveEnabled ? "bg-red-600 hover:bg-red-700" : "bg-emerald-700 hover:bg-emerald-800"
              }`}
            >
              {liveEnabled ? <MicOff className="size-4" /> : <Mic className="size-4" />}
              {liveEnabled ? "Stop" : "Start live"}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-4 px-4 py-4 lg:grid-cols-[320px_1fr]">
        <aside className="space-y-4">
          <section className="rounded-lg border border-slate-300 bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-center gap-2 text-sm font-extrabold">
              <Settings className="size-4" />
              Endpoint
            </div>
            <input
              value={apiBaseInput}
              onChange={(event) => setApiBaseInput(event.target.value)}
              placeholder="http://192.168.10.30:8000"
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-emerald-700"
            />
            <div className="mt-2 grid grid-cols-2 gap-2">
              <button
                onClick={saveApiBase}
                className="rounded-md bg-slate-900 px-3 py-2 text-sm font-bold text-white hover:bg-slate-800"
              >
                Save
              </button>
              <button
                onClick={() => void measureBackend().catch((error) => toast.error(error instanceof Error ? error.message : "Check failed"))}
                className="inline-flex items-center justify-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-bold hover:bg-slate-50"
              >
                <Wifi className="size-4" />
                Check
              </button>
            </div>
          </section>

          {typeof window !== "undefined" && !window.isSecureContext && (
            <section className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm font-semibold text-amber-950">
              Microphone capture is blocked on this origin. Use localhost on the kiosk machine or serve this route over HTTPS.
            </section>
          )}

          <section className="rounded-lg border border-slate-300 bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between gap-2">
              <span className="text-sm font-extrabold">Mic level</span>
              <span className="text-xs font-bold text-slate-500">{Math.round(level * 1000)}</span>
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-slate-200">
              <div className="h-full rounded-full bg-emerald-600 transition-[width]" style={{ width: meterWidth }} />
            </div>
            <label className="mt-4 flex items-center justify-between gap-3 text-sm font-bold">
              <span className="inline-flex items-center gap-2">
                <Volume2 className="size-4" />
                Voice reply
              </span>
              <input
                type="checkbox"
                checked={autoSpeak}
                onChange={(event) => setAutoSpeak(event.target.checked)}
                className="size-5 accent-emerald-700"
              />
            </label>
            <button
              onClick={resetConversation}
              className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-bold hover:bg-slate-50"
            >
              <RotateCcw className="size-4" />
              Reset conversation
            </button>
          </section>

          <section className="rounded-lg border border-slate-300 bg-white p-4 shadow-sm">
            <div className="mb-3 text-sm font-extrabold">Latency</div>
            <Metric label="Network" value={formatMs(metrics.networkMs)} />
            <Metric label="Live ASR" value={formatMs(metrics.partialAsrMs)} />
            <Metric label="ASR" value={formatMs(metrics.asrMs)} />
            <Metric label="Retrieval" value={formatMs(metrics.retrievalMs)} />
            <Metric label="Generation" value={formatMs(metrics.generationMs)} />
            <Metric label="TTS" value={formatMs(metrics.ttsMs)} />
            {statusText && <p className="mt-3 text-xs font-semibold text-slate-500">{statusText}</p>}
          </section>
        </aside>

        <section className="flex min-h-[calc(100vh-8rem)] flex-col rounded-lg border border-slate-300 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              {phase === "listening" && <CheckCircle2 className="size-5 text-emerald-700" />}
              {phase === "speech" && <Mic className="size-5 text-emerald-700" />}
              {(phase === "transcribing" || phase === "thinking" || phase === "speaking") && (
                <Loader2 className="size-5 animate-spin text-slate-700" />
              )}
              {phase === "error" && <AlertTriangle className="size-5 text-red-600" />}
              <span className="text-lg font-extrabold">{phaseLabel(phase)}</span>
              {lastTranscript && <span className="text-sm font-semibold text-slate-500">Last: {lastTranscript}</span>}
            </div>
            {interimTranscript && phase === "speech" && (
              <p className="mt-2 text-base font-semibold text-emerald-800">{interimTranscript}</p>
            )}
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4">
            {turns.length === 0 && (
              <div className="flex h-full min-h-[420px] items-center justify-center text-center">
                <div>
                  <Mic className="mx-auto size-14 text-emerald-700" />
                  <p className="mt-4 text-2xl font-display font-extrabold">Ready for voice intake</p>
                  <p className="mt-1 text-sm font-semibold text-slate-500">Ask one government-service question at a time.</p>
                </div>
              </div>
            )}
            {turns.map((turn) => (
              <article key={turn.id} className="space-y-3">
                <div className="max-w-[82%] rounded-lg bg-emerald-700 px-4 py-3 text-white">
                  <p className="text-xs font-bold uppercase tracking-wide text-emerald-100">Citizen</p>
                  <p className="mt-1 text-lg font-semibold">{turn.user}</p>
                  {turn.asr && (
                    <p className="mt-2 text-xs font-semibold text-emerald-100">
                      ASR {turn.asr.provider} · {formatMs(turn.asr.latency_ms.total)}
                    </p>
                  )}
                </div>
                <div className="ml-auto max-w-[88%] rounded-lg border border-slate-300 bg-slate-50 px-4 py-3">
                  <p className="text-xs font-bold uppercase tracking-wide text-slate-500">PreVillage</p>
                  {turn.error ? (
                    <p className="mt-1 text-red-700">{turn.error}</p>
                  ) : (
                    <p className="mt-1 whitespace-pre-wrap text-lg leading-relaxed">{turn.assistant || "..."}</p>
                  )}
                  {turn.streaming && (
                    <p className="mt-2 inline-flex items-center gap-2 text-xs font-bold text-slate-500">
                      <Loader2 className="size-3 animate-spin" />
                      streaming
                    </p>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 py-1.5 text-sm last:border-b-0">
      <span className="font-semibold text-slate-500">{label}</span>
      <span className="font-extrabold text-slate-900">{value}</span>
    </div>
  );
}
