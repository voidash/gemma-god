import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  ChevronDown,
  ChevronRight,
  LogOut,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { StickerButton } from "@/components/sticker/StickerButton";
import { StickerCard } from "@/components/sticker/StickerCard";
import { Squiggle } from "@/components/sticker/decor";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import {
  AdminAuthError,
  adminApprove,
  adminAudioUrl,
  adminPhotoUrl,
  adminReject,
  clearAdminCreds,
  getAdminSubmission,
  hasAdminCreds,
  listAdminSubmissions,
  setAdminCreds,
  type Submission,
} from "@/lib/api";

type Filter = "all" | "pending" | "approved" | "rejected";

export function Admin() {
  const [authed, setAuthed] = useState(hasAdminCreds());
  if (!authed) return <AdminLogin onSuccess={() => setAuthed(true)} />;
  return <AdminDashboard onSignOut={() => setAuthed(false)} />;
}

function AdminLogin({ onSuccess }: { onSuccess: () => void }) {
  const { t } = useTranslation();
  const [user, setUser] = useState("admin");
  const [pass, setPass] = useState("");
  const [busy, setBusy] = useState(false);

  async function go(e: React.FormEvent) {
    e.preventDefault();
    if (!user || !pass) return;
    setBusy(true);
    setAdminCreds(user, pass);
    try {
      await listAdminSubmissions();
      onSuccess();
    } catch (err) {
      clearAdminCreds();
      toast.error(
        err instanceof AdminAuthError
          ? t("admin.sign_in_failed")
          : err instanceof Error
            ? err.message
            : String(err),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md px-4 py-20">
      <StickerCard tone="violet" className="p-8">
        <div className="flex items-center gap-3">
          <span className="inline-flex size-10 items-center justify-center rounded-full border-2 border-ink bg-violet text-white shadow-[2px_2px_0_0_var(--ink)]">
            <ShieldCheck className="size-5" strokeWidth={2.5} />
          </span>
          <div>
            <h1 className="font-display font-extrabold text-xl text-ink leading-tight">
              {t("admin.login_title")}
            </h1>
            <Squiggle size={64} className="text-pink mt-1" />
          </div>
        </div>
        <p className="mt-3 text-sm text-ink/70">{t("admin.login_body")}</p>
        <form onSubmit={go} className="mt-6 grid gap-4">
          <div className="grid gap-2">
            <Label
              htmlFor="adm-user"
              className="text-xs uppercase tracking-widest font-display font-bold text-ink/65"
            >
              {t("admin.username")}
            </Label>
            <Input
              id="adm-user"
              value={user}
              onChange={(e) => setUser(e.target.value)}
              autoComplete="username"
              className="h-11 rounded-xl border-2 border-ink bg-card shadow-[3px_3px_0_0_var(--ink)] focus-visible:border-violet focus-visible:ring-0 focus-visible:shadow-[3px_3px_0_0_var(--violet)]"
            />
          </div>
          <div className="grid gap-2">
            <Label
              htmlFor="adm-pass"
              className="text-xs uppercase tracking-widest font-display font-bold text-ink/65"
            >
              {t("admin.password")}
            </Label>
            <Input
              id="adm-pass"
              type="password"
              value={pass}
              onChange={(e) => setPass(e.target.value)}
              autoComplete="current-password"
              required
              className="h-11 rounded-xl border-2 border-ink bg-card shadow-[3px_3px_0_0_var(--ink)] focus-visible:border-violet focus-visible:ring-0 focus-visible:shadow-[3px_3px_0_0_var(--violet)]"
            />
          </div>
          <StickerButton type="submit" tone="violet" size="lg" disabled={busy}>
            {busy ? t("common.loading") : t("admin.sign_in")}
          </StickerButton>
        </form>
      </StickerCard>
    </div>
  );
}

function AdminDashboard({ onSignOut }: { onSignOut: () => void }) {
  const { t } = useTranslation();
  const [items, setItems] = useState<Submission[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  async function load() {
    setError(null);
    try {
      const data = await listAdminSubmissions();
      setItems(data.submissions);
    } catch (err) {
      if (err instanceof AdminAuthError) {
        clearAdminCreds();
        onSignOut();
        return;
      }
      setError(err instanceof Error ? err.message : String(err));
    }
  }
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    if (!items) return [];
    return filter === "all" ? items : items.filter((s) => s.status === filter);
  }, [items, filter]);

  const counts = useMemo(() => {
    const c = { all: 0, pending: 0, approved: 0, rejected: 0 };
    if (items) {
      c.all = items.length;
      for (const s of items) c[s.status] = (c[s.status] || 0) + 1;
    }
    return c;
  }, [items]);

  function onSignOutClick() {
    clearAdminCreds();
    onSignOut();
  }

  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-6 py-8">
      <header className="flex flex-wrap items-end gap-3 mb-8">
        <div className="flex-1">
          <h1 className="font-display font-extrabold text-3xl tracking-tight text-ink">
            {t("admin.title")}
          </h1>
          <Squiggle size={88} className="text-pink mt-1" />
          <p className="mt-2 text-sm text-ink/65">{t("admin.subtitle")}</p>
        </div>
        <div className="flex gap-2">
          <StickerButton tone="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className="size-4" strokeWidth={2.5} />
            {t("admin.refresh")}
          </StickerButton>
          <StickerButton tone="ghost" size="sm" onClick={onSignOutClick}>
            <LogOut className="size-4" strokeWidth={2.5} />
            {t("admin.sign_out")}
          </StickerButton>
        </div>
      </header>

      <div className="mb-6 flex flex-wrap gap-2">
        {(["all", "pending", "approved", "rejected"] as const).map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => setFilter(k)}
            className={cn(
              "inline-flex items-center gap-2 h-9 px-4 rounded-full border-2 border-ink",
              "text-sm font-display font-bold transition-all duration-200",
              "ease-[cubic-bezier(0.34,1.56,0.64,1)]",
              filter === k
                ? "bg-ink text-cream shadow-[3px_3px_0_0_var(--violet)]"
                : "bg-card text-ink hover:bg-amber/30 hover:-translate-y-0.5 hover:shadow-[3px_3px_0_0_var(--ink)] motion-reduce:hover:transform-none",
            )}
          >
            {t(`admin.${k}`)}
            <span
              className={cn(
                "inline-flex items-center justify-center min-w-5 h-5 px-1.5 rounded-full",
                "text-[10px] font-display font-extrabold",
                filter === k ? "bg-cream text-ink" : "bg-secondary text-ink/70",
              )}
            >
              {counts[k]}
            </span>
          </button>
        ))}
      </div>

      {items === null && !error && (
        <div className="grid gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16 rounded-2xl border-2 border-ink/15" />
          ))}
        </div>
      )}

      {error && (
        <StickerCard tone="ink" className="border-destructive bg-destructive/5 p-4">
          <p className="text-sm text-destructive font-medium">
            {t("admin.load_failed")}: {error}
          </p>
        </StickerCard>
      )}

      {items !== null && filtered.length === 0 && !error && (
        <StickerCard tone="soft" className="p-12 text-center">
          <p className="text-sm text-ink/55">
            {filter === "all" ? t("admin.empty_all") : t("admin.empty_filter")}
          </p>
        </StickerCard>
      )}

      <div className="grid gap-3">
        {filtered.map((s) => (
          <SubmissionRow key={s.id} sub={s} onChanged={() => void load()} />
        ))}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: Submission["status"] }) {
  const { t } = useTranslation();
  const cls =
    status === "pending"
      ? "bg-amber text-ink"
      : status === "approved"
        ? "bg-mint text-ink"
        : "bg-secondary text-ink/65";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border-2 border-ink px-3 py-0.5",
        "text-[10px] font-display font-extrabold uppercase tracking-wider",
        cls,
      )}
    >
      {t(`admin.${status}`)}
    </span>
  );
}

function SubmissionRow({
  sub,
  onChanged,
}: {
  sub: Submission;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<Submission | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [actionState, setActionState] = useState<
    | { kind: "idle" }
    | { kind: "confirm"; action: "approve" | "reject" }
    | { kind: "running"; action: "approve" | "reject" }
  >({ kind: "idle" });

  async function toggle() {
    if (expanded) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    if (!detail) {
      setLoadingDetail(true);
      try {
        setDetail(await getAdminSubmission(sub.id));
      } catch (err) {
        toast.error(err instanceof Error ? err.message : String(err));
      } finally {
        setLoadingDetail(false);
      }
    }
  }

  async function runAction() {
    if (actionState.kind !== "confirm") return;
    const a = actionState.action;
    setActionState({ kind: "running", action: a });
    try {
      if (a === "approve") {
        const res = await adminApprove(sub.id);
        const errs = Object.keys(res.transcribe_errors || {}).length;
        if (errs) {
          toast.warning(
            t("admin.approve_partial", { claims: res.claims, errors: errs }),
          );
        } else {
          toast.success(t("admin.approve_success", { claims: res.claims }));
        }
      } else {
        await adminReject(sub.id);
        toast.success(t("admin.reject_success"));
      }
      onChanged();
      setExpanded(false);
      setDetail(null);
      setActionState({ kind: "idle" });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
      setActionState({ kind: "idle" });
    }
  }

  return (
    <StickerCard tone="soft" className="overflow-hidden">
      <button
        type="button"
        onClick={() => void toggle()}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-amber/15 transition-colors"
      >
        {expanded ? (
          <ChevronDown
            className="size-4 text-ink/55 shrink-0"
            strokeWidth={2.5}
          />
        ) : (
          <ChevronRight
            className="size-4 text-ink/55 shrink-0"
            strokeWidth={2.5}
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-display font-bold text-ink truncate">
              {sub.name}
            </span>
            <span className="text-sm text-ink/60 truncate">{sub.office}</span>
          </div>
        </div>
        <span className="text-xs text-ink/55 font-mono shrink-0">
          🎤 {sub.audio?.length ?? 0} · 📷 {sub.photos?.length ?? 0}
        </span>
        <span className="text-xs text-ink/55 shrink-0 hidden sm:inline">
          {timeAgo(sub.submitted_at)}
        </span>
        <StatusBadge status={sub.status} />
      </button>

      {expanded && (
        <div className="px-4 pb-5 pt-0">
          <div className="border-t-2 border-dashed border-ink/15 mb-4" />

          {loadingDetail && (
            <div className="grid gap-3">
              <Skeleton className="h-16 rounded-xl" />
              <Skeleton className="h-16 rounded-xl" />
            </div>
          )}

          {detail && (
            <div className="flex flex-col gap-5">
              <div className="text-xs text-ink/55 font-mono">
                {t("admin.submission_meta", {
                  id: detail.id,
                  ip: detail.ip || "-",
                })}{" "}
                · {detail.submitted_at}
              </div>

              <div>
                <p className="mb-2 text-xs uppercase tracking-widest font-display font-bold text-ink/55">
                  {t("admin.audio_label")}
                </p>
                <div className="grid gap-3">
                  {(detail.audio || []).map((a) => (
                    <AudioCard
                      key={a.filename}
                      submissionId={detail.id}
                      filename={a.filename}
                      questionId={a.question_id}
                      bytes={a.bytes}
                      transcript={detail.transcripts?.[a.question_id]}
                    />
                  ))}
                </div>
              </div>

              {(detail.photos || []).length > 0 && (
                <div>
                  <p className="mb-2 text-xs uppercase tracking-widest font-display font-bold text-ink/55">
                    {t("admin.photos_label")}
                  </p>
                  <div className="flex flex-wrap gap-3">
                    {detail.photos!.map((p) => (
                      <PhotoThumb
                        key={p.filename}
                        submissionId={detail.id}
                        filename={p.filename}
                      />
                    ))}
                  </div>
                </div>
              )}

              {detail.status === "pending" && (
                <div className="flex flex-wrap gap-3 pt-2">
                  <StickerButton
                    type="button"
                    tone="mint"
                    onClick={() =>
                      setActionState({ kind: "confirm", action: "approve" })
                    }
                    disabled={actionState.kind === "running"}
                  >
                    <Check className="size-4" strokeWidth={2.5} />
                    {t("admin.approve_action")}
                  </StickerButton>
                  <StickerButton
                    type="button"
                    tone="pink"
                    onClick={() =>
                      setActionState({ kind: "confirm", action: "reject" })
                    }
                    disabled={actionState.kind === "running"}
                  >
                    <X className="size-4" strokeWidth={2.5} />
                    {t("admin.reject_action")}
                  </StickerButton>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <Dialog
        open={
          actionState.kind === "confirm" || actionState.kind === "running"
        }
        onOpenChange={(o) => {
          if (!o && actionState.kind === "confirm")
            setActionState({ kind: "idle" });
        }}
      >
        <DialogContent className="border-2 border-ink rounded-2xl shadow-[6px_6px_0_0_var(--ink)] bg-card">
          <DialogHeader>
            <DialogTitle className="font-display font-extrabold text-2xl">
              {actionState.kind !== "idle" && actionState.action === "approve"
                ? t("admin.approve_confirm_title")
                : t("admin.reject_confirm_title")}
            </DialogTitle>
            <DialogDescription className="text-ink/65">
              {actionState.kind !== "idle" && actionState.action === "approve"
                ? t("admin.approve_confirm_body")
                : t("admin.reject_confirm_body")}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <StickerButton
              type="button"
              tone="ghost"
              disabled={actionState.kind === "running"}
              onClick={() => setActionState({ kind: "idle" })}
            >
              {t("common.cancel")}
            </StickerButton>
            <StickerButton
              type="button"
              tone={
                actionState.kind !== "idle" && actionState.action === "approve"
                  ? "mint"
                  : "pink"
              }
              onClick={() => void runAction()}
              disabled={actionState.kind === "running"}
            >
              {actionState.kind === "running"
                ? actionState.action === "approve"
                  ? t("admin.transcribing")
                  : t("admin.rejecting")
                : actionState.kind === "confirm" &&
                    actionState.action === "approve"
                  ? t("admin.approve_action")
                  : t("admin.reject_action")}
            </StickerButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </StickerCard>
  );
}

function AudioCard({
  submissionId,
  filename,
  questionId,
  bytes,
  transcript,
}: {
  submissionId: string;
  filename: string;
  questionId: string;
  bytes?: number;
  transcript?: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="rounded-xl border-2 border-ink bg-cream p-3">
      <div className="text-xs text-ink/60 font-mono mb-2">
        {questionId} {bytes ? `· ${Math.round(bytes / 1024)} KB` : ""}
      </div>
      <AuthedAudio src={adminAudioUrl(submissionId, filename)} />
      {transcript ? (
        <div className="mt-3 text-sm bg-card border-l-4 border-mint px-3 py-2 rounded-r-lg">
          {transcript}
        </div>
      ) : (
        <p className="mt-2 text-xs text-ink/45 italic">
          {t("admin.no_transcripts")}
        </p>
      )}
    </div>
  );
}

function AuthedAudio({ src }: { src: string }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    let cancelled = false;
    let createdUrl: string | null = null;
    fetch(src, {
      headers: {
        Authorization: `Basic ${localStorage.getItem("helpdesk.admin.b64") || ""}`,
      },
    })
      .then((r) => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.blob();
      })
      .then((b) => {
        if (cancelled) return;
        createdUrl = URL.createObjectURL(b);
        setBlobUrl(createdUrl);
      })
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [src]);

  if (error)
    return <p className="text-xs text-destructive">audio failed: {error}</p>;
  if (!blobUrl) return <Skeleton className="h-9 w-full rounded-lg" />;
  return (
    <audio ref={audioRef} src={blobUrl} controls className="w-full h-9" />
  );
}

function PhotoThumb({
  submissionId,
  filename,
}: {
  submissionId: string;
  filename: string;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    let url: string | null = null;
    fetch(adminPhotoUrl(submissionId, filename), {
      headers: {
        Authorization: `Basic ${localStorage.getItem("helpdesk.admin.b64") || ""}`,
      },
    })
      .then((r) => (r.ok ? r.blob() : Promise.reject("HTTP " + r.status)))
      .then((b) => {
        if (cancelled) return;
        url = URL.createObjectURL(b);
        setBlobUrl(url);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [submissionId, filename]);
  if (!blobUrl)
    return <Skeleton className="size-24 rounded-xl border-2 border-ink/15" />;
  return (
    <a href={blobUrl} target="_blank" rel="noreferrer">
      <img
        src={blobUrl}
        alt=""
        className="size-24 rounded-xl object-cover border-2 border-ink shadow-[3px_3px_0_0_var(--ink)]"
      />
    </a>
  );
}

function timeAgo(iso?: string): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  const ago = Math.floor((Date.now() - t) / 1000);
  if (ago < 60) return ago + "s";
  if (ago < 3600) return Math.floor(ago / 60) + "m";
  if (ago < 86400) return Math.floor(ago / 3600) + "h";
  return Math.floor(ago / 86400) + "d";
}
