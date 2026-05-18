import express from "express";
import { randomUUID } from "node:crypto";
import { appendFile, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { promisify } from "node:util";
import { execFile } from "node:child_process";
import Pino from "pino";
import QRCode from "qrcode";
import { Boom } from "@hapi/boom";
import makeWASocket, {
  Browsers,
  DisconnectReason,
  downloadMediaMessage,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
} from "@whiskeysockets/baileys";

const PORT = Number(process.env.PORT || 8787);
const HOST = process.env.HOST || "127.0.0.1";
const AUTH_DIR = process.env.AUTH_DIR || new URL("../auth", import.meta.url).pathname;
const API_TOKEN = process.env.API_TOKEN || process.env.WHATSAPP_BRIDGE_TOKEN || "";
const HELP_DESK_BASE_URL = (process.env.HELP_DESK_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const SPEAKGOV_QUERY_URL = process.env.SPEAKGOV_QUERY_URL || "http://127.0.0.1:8000/query";
const SPEAKGOV_TRANSCRIBE_URL = process.env.SPEAKGOV_TRANSCRIBE_URL || `${HELP_DESK_BASE_URL}/voice/transcribe`;
const SPEAKGOV_SYNTHESIZE_URL = process.env.SPEAKGOV_SYNTHESIZE_URL || `${HELP_DESK_BASE_URL}/voice/synthesize`;
const AUTO_REPLY = !["0", "false", "no", "off"].includes(String(process.env.AUTO_REPLY || "true").toLowerCase());
const AUTO_CONNECT = ["1", "true", "yes", "on"].includes(String(process.env.AUTO_CONNECT || "false").toLowerCase());
const ALLOW_GROUPS = ["1", "true", "yes", "on"].includes(String(process.env.ALLOW_GROUPS || "false").toLowerCase());
const SEND_VOICE_REPLIES = !["0", "false", "no", "off"].includes(String(process.env.SEND_VOICE_REPLIES || "true").toLowerCase());
const MAX_HISTORY_TURNS = Number(process.env.MAX_HISTORY_TURNS || 8);
const MAX_REPLY_CHARS = Number(process.env.MAX_REPLY_CHARS || 3600);
const MAX_VOICE_REPLY_CHARS = Number(process.env.MAX_VOICE_REPLY_CHARS || 420);
const QUERY_TIMEOUT_MS = Number(process.env.QUERY_TIMEOUT_MS || 120000);
const VOICE_TIMEOUT_MS = Number(process.env.VOICE_TIMEOUT_MS || 300000);
const FFMPEG_BIN = process.env.FFMPEG_BIN || "ffmpeg";
const DEDUPE_STORE_FILE = process.env.DEDUPE_STORE_FILE || join(AUTH_DIR, "speakgov-seen-messages.json");
const DEDUPE_TTL_MS = Number(process.env.DEDUPE_TTL_MS || 24 * 60 * 60 * 1000);
const DEDUPE_MAX = Number(process.env.DEDUPE_MAX || 1000);
const PROACTIVE_OUTREACH_DEMO = ["1", "true", "yes", "on"].includes(String(process.env.PROACTIVE_OUTREACH_DEMO || "false").toLowerCase());
const PROACTIVE_OUTREACH_AUTO_SEND = ["1", "true", "yes", "on"].includes(String(process.env.PROACTIVE_OUTREACH_AUTO_SEND || "false").toLowerCase());
const PROACTIVE_OUTREACH_NOTIFY_USER = !["0", "false", "no", "off"].includes(String(process.env.PROACTIVE_OUTREACH_NOTIFY_USER || "true").toLowerCase());
const PROACTIVE_OUTREACH_TRIGGER = String(process.env.PROACTIVE_OUTREACH_TRIGGER || "noted_gov_query").toLowerCase();
const PROACTIVE_OUTREACH_LOG_FILE = process.env.PROACTIVE_OUTREACH_LOG_FILE || join(AUTH_DIR, "speakgov-outreach-demo.jsonl");
const PROACTIVE_OUTREACH_MIN_CHARS = Number(process.env.PROACTIVE_OUTREACH_MIN_CHARS || 12);
const PROACTIVE_OUTREACH_COOLDOWN_MS = Number(process.env.PROACTIVE_OUTREACH_COOLDOWN_MS || 5 * 60 * 1000);
const PROACTIVE_OUTREACH_USER_ALLOWLIST = new Set(
  String(process.env.PROACTIVE_OUTREACH_USER_ALLOWLIST || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean),
);
const PROACTIVE_OUTREACH_IGNORE_JIDS = new Set(
  String(process.env.PROACTIVE_OUTREACH_IGNORE_JIDS || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean),
);
const HELP_DESK_ADMIN_USERNAME = process.env.HELP_DESK_ADMIN_USERNAME || process.env.ADMIN_USERNAME || "admin";
const HELP_DESK_ADMIN_PASSWORD = process.env.HELP_DESK_ADMIN_PASSWORD || process.env.ADMIN_PASSWORD || "";

const logger = Pino({ level: process.env.LOG_LEVEL || "info" });
const baileysLogger = Pino({ level: process.env.BAILEYS_LOG_LEVEL || "silent" });
const app = express();
const execFileAsync = promisify(execFile);

app.use(express.json({ limit: "1mb" }));

let sock = null;
let starting = null;
let saveCreds = null;
let connectionStatus = "idle";
let connectedJid = null;
let latestQr = null;
let latestQrDataUrl = null;
let latestQrUpdatedAt = null;
let lastError = null;
let lastDisconnectReason = null;
let inboundCount = 0;
let outboundCount = 0;
let inboundAudioCount = 0;
let outboundAudioCount = 0;
let lastInboundAt = null;
let lastOutboundAt = null;
let lastAudioTranscript = null;
const histories = new Map();
const seenMessages = new Map();
const outreachCooldown = new Map();
const outreachDemoRecipients = new Set(PROACTIVE_OUTREACH_IGNORE_JIDS);
let seenStoreLoaded = false;
let seenStoreWrite = Promise.resolve();

function requireToken(req, res, next) {
  if (!API_TOKEN) return next();
  const header = req.get("authorization") || "";
  const token = header.startsWith("Bearer ") ? header.slice("Bearer ".length) : "";
  if (token && token === API_TOKEN) return next();
  return res.status(401).json({ error: "unauthorized" });
}

function publicStatus() {
  return {
    status: connectionStatus,
    connected: connectionStatus === "open",
    connectedJid,
    hasQr: Boolean(latestQrDataUrl),
    qrUpdatedAt: latestQrUpdatedAt,
    lastError,
    lastDisconnectReason,
    autoReply: AUTO_REPLY,
    allowGroups: ALLOW_GROUPS,
    sendVoiceReplies: SEND_VOICE_REPLIES,
    proactiveOutreachDemo: PROACTIVE_OUTREACH_DEMO,
    proactiveOutreachAutoSend: PROACTIVE_OUTREACH_AUTO_SEND,
    proactiveOutreachTrigger: PROACTIVE_OUTREACH_TRIGGER,
    inboundCount,
    outboundCount,
    inboundAudioCount,
    outboundAudioCount,
    lastInboundAt,
    lastOutboundAt,
    lastAudioTranscript,
    authDir: AUTH_DIR,
  };
}

function nowIso() {
  return new Date().toISOString();
}

function normalizeToJid(to) {
  const value = String(to || "").trim();
  if (!value) throw new Error("missing recipient");
  if (value.includes("@")) return value;
  const digits = value.replace(/[^\d]/g, "");
  if (digits.length < 8) throw new Error("recipient must include country code");
  return `${digits}@s.whatsapp.net`;
}

function unwrapMessage(message) {
  let current = message || {};
  for (let i = 0; i < 5; i += 1) {
    if (current.ephemeralMessage?.message) current = current.ephemeralMessage.message;
    else if (current.viewOnceMessage?.message) current = current.viewOnceMessage.message;
    else if (current.viewOnceMessageV2?.message) current = current.viewOnceMessageV2.message;
    else if (current.documentWithCaptionMessage?.message) current = current.documentWithCaptionMessage.message;
    else break;
  }
  return current;
}

function extractText(message) {
  const msg = unwrapMessage(message);
  return (
    msg.conversation ||
    msg.extendedTextMessage?.text ||
    msg.imageMessage?.caption ||
    msg.videoMessage?.caption ||
    msg.documentMessage?.caption ||
    msg.buttonsResponseMessage?.selectedDisplayText ||
    msg.buttonsResponseMessage?.selectedButtonId ||
    msg.listResponseMessage?.title ||
    ""
  ).trim();
}

function hasAudio(message) {
  const msg = unwrapMessage(message);
  return Boolean(msg.audioMessage);
}

function pushHistory(jid, role, content) {
  const prior = histories.get(jid) || [];
  const next = [...prior, { role, content: String(content || "").slice(0, 900) }].slice(-MAX_HISTORY_TURNS);
  histories.set(jid, next);
}

function compactSources(sources) {
  const seen = new Set();
  const urls = [];
  for (const source of sources || []) {
    const url = source?.url;
    if (!url || seen.has(url)) continue;
    seen.add(url);
    urls.push(url);
    if (urls.length >= 3) break;
  }
  return urls;
}

async function appendDemoEvent(event) {
  if (!PROACTIVE_OUTREACH_DEMO) return;
  const payload = {
    ts: nowIso(),
    ...event,
  };
  logger.info(payload, "whatsapp demo event");
  try {
    await mkdir(dirname(PROACTIVE_OUTREACH_LOG_FILE), { recursive: true });
    await appendFile(PROACTIVE_OUTREACH_LOG_FILE, `${JSON.stringify(payload)}\n`, "utf8");
  } catch (error) {
    logger.warn({ err: error, file: PROACTIVE_OUTREACH_LOG_FILE }, "failed to append proactive outreach demo event");
  }
}

function formatReply(data) {
  let text = String(data?.answer || "").trim();
  if (!text) text = "माफ गर्नुहोस्, अहिले उत्तर बनाउन सकिनँ। कृपया फेरि सोध्नुहोस्।";
  const urls = compactSources(data?.sources);
  if (urls.length) {
    text += `\n\nSources:\n${urls.map((url, idx) => `${idx + 1}. ${url}`).join("\n")}`;
  }
  if (text.length > MAX_REPLY_CHARS) {
    text = `${text.slice(0, MAX_REPLY_CHARS - 40).trim()}\n\n...`;
  }
  return text;
}

function formatVoiceReply(data) {
  let text = String(data?.answer || "").trim();
  if (!text) text = "माफ गर्नुहोस्, अहिले उत्तर बनाउन सकिनँ। कृपया टेक्स्टमा फेरि सोध्नुहोस्।";
  text = text
    .replace(/\n+Sources:[\s\S]*$/i, "")
    .replace(/https?:\/\/\S+/gi, "")
    .replace(/\s+/g, " ")
    .trim();
  if (text.length > MAX_VOICE_REPLY_CHARS) {
    const clipped = text.slice(0, MAX_VOICE_REPLY_CHARS - 32);
    const sentenceEnd = Math.max(clipped.lastIndexOf("।"), clipped.lastIndexOf("."), clipped.lastIndexOf("?"));
    text = `${(sentenceEnd > 120 ? clipped.slice(0, sentenceEnd + 1) : clipped).trim()} थप विवरण टेक्स्टमा पठाएको छु।`;
  }
  return text;
}

function messageDedupeKey(message) {
  const key = message?.key || {};
  const id = key.id ? String(key.id) : "";
  const remoteJid = key.remoteJid ? String(key.remoteJid) : "";
  const participant = key.participant ? String(key.participant) : "";
  if (!id || !remoteJid) return "";
  return `${remoteJid}:${participant}:${id}`;
}

function pruneSeenMessages(now = Date.now()) {
  for (const [key, value] of seenMessages.entries()) {
    if (now - Number(value || 0) > DEDUPE_TTL_MS) seenMessages.delete(key);
  }
  if (seenMessages.size <= DEDUPE_MAX) return;
  const sorted = [...seenMessages.entries()].sort((a, b) => Number(a[1]) - Number(b[1]));
  for (const [key] of sorted.slice(0, Math.max(0, seenMessages.size - DEDUPE_MAX))) {
    seenMessages.delete(key);
  }
}

async function loadSeenMessages() {
  if (seenStoreLoaded) return;
  seenStoreLoaded = true;
  try {
    const raw = await readFile(DEDUPE_STORE_FILE, "utf8");
    const parsed = JSON.parse(raw);
    for (const item of parsed?.messages || []) {
      if (item?.key && item?.seenAt) seenMessages.set(String(item.key), Number(item.seenAt));
    }
    pruneSeenMessages();
  } catch (error) {
    if (error?.code !== "ENOENT") logger.warn({ err: error }, "failed to load whatsapp dedupe store");
  }
}

function saveSeenMessagesSoon() {
  const payload = {
    savedAt: nowIso(),
    messages: [...seenMessages.entries()].map(([key, seenAt]) => ({ key, seenAt })),
  };
  seenStoreWrite = seenStoreWrite
    .catch(() => {})
    .then(async () => {
      try {
        await mkdir(AUTH_DIR, { recursive: true });
        await writeFile(DEDUPE_STORE_FILE, JSON.stringify(payload), "utf8");
      } catch (error) {
        logger.warn({ err: error }, "failed to save whatsapp dedupe store");
      }
    });
}

function markIncomingOnce(message) {
  const key = messageDedupeKey(message);
  if (!key) return true;
  const now = Date.now();
  pruneSeenMessages(now);
  if (seenMessages.has(key)) return false;
  seenMessages.set(key, now);
  saveSeenMessagesSoon();
  return true;
}

async function callHelpdesk(jid, question, historyOverride = null) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), QUERY_TIMEOUT_MS);
  try {
    const response = await fetch(SPEAKGOV_QUERY_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        history: historyOverride || histories.get(jid) || [],
        top_k_tacit: 3,
        top_k_gov: 3,
        max_new_tokens: 320,
      }),
      signal: controller.signal,
    });
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`helpdesk HTTP ${response.status}: ${text.slice(0, 200)}`);
    }
    return JSON.parse(text);
  } finally {
    clearTimeout(timeout);
  }
}

async function callHelpdeskAdmin(path, { method = "GET", body = null, timeoutMs = QUERY_TIMEOUT_MS } = {}) {
  if (!HELP_DESK_ADMIN_PASSWORD) {
    throw new Error("missing HELP_DESK_ADMIN_PASSWORD/ADMIN_PASSWORD for admin outreach");
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const headers = {
    Authorization: `Basic ${Buffer.from(`${HELP_DESK_ADMIN_USERNAME}:${HELP_DESK_ADMIN_PASSWORD}`).toString("base64")}`,
  };
  if (body !== null) headers["Content-Type"] = "application/json";
  try {
    const response = await fetch(`${HELP_DESK_BASE_URL}${path}`, {
      method,
      headers,
      body: body === null ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`admin HTTP ${response.status}: ${text.slice(0, 300)}`);
    }
    return text ? JSON.parse(text) : {};
  } finally {
    clearTimeout(timeout);
  }
}

async function transcribeAudioBuffer(buffer, filename = "voice.ogg") {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), VOICE_TIMEOUT_MS);
  try {
    const form = new FormData();
    form.append("audio", new Blob([buffer], { type: "audio/ogg" }), filename);
    const response = await fetch(SPEAKGOV_TRANSCRIBE_URL, {
      method: "POST",
      body: form,
      signal: controller.signal,
    });
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`ASR HTTP ${response.status}: ${text.slice(0, 200)}`);
    }
    return JSON.parse(text);
  } finally {
    clearTimeout(timeout);
  }
}

async function synthesizeReply(text) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), VOICE_TIMEOUT_MS);
  try {
    const response = await fetch(SPEAKGOV_SYNTHESIZE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    });
    const bytes = Buffer.from(await response.arrayBuffer());
    if (!response.ok) {
      throw new Error(`TTS HTTP ${response.status}: ${bytes.toString("utf8", 0, 200)}`);
    }
    return bytes;
  } finally {
    clearTimeout(timeout);
  }
}

async function wavToOpusOgg(wavBuffer) {
  const dir = join(tmpdir(), `speakgov-wa-${randomUUID()}`);
  await mkdir(dir, { recursive: true });
  const wavPath = join(dir, "reply.wav");
  const oggPath = join(dir, "reply.ogg");
  try {
    await writeFile(wavPath, wavBuffer);
    await execFileAsync(
      FFMPEG_BIN,
      [
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        wavPath,
        "-vn",
        "-c:a",
        "libopus",
        "-b:a",
        "32k",
        "-ar",
        "48000",
        "-ac",
        "1",
        oggPath,
      ],
      { timeout: 60000 },
    );
    return await readFile(oggPath);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

async function sendWhatsAppMessage(to, text) {
  if (!sock || connectionStatus !== "open") {
    throw new Error("WhatsApp is not connected");
  }
  const jid = normalizeToJid(to);
  const result = await sock.sendMessage(jid, { text: String(text || "") });
  outboundCount += 1;
  lastOutboundAt = nowIso();
  return { jid, messageId: result?.key?.id || null };
}

async function sendWhatsAppVoice(to, oggBuffer) {
  if (!sock || connectionStatus !== "open") {
    throw new Error("WhatsApp is not connected");
  }
  const jid = normalizeToJid(to);
  const result = await sock.sendMessage(jid, {
    audio: oggBuffer,
    mimetype: "audio/ogg; codecs=opus",
    ptt: true,
  });
  outboundCount += 1;
  outboundAudioCount += 1;
  lastOutboundAt = nowIso();
  return { jid, messageId: result?.key?.id || null };
}

function isLikelyGibberish(text) {
  const clean = String(text || "").trim();
  if (clean.length < PROACTIVE_OUTREACH_MIN_CHARS) return true;
  const letters = [...clean].filter((c) => /[A-Za-z\u0900-\u097f]/u.test(c)).length;
  const tokens = clean.split(/\s+/).filter(Boolean);
  if (letters < 5 || tokens.length < 2) return true;
  const punctuation = [...clean].filter((c) => /[^\w\s\u0900-\u097f]/u.test(c)).length;
  return punctuation > letters * 1.5;
}

function answerSignalsSourceGap(data) {
  const answer = String(data?.answer || "").toLowerCase();
  if (data?.did_refuse) return true;
  return (
    answer.includes("cannot find an authoritative source") ||
    answer.includes("could not safely produce") ||
    answer.includes("adhikarik srot bhetina") ||
    answer.includes("आधिकारिक स्रोत भेटिन") ||
    answer.includes("not have a reliable current source") ||
    answer.includes("source gap")
  );
}

function shouldCreateDemoOutreach(remoteJid, question, data) {
  if (!PROACTIVE_OUTREACH_DEMO) return { ok: false, reason: "demo disabled" };
  if (PROACTIVE_OUTREACH_USER_ALLOWLIST.size && !PROACTIVE_OUTREACH_USER_ALLOWLIST.has(remoteJid)) {
    return { ok: false, reason: "sender not allowlisted" };
  }
  if (outreachDemoRecipients.has(remoteJid)) {
    return { ok: false, reason: "sender is an outreach recipient" };
  }
  if (isLikelyGibberish(question)) return { ok: false, reason: "looks gibberish or too short" };
  if (/speakgov is trying to answer a public government-service question/i.test(question)) {
    return { ok: false, reason: "looks like an outreach message" };
  }
  const planner = data?.planner || {};
  const location = planner?.location || {};
  const sources = Array.isArray(data?.sources) ? data.sources : [];
  const hasGovIntent = Boolean(
    planner.service ||
    planner.action ||
    (Array.isArray(planner.expected_domains) && planner.expected_domains.length) ||
    (Array.isArray(location.local_domains) && location.local_domains.length) ||
    sources.length,
  );
  if (!hasGovIntent) return { ok: false, reason: "no government-service intent" };
  if (planner.decision === "off_domain_light_answer") return { ok: false, reason: "off domain" };
  const gap = answerSignalsSourceGap(data);
  const hasLocationOrOffice = Boolean(
    location.municipality ||
    location.district ||
    (Array.isArray(location.local_domains) && location.local_domains.length) ||
    (Array.isArray(planner.expected_domains) && planner.expected_domains.length),
  );
  const notable = PROACTIVE_OUTREACH_TRIGGER === "all" ||
    PROACTIVE_OUTREACH_TRIGGER === "noted_gov_query" ||
    (PROACTIVE_OUTREACH_TRIGGER === "gap" && gap);
  if (!notable) return { ok: false, reason: "not notable under trigger" };
  if (!gap && !hasLocationOrOffice) return { ok: false, reason: "no office/contact target" };
  const lastSentAt = outreachCooldown.get(remoteJid) || 0;
  if (Date.now() - lastSentAt < PROACTIVE_OUTREACH_COOLDOWN_MS) {
    return { ok: false, reason: "cooldown" };
  }
  return { ok: true, reason: gap ? "source gap or refusal" : "meaningful government-service query" };
}

function cleanOutreachContactName(name) {
  const clean = String(name || "").trim().replace(/\s+/g, " ");
  if (!clean) return "";
  const roleLike = /(कार्यालय|सूचना|सम्पर्क|संपर्क|अधिकृत|अधिकारी|निरीक्षक|प्रमुख|अध्यक्ष|उपाध्यक्ष|सचिव|फोन|मोबाइल|शाखा)/u;
  if (clean.length > 36 || clean.split(/\s+/).length > 3 || roleLike.test(clean)) return "";
  return clean;
}

function outreachContactLabel(record) {
  const contact = record?.contact || {};
  const name = cleanOutreachContactName(contact.name);
  return [
    name,
    contact.role || "",
    contact.phone || "",
  ].filter(Boolean).join(", ") || contact.whatsapp_to || "official contact";
}

async function maybeRunDemoOutreach(remoteJid, question, data) {
  const decision = shouldCreateDemoOutreach(remoteJid, question, data);
  await appendDemoEvent({
    kind: "decision",
    remoteJid,
    question,
    decision,
    planner: data?.planner || null,
    answerPreview: String(data?.answer || "").slice(0, 260),
  });
  if (!decision.ok) return;

  try {
    const draft = await callHelpdeskAdmin("/admin/outreach/draft", {
      method: "POST",
      body: {
        question,
        history: histories.get(remoteJid) || [],
        reason: `demo auto-outreach: ${decision.reason}`,
        top_k_gov: 8,
      },
    });
    await appendDemoEvent({
      kind: "draft",
      remoteJid,
      question,
      outreachId: draft?.id,
      status: draft?.status,
      contact: draft?.contact || null,
      messagePreview: String(draft?.message || "").slice(0, 420),
    });
    if (!draft?.id || !draft?.contact || !draft?.message) return;

    if (!PROACTIVE_OUTREACH_AUTO_SEND) {
      if (PROACTIVE_OUTREACH_NOTIFY_USER) {
        await sendWhatsAppMessage(
          remoteJid,
          `Demo: I found a likely official contact (${outreachContactLabel(draft)}) and prepared an outreach draft. It was not auto-sent.`,
        );
      }
      return;
    }

    const sent = await callHelpdeskAdmin(`/admin/outreach/${encodeURIComponent(draft.id)}/send`, {
      method: "POST",
      body: {},
    });
    if (draft?.contact?.whatsapp_to) {
      try {
        outreachDemoRecipients.add(normalizeToJid(draft.contact.whatsapp_to));
      } catch {
        // Keep demo flow moving even if the contact was not a normal WhatsApp JID.
      }
    }
    outreachCooldown.set(remoteJid, Date.now());
    await appendDemoEvent({
      kind: "sent",
      remoteJid,
      question,
      outreachId: draft.id,
      contact: draft.contact,
      sendResult: sent?.send_result || sent,
    });
    if (PROACTIVE_OUTREACH_NOTIFY_USER) {
      await sendWhatsAppMessage(
        remoteJid,
        `Demo: I also routed a sanitized question to ${outreachContactLabel(draft)} for official confirmation. No private citizen details were shared.`,
      );
    }
  } catch (error) {
    await appendDemoEvent({
      kind: "error",
      remoteJid,
      question,
      error: error?.message || String(error),
    });
  }
}

async function handleIncoming(message) {
  const remoteJid = message?.key?.remoteJid;
  if (!remoteJid || message?.key?.fromMe) return;
  if (remoteJid === "status@broadcast" || remoteJid.endsWith("@newsletter")) return;
  if (!ALLOW_GROUPS && remoteJid.endsWith("@g.us")) return;
  if (!markIncomingOnce(message)) {
    logger.info({ remoteJid, messageId: message?.key?.id }, "skipping duplicate whatsapp message");
    return;
  }

  const isAudio = hasAudio(message.message);
  let text = extractText(message.message);
  if (!text && isAudio) {
    inboundCount += 1;
    inboundAudioCount += 1;
    lastInboundAt = nowIso();
    logger.info({ remoteJid }, "incoming whatsapp audio");
    try {
      await sock.sendPresenceUpdate?.("recording", remoteJid);
      const media = await downloadMediaMessage(
        message,
        "buffer",
        {},
        {
          logger: baileysLogger,
          reuploadRequest: sock.updateMediaMessage,
        },
      );
      const asr = await transcribeAudioBuffer(media, "whatsapp-voice.ogg");
      text = String(asr?.transcript || "").trim();
      lastAudioTranscript = text;
      if (!text) {
        await sendWhatsAppMessage(remoteJid, "आवाज स्पष्ट बुझिएन। कृपया फेरि आवाज पठाउनुहोस् वा टेक्स्टमा लेख्नुहोस्।");
        await sock.sendPresenceUpdate?.("paused", remoteJid);
        return;
      }
      await sendWhatsAppMessage(remoteJid, `सुनेको: ${text}`);
    } catch (error) {
      logger.error({ err: error, remoteJid }, "audio transcription failed");
      try {
        await sendWhatsAppMessage(remoteJid, "आवाज पढ्न सकिएन। कृपया फेरि पठाउनुहोस् वा टेक्स्टमा लेख्नुहोस्।");
      } catch (sendError) {
        logger.error({ err: sendError, remoteJid }, "failed to send audio fallback");
      }
      return;
    }
  }
  if (!text) return;

  if (!isAudio) {
    inboundCount += 1;
    lastInboundAt = nowIso();
  }
  logger.info({ remoteJid, text: text.slice(0, 120), isAudio }, "incoming whatsapp message");
  await appendDemoEvent({ kind: "incoming", remoteJid, isAudio, text });

  if (!AUTO_REPLY) {
    pushHistory(remoteJid, "user", text);
    return;
  }

  let wroteUserHistory = false;
  try {
    await sock.sendPresenceUpdate?.("composing", remoteJid);
    const priorHistory = histories.get(remoteJid) || [];
    const data = await callHelpdesk(remoteJid, text, priorHistory);
    const reply = formatReply(data);
    if (isAudio && SEND_VOICE_REPLIES) {
      let sentTextReply = false;
      try {
        const voiceReply = formatVoiceReply(data);
        await sendWhatsAppMessage(remoteJid, reply);
        sentTextReply = true;
        const wav = await synthesizeReply(voiceReply);
        const ogg = await wavToOpusOgg(wav);
        await sendWhatsAppVoice(remoteJid, ogg);
      } catch (voiceError) {
        logger.error({ err: voiceError, remoteJid }, "voice reply failed; falling back to text");
        if (!sentTextReply) await sendWhatsAppMessage(remoteJid, reply);
      }
    } else {
      await sendWhatsAppMessage(remoteJid, reply);
    }
    pushHistory(remoteJid, "user", text);
    wroteUserHistory = true;
    pushHistory(remoteJid, "assistant", reply);
    await maybeRunDemoOutreach(remoteJid, text, data);
    await sock.sendPresenceUpdate?.("paused", remoteJid);
  } catch (error) {
    logger.error({ err: error, remoteJid }, "auto reply failed");
    try {
      await sendWhatsAppMessage(
        remoteJid,
        "माफ गर्नुहोस्, अहिले helpdesk service बाट उत्तर ल्याउन सकिएन। केही समयपछि फेरि प्रयास गर्नुहोस्।",
      );
    } catch (sendError) {
      logger.error({ err: sendError, remoteJid }, "failed to send fallback error");
    }
    if (!wroteUserHistory) {
      pushHistory(remoteJid, "user", text);
    }
  }
}

async function startSocket() {
  if (connectionStatus === "open" && sock) return sock;
  if (starting) return starting;

  starting = (async () => {
    connectionStatus = "connecting";
    lastError = null;
    const auth = await useMultiFileAuthState(AUTH_DIR);
    await loadSeenMessages();
    saveCreds = auth.saveCreds;
    const { version } = await fetchLatestBaileysVersion();
    sock = makeWASocket({
      auth: auth.state,
      browser: Browsers.macOS("PreVillage"),
      logger: baileysLogger,
      markOnlineOnConnect: false,
      printQRInTerminal: false,
      syncFullHistory: false,
      version,
    });

    sock.ev.on("creds.update", saveCreds);
    sock.ev.on("connection.update", async (update) => {
      const { connection, lastDisconnect, qr } = update;
      if (qr) {
        latestQr = qr;
        latestQrDataUrl = await QRCode.toDataURL(qr, { margin: 1, width: 320 });
        latestQrUpdatedAt = nowIso();
        connectionStatus = "qr";
      }
      if (connection === "open") {
        connectionStatus = "open";
        connectedJid = sock.user?.id || null;
        latestQr = null;
        latestQrDataUrl = null;
        latestQrUpdatedAt = null;
        lastError = null;
        logger.info({ connectedJid }, "whatsapp connected");
      }
      if (connection === "close") {
        const statusCode = new Boom(lastDisconnect?.error)?.output?.statusCode;
        lastDisconnectReason = statusCode || null;
        connectionStatus = "close";
        connectedJid = null;
        sock = null;
        logger.warn({ statusCode, err: lastDisconnect?.error }, "whatsapp connection closed");
        if (statusCode !== DisconnectReason.loggedOut) {
          setTimeout(() => {
            startSocket().catch((error) => {
              lastError = error?.message || String(error);
              logger.error({ err: error }, "whatsapp reconnect failed");
            });
          }, 3000);
        }
      }
    });
    sock.ev.on("messages.upsert", async ({ messages, type }) => {
      if (type !== "notify") return;
      for (const message of messages || []) {
        await handleIncoming(message);
      }
    });
    return sock;
  })();

  try {
    return await starting;
  } catch (error) {
    connectionStatus = "error";
    lastError = error?.message || String(error);
    sock = null;
    throw error;
  } finally {
    starting = null;
  }
}

app.get("/health", (_req, res) => {
  res.json({ status: "ok", bridge: "baileys", ...publicStatus() });
});

app.get("/status", requireToken, (_req, res) => {
  res.json(publicStatus());
});

app.post("/connect", requireToken, async (_req, res, next) => {
  try {
    await startSocket();
    res.json(publicStatus());
  } catch (error) {
    next(error);
  }
});

app.get("/qr", requireToken, (_req, res) => {
  res.json({
    qr: latestQr,
    qrDataUrl: latestQrDataUrl,
    updatedAt: latestQrUpdatedAt,
    status: connectionStatus,
    connected: connectionStatus === "open",
  });
});

app.post("/send", requireToken, async (req, res, next) => {
  try {
    const result = await sendWhatsAppMessage(req.body?.to, req.body?.text);
    res.json({ ok: true, ...result });
  } catch (error) {
    next(error);
  }
});

app.post("/logout", requireToken, async (_req, res, next) => {
  try {
    if (sock) await sock.logout();
    sock = null;
    connectionStatus = "logged_out";
    connectedJid = null;
    latestQr = null;
    latestQrDataUrl = null;
    latestQrUpdatedAt = null;
    histories.clear();
    res.json(publicStatus());
  } catch (error) {
    next(error);
  }
});

app.post("/history/clear", requireToken, (req, res) => {
  const jid = req.body?.jid;
  if (jid) histories.delete(String(jid));
  else histories.clear();
  res.json({ ok: true, cleared: jid || "all" });
});

app.use((error, _req, res, _next) => {
  lastError = error?.message || String(error);
  logger.error({ err: error }, "bridge request failed");
  res.status(500).json({ error: lastError });
});

const server = app.listen(PORT, HOST, () => {
  logger.info({ host: HOST, port: PORT, authDir: AUTH_DIR, autoReply: AUTO_REPLY }, "whatsapp bridge listening");
  if (AUTO_CONNECT) {
    startSocket().catch((error) => {
      lastError = error?.message || String(error);
      logger.error({ err: error }, "whatsapp auto-connect failed");
    });
  }
});

async function shutdown() {
  logger.info("whatsapp bridge shutting down");
  server.close();
  try {
    if (saveCreds) await saveCreds();
  } catch (error) {
    logger.warn({ err: error }, "failed to save creds on shutdown");
  }
  process.exit(0);
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
