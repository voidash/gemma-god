import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  FileText,
  MessageCircle,
  Mic,
  Phone,
  Send,
  Sparkles,
} from "lucide-react";
import { StickerButton } from "@/components/sticker/StickerButton";
import { StickerCard } from "@/components/sticker/StickerCard";
import { Sparkle, Squiggle } from "@/components/sticker/decor";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  postQuery,
  postQueryStream,
  type ChatHistoryTurn,
  type QueryResponse,
  type QuerySource,
  type QueryStreamMeta,
} from "@/lib/api";

type ChatMessage =
  | { kind: "user"; text: string }
  | { kind: "ai"; data: QueryResponse; id?: string; streaming?: boolean }
  | { kind: "error"; text: string };

const INLINE_MARKDOWN_RE =
  /\[(https?:\/\/[^\]\s]+)\]|(https?:\/\/[^\s<]+[^\s<.,;:!?])|`([^`]+)`|\*\*([^*]+)\*\*/g;

function renderInlineAnswer(text: string, keyPrefix: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  INLINE_MARKDOWN_RE.lastIndex = 0;
  while ((m = INLINE_MARKDOWN_RE.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const bracketedUrl = m[1];
    const bareUrl = m[2];
    const code = m[3];
    const strong = m[4];
    if (bracketedUrl || bareUrl) {
      const url = bracketedUrl || bareUrl;
      const label = bracketedUrl ? `[${bracketedUrl}]` : bareUrl;
      parts.push(
        <a
          key={`${keyPrefix}-u-${i++}`}
          href={url}
          target="_blank"
          rel="noreferrer"
          className="font-display font-semibold text-violet underline decoration-2 underline-offset-2 hover:text-pink break-all"
        >
          {label}
        </a>,
      );
    } else if (code) {
      parts.push(
        <code
          key={`${keyPrefix}-c-${i++}`}
          className="rounded bg-ink/10 px-1 py-0.5 font-mono text-[0.92em]"
        >
          {code}
        </code>,
      );
    } else if (strong) {
      parts.push(
        <strong key={`${keyPrefix}-b-${i++}`} className="font-bold">
          {strong}
        </strong>,
      );
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function renderAnswer(text: string): ReactNode[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const out: ReactNode[] = [];
  let paragraph: string[] = [];
  let listType: "ul" | "ol" | null = null;
  let listItems: string[] = [];
  let block = 0;

  function flushParagraph() {
    if (!paragraph.length) return;
    const key = `p-${block++}`;
    out.push(
      <p key={key} className="mb-3 last:mb-0">
        {paragraph.flatMap((line, i) => [
          i > 0 ? <br key={`${key}-br-${i}`} /> : null,
          ...renderInlineAnswer(line, `${key}-${i}`),
        ])}
      </p>,
    );
    paragraph = [];
  }

  function flushList() {
    if (!listType) return;
    const key = `l-${block++}`;
    const items = listItems.map((item, i) => (
      <li key={`${key}-${i}`}>{renderInlineAnswer(item, `${key}-${i}`)}</li>
    ));
    out.push(
      listType === "ul" ? (
        <ul key={key} className="mb-3 ml-5 list-disc space-y-1 last:mb-0">
          {items}
        </ul>
      ) : (
        <ol key={key} className="mb-3 ml-5 list-decimal space-y-1 last:mb-0">
          {items}
        </ol>
      ),
    );
    listType = null;
    listItems = [];
  }

  for (const line of lines) {
    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }
    const bullet = line.match(/^\s*[-*]\s+(.+)$/);
    const numbered = line.match(/^\s*\d+\.\s+(.+)$/);
    if (bullet || numbered) {
      flushParagraph();
      const nextType = bullet ? "ul" : "ol";
      if (listType && listType !== nextType) flushList();
      listType = nextType;
      listItems.push((bullet || numbered)?.[1] || "");
      continue;
    }
    flushList();
    paragraph.push(line);
  }
  flushParagraph();
  flushList();
  return out;
}

function emptyQueryResponse(patch: Partial<QueryResponse> = {}): QueryResponse {
  const latency = { retrieval: 0, generation: 0, total: 0, ...patch.latency_ms };
  return {
    answer: "",
    citations: [],
    sources: [],
    did_refuse: false,
    retrieved_tacit: 0,
    retrieved_gov: 0,
    detected_lang: "",
    ...patch,
    latency_ms: latency,
  };
}

function buildRequestHistory(messages: ChatMessage[]): ChatHistoryTurn[] {
  return messages
    .filter((m) => !(m.kind === "ai" && m.streaming))
    .flatMap((m): ChatHistoryTurn[] => {
      if (m.kind === "user") {
        return [{ role: "user", content: m.text.slice(0, 400) }];
      }
      if (m.kind === "ai" && m.data.answer) {
        return [{ role: "assistant", content: m.data.answer.slice(0, 700) }];
      }
      return [];
    })
    .slice(-6);
}

function normalizeSourceUrl(url?: string | null) {
  return (url || "").split("#", 1)[0].replace(/\/+$/, "");
}

function citedSources(resp: QueryResponse): QuerySource[] {
  if (!resp.citations.length) return [];
  const byRank = new Map(resp.sources.map((s) => [s.rank, s]));
  const out: QuerySource[] = [];
  const seen = new Set<string>();
  for (const citation of resp.citations) {
    const source =
      byRank.get(citation.rank) ||
      resp.sources.find(
        (s) => normalizeSourceUrl(s.url) === normalizeSourceUrl(citation.url),
      );
    if (!source) continue;
    const key = `${source.rank}:${normalizeSourceUrl(citation.url || source.url)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({
      ...source,
      url: citation.url || source.url,
      snippet: citation.snippet || source.snippet,
    });
  }
  return out;
}

export function Chat() {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const stickToBottomRef = useRef(true);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (scroller && stickToBottomRef.current) {
      scroller.scrollTop = scroller.scrollHeight;
    }
  }, [messages, loading]);

  function handleScroll() {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const distanceFromBottom =
      scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
    stickToBottomRef.current = distanceFromBottom < 96;
  }

  async function send(question: string) {
    if (!question.trim() || loading) return;
    const history = buildRequestHistory(messages);
    stickToBottomRef.current = true;
    setMessages((prev) => [...prev, { kind: "user", text: question }]);
    setInput("");
    setLoading(true);
    const streamId =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random()}`;
    let streamInserted = false;

    const upsertStream = (patch: Partial<QueryResponse>) => {
      streamInserted = true;
      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.kind === "ai" && m.id === streamId);
        const base =
          idx >= 0 && prev[idx].kind === "ai"
            ? prev[idx].data
            : emptyQueryResponse();
        const nextData = emptyQueryResponse({
          ...base,
          ...patch,
          latency_ms: {
            ...base.latency_ms,
            ...patch.latency_ms,
          },
        });
        const nextMsg: ChatMessage = {
          kind: "ai",
          id: streamId,
          streaming: true,
          data: nextData,
        };
        if (idx < 0) return [...prev, nextMsg];
        const next = [...prev];
        next[idx] = nextMsg;
        return next;
      });
    };

    const appendStreamText = (text: string) => {
      if (!text) return;
      streamInserted = true;
      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.kind === "ai" && m.id === streamId);
        const base =
          idx >= 0 && prev[idx].kind === "ai"
            ? prev[idx].data
            : emptyQueryResponse();
        const nextMsg: ChatMessage = {
          kind: "ai",
          id: streamId,
          streaming: true,
          data: emptyQueryResponse({
            ...base,
            answer: `${base.answer}${text}`,
          }),
        };
        if (idx < 0) return [...prev, nextMsg];
        const next = [...prev];
        next[idx] = nextMsg;
        return next;
      });
    };

    const finalizeStream = (data: QueryResponse) => {
      streamInserted = true;
      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.kind === "ai" && m.id === streamId);
        const nextMsg: ChatMessage = { kind: "ai", id: streamId, data };
        if (idx < 0) return [...prev, nextMsg];
        const next = [...prev];
        next[idx] = nextMsg;
        return next;
      });
    };

    const removeStream = () => {
      if (!streamInserted) return;
      setMessages((prev) =>
        prev.filter((m) => !(m.kind === "ai" && m.id === streamId)),
      );
    };

    try {
      await postQueryStream(question, history, {
        onMeta: (meta: QueryStreamMeta) =>
          upsertStream({
            retrieved_tacit: meta.retrieved_tacit,
            retrieved_gov: meta.retrieved_gov,
            detected_lang: meta.detected_lang,
            latency_ms: {
              retrieval: meta.latency_ms.retrieval,
              generation: 0,
              total: 0,
            },
          }),
        onToken: appendStreamText,
        onFinal: finalizeStream,
      });
    } catch (e) {
      removeStream();
      try {
        const data = await postQuery(question, history);
        setMessages((prev) => [...prev, { kind: "ai", data }]);
      } catch (fallbackError) {
        const msg =
          fallbackError instanceof Error
            ? fallbackError.message
            : String(fallbackError);
        setMessages((prev) => [...prev, { kind: "error", text: msg }]);
      }
    } finally {
      setLoading(false);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    void send(input);
  }
  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send(input);
    }
  }

  const hasStreamingAnswer = messages.some((m) => m.kind === "ai" && m.streaming);

  return (
    <div className="flex flex-col h-[calc(100svh-4rem)] bg-cream">
      <SubHeader />

      <div
        ref={scrollerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
      >
        <div className="mx-auto max-w-3xl px-4 sm:px-6 py-8 flex flex-col gap-6">
          {messages.length === 0 && !loading && (
            <EmptyState
              onPick={(q) => void send(q)}
              examples={[
                t("chat.example_1"),
                t("chat.example_2"),
                t("chat.example_3"),
              ]}
              title={t("chat.empty_title")}
              body={t("chat.empty_body")}
              examplesTitle={t("chat.empty_examples_title")}
            />
          )}

          {messages.map((m, i) => {
            if (m.kind === "user") return <UserBubble key={i} text={m.text} />;
            if (m.kind === "error")
              return (
                <StickerCard
                  key={i}
                  tone="ink"
                  className="border-destructive bg-destructive/5 p-4"
                >
                  <p className="text-sm text-destructive font-medium">
                    {t("chat.error_prefix")}: {m.text}
                  </p>
                </StickerCard>
              );
            return <AiBubble key={i} resp={m.data} streaming={m.streaming} />;
          })}

          {loading && !hasStreamingAnswer && <ThinkingBubble label={t("chat.thinking")} />}
        </div>
      </div>

      <div className="border-t-2 border-ink bg-cream/95">
        <form
          onSubmit={onSubmit}
          className="mx-auto max-w-3xl px-4 sm:px-6 py-4 flex items-end gap-3"
        >
          <Textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={t("chat.placeholder")}
            rows={1}
            disabled={loading}
            className={cn(
              "min-h-12 max-h-40 resize-none flex-1",
              "rounded-2xl border-2 border-ink bg-card text-base",
              "shadow-[3px_3px_0_0_var(--ink)]",
              "focus-visible:border-violet focus-visible:ring-0 focus-visible:shadow-[3px_3px_0_0_var(--violet)]",
            )}
          />
          <StickerButton
            type="submit"
            tone="violet"
            size="icon"
            disabled={loading || !input.trim()}
            aria-label={t("chat.send")}
            title={t("chat.send")}
          >
            <Send className="size-5" strokeWidth={2.5} />
          </StickerButton>
        </form>
      </div>
    </div>
  );
}

function SubHeader() {
  const { t } = useTranslation();
  return (
    <div className="border-b-2 border-ink bg-cream relative overflow-hidden">
      <div
        aria-hidden
        className="absolute inset-0 dot-grid-soft opacity-60"
      />
      <div className="relative mx-auto max-w-3xl px-4 sm:px-6 py-5 flex items-center gap-3">
        <span className="inline-flex size-9 items-center justify-center rounded-full border-2 border-ink bg-violet text-white shadow-[2px_2px_0_0_var(--ink)]">
          <MessageCircle className="size-4" strokeWidth={2.5} />
        </span>
        <div>
          <h1 className="font-display font-extrabold text-lg leading-tight text-ink">
            {t("chat.title")}
          </h1>
          <p className="text-xs text-ink/60">{t("chat.subtitle")}</p>
        </div>
      </div>
    </div>
  );
}

function EmptyState({
  title,
  body,
  examples,
  examplesTitle,
  onPick,
}: {
  title: string;
  body: string;
  examples: string[];
  examplesTitle: string;
  onPick: (q: string) => void;
}) {
  return (
    <div className="flex flex-col items-center text-center pt-6 animate-pop-in">
      <div className="relative">
        <div
          aria-hidden
          className="absolute -inset-4 rounded-full bg-amber/40 -z-10"
        />
        <div className="flex size-16 items-center justify-center rounded-full border-2 border-ink bg-violet text-white shadow-[3px_3px_0_0_var(--ink)]">
          <Sparkles className="size-7" strokeWidth={2.5} />
        </div>
      </div>
      <h2 className="mt-6 text-3xl sm:text-4xl font-display font-extrabold tracking-tight text-ink">
        {title}
      </h2>
      <Squiggle size={100} className="mt-2 text-pink" />
      <p className="mt-3 max-w-md text-sm text-ink/75 leading-relaxed">
        {body}
      </p>
      <div className="mt-8 w-full max-w-xl">
        <div className="text-xs uppercase tracking-widest font-display font-bold text-ink/55 mb-3">
          {examplesTitle}
        </div>
        <div className="flex flex-col gap-3">
          {examples.map((q, i) => {
            const tones = ["mint", "amber", "pink"] as const;
            return (
              <button
                key={i}
                onClick={() => onPick(q)}
                className={cn(
                  "group text-left rounded-2xl border-2 border-ink bg-card",
                  "px-4 py-3.5 text-sm text-ink font-medium",
                  "shadow-[4px_4px_0_0_var(--ink)] transition-all duration-200",
                  "ease-[cubic-bezier(0.34,1.56,0.64,1)]",
                  "hover:-translate-x-0.5 hover:-translate-y-0.5",
                  "hover:shadow-[6px_6px_0_0_var(--" + tones[i] + ")]",
                  "motion-reduce:hover:transform-none",
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <span>{q}</span>
                  <ArrowRight
                    className="size-4 shrink-0 text-ink/50 group-hover:text-ink"
                    strokeWidth={2.5}
                  />
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end animate-pop-in">
      <div className="max-w-[85%] rounded-2xl rounded-br-none border-2 border-ink bg-violet text-white px-5 py-3 text-sm font-medium leading-relaxed whitespace-pre-wrap break-words shadow-[4px_4px_0_0_var(--ink)]">
        {text}
      </div>
    </div>
  );
}

function ThinkingBubble({ label }: { label: string }) {
  return (
    <div className="flex flex-col gap-3 max-w-[85%] animate-pop-in">
      <div className="flex items-center gap-2 text-sm text-ink/70 font-display font-semibold">
        <span className="size-2.5 rounded-full bg-pink border border-ink animate-pulse" />
        <span>{label}</span>
      </div>
      <Skeleton className="h-4 w-[60%] rounded-full" />
      <Skeleton className="h-4 w-[80%] rounded-full" />
      <Skeleton className="h-4 w-[40%] rounded-full" />
    </div>
  );
}

function AiBubble({
  resp,
  streaming = false,
}: {
  resp: QueryResponse;
  streaming?: boolean;
}) {
  const { t } = useTranslation();
  const displaySources = streaming ? [] : citedSources(resp);
  return (
    <StickerCard tone="soft" className="p-5 sm:p-6 animate-pop-in">
      <div className="text-base leading-relaxed break-words text-ink">
        {resp.answer ? (
          renderAnswer(resp.answer)
        ) : streaming ? (
          <p className="text-ink/55">{t("chat.thinking")}</p>
        ) : null}
      </div>

      {resp.did_refuse && (
        <a
          href="tel:1111"
          className={cn(
            "mt-4 inline-flex items-center gap-2 rounded-full border-2 border-ink",
            "bg-amber px-4 py-2 text-sm font-display font-bold text-ink",
            "shadow-[3px_3px_0_0_var(--ink)] transition-all duration-200",
            "ease-[cubic-bezier(0.34,1.56,0.64,1)]",
            "hover:-translate-y-0.5 hover:shadow-[5px_5px_0_0_var(--ink)]",
            "motion-reduce:hover:transform-none",
          )}
        >
          <Phone className="size-4" strokeWidth={2.5} />
          {t("chat.refusal_cta")}
        </a>
      )}

      {displaySources.length > 0 && (
        <div className="mt-5 pt-5 border-t-2 border-dashed border-ink/15">
          <div className="flex items-center gap-2 mb-3">
            <Sparkle size={16} className="text-pink" />
            <p className="text-xs uppercase tracking-widest font-display font-bold text-ink/55">
              {t("chat.sources_label")}
            </p>
          </div>
          <div className="flex flex-col gap-3">
            {displaySources.map((s) => (
              <SourceCard key={s.rank} source={s} />
            ))}
          </div>
        </div>
      )}

      <div className="mt-5 pt-3 border-t-2 border-dashed border-ink/15 text-[11px] text-ink/55 font-mono">
        {resp.detected_lang || "language pending"} ·{" "}
        {streaming ? "streaming" : `${resp.latency_ms.total} ${t("chat.footer_latency")}`} ·{" "}
        {t("chat.footer_sources", {
          tacit: resp.retrieved_tacit,
          gov: resp.retrieved_gov,
        })}
      </div>
    </StickerCard>
  );
}

function SourceCard({ source }: { source: QuerySource }) {
  const { t } = useTranslation();
  const isTacit = source.is_tacit;
  return (
    <div
      className={cn(
        "relative rounded-xl border-2 border-ink p-3 pl-12",
        isTacit ? "bg-mint/15" : "bg-sky/10",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "absolute left-3 top-3 inline-flex size-7 items-center justify-center rounded-full border-2 border-ink",
          isTacit ? "bg-mint text-ink" : "bg-sky text-ink",
        )}
      >
        {isTacit ? (
          <Mic className="size-3.5" strokeWidth={2.5} />
        ) : (
          <FileText className="size-3.5" strokeWidth={2.5} />
        )}
      </span>
      <div className="flex items-center gap-2 flex-wrap">
        <span
          className={cn(
            "inline-flex items-center rounded-full border-2 border-ink px-2 py-0.5",
            "text-[10px] font-display font-bold uppercase tracking-wider",
            isTacit ? "bg-mint" : "bg-sky",
            "text-ink",
          )}
        >
          {isTacit ? t("chat.tag_tacit") : t("chat.tag_gov")}
        </span>
        <span className="text-[10px] text-ink/55 uppercase tracking-wider font-display font-semibold">
          {source.source_ref || `S${source.rank}`}
        </span>
        {source.confidence && (
          <span className="text-[10px] text-ink/55 uppercase tracking-wider font-display font-semibold">
            {source.confidence}
          </span>
        )}
        {source.interviewee_role && (
          <span className="text-[11px] text-ink/65 truncate">
            {source.interviewee_role}
          </span>
        )}
      </div>
      <p className="mt-1.5 text-sm text-ink/85 leading-relaxed">
        {source.snippet}
      </p>
      {!isTacit && source.url && (
        <a
          href={source.url}
          target="_blank"
          rel="noreferrer"
          className="mt-2 block text-[11px] text-violet font-mono truncate hover:text-pink"
        >
          {source.url}
        </a>
      )}
    </div>
  );
}
