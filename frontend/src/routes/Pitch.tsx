import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Cpu,
  Database,
  Maximize,
  Mic,
  Minimize,
  Phone,
  Sparkles,
} from "lucide-react";
import { StickerButton } from "@/components/sticker/StickerButton";
import { StickerCard } from "@/components/sticker/StickerCard";
import {
  BurstStar,
  Dot,
  Sparkle,
  Squiggle,
  Triangle,
} from "@/components/sticker/decor";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { cn } from "@/lib/utils";

/**
 * Pitch deck. Designed for a 5-minute live presentation to government
 * officials. Each <Slide> is full-viewport; navigation is keyboard-first
 * (←/→/Space/F for fullscreen) so the presenter never reaches for a mouse.
 *
 * Design choices:
 * - Slides reuse the Memphis sticker primitives so the deck visually IS the
 *   product. Switching to /chat for the live demo on slide 5 is a single tab
 *   away and doesn't break aesthetic continuity.
 * - The story (slide 2) is told in the founder's first person — quotes are
 *   verbatim. No rephrasing of "Tripureshwor → Kalimati → Kalanki" or the
 *   8,000-rupee figure: specifics carry weight.
 * - Architecture (slide 6) speaks ingredients, not infrastructure. Officials
 *   don't need to hear "FastAPI on M2 Ultra"; they need to hear "open AI,
 *   runs on a Pi, your data stays in Nepal."
 */

const TOTAL_SLIDES = 10;

export function Pitch() {
  const [index, setIndex] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const goNext = useCallback(
    () => setIndex((i) => Math.min(TOTAL_SLIDES - 1, i + 1)),
    [],
  );
  const goPrev = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);
  const goTo = useCallback((i: number) => setIndex(Math.max(0, Math.min(TOTAL_SLIDES - 1, i))), []);

  // Keyboard navigation
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      // Don't hijack arrow keys when an input/textarea has focus
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea") return;
      if (e.key === "ArrowRight" || e.key === " " || e.key === "PageDown") {
        e.preventDefault();
        goNext();
      } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
        e.preventDefault();
        goPrev();
      } else if (e.key === "Home") {
        e.preventDefault();
        goTo(0);
      } else if (e.key === "End") {
        e.preventDefault();
        goTo(TOTAL_SLIDES - 1);
      } else if (e.key.toLowerCase() === "f") {
        e.preventDefault();
        toggleFullscreen();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goNext, goPrev, goTo]);

  function toggleFullscreen() {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  }
  useEffect(() => {
    const onFs = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  return (
    <div
      ref={containerRef}
      className="relative h-[calc(100svh-4rem)] overflow-hidden bg-cream"
    >
      <Slides index={index} />
      <ChromeBar
        index={index}
        total={TOTAL_SLIDES}
        onPrev={goPrev}
        onNext={goNext}
        onJump={goTo}
        onFullscreen={toggleFullscreen}
        isFullscreen={isFullscreen}
      />
    </div>
  );
}

function Slides({ index }: { index: number }) {
  // Render only the active slide. Mounting/unmounting between slides resets
  // any animation states so each transition feels fresh.
  switch (index) {
    case 0:
      return <Slide1 />;
    case 1:
      return <Slide2 />;
    case 2:
      return <Slide3 />;
    case 3:
      return <Slide4 />;
    case 4:
      return <Slide5 />;
    case 5:
      return <Slide6Eli5 />;
    case 6:
      return <Slide6Tech />;
    case 7:
      return <Slide7 />;
    case 8:
      return <Slide8 />;
    case 9:
      return <Slide9 />;
    default:
      return null;
  }
}

function ChromeBar({
  index,
  total,
  onPrev,
  onNext,
  onJump,
  onFullscreen,
  isFullscreen,
}: {
  index: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
  onJump: (i: number) => void;
  onFullscreen: () => void;
  isFullscreen: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="absolute bottom-0 left-0 right-0 z-30 border-t-2 border-ink bg-cream/90 backdrop-blur">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-2.5 flex items-center gap-3">
        <button
          type="button"
          onClick={onPrev}
          disabled={index === 0}
          aria-label={t("pitch.prev")}
          className={cn(
            "inline-flex size-9 items-center justify-center rounded-full border-2 border-ink",
            "bg-card transition-all duration-200 ease-[cubic-bezier(0.34,1.56,0.64,1)]",
            "hover:bg-amber hover:-translate-y-0.5 hover:shadow-[3px_3px_0_0_var(--ink)]",
            "disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:transform-none",
            "motion-reduce:hover:transform-none",
          )}
        >
          <ArrowLeft className="size-4" strokeWidth={2.5} />
        </button>

        <div className="flex-1 flex items-center gap-1.5 justify-center" role="tablist">
          {Array.from({ length: total }).map((_, i) => (
            <button
              key={i}
              type="button"
              role="tab"
              aria-selected={i === index}
              aria-label={`Slide ${i + 1}`}
              onClick={() => onJump(i)}
              className={cn(
                "h-2 rounded-full border-2 border-ink transition-all duration-200",
                i === index
                  ? "w-8 bg-violet"
                  : i < index
                    ? "w-2 bg-mint"
                    : "w-2 bg-card hover:bg-amber",
              )}
            />
          ))}
        </div>

        <span className="text-xs font-mono text-ink/65 hidden sm:inline">
          {t("pitch.slide_count", { current: index + 1, total })}
        </span>

        <LanguageSwitcher />

        <button
          type="button"
          onClick={onFullscreen}
          aria-label={isFullscreen ? t("pitch.exit_fullscreen") : t("pitch.fullscreen")}
          className={cn(
            "inline-flex size-9 items-center justify-center rounded-full border-2 border-ink",
            "bg-card transition-all duration-200 ease-[cubic-bezier(0.34,1.56,0.64,1)]",
            "hover:bg-amber hover:-translate-y-0.5 hover:shadow-[3px_3px_0_0_var(--ink)]",
            "motion-reduce:hover:transform-none",
          )}
        >
          {isFullscreen ? (
            <Minimize className="size-4" strokeWidth={2.5} />
          ) : (
            <Maximize className="size-4" strokeWidth={2.5} />
          )}
        </button>

        <button
          type="button"
          onClick={onNext}
          disabled={index === total - 1}
          aria-label={t("pitch.next")}
          className={cn(
            "inline-flex size-9 items-center justify-center rounded-full border-2 border-ink",
            "bg-violet text-white transition-all duration-200 ease-[cubic-bezier(0.34,1.56,0.64,1)]",
            "shadow-[3px_3px_0_0_var(--ink)]",
            "hover:-translate-y-0.5 hover:shadow-[5px_5px_0_0_var(--ink)]",
            "disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:transform-none disabled:shadow-[3px_3px_0_0_var(--ink)]",
            "motion-reduce:hover:transform-none",
          )}
        >
          <ArrowRight className="size-4" strokeWidth={2.5} />
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------ *
 * Shared slide shell                                                       *
 * ------------------------------------------------------------------------ */

function SlideFrame({
  children,
  className,
  decoration,
}: {
  children: React.ReactNode;
  className?: string;
  decoration?: React.ReactNode;
}) {
  return (
    <section
      className={cn(
        "absolute inset-0 bottom-14 overflow-y-auto animate-pop-in",
        "flex items-center justify-center",
        className,
      )}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 dot-grid-soft opacity-60"
      />
      {decoration}
      <div className="relative w-full max-w-5xl px-6 sm:px-10 py-10">
        {children}
      </div>
    </section>
  );
}

function Kicker({ children, color = "text-violet" }: { children: React.ReactNode; color?: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className={cn("text-xs sm:text-sm uppercase tracking-[0.2em] font-display font-extrabold", color)}>
        {children}
      </span>
      <Squiggle size={64} className={color} />
    </div>
  );
}

/* ------------------------------------------------------------------------ *
 * Slide 1 — cold open                                                       *
 * ------------------------------------------------------------------------ */

function Slide1() {
  const { t } = useTranslation();
  return (
    <SlideFrame
      decoration={
        <>
          <div
            aria-hidden
            className="absolute -top-32 -left-24 size-[460px] rounded-full bg-amber border-2 border-ink hidden md:block"
          />
          <Triangle size={64} className="absolute top-20 right-12 text-pink hidden md:block animate-float" />
          <Sparkle size={36} className="absolute bottom-32 right-1/4 text-violet hidden md:block animate-float" />
        </>
      }
    >
      <div className="text-center">
        <p className="font-display font-extrabold text-xs sm:text-sm uppercase tracking-[0.3em] text-ink/55">
          helpdesk.ampixa.com
        </p>
        <h1 className="mt-6 font-display font-extrabold tracking-tight leading-[1.05] text-ink text-5xl sm:text-7xl md:text-8xl">
          {t("pitch.s1_title")}
        </h1>
        <p className="mt-8 text-xl sm:text-2xl text-ink/70 font-display font-semibold">
          {t("pitch.s1_sub")}
        </p>
      </div>
    </SlideFrame>
  );
}

/* ------------------------------------------------------------------------ *
 * Slide 2 — the story                                                       *
 * ------------------------------------------------------------------------ */

function Slide2() {
  const { t } = useTranslation();
  return (
    <SlideFrame
      decoration={
        <Triangle size={56} className="absolute top-16 right-12 text-amber hidden md:block animate-float" />
      }
    >
      <Kicker color="text-pink">{t("pitch.s2_kicker")}</Kicker>
      <h1 className="mt-4 font-display font-extrabold leading-[1.05] text-4xl sm:text-6xl md:text-7xl text-ink">
        {t("pitch.s2_h1")}
      </h1>
      <h2 className="mt-3 font-display font-extrabold leading-[1.1] text-3xl sm:text-5xl md:text-6xl">
        <span
          className="px-1"
          style={{
            background: "linear-gradient(180deg, transparent 55%, var(--pink) 55%, var(--pink) 95%, transparent 95%)",
            WebkitBoxDecorationBreak: "clone",
            boxDecorationBreak: "clone",
          }}
        >
          {t("pitch.s2_h2")}
        </span>
      </h2>
      <div className="mt-8 inline-flex items-center gap-3 rounded-full border-2 border-ink bg-card px-5 py-2 shadow-[4px_4px_0_0_var(--ink)] font-display font-bold">
        {t("pitch.s2_route")}
      </div>
      <p className="mt-8 max-w-3xl text-base sm:text-lg text-ink/80 leading-relaxed">
        {t("pitch.s2_body")}
      </p>
      <p className="mt-6 max-w-3xl text-lg sm:text-xl font-display font-bold text-ink">
        {t("pitch.s2_punch")}
      </p>
    </SlideFrame>
  );
}

/* ------------------------------------------------------------------------ *
 * Slide 3 — diagnosis                                                       *
 * ------------------------------------------------------------------------ */

function Slide3() {
  const { t } = useTranslation();
  return (
    <SlideFrame
      decoration={
        <BurstStar size={84} className="absolute top-12 right-10 text-amber hidden md:block" />
      }
    >
      <Kicker color="text-amber">{t("pitch.s3_kicker")}</Kicker>
      <StickerCard tone="amber" className="mt-8 p-8 sm:p-12 max-w-4xl">
        <span className="absolute -top-4 -left-4 inline-flex size-12 items-center justify-center rounded-full border-2 border-ink bg-amber text-3xl font-display font-extrabold shadow-[3px_3px_0_0_var(--ink)]">
          “
        </span>
        <p className="font-display font-extrabold text-2xl sm:text-3xl md:text-4xl leading-tight text-ink">
          {t("pitch.s3_quote")}
        </p>
      </StickerCard>
      <p className="mt-8 max-w-3xl text-base sm:text-lg text-ink/75 leading-relaxed">
        {t("pitch.s3_body")}
      </p>
    </SlideFrame>
  );
}

/* ------------------------------------------------------------------------ *
 * Slide 4 — vision                                                          *
 * ------------------------------------------------------------------------ */

function Slide4() {
  const { t } = useTranslation();
  return (
    <SlideFrame
      decoration={
        <>
          <Dot size={28} className="absolute top-20 right-1/3 text-mint hidden md:block" />
          <Sparkle size={32} className="absolute bottom-24 left-12 text-violet hidden md:block animate-float" />
        </>
      }
    >
      <div className="text-center">
        <Kicker color="text-mint">{t("pitch.s4_kicker")}</Kicker>
        <h1 className="mt-8 font-display font-extrabold tracking-tight leading-[1.05] text-4xl sm:text-6xl md:text-7xl text-ink">
          {t("pitch.s4_h1")}
        </h1>
        <p className="mt-8 mx-auto max-w-3xl text-lg sm:text-xl text-ink/75 leading-relaxed">
          {t("pitch.s4_sub")}
        </p>
      </div>
    </SlideFrame>
  );
}

/* ------------------------------------------------------------------------ *
 * Slide 5 — live demo CTA                                                   *
 * ------------------------------------------------------------------------ */

function Slide5() {
  const { t } = useTranslation();
  return (
    <SlideFrame
      decoration={
        <>
          <div
            aria-hidden
            className="absolute -bottom-32 -right-24 size-[420px] rounded-full bg-violet/10 border-2 border-ink hidden md:block"
          />
          <Triangle size={48} className="absolute top-16 left-12 text-pink hidden md:block animate-float" />
        </>
      }
    >
      <Kicker color="text-violet">{t("pitch.s5_kicker")}</Kicker>
      <h1 className="mt-4 font-display font-extrabold leading-[1.05] text-4xl sm:text-6xl md:text-7xl text-ink">
        {t("pitch.s5_h1")}
      </h1>
      <p className="mt-6 max-w-3xl text-lg sm:text-xl text-ink/75 leading-relaxed">
        {t("pitch.s5_sub")}
      </p>
      <div className="mt-10 flex flex-wrap items-center gap-4">
        <StickerButton asChild tone="violet" size="xl">
          <a href="/chat" target="_blank" rel="noreferrer">
            <Sparkles className="size-5" strokeWidth={2.5} />
            {t("pitch.s5_demo_button")}
            <ArrowUpRight className="size-5" strokeWidth={2.5} />
          </a>
        </StickerButton>
      </div>
      <div className="mt-8 inline-flex items-center gap-3 rounded-2xl border-2 border-ink bg-amber/40 px-4 py-3 max-w-xl">
        <Phone className="size-5 shrink-0 text-ink" strokeWidth={2.5} />
        <p className="text-sm sm:text-base text-ink/80 leading-snug">
          {t("pitch.s5_hint")}
        </p>
      </div>
    </SlideFrame>
  );
}

/* ------------------------------------------------------------------------ *
 * Slide 6 — architecture (ELI5: 3 ingredients)                              *
 * ------------------------------------------------------------------------ */

function Slide6Eli5() {
  const { t } = useTranslation();
  const cards = [
    {
      icon: Database,
      tone: "violet" as const,
      iconBg: "bg-violet text-white",
      title: t("pitch.s6_card1_title"),
      body: t("pitch.s6_card1_body"),
    },
    {
      icon: Mic,
      tone: "pink" as const,
      iconBg: "bg-pink text-ink",
      title: t("pitch.s6_card2_title"),
      body: t("pitch.s6_card2_body"),
    },
    {
      icon: Cpu,
      tone: "mint" as const,
      iconBg: "bg-mint text-ink",
      title: t("pitch.s6_card3_title"),
      body: t("pitch.s6_card3_body"),
    },
  ];
  return (
    <SlideFrame>
      <Kicker color="text-violet">{t("pitch.s6_kicker")}</Kicker>
      <div className="mt-8 grid gap-6 md:grid-cols-3">
        {cards.map((c, i) => {
          const Icon = c.icon;
          return (
            <StickerCard
              key={c.title}
              tone={c.tone}
              tilt={i === 0 ? "left" : i === 2 ? "right" : "none"}
              className="p-6 pt-9"
            >
              <div
                className={cn(
                  "absolute -top-5 -left-3 size-12 rounded-full border-2 border-ink",
                  "shadow-[3px_3px_0_0_var(--ink)] flex items-center justify-center",
                  c.iconBg,
                )}
                aria-hidden
              >
                <Icon className="size-5" strokeWidth={2.5} />
              </div>
              <h3 className="font-display font-extrabold text-lg text-ink">
                {c.title}
              </h3>
              <p className="mt-2 text-sm text-ink/75 leading-relaxed">
                {c.body}
              </p>
            </StickerCard>
          );
        })}
      </div>
      <div className="mt-10 flex justify-center">
        <p className="inline-flex items-center gap-3 rounded-full border-2 border-ink bg-amber px-6 py-2 font-display font-extrabold text-base sm:text-lg text-ink shadow-[4px_4px_0_0_var(--ink)]">
          {t("pitch.s6_tagline")}
        </p>
      </div>
    </SlideFrame>
  );
}

/* ------------------------------------------------------------------------ *
 * Slide 6b — architecture (technical: pipeline + stack)                     *
 *                                                                           *
 * For the engineers and curious officials in the room. Numbers are the live *
 * counts from the SQLite corpus on k2 — keep them honest, update if the     *
 * crawler grows the corpus.                                                 *
 * ------------------------------------------------------------------------ */

function Slide6Tech() {
  const { t } = useTranslation();
  const steps = [
    { key: "s6b_step1", tone: "violet" as const },
    { key: "s6b_step2", tone: "pink" as const },
    { key: "s6b_step3", tone: "amber" as const },
    { key: "s6b_step4", tone: "mint" as const },
    { key: "s6b_step5", tone: "sky" as const },
  ];
  const stack = [
    { key: "s6b_stack_crawler", color: "var(--violet)" },
    { key: "s6b_stack_retrieval", color: "var(--pink)" },
    { key: "s6b_stack_composer", color: "var(--amber)" },
    { key: "s6b_stack_hardware", color: "var(--mint)" },
    { key: "s6b_stack_deploy", color: "var(--sky)" },
  ];
  return (
    <SlideFrame>
      <Kicker color="text-violet">{t("pitch.s6b_kicker")}</Kicker>
      <h1 className="mt-3 font-display font-extrabold leading-[1.1] text-2xl sm:text-3xl md:text-4xl text-ink">
        {t("pitch.s6b_h1")}
      </h1>

      <div className="mt-7 grid gap-8 lg:grid-cols-[1.05fr_1fr]">
        {/* Pipeline (request flow) */}
        <ol className="grid gap-3">
          {steps.map((s, i) => (
            <li key={s.key} className="relative flex items-start gap-3">
              <span
                className="inline-flex size-10 shrink-0 items-center justify-center rounded-full border-2 border-ink shadow-[2px_2px_0_0_var(--ink)] font-display font-extrabold text-base text-ink"
                style={{ backgroundColor: `var(--${s.tone})` }}
                aria-hidden
              >
                {i + 1}
              </span>
              <div className="flex-1 rounded-2xl border-2 border-ink bg-card px-4 py-2.5">
                <p className="font-display font-extrabold text-sm sm:text-base text-ink leading-tight">
                  {t(`pitch.${s.key}_label`)}
                </p>
                <p className="mt-0.5 text-xs sm:text-sm text-ink/75 leading-snug">
                  {t(`pitch.${s.key}_body`)}
                </p>
              </div>
            </li>
          ))}
        </ol>

        {/* Stack list */}
        <StickerCard tone="violet" className="p-5 self-start">
          <p className="text-xs uppercase tracking-widest font-display font-extrabold text-ink/65 mb-3">
            {t("pitch.s6b_stack_label")}
          </p>
          <ul className="grid gap-2.5">
            {stack.map((s) => (
              <li key={s.key} className="flex items-start gap-2.5">
                <span
                  className="mt-1.5 size-2.5 shrink-0 rounded-full border-2 border-ink"
                  style={{ backgroundColor: s.color }}
                  aria-hidden
                />
                <span className="text-xs sm:text-sm text-ink/85 leading-snug">
                  {t(`pitch.${s.key}`)}
                </span>
              </li>
            ))}
          </ul>
        </StickerCard>
      </div>

      <div className="mt-6 flex justify-center">
        <p className="inline-flex items-center gap-3 rounded-full border-2 border-ink bg-amber px-5 py-2 font-display font-extrabold text-sm sm:text-base text-ink shadow-[3px_3px_0_0_var(--ink)] text-center">
          {t("pitch.s6b_callout")}
        </p>
      </div>
    </SlideFrame>
  );
}

/* ------------------------------------------------------------------------ *
 * Slide 7 — Jiri-specific positioning                                       *
 * ------------------------------------------------------------------------ */

function Slide7() {
  const { t } = useTranslation();
  return (
    <SlideFrame>
      <Kicker color="text-mint">{t("pitch.s7_kicker")}</Kicker>
      <h1 className="mt-4 font-display font-extrabold leading-[1.05] text-3xl sm:text-5xl md:text-6xl text-ink">
        {t("pitch.s7_h1")}
      </h1>
      <p className="mt-4 max-w-3xl text-base sm:text-lg text-ink/75 leading-relaxed">
        {t("pitch.s7_body")}
      </p>
      <div className="mt-10">
        <p className="text-sm uppercase tracking-widest font-display font-extrabold text-ink/65">
          {t("pitch.s7_gap_kicker")}
        </p>
        <ul className="mt-4 grid gap-3 sm:grid-cols-2 max-w-3xl">
          {["s7_gap_1", "s7_gap_2", "s7_gap_3", "s7_gap_4"].map((k, i) => {
            const tones = ["violet", "pink", "amber", "mint"] as const;
            return (
              <li
                key={k}
                className="flex items-start gap-3 rounded-2xl border-2 border-ink bg-card p-3 shadow-[3px_3px_0_0_var(--ink)]"
              >
                <span
                  className="mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full border-2 border-ink font-display font-extrabold text-xs"
                  style={{ backgroundColor: `var(--${tones[i]})` }}
                >
                  {i + 1}
                </span>
                <span className="text-sm sm:text-base text-ink/85">
                  {t(`pitch.${k}`)}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </SlideFrame>
  );
}

/* ------------------------------------------------------------------------ *
 * Slide 8 — the ask                                                         *
 * ------------------------------------------------------------------------ */

function Slide8() {
  const { t } = useTranslation();
  return (
    <SlideFrame
      decoration={
        <BurstStar size={80} className="absolute top-12 right-8 text-amber hidden md:block animate-float" />
      }
    >
      <Kicker color="text-pink">{t("pitch.s8_kicker")}</Kicker>
      <h1 className="mt-4 font-display font-extrabold leading-[1.05] text-3xl sm:text-5xl md:text-6xl text-ink">
        {t("pitch.s8_h1")}
      </h1>
      <p className="mt-4 max-w-3xl text-base sm:text-lg text-ink/75 leading-relaxed">
        {t("pitch.s8_sub")}
      </p>
      <p className="mt-6 inline-flex items-center gap-2 rounded-full border-2 border-ink bg-pink px-5 py-2 font-display font-extrabold text-lg text-ink shadow-[4px_4px_0_0_var(--ink)]">
        {t("pitch.s8_when")}
      </p>

      <div className="mt-10">
        <p className="text-sm uppercase tracking-widest font-display font-extrabold text-ink/65">
          {t("pitch.s8_what_you_get")}
        </p>
        <ul className="mt-4 grid gap-3 max-w-2xl">
          {["s8_get_1", "s8_get_2", "s8_get_3"].map((k, i) => {
            const tones = ["mint", "amber", "violet"] as const;
            return (
              <li key={k} className="flex items-center gap-3">
                <span
                  className="inline-flex size-9 shrink-0 items-center justify-center rounded-full border-2 border-ink shadow-[2px_2px_0_0_var(--ink)] text-base font-display font-extrabold text-ink"
                  style={{ backgroundColor: `var(--${tones[i]})` }}
                >
                  ✓
                </span>
                <span className="text-base sm:text-lg text-ink/85">
                  {t(`pitch.${k}`)}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </SlideFrame>
  );
}

/* ------------------------------------------------------------------------ *
 * Slide 9 — Q&A                                                             *
 * ------------------------------------------------------------------------ */

function Slide9() {
  const { t } = useTranslation();
  return (
    <SlideFrame
      decoration={
        <>
          <BurstStar size={70} className="absolute top-20 left-12 text-amber animate-float" />
          <Triangle size={48} className="absolute top-32 right-16 text-pink animate-float" />
          <Dot size={26} className="absolute bottom-32 left-1/3 text-mint" />
          <Sparkle size={28} className="absolute bottom-20 right-1/4 text-violet animate-float" />
        </>
      }
    >
      <div className="text-center">
        <h1 className="font-display font-extrabold tracking-tight leading-[1.05] text-5xl sm:text-7xl md:text-8xl text-ink">
          {t("pitch.s9_h1")}
        </h1>
        <p className="mt-8 text-2xl sm:text-3xl font-display font-bold text-ink/70">
          {t("pitch.s9_sub")}
        </p>
        <p className="mt-12 inline-block rounded-full border-2 border-ink bg-card px-5 py-2 font-mono text-sm text-ink/80 shadow-[3px_3px_0_0_var(--ink)]">
          {t("pitch.s9_contact")}
        </p>
      </div>
    </SlideFrame>
  );
}

// referenced to silence unused-import warning when memo isn't needed
void useMemo;
