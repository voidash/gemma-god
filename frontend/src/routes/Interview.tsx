import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Camera,
  CheckCircle2,
  Mic,
  RotateCcw,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { StickerButton } from "@/components/sticker/StickerButton";
import { StickerCard } from "@/components/sticker/StickerCard";
import {
  BurstStar,
  Dot,
  Sparkle,
  Squiggle,
  Triangle,
} from "@/components/sticker/decor";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  getQuestionnaire,
  submitInterview,
  type Questionnaire,
} from "@/lib/api";

type RecState = {
  blob?: Blob;
  ext?: string;
  mediaRecorder?: MediaRecorder;
  stream?: MediaStream;
  startedAt?: number;
  status: "idle" | "recording" | "done";
};

const AUDIO_MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
];

function pickMime(): string {
  if (typeof MediaRecorder === "undefined") return "";
  for (const m of AUDIO_MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return "";
}
function extFromMime(m: string): string {
  if (m.startsWith("audio/webm")) return "webm";
  if (m.startsWith("audio/mp4")) return "m4a";
  if (m.startsWith("audio/ogg")) return "ogg";
  return "webm";
}

const Q_TONES = [
  "violet",
  "pink",
  "amber",
  "mint",
  "sky",
  "violet",
  "pink",
  "amber",
] as const;

export function Interview() {
  const { t, i18n } = useTranslation();
  const [questionnaire, setQuestionnaire] = useState<Questionnaire | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [office, setOffice] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const [recordings, setRecordings] = useState<Record<string, RecState>>({});
  const [, setTick] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState<string | null>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getQuestionnaire()
      .then(setQuestionnaire)
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => {
      const recording = Object.values(recordings).some(
        (r) => r.status === "recording",
      );
      if (recording) setTick((x) => x + 1);
    }, 500);
    return () => window.clearInterval(id);
  }, [recordings]);

  async function startRecording(qid: string) {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      toast.error(
        t("interview.mic_denied") +
          ": " +
          (e instanceof Error ? e.message : String(e)),
      );
      return;
    }
    const mime = pickMime();
    const mr = mime
      ? new MediaRecorder(stream, { mimeType: mime })
      : new MediaRecorder(stream);
    const chunks: Blob[] = [];
    mr.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) chunks.push(ev.data);
    };
    mr.onstop = () => {
      const finalMime = mr.mimeType || mime || "audio/webm";
      const blob = new Blob(chunks, { type: finalMime });
      setRecordings((prev) => ({
        ...prev,
        [qid]: { blob, ext: extFromMime(finalMime), status: "done" },
      }));
      stream.getTracks().forEach((t) => t.stop());
    };
    setRecordings((prev) => ({
      ...prev,
      [qid]: {
        mediaRecorder: mr,
        stream,
        startedAt: Date.now(),
        status: "recording",
      },
    }));
    mr.start();
  }

  function stopRecording(qid: string) {
    const r = recordings[qid];
    if (r?.mediaRecorder && r.mediaRecorder.state === "recording") {
      r.mediaRecorder.stop();
    }
  }

  function resetRecording(qid: string) {
    setRecordings((prev) => {
      const next = { ...prev };
      delete next[qid];
      return next;
    });
  }

  function onPhotosPicked(files: FileList | null) {
    if (!files) return;
    const next = [...photos];
    for (const f of Array.from(files)) {
      if (next.length >= 5) break;
      if (f.size > 5 * 1024 * 1024) {
        toast.error(`${f.name}: too large (max 5 MB)`);
        continue;
      }
      next.push(f);
    }
    setPhotos(next);
  }

  function removePhoto(idx: number) {
    setPhotos(photos.filter((_, i) => i !== idx));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !office.trim()) {
      toast.error(t("interview.submit_validation_name"));
      return;
    }
    const recorded = Object.entries(recordings).filter(
      ([, v]) => v.status === "done" && v.blob,
    );
    if (recorded.length === 0) {
      toast.error(t("interview.submit_validation_audio"));
      return;
    }

    setSubmitting(true);
    const fd = new FormData();
    fd.append("name", name.trim());
    fd.append("office", office.trim());
    for (const [qid, st] of recorded) {
      fd.append("question_ids", qid);
      fd.append("audio_files", st.blob!, `${qid}.${st.ext ?? "webm"}`);
    }
    for (const f of photos) fd.append("photo_files", f, f.name);

    try {
      const res = await submitInterview(fd);
      setSubmitted(res.id);
    } catch (err) {
      toast.error(
        t("interview.submit_failed") +
          ": " +
          (err instanceof Error ? err.message : String(err)),
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) return <SuccessState id={submitted} />;

  const isNe = i18n.resolvedLanguage === "ne";
  const title =
    (isNe ? questionnaire?.title_ne || questionnaire?.title : questionnaire?.title) ||
    t("interview.title");
  const intro =
    (isNe ? questionnaire?.intro_ne || questionnaire?.intro : questionnaire?.intro) ||
    t("interview.intro_fallback");

  return (
    <div className="relative bg-cream pb-24">
      {/* Decoration */}
      <Triangle
        size={56}
        className="absolute top-12 right-8 text-pink hidden md:block animate-float"
      />
      <Dot
        size={24}
        className="absolute top-32 right-1/3 text-amber hidden md:block"
      />
      <div
        aria-hidden
        className="absolute top-0 left-0 w-full h-72 dot-grid-soft opacity-60 pointer-events-none"
      />

      <form
        onSubmit={onSubmit}
        className="relative mx-auto max-w-3xl px-4 sm:px-6 py-12 flex flex-col gap-10"
      >
        <header>
          <div className="inline-flex items-center gap-2 rounded-full border-2 border-ink bg-card px-3 py-1 text-xs font-display font-bold shadow-[2px_2px_0_0_var(--ink)]">
            <Mic className="size-3.5" strokeWidth={2.5} />
            {t("interview.subtitle")}
          </div>
          <h1 className="mt-4 text-3xl sm:text-5xl font-display font-extrabold tracking-tight text-ink leading-tight">
            {title}
          </h1>
          <Squiggle size={120} className="mt-2 text-pink" />
          <p className="mt-4 max-w-2xl text-base text-ink/75 leading-relaxed">
            {intro}
          </p>
        </header>

        {/* About you */}
        <section className="grid gap-4">
          <FieldLabel tone="violet">{t("interview.about_you")}</FieldLabel>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="iv-name" className="text-xs uppercase tracking-widest font-display font-bold text-ink/65">
                {t("interview.your_name")}
              </Label>
              <PoppyInput
                id="iv-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("interview.your_name_placeholder")}
                autoComplete="name"
                required
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="iv-office" className="text-xs uppercase tracking-widest font-display font-bold text-ink/65">
                {t("interview.your_office")}
              </Label>
              <PoppyInput
                id="iv-office"
                value={office}
                onChange={(e) => setOffice(e.target.value)}
                placeholder={t("interview.your_office_placeholder")}
                autoComplete="organization"
                required
              />
            </div>
          </div>
        </section>

        {/* Questions */}
        <section className="grid gap-5">
          <FieldLabel tone="pink">
            {t("interview.questions_section")}
          </FieldLabel>

          {!questionnaire && !loadError && (
            <div className="grid gap-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-36 rounded-2xl border-2 border-ink/20" />
              ))}
            </div>
          )}

          {loadError && (
            <StickerCard tone="ink" className="border-destructive bg-destructive/5 p-4">
              <p className="text-sm text-destructive font-medium">
                {t("interview.questionnaire_failed")}: {loadError}
              </p>
            </StickerCard>
          )}

          {questionnaire?.questions.map((q, i) => {
            const state = recordings[q.id];
            const tone = Q_TONES[i % Q_TONES.length];
            const primary = isNe ? q.question_ne || q.question : q.question;
            const secondary = isNe ? q.question : q.question_ne || "";
            return (
              <StickerCard
                key={q.id}
                tone={tone}
                className={cn(
                  "p-6 pt-9",
                  state?.status === "recording" && "ring-4 ring-rose-400/30",
                )}
              >
                {/* Floating Q-number bubble */}
                <div
                  className={cn(
                    "absolute -top-5 -left-3 size-12 rounded-full border-2 border-ink",
                    "shadow-[3px_3px_0_0_var(--ink)] flex items-center justify-center",
                    "font-display font-extrabold text-base",
                    tone === "violet" && "bg-violet text-white",
                    tone === "pink" && "bg-pink text-ink",
                    tone === "amber" && "bg-amber text-ink",
                    tone === "mint" && "bg-mint text-ink",
                    tone === "sky" && "bg-sky text-ink",
                  )}
                  aria-hidden
                >
                  Q{i + 1}
                </div>

                <p className="text-base sm:text-lg font-display font-bold text-ink leading-snug">
                  {primary}
                </p>
                {secondary && (
                  <p className="mt-1.5 text-sm text-ink/55 leading-snug">
                    {secondary}
                  </p>
                )}

                <div className="mt-5 flex flex-wrap items-center gap-3">
                  <RecordControl
                    state={state}
                    onStart={() => void startRecording(q.id)}
                    onStop={() => stopRecording(q.id)}
                    onReset={() => resetRecording(q.id)}
                  />
                  {state?.status === "done" && state.blob && (
                    <audio
                      controls
                      src={URL.createObjectURL(state.blob)}
                      className="h-10 max-w-full"
                    />
                  )}
                </div>
              </StickerCard>
            );
          })}
        </section>

        {/* Photos */}
        <section className="grid gap-4">
          <FieldLabel tone="amber">{t("interview.photos_section")}</FieldLabel>
          <input
            ref={photoInputRef}
            type="file"
            accept="image/*"
            multiple
            capture="environment"
            className="hidden"
            onChange={(e) => onPhotosPicked(e.target.files)}
          />
          <button
            type="button"
            onClick={() => photoInputRef.current?.click()}
            disabled={photos.length >= 5}
            className={cn(
              "flex items-center justify-center gap-3 rounded-2xl border-[3px] border-dashed border-ink/40",
              "py-8 px-4 text-sm font-display font-semibold text-ink/65",
              "bg-card transition-colors",
              "hover:border-ink hover:bg-amber/10 hover:text-ink",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
          >
            <span className="flex size-10 items-center justify-center rounded-full border-2 border-ink bg-amber text-ink shadow-[2px_2px_0_0_var(--ink)]">
              <Camera className="size-4" strokeWidth={2.5} />
            </span>
            {t("interview.photos_hint")}
          </button>
          {photos.length > 0 && (
            <div className="flex flex-wrap gap-3">
              {photos.map((p, i) => (
                <div key={i} className="relative">
                  <img
                    src={URL.createObjectURL(p)}
                    alt=""
                    className="size-24 rounded-xl object-cover border-2 border-ink shadow-[3px_3px_0_0_var(--ink)]"
                  />
                  <button
                    type="button"
                    onClick={() => removePhoto(i)}
                    className="absolute -top-2 -right-2 size-7 rounded-full border-2 border-ink bg-pink text-ink flex items-center justify-center shadow-[2px_2px_0_0_var(--ink)]"
                    aria-label="Remove photo"
                  >
                    <X className="size-3.5" strokeWidth={2.75} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Submit */}
        <div className="pt-4">
          <StickerButton
            type="submit"
            tone="violet"
            size="xl"
            disabled={submitting}
          >
            {submitting ? t("interview.uploading") : t("interview.submit")}
            <Sparkles className="size-5" strokeWidth={2.5} />
          </StickerButton>
        </div>
      </form>
    </div>
  );
}

/** Section eyebrow with squiggle. */
function FieldLabel({
  children,
  tone,
}: {
  children: React.ReactNode;
  tone: "violet" | "pink" | "amber" | "mint";
}) {
  const colorClass =
    tone === "violet"
      ? "text-violet"
      : tone === "pink"
        ? "text-pink"
        : tone === "amber"
          ? "text-amber"
          : "text-mint";
  return (
    <div className="flex items-center gap-2">
      <h2 className="text-xs uppercase tracking-widest font-display font-extrabold text-ink/70">
        {children}
      </h2>
      <Squiggle size={50} className={colorClass} />
    </div>
  );
}

const PoppyInput = (props: React.ComponentProps<typeof Input>) => (
  <Input
    {...props}
    className={cn(
      "h-12 rounded-xl border-2 border-ink bg-card text-base shadow-[3px_3px_0_0_var(--ink)]",
      "focus-visible:border-violet focus-visible:ring-0 focus-visible:shadow-[3px_3px_0_0_var(--violet)]",
      props.className,
    )}
  />
);

function RecordControl({
  state,
  onStart,
  onStop,
  onReset,
}: {
  state?: RecState;
  onStart: () => void;
  onStop: () => void;
  onReset: () => void;
}) {
  const { t } = useTranslation();

  if (!state || state.status === "idle") {
    return (
      <button
        type="button"
        onClick={onStart}
        className={cn(
          "inline-flex items-center gap-2 rounded-full border-2 border-ink",
          "bg-pink text-ink px-4 h-11 text-sm font-display font-bold",
          "shadow-[3px_3px_0_0_var(--ink)] transition-all duration-200",
          "ease-[cubic-bezier(0.34,1.56,0.64,1)]",
          "hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[5px_5px_0_0_var(--ink)]",
          "active:translate-x-0.5 active:translate-y-0.5 active:shadow-[2px_2px_0_0_var(--ink)]",
          "motion-reduce:hover:transform-none",
        )}
      >
        <span className="inline-flex size-7 items-center justify-center rounded-full border-2 border-ink bg-cream">
          <Mic className="size-3.5 text-ink" strokeWidth={2.5} />
        </span>
        {t("interview.rec_idle")}
      </button>
    );
  }
  if (state.status === "recording") {
    const elapsed = Math.floor((Date.now() - (state.startedAt ?? Date.now())) / 1000);
    return (
      <button
        type="button"
        onClick={onStop}
        className={cn(
          "inline-flex items-center gap-2 rounded-full border-2 border-ink",
          "bg-rose-500 text-white px-4 h-11 text-sm font-display font-bold",
          "shadow-[3px_3px_0_0_var(--ink)]",
          "animate-pulse",
        )}
      >
        <Square className="size-3.5 fill-current" strokeWidth={2.5} />
        {t("interview.rec_recording")} · {elapsed}s
      </button>
    );
  }
  const kb = state.blob ? Math.round(state.blob.size / 1024) : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="inline-flex items-center gap-2 rounded-full border-2 border-ink bg-mint px-3 h-11 text-sm font-display font-bold text-ink shadow-[2px_2px_0_0_var(--ink)]">
        <CheckCircle2 className="size-4" strokeWidth={2.5} />
        {t("interview.rec_done", { kb })}
      </span>
      <button
        type="button"
        onClick={onReset}
        className="inline-flex items-center gap-1 px-3 h-9 rounded-full border-2 border-ink bg-cream text-xs font-display font-bold text-ink hover:bg-amber"
      >
        <RotateCcw className="size-3.5" strokeWidth={2.5} />
        {t("interview.rec_re")}
      </button>
    </div>
  );
}

function SuccessState({ id }: { id: string }) {
  const { t } = useTranslation();
  return (
    <div className="relative mx-auto max-w-2xl px-4 py-20">
      <BurstStar
        size={88}
        className="absolute -top-2 left-4 text-amber animate-float"
      />
      <Triangle
        size={50}
        className="absolute top-12 right-12 text-pink animate-float"
      />
      <Dot size={26} className="absolute top-24 left-1/3 text-mint" />
      <Sparkle size={28} className="absolute top-8 right-1/4 text-violet" />

      <StickerCard
        tone="mint"
        className="p-10 text-center animate-pop-in"
      >
        <div className="inline-flex size-16 items-center justify-center rounded-full border-2 border-ink bg-mint shadow-[3px_3px_0_0_var(--ink)]">
          <CheckCircle2 className="size-8 text-ink" strokeWidth={2.5} />
        </div>
        <h2 className="mt-6 text-3xl font-display font-extrabold tracking-tight text-ink">
          {t("interview.submit_success_title")}
        </h2>
        <Squiggle size={120} className="mx-auto mt-2 text-pink" />
        <p className="mt-4 text-base text-ink/75 leading-relaxed">
          {t("interview.submit_success_body")}
        </p>
        <p className="mt-8 text-xs text-ink/55 font-display font-semibold uppercase tracking-wider">
          {t("interview.submission_id")}:{" "}
          <span className="font-mono text-ink/80">{id}</span>
        </p>
      </StickerCard>
    </div>
  );
}
