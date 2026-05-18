import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, Cpu, Mic, Search, ShieldCheck } from "lucide-react";
import { StickerButton } from "@/components/sticker/StickerButton";
import { StickerCard } from "@/components/sticker/StickerCard";
import {
  BurstStar,
  DashedConnector,
  Dot,
  Leaf,
  Sparkle,
  Squiggle,
  Triangle,
} from "@/components/sticker/decor";
import { ArchitectureSvg } from "@/components/ArchitectureSvg";

/**
 * The brand-defining page. Every section follows "Stable Grid, Wild
 * Decoration" — content blocks are predictable rectangles, but the negative
 * space around them is sprinkled with confetti shapes, dot grids, and
 * squiggles. Decoration is purely visual (aria-hidden) so screen readers
 * read the content cleanly.
 */
const STACK_KEYS = [
  "crawler",
  "retrieval",
  "composer",
  "server",
  "asr",
  "hosting",
] as const;

const STACK_TONES = [
  "violet",
  "pink",
  "amber",
  "mint",
  "sky",
  "violet",
] as const;

export function Landing() {
  const { t } = useTranslation();

  const features = [
    {
      icon: Search,
      tone: "violet" as const,
      iconBg: "bg-violet text-white",
      title: t("landing.feature_corpus_title"),
      value: t("landing.feature_corpus_value"),
      body: t("landing.feature_corpus_body"),
    },
    {
      icon: Mic,
      tone: "pink" as const,
      iconBg: "bg-pink text-ink",
      title: t("landing.feature_tacit_title"),
      value: t("landing.feature_tacit_value"),
      body: t("landing.feature_tacit_body"),
    },
    {
      icon: Cpu,
      tone: "amber" as const,
      iconBg: "bg-amber text-ink",
      title: t("landing.feature_model_title"),
      value: t("landing.feature_model_value"),
      body: t("landing.feature_model_body"),
    },
    {
      icon: ShieldCheck,
      tone: "mint" as const,
      iconBg: "bg-mint text-ink",
      title: t("landing.feature_refuse_title"),
      value: t("landing.feature_refuse_value"),
      body: t("landing.feature_refuse_body"),
    },
  ];

  const fullTitle = t("landing.title");
  const accent = t("landing.title_accent");
  const idx = fullTitle.indexOf(accent);
  const titleBefore = idx >= 0 ? fullTitle.slice(0, idx) : fullTitle;
  const titleAfter = idx >= 0 ? fullTitle.slice(idx + accent.length) : "";

  return (
    <div className="relative overflow-hidden bg-cream">
      {/* HERO ------------------------------------------------------------- */}
      <section className="relative">
        <BackgroundDots />

        {/* Big amber sticker behind the heading — the keystone of the brand */}
        <div
          aria-hidden
          className="absolute -top-32 -left-24 size-[460px] rounded-full bg-amber border-2 border-ink hidden sm:block"
        />
        <Triangle
          size={64}
          className="absolute top-24 right-12 text-pink hidden md:block animate-float"
          aria-hidden
        />
        <Dot size={28} className="absolute top-44 right-1/3 text-mint hidden md:block" />
        <Sparkle size={36} className="absolute top-10 right-1/4 text-violet hidden md:block animate-float" />

        <div className="relative mx-auto max-w-5xl px-6 pt-24 pb-20 text-center">
          <div className="inline-flex items-center gap-2 rounded-full border-2 border-ink bg-card px-4 py-1.5 text-xs font-display font-semibold shadow-[3px_3px_0_0_var(--ink)]">
            <span className="size-2 rounded-full bg-mint border border-ink" />
            live · helpdesk.ampixa.com
          </div>

          <h1 className="mt-8 font-display font-extrabold text-4xl sm:text-5xl md:text-6xl lg:text-7xl tracking-tight leading-[1.05] text-ink">
            {titleBefore}
            {idx >= 0 && (
              <span
                className="px-1"
                style={{
                  background:
                    "linear-gradient(180deg, transparent 55%, var(--pink) 55%, var(--pink) 95%, transparent 95%)",
                  // box-decoration-break makes the pen-stripe wrap cleanly to next line
                  WebkitBoxDecorationBreak: "clone",
                  boxDecorationBreak: "clone",
                }}
              >
                {accent}
              </span>
            )}
            {titleAfter}
          </h1>

          <p className="mt-6 mx-auto max-w-2xl text-base sm:text-lg text-ink/75 leading-relaxed">
            {t("landing.tagline")}
          </p>

          <div className="mt-10 flex items-center justify-center gap-4 flex-wrap">
            <StickerButton asChild tone="violet" size="lg">
              <Link to="/chat">
                {t("landing.cta_chat")}
                <span className="ml-1 inline-flex size-6 items-center justify-center rounded-full bg-cream text-ink">
                  <ArrowRight className="size-3.5" strokeWidth={2.5} />
                </span>
              </Link>
            </StickerButton>
            <StickerButton asChild tone="ghost" size="lg">
              <Link to="/interview">{t("landing.cta_contribute")}</Link>
            </StickerButton>
          </div>
        </div>
      </section>

      {/* PROBLEM ---------------------------------------------------------- */}
      <Section>
        <SectionEyebrow color="text-pink">
          {t("landing.problem_title")}
        </SectionEyebrow>
        <div className="mt-6 grid gap-4 max-w-3xl">
          <p className="text-lg text-ink/80 leading-relaxed">
            {t("landing.problem_body_1")}
          </p>
          <p className="text-lg text-ink/80 leading-relaxed">
            {t("landing.problem_body_2")}
          </p>
        </div>
        <Triangle
          size={48}
          className="absolute -top-4 right-12 text-amber hidden md:block animate-float"
        />
      </Section>

      {/* WHAT WE BUILT ---------------------------------------------------- */}
      <Section className="relative">
        <SectionEyebrow color="text-violet">
          {t("landing.what_we_built_title")}
        </SectionEyebrow>

        <div className="relative mt-12 grid gap-8 sm:grid-cols-2">
          {features.map((f, i) => {
            const Icon = f.icon;
            return (
              <StickerCard
                key={f.title}
                tone={f.tone}
                wiggle
                tilt={i % 2 === 0 ? "none" : "right"}
                className="p-6 pt-9"
              >
                {/* Icon bubble that sits half-out of the top-left corner */}
                <div
                  className={`absolute -top-5 -left-5 size-12 rounded-full border-2 border-ink shadow-[3px_3px_0_0_var(--ink)] flex items-center justify-center ${f.iconBg}`}
                  aria-hidden
                >
                  <Icon className="size-5" strokeWidth={2.5} />
                </div>
                <p className="text-xs uppercase tracking-widest font-display font-bold text-ink/60">
                  {f.title}
                </p>
                <p className="mt-2 text-3xl font-display font-extrabold text-ink">
                  {f.value}
                </p>
                <p className="mt-3 text-sm text-ink/70 leading-relaxed">
                  {f.body}
                </p>
              </StickerCard>
            );
          })}
        </div>
      </Section>

      {/* HOW IT WORKS ----------------------------------------------------- */}
      <Section className="relative">
        <SectionEyebrow color="text-amber">
          {t("landing.how_title")}
        </SectionEyebrow>

        <StickerCard tone="ink" className="mt-8 overflow-x-auto p-4 sm:p-6 bg-cream">
          <ArchitectureSvg />
        </StickerCard>

        <div className="relative mt-10 grid gap-6 md:grid-cols-3">
          <DashedConnector
            className="absolute left-1/3 top-1/2 -translate-y-1/2 text-ink/40 hidden md:block"
            width={140}
            height={20}
          />
          <DashedConnector
            className="absolute right-1/3 top-1/2 -translate-y-1/2 text-ink/40 hidden md:block"
            width={140}
            height={20}
          />
          {[
            { titleKey: "how_citizen_title", bodyKey: "how_citizen_body", tone: "violet" as const },
            { titleKey: "how_interview_title", bodyKey: "how_interview_body", tone: "pink" as const },
            { titleKey: "how_runtime_title", bodyKey: "how_runtime_body", tone: "mint" as const },
          ].map((b, i) => (
            <StickerCard
              key={b.titleKey}
              tone={b.tone}
              tilt={i === 1 ? "left" : i === 2 ? "right" : "none"}
              className="p-5"
            >
              <p className="text-xs uppercase tracking-widest font-display font-bold text-ink">
                {t(`landing.${b.titleKey}`)}
              </p>
              <p className="mt-2 text-sm text-ink/75 leading-relaxed">
                {t(`landing.${b.bodyKey}`)}
              </p>
            </StickerCard>
          ))}
        </div>
      </Section>

      {/* STACK ------------------------------------------------------------ */}
      <Section>
        <SectionEyebrow color="text-mint">{t("landing.stack_title")}</SectionEyebrow>

        <StickerCard tone="violet" className="mt-8 overflow-hidden">
          <ul className="divide-y-2 divide-ink/10">
            {STACK_KEYS.map((k, i) => (
              <li
                key={k}
                className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-6 px-6 py-5"
              >
                <div className="flex items-center gap-3 sm:min-w-44">
                  <span
                    className="inline-block size-3 rounded-full border-2 border-ink"
                    style={{
                      backgroundColor: `var(--${STACK_TONES[i]})`,
                    }}
                    aria-hidden
                  />
                  <span className="text-sm font-display font-bold text-ink uppercase tracking-wide">
                    {t(`landing.stack_${k}_label`)}
                  </span>
                </div>
                <span className="text-sm text-ink/75">
                  {t(`landing.stack_${k}_value`)}
                </span>
              </li>
            ))}
          </ul>
        </StickerCard>
      </Section>

      {/* TRY IT ----------------------------------------------------------- */}
      <Section className="relative pb-24">
        <BurstStar
          size={72}
          className="absolute -top-4 right-8 text-amber hidden md:block"
          aria-hidden
        />
        <SectionEyebrow color="text-pink">{t("landing.try_title")}</SectionEyebrow>

        <div className="mt-8 grid gap-6 sm:grid-cols-2">
          <StickerCard tone="violet" wiggle tilt="left" className="p-7 flex flex-col">
            <Sparkle size={24} className="text-violet" />
            <h3 className="mt-3 text-2xl font-display font-extrabold text-ink">
              {t("landing.try_chat_title")}
            </h3>
            <p className="mt-2 flex-1 text-sm text-ink/75 leading-relaxed">
              {t("landing.try_chat_body")}
            </p>
            <StickerButton asChild tone="violet" className="mt-5 self-start">
              <Link to="/chat">
                {t("landing.try_chat_cta")}
                <ArrowRight className="size-4" strokeWidth={2.5} />
              </Link>
            </StickerButton>
          </StickerCard>

          <StickerCard tone="pink" wiggle tilt="right" className="p-7 flex flex-col">
            <Leaf size={28} className="text-pink" />
            <h3 className="mt-3 text-2xl font-display font-extrabold text-ink">
              {t("landing.try_interview_title")}
            </h3>
            <p className="mt-2 flex-1 text-sm text-ink/75 leading-relaxed">
              {t("landing.try_interview_body")}
            </p>
            <StickerButton asChild tone="pink" className="mt-5 self-start">
              <Link to="/interview">
                {t("landing.try_interview_cta")}
                <ArrowRight className="size-4" strokeWidth={2.5} />
              </Link>
            </StickerButton>
          </StickerCard>
        </div>
      </Section>

      <footer className="border-t-2 border-ink bg-amber/30 py-10">
        <div className="mx-auto max-w-5xl px-6 flex flex-col items-center gap-3">
          <Squiggle size={140} className="text-ink" />
          <p className="text-center text-base sm:text-lg font-display font-extrabold text-ink">
            {t("landing.footer_tagline")}
          </p>
          <p className="text-center text-sm text-ink/65">
            {t("landing.footer_help")}
          </p>
        </div>
      </footer>
    </div>
  );
}

/** Centered max-width section with breathing room. */
function Section({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`relative mx-auto max-w-5xl px-6 py-20 ${className}`}>
      {children}
    </section>
  );
}

/** Heading with a colored squiggle underline. */
function SectionEyebrow({
  children,
  color,
}: {
  children: React.ReactNode;
  color: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight text-ink">
        {children}
      </h2>
      <Squiggle size={84} className={color} />
    </div>
  );
}

/** Subtle dot wash on light cream paper. */
function BackgroundDots() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 dot-grid-soft opacity-90"
    />
  );
}
