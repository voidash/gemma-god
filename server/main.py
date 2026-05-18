"""FastAPI server for the Nepal-gov-helpdesk RAG.

Stateless wrt which adapter version is loaded — point ADAPTER_PATH at v1,
v2, v3 etc. via env without touching code. Designed to run on k2 (Mac Studio
M2 Ultra) under Tailscale Funnel for the Android demo, but starts up fine
on any Mac with MLX. For Linux/CUDA we'd swap mlx-lm → transformers.

Endpoints:
  POST /query         full RAG: retrieve → compose → cite
  GET  /health        liveness + which adapter is loaded
  GET  /admin/info    model/db stats, chunk counts, FTS5 status (tailnet only)
  POST /admin/reindex rebuild the FTS5 index over chunks  (tailnet only)

Run locally:
  ADAPTER_PATH=voidash/gemma-helpdesk-seed42 \\
  DB_PATH=/Volumes/T9/gemma-god/corpus_v2/index.db \\
  python -m uvicorn server.main:app --reload --port 8000

Expose publicly via Tailscale Funnel:
  tailscale funnel --bg 8000          # k2 only — public HTTPS
  curl https://k2.<tailnet>.ts.net/health
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import secrets
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import uuid
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from server.navigator import (
    CaseFrame,
    filter_gov_results_for_frame,
    filter_tacit_results_for_frame,
    followup_answer,
    location_no_source_answer,
    planner_contract,
    resolve_case,
    should_force_no_source_for_location,
)


# ---- Config ---------------------------------------------------------------

MODEL_ID = os.environ.get("MODEL_ID", "mlx-community/gemma-4-e4b-it-bf16")
ADAPTER_PATH = os.environ.get("ADAPTER_PATH")  # HF repo id or local path; None = base model
DB_PATH = os.environ.get("DB_PATH", "/Volumes/T9/gemma-god/corpus_v2/index.db")
TACIT_DIR = os.environ.get("TACIT_DIR", "corpora/tacit/processed")  # tacit-knowledge corpus
TOP_K_TACIT = int(os.environ.get("TOP_K_TACIT", "3"))   # guaranteed slots for tacit
TOP_K_GOV = int(os.environ.get("TOP_K_GOV", "3"))       # gov.np slots
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "600"))
DECODE_DO_SAMPLE = os.environ.get("DECODE_DO_SAMPLE", "true").lower() in ("1", "true", "yes")
DECODE_TEMPERATURE = float(os.environ.get("DECODE_TEMPERATURE", "0.3"))
DECODE_TOP_P = float(os.environ.get("DECODE_TOP_P", "0.9"))
DECODE_REPETITION_PENALTY = float(os.environ.get("DECODE_REPETITION_PENALTY", "1.0"))
DECODE_NO_REPEAT_NGRAM_SIZE = int(os.environ.get("DECODE_NO_REPEAT_NGRAM_SIZE", "0"))
CHUNK_TEXT_MAX_CHARS = int(os.environ.get("CHUNK_TEXT_MAX_CHARS", "1200"))
ALLOW_ORIGINS = os.environ.get("ALLOW_ORIGINS", "*").split(",")
BEARER_TOKEN = os.environ.get("BEARER_TOKEN")  # legacy; /query is now public
HF_TOKEN = os.environ.get("HF_TOKEN")  # for downloading gated models / adapters
SOURCE_REGISTRY_PATH = os.environ.get("SOURCE_REGISTRY_PATH", "corpora/sources_tiered.jsonl")

# Legacy single-K alias (when set, it's split between tacit + gov)
TOP_K = int(os.environ.get("TOP_K", str(TOP_K_TACIT + TOP_K_GOV)))

# ---- Admin / interview infra ---------------------------------------------
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
VERTEX_KEY = os.environ.get("VERTEX_KEY", "")
VERTEX_MODEL = os.environ.get("VERTEX_MODEL", "gemini-2.5-flash")
VOICE_ASR_PROVIDER = os.environ.get("VOICE_ASR_PROVIDER", "vertex").strip().lower()
VOICE_ASR_MODEL_ID = os.environ.get(
    "VOICE_ASR_MODEL_ID",
    "voidash/nepali-asr-staging",
)
VOICE_ASR_NEMO_FILE = os.environ.get(
    "VOICE_ASR_NEMO_FILE",
    "training-artifacts/fastconformer/hi_ctc_medium_slr54init_mixed491h_e10/"
    "checkpoints/ne-fastconformer-hybrid-bpe-v256-stt-hi-ctc-medium-"
    "slr54init-mixed491h-e10-lr5e5.nemo",
)
VOICE_ASR_SPACE_URL = os.environ.get(
    "VOICE_ASR_SPACE_URL",
    "https://voidash-nepali-fastconformer-demo.hf.space",
)
VOICE_ASR_SPACE_API_NAME = os.environ.get("VOICE_ASR_SPACE_API_NAME", "/transcribe")
VOICE_ASR_WORKER_URL = os.environ.get("VOICE_ASR_WORKER_URL", "http://127.0.0.1:8789").rstrip("/")
VOICE_ASR_CMD = os.environ.get("VOICE_ASR_CMD", "").strip()
VOICE_TTS_PROVIDER = os.environ.get("VOICE_TTS_PROVIDER", "disabled").strip().lower()
VOICE_TTS_MODEL_REPO = os.environ.get("VOICE_TTS_MODEL_REPO", "ampixa/real-nepali-v0.2-kala")
VOICE_TTS_SPEAKER = os.environ.get("VOICE_TTS_SPEAKER", "kala")
VOICE_TTS_SPACE_URL = os.environ.get("VOICE_TTS_SPACE_URL", "https://ampixa-real-nepali-tts.hf.space")
VOICE_TTS_SPACE_API_NAME = os.environ.get("VOICE_TTS_SPACE_API_NAME", "/synthesize")
VOICE_TTS_WORKER_URL = os.environ.get("VOICE_TTS_WORKER_URL", "http://127.0.0.1:8788").rstrip("/")
VOICE_TTS_CMD = os.environ.get("VOICE_TTS_CMD", "").strip()
VOICE_TIMEOUT_SECONDS = float(os.environ.get("VOICE_TIMEOUT_SECONDS", "180"))
VOICE_TTS_MAX_CHARS = int(os.environ.get("VOICE_TTS_MAX_CHARS", "230"))
WHATSAPP_BRIDGE_URL = os.environ.get("WHATSAPP_BRIDGE_URL", "http://127.0.0.1:8787").rstrip("/")
WHATSAPP_BRIDGE_TOKEN = os.environ.get("WHATSAPP_BRIDGE_TOKEN", "")
WHATSAPP_BRIDGE_TIMEOUT_SECONDS = float(os.environ.get("WHATSAPP_BRIDGE_TIMEOUT_SECONDS", "20"))
INTERVIEWS_DIR = Path(os.environ.get("INTERVIEWS_DIR", "/Volumes/T9/gemma-god/interviews"))
OUTREACH_DIR = Path(os.environ.get("OUTREACH_DIR", "/Volumes/T9/gemma-god/outreach"))
WEB_DIR = Path(os.environ.get("WEB_DIR", str(Path(__file__).parent.parent / "web")))
MAX_AUDIO_FILE_BYTES = int(os.environ.get("MAX_AUDIO_FILE_BYTES", str(25 * 1024 * 1024)))
MAX_PHOTO_FILE_BYTES = int(os.environ.get("MAX_PHOTO_FILE_BYTES", str(5 * 1024 * 1024)))
MAX_AUDIO_FILES = int(os.environ.get("MAX_AUDIO_FILES", "15"))
MAX_PHOTO_FILES = int(os.environ.get("MAX_PHOTO_FILES", "5"))
MAX_SUBMISSIONS_PER_IP_DAY = int(os.environ.get("MAX_SUBMISSIONS_PER_IP_DAY", "5"))

# VERTEX_KEY can also live in /Users/k2/.vertex_key (chmod 600). Read at import time.
if not VERTEX_KEY:
    _vk = Path(os.environ.get("VERTEX_KEY_FILE", "/Users/k2/.vertex_key"))
    if _vk.exists():
        try:
            VERTEX_KEY = _vk.read_text(encoding="utf-8").strip()
        except Exception:
            pass


# ---- Bilingual anchor map for FTS expansion -------------------------------
#
# The chunks table is ~90% Devanagari (gov.np docs). FTS5 BM25 ranks by token
# rarity and presence — for Devanagari technical queries this works. For
# English/Roman-NE queries, common English words match thousands of NHRC /
# speech / report chunks instead of the actual gov procedural docs.
#
# Hack: when an English/Roman-NE token matches a known gov-domain anchor,
# OR-add its Devanagari translation(s) into the FTS query. The retriever
# then unions chunks that match either form. Right doc wins on BM25.
#
# Multi-word values are split into individual tokens by the caller. Both
# Roman-NE transliterations and English forms are keys (lower-case).

BILINGUAL_ANCHORS: dict[str, tuple[str, ...]] = {
    # documents / certificates
    "citizenship": ("नागरिकता", "नागरिकता प्रमाणपत्र"),
    "nagarikta":   ("नागरिकता",),
    "passport":    ("राहदानी", "पासपोर्ट"),
    "rahadani":    ("राहदानी",),
    "license":     ("लाइसेन्स", "अनुमतिपत्र"),
    "licence":     ("लाइसेन्स", "अनुमतिपत्र"),
    "anumatipatra":("अनुमतिपत्र",),
    "certificate": ("प्रमाणपत्र",),
    "pramanpatra": ("प्रमाणपत्र",),
    "recommendation": ("सिफारिश",),
    "sifarish":    ("सिफारिश",),
    "voter":       ("मतदाता", "मतदाता परिचयपत्र"),
    "matadata":    ("मतदाता",),
    "national":    ("राष्ट्रिय", "परिचयपत्र"),
    "identity":    ("परिचयपत्र",),
    "card":        ("कार्ड",),
    "contact":     ("सम्पर्क", "फोन", "ईमेल", "पदाधिकारी", "सूचना अधिकारी"),
    "person":      ("व्यक्ति", "पदाधिकारी", "सूचना अधिकारी", "नगर प्रमुख"),
    "official":    ("पदाधिकारी", "कर्मचारी"),
    "officials":   ("पदाधिकारी", "कर्मचारी"),
    "mayor":       ("नगर प्रमुख",),
    "deputy":      ("उप प्रमुख",),
    "information": ("सूचना", "सूचना अधिकारी"),
    "officer":     ("अधिकृत", "अधिकारी", "पदाधिकारी", "कर्मचारी", "सूचना अधिकारी"),
    "officers":    ("अधिकृत", "अधिकारी", "पदाधिकारी", "कर्मचारी", "सूचना अधिकारी", "नगर प्रमुख"),
    "staff":       ("कर्मचारी", "पदाधिकारी", "अधिकारी"),
    "employee":    ("कर्मचारी",),
    "employees":   ("कर्मचारी", "पदाधिकारी"),
    "phone":       ("फोन", "सम्पर्क", "contact", "contact no"),
    "email":       ("ईमेल",),
    # actions / verbs
    "lost":        ("हराएमा", "हराएको"),
    "haraayo":     ("हराएमा",),
    "haraayeko":   ("हराएमा",),
    "renew":       ("नविकरण",),
    "nawikaran":   ("नविकरण",),
    "nabikaran":   ("नविकरण",),
    "apply":       ("निवेदन",),
    "application": ("निवेदन",),
    "nibedan":     ("निवेदन",),
    "register":    ("दर्ता",),
    "registration":("दर्ता",),
    "enroll":      ("दर्ता", "विवरण"),
    "enrollment":  ("दर्ता", "विवरण"),
    "appointment": ("appointment", "biometric", "विवरण"),
    "darta":       ("दर्ता",),
    "replace":     ("प्रतिलिपि",),
    "duplicate":   ("प्रतिलिपि",),
    # offices / bodies
    "office":      ("कार्यालय",),
    "karyalaya":   ("कार्यालय",),
    "ministry":    ("मन्त्रालय",),
    "mantralaya":  ("मन्त्रालय",),
    "department":  ("विभाग",),
    "vibhag":      ("विभाग",),
    "municipality":("नगरपालिका",),
    "nagarpalika": ("नगरपालिका",),
    "jiri":        ("जिरी", "जिरी नगरपालिका"),
    "jirimun":     ("जिरी", "जिरी नगरपालिका"),
    "जिरी":        ("jiri", "jirimun", "जिरी नगरपालिका", "नगरपालिका"),
    "जिरि":        ("jiri", "jirimun", "जिरी", "जिरी नगरपालिका", "नगरपालिका"),
    "dharmadevi":  ("धर्मदेवी", "धर्मदेवी नगरपालिका"),
    "dharmadevimun": ("धर्मदेवी", "धर्मदेवी नगरपालिका"),
    "धर्मदेवी":    ("dharmadevi", "dharmadevimun", "धर्मदेवी नगरपालिका", "नगरपालिका"),
    "धर्मधेवी":    ("dharmadevi", "dharmadevimun", "धर्मदेवी", "धर्मदेवी नगरपालिका", "नगरपालिका"),
    "धर्मध्यपी":   ("dharmadevi", "dharmadevimun", "धर्मदेवी", "धर्मदेवी नगरपालिका", "नगरपालिका"),
    "धर्माधिपी":   ("dharmadevi", "dharmadevimun", "धर्मदेवी", "धर्मदेवी नगरपालिका", "नगरपालिका"),
    "धर्मदेव":     ("dharmadevi", "dharmadevimun", "धर्मदेवी", "धर्मदेवी नगरपालिका", "नगरपालिका"),
    "धर्म देव":    ("dharmadevi", "dharmadevimun", "धर्मदेवी", "धर्मदेवी नगरपालिका", "नगरपालिका"),
    "helpdesk":    ("contact", "contact no", "सम्पर्क", "सूचना अधिकारी", "पदाधिकारी"),
    "हेल्पडेस्क":  ("contact", "contact no", "सम्पर्क", "सूचना अधिकारी", "पदाधिकारी"),
    "हेल्पडेष्क":  ("contact", "contact no", "सम्पर्क", "सूचना अधिकारी", "पदाधिकारी"),
    "जिरिहेल्पडेस्क": ("jiri", "jirimun", "जिरी", "जिरी नगरपालिका", "contact", "सम्पर्क", "सूचना अधिकारी"),
    "जिरिहेल्पडेष्क": ("jiri", "jirimun", "जिरी", "जिरी नगरपालिका", "contact", "सम्पर्क", "सूचना अधिकारी"),
    "ward":        ("वडा",),
    "wada":        ("वडा",),
    "district":    ("जिल्ला",),
    "jilla":       ("जिल्ला",),
    "dao":         ("जिल्ला प्रशासन कार्यालय",),
    "cdo":         ("प्रमुख जिल्ला अधिकारी",),
    "police":      ("प्रहरी",),
    "prahari":     ("प्रहरी",),
    "clearance":   ("चालचलन प्रमाणपत्र", "चारित्रिक प्रमाणपत्र"),
    "conduct":     ("चालचलन",),
    "character":   ("चारित्रिक",),
    # life events
    "vital":       (
        "व्यक्तिगत घटना दर्ता",
        "birth death marriage registration",
        "जन्म दर्ता मृत्यु दर्ता विवाह दर्ता बसाइँसराई सम्बन्धविच्छेद",
    ),
    "civil":       ("व्यक्तिगत घटना दर्ता", "पञ्जीकरण"),
    "event":       ("घटना दर्ता",),
    "events":      ("घटना दर्ता",),
    "panjikaran":  ("पञ्जीकरण", "व्यक्तिगत घटना दर्ता"),
    "birth":       ("जन्म दर्ता",),
    "janmadarta":  ("जन्म दर्ता",),
    "janma_darta": ("जन्म दर्ता",),
    "janma-darta": ("जन्म दर्ता",),
    "जनमदता":      ("जन्म दर्ता", "जन्मदर्ता", "birth registration"),
    "जनमदाता":     ("जन्म दर्ता", "जन्मदर्ता", "birth registration"),
    "जनमदर्ता":    ("जन्म दर्ता", "जन्मदर्ता", "birth registration"),
    "जनम":         ("जन्म", "जन्म दर्ता"),
    "जन्मदता":     ("जन्म दर्ता", "जन्मदर्ता", "birth registration"),
    "जन्मदाता":    ("जन्म दर्ता", "जन्मदर्ता", "birth registration"),
    "जन्मदरता":    ("जन्म दर्ता", "जन्मदर्ता", "birth registration"),
    "जन्मदर्त":    ("जन्म दर्ता", "जन्मदर्ता", "birth registration"),
    "जन्मदर्ल":    ("जन्म दर्ता", "जन्मदर्ता", "birth registration"),
    "जन्मदार्त":   ("जन्म दर्ता", "जन्मदर्ता", "birth registration"),
    "जन्मदार््त":  ("जन्म दर्ता", "जन्मदर्ता", "birth registration"),
    "death":       ("मृत्यु दर्ता",),
    "marriage":    ("विवाह दर्ता",),
    "divorce":     ("सम्बन्ध विच्छेद", "सम्बन्ध बिच्छेद", "सम्बन्धविच्छेद"),
    "separation":  ("सम्बन्ध विच्छेद", "सम्बन्ध बिच्छेद", "सम्बन्धविच्छेद"),
    "vivah":       ("विवाह",),
    "janma":       ("जन्म",),
    "mrityu":      ("मृत्यु",),
    "hours":       ("कार्यालय समय", "सेवा समय"),
    "opening":     ("कार्यालय समय",),
    "location":    ("ठेगाना", "स्थान"),
    "address":     ("ठेगाना",),
    # other gov-domain
    "pan":         ("स्थायी लेखा नम्बर", "करदाता"),
    "vat":         ("मूल्य अभिवृद्धि कर",),
    "ird":         ("आन्तरिक राजस्व विभाग",),
    "taxpayer":    ("करदाता",),
    "driving":     ("सवारी चालक अनुमतिपत्र", "यातायात"),
    "savari":      ("सवारी",),
    "chalak":      ("चालक",),
    "company":     ("कम्पनी",),
    "reserve":     ("आरक्षण", "नाम"),
    "tax":         ("कर", "मालपोत"),
    "kar":         ("कर",),
    "malpot":      ("मालपोत",),
    "land":        ("जग्गा",),
    "jagga":       ("जग्गा",),
    "lalpurja":    ("लालपुर्जा", "जग्गा धनी प्रमाण पुर्जा"),
    "ownership":   ("स्वामित्व", "जग्गा धनी प्रमाण पुर्जा"),
    "consular":    ("कन्सुलर", "वाणिज्यदूत", "प्रमाणीकरण"),
    "attestation": ("प्रमाणीकरण", "कागजात प्रमाणीकरण"),
    "attest":      ("प्रमाणीकरण",),
    "foreign":     ("वैदेशिक",),
    "employment":  ("रोजगार",),
    "labor":       ("श्रम", "श्रम स्वीकृति"),
    "labour":      ("श्रम", "श्रम स्वीकृति"),
    "permit":      ("स्वीकृति", "श्रम स्वीकृति"),
    "shram":       ("श्रम", "श्रम स्वीकृति"),
    "fee":         ("शुल्क",),
    "shulka":      ("शुल्क",),
    "nepal":       ("नेपाल",),
    "government":  ("सरकार",),
    "sarkar":      ("सरकार",),
    "citizen":     ("नागरिक",),
    "service":     ("सेवा",),
    "newspaper":   ("पत्रिका",),
    "patrika":     ("पत्रिका",),
}

LOG = logging.getLogger("gemma-god.server")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


# ---- System prompt / RAG contract -----------------------------------------

SYSTEM_GROUNDED = """\
You are SpeakGov, an independent helpdesk assistant for navigating Nepal \
government services. Your purpose is to help people find and understand \
official procedures using retrieved government and citizen-experience sources. You do not represent \
the Government of Nepal, SEBON, passport office, police, or any other single \
agency, even when a retrieved source comes from that agency. Answer the \
question using ONLY the provided Sources below: GOV.NP sources for official \
rules, and CITIZEN-EXPERIENCE INTERVIEW sources only for practical local \
office details such as location, timing, queues, counters, and real-world \
process notes.

HARD RULES:
0. If the user asks who you are, what your purpose is, or whether you are a \
specific agency chatbot, answer that you are SpeakGov, an independent \
assistant for navigating Nepal government services using official sources. Do \
not claim to represent any government agency.
1. After every factual claim, cite the source ID shown in Sources, e.g. \
[S1]. Do not invent source IDs. Do not copy raw URLs unless the user asks \
for a URL; the server maps source IDs to URLs.
2. If a claim is not directly supported by ANY source, drop it or mark \
[unverified].
2a. Do not copy OCR-damaged contact numbers, emails, or names. If a contact \
field is visibly garbled, say that the source has contact information but the \
specific contact value is not reliably readable. Clean short helplines such as \
1111 or 1141 may be used when clearly shown.
3. If sources support only part of the answer, answer the supported part and \
state what specific local/current detail is missing. Do not refuse the whole \
question when a narrower supported answer is possible.
4. If NO source meaningfully addresses the question, refuse with: \
"मलाई यो प्रश्नको आधिकारिक स्रोत भेटिनँ" (Devanagari) or \
"Yo prashnako adhikarik srot bhetina" (Roman-Nepali) or \
"I cannot find an authoritative source for this" (English) — match \
the question's language.
5. Respond in the same language/script as the question. If the question is \
English, answer in English even when sources are Nepali. Never answer an \
English question in Hindi, Nepali, or Devanagari script. If the question is \
Roman-Nepali, answer in Latin-script Roman Nepali, not Devanagari.
6. Be concise and procedural.
7. Do NOT introduce yourself, do NOT mention being an AI, do NOT use vendor \
names.
8. Answer ONLY the exact topic asked. Do NOT extrapolate from a source about \
topic X to make claims about topic Y (e.g. do not use a citizenship-replacement \
source to describe passport replacement). If a related topic isn't covered by \
any source, omit it entirely or say so plainly."""

SYSTEM_LANGUAGE_REPAIR = """\
You rewrite government-service helpdesk answers into the requested language.
Do not add new facts. Preserve source citations exactly, such as [S1] or
[S1, S2]. Do not copy raw URLs. If the requested language is English, use
English only except official names, emails, and phone numbers.
"""


# ---- Citation + refusal patterns (match eval_groundedness.py) -------------

URL_BRACKETED_RE = re.compile(r"\[(https?://[^\]\s]+)\]")
URL_BARE_RE = re.compile(r"https?://[^\s\)\]\>'\"`]+")
SOURCE_ID_CITATION_RE = re.compile(r"\[(?:S|s)(\d{1,2})\]")
SOURCE_ID_GROUP_RE = re.compile(r"\[([Ss]\d{1,2}(?:\s*,\s*[Ss]?\d{1,2})*)\]")
NUMERIC_CITATION_RE = re.compile(r"\[(\d{1,2})\]")
NUMERIC_GROUP_RE = re.compile(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})+)\]")
TRAILING_PUNCT = ",.;:!?)>\"'"

REFUSAL_PATTERNS = [
    re.compile(r"\bNO_SOURCE_AVAILABLE\b", re.I),
    re.compile(
        r"\b(?:cannot|can'?t|do(?:es)? not|don'?t|unable to)\s+"
        r"(?:find|locate|access|provide|determine|confirm|verify|cite|answer)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:no|not|insufficient|lack of|don'?t have)\b[^\.\n]{0,80}\b"
        r"(?:source|sources|info|information|data|details?|reference|coverage)\b",
        re.I,
    ),
    re.compile(r"मलाई[^\.\n]{0,80}स्रोत[^\.\n]{0,40}भेटि", re.U),
    re.compile(r"स्रोत\s*भेटि", re.U),
    re.compile(r"स्रोत[^\.\n]{0,40}छैन", re.U),
    re.compile(r"आधिकारिक\s+(?:जानकारी|स्रोत|उत्तर)[^\.\n]{0,30}(?:छैन|भेटि|पाइ(?:ँ|न))", re.U),
    re.compile(r"\b(?:srot|source)\s+(?:bhetin|chaina|nai chaina|bhetena)", re.I),
    re.compile(r"\badhikarik\s+(?:srot|jawab|jankari)", re.I),
    re.compile(r"हेलो\s*सरकार\s*1111", re.U),
    re.compile(r"\bhello\s*sarkar\b[^\n]{0,10}1111", re.I),
]


def extract_citations(text: str) -> list[str]:
    if not text:
        return []
    raw: list[str] = []
    raw.extend(URL_BRACKETED_RE.findall(text))
    cleaned: list[str] = []
    for u in raw:
        u = u.rstrip(TRAILING_PUNCT)
        if u:
            cleaned.append(u)
    # dedupe preserving order
    return list(dict.fromkeys(cleaned))


def _extract_source_ref_ranks(text: str) -> list[int]:
    if not text:
        return []

    ranks: list[int] = []
    seen: set[int] = set()

    def add(raw: str) -> None:
        try:
            rank = int(raw)
        except ValueError:
            return
        if rank not in seen:
            ranks.append(rank)
            seen.add(rank)

    for group in SOURCE_ID_GROUP_RE.findall(text):
        for raw_rank in re.findall(r"[Ss]?(\d{1,2})", group):
            add(raw_rank)
    for raw_rank in SOURCE_ID_CITATION_RE.findall(text):
        add(raw_rank)
    for group in NUMERIC_GROUP_RE.findall(text):
        for raw_rank in re.findall(r"\d{1,2}", group):
            add(raw_rank)
    for raw_rank in NUMERIC_CITATION_RE.findall(text):
        add(raw_rank)

    return ranks


def is_refusal(text: str) -> bool:
    if not text:
        return False
    return any(p.search(text) for p in REFUSAL_PATTERNS)


def normalize_url(u: str) -> str:
    if not u:
        return ""
    try:
        parsed = urllib.parse.urlsplit(urllib.parse.unquote(u.strip()))
        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        parsed = parsed._replace(scheme=scheme, netloc=netloc, fragment="")
        return urllib.parse.urlunsplit(parsed).rstrip("/")
    except Exception:
        return u.strip().rstrip("/")


def _tacit_rank_from_citation_url(u: str) -> int | None:
    try:
        fragment = urllib.parse.urlsplit(u.strip()).fragment
    except Exception:
        return None
    m = re.fullmatch(r"tacit-(\d{1,2})", fragment or "")
    if not m:
        return None
    return int(m.group(1))


def _same_url_host(a: str, b: str) -> bool:
    try:
        return urllib.parse.urlsplit(a).netloc.lower() == urllib.parse.urlsplit(b).netloc.lower()
    except Exception:
        return False


URL_FOLLOW_CHAR_RE = r"[A-Za-z0-9._~:/?#@!$&'()*+,;=%-]"


def _replace_cited_url(text: str, cited: str, replacement: str) -> str:
    return re.sub(
        re.escape(cited) + rf"(?!{URL_FOLLOW_CHAR_RE})",
        lambda _: replacement,
        text,
    )


def _repair_citation_urls(answer: str, tacit_results: list[dict], gov_results: list[dict]) -> str:
    """Replace model-truncated citation URLs with exact retrieved source URLs."""
    if not answer:
        return answer
    known_urls = [
        *(g.get("url") or "" for g in gov_results),
        *(t.get("office_url") or "" for t in tacit_results),
    ]
    known_urls = [u for u in known_urls if u]
    known_norms = {normalize_url(u) for u in known_urls}
    repaired = answer
    for cited in sorted(extract_citations(answer), key=len, reverse=True):
        cited_norm = normalize_url(cited)
        if not cited_norm or cited_norm in known_norms:
            continue
        try:
            cited_path = urllib.parse.urlsplit(cited_norm).path.strip("/")
        except Exception:
            continue
        same_host_matches = [u for u in known_urls if _same_url_host(cited_norm, u)]
        if not cited_path and same_host_matches:
            repaired = _replace_cited_url(repaired, cited, same_host_matches[0])
            continue
        if len(cited_norm) < 30 or len(cited_path) < 8:
            continue
        matches = [
            u for u in same_host_matches
            if normalize_url(u).startswith(cited_norm)
        ]
        if len(matches) == 1:
            repaired = _replace_cited_url(repaired, cited, matches[0])
    return repaired


def _replace_known_url_citations_with_source_refs(answer: str, sources: list["SourceOut"]) -> str:
    """Normalize old URL citations to the v5 source-ID contract."""
    if not answer:
        return answer
    out = answer
    by_url = [
        (s.url or "", s.source_ref)
        for s in sources
        if s.url
    ]
    for url, source_ref in sorted(by_url, key=lambda x: len(x[0]), reverse=True):
        if not url:
            continue
        replacements = {url}
        for cited in extract_citations(out):
            if normalize_url(cited) == normalize_url(url):
                replacements.add(cited)
        for cited in sorted(replacements, key=len, reverse=True):
            out = re.sub(
                rf"\[{re.escape(cited)}\]",
                f"[{source_ref}]",
                out,
            )
    return out


def _focused_snippet(text: str, markers: tuple[str, ...] = (), max_chars: int = 280) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if len(clean) <= max_chars:
        return clean
    lower = clean.lower()
    hit_at: int | None = None
    for marker in markers:
        if not marker:
            continue
        idx = lower.find(marker.lower())
        if idx >= 0 and (hit_at is None or idx < hit_at):
            hit_at = idx
    if hit_at is None:
        return clean[:max_chars]
    start = max(0, hit_at - max_chars // 4)
    end = min(len(clean), start + max_chars)
    if end - start < max_chars:
        start = max(0, end - max_chars)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(clean) else ""
    return f"{prefix}{clean[start:end]}{suffix}"


# ---- Retrieval diagnostics/ranking ----------------------------------------

RETRIEVAL_STOPWORDS = frozenset({
    # English
    "a", "an", "the", "and", "or", "to", "for", "of", "in", "on", "with",
    "from", "by", "is", "are", "be", "do", "does", "did", "how", "what",
    "where", "which", "who", "when", "why", "can", "need", "needed", "get",
    "make", "apply", "application", "number", "no", "new", "old",
    # Roman Nepali
    "ko", "ka", "ki", "lai", "lagi", "le", "ma", "ra", "ani", "yo", "tyo",
    "k", "ke", "kun", "kaha", "kasari", "garna", "garne", "garnu", "garda",
    "parcha", "parne", "cha", "chha", "chaine", "chaincha", "janu", "banau",
    "banaune", "paune", "milcha", "huncha", "ho",
    # Devanagari Nepali
    "के", "कुन", "कहाँ", "कसरी", "गर्ने", "गर्न", "गर्नु", "पर्छ", "पर्ने",
    "लागि", "को", "का", "कि", "मा", "र", "वा", "नयाँ", "पुरानो",
})


TOPIC_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "passport": {
        "keywords": ("passport", "rahadani", "राहदानी", "पासपोर्ट"),
        "domains": ("nepalpassport.gov.np",),
    },
    "citizenship": {
        "keywords": (
            "citizenship", "citizenship certificate", "citizen certificate",
            "nagarikta", "nagarikta certificate", "nagarikta pramanpatra",
            "नागरिकता", "नागरिकता प्रमाणपत्र",
        ),
        "domains": ("moha.gov.np",),
    },
    "pan_tax": {
        "keywords": ("pan", "vat", "ird", "tax", "taxpayer", "kar", "कर", "करदाता", "स्थायी लेखा"),
        "domains": ("ird.gov.np",),
    },
    "driving_license": {
        "keywords": ("driving", "license", "licence", "savari", "chalak", "सवारी", "चालक", "अनुमतिपत्र"),
        "domains": ("dotm.gov.np", "transportmanagement.gov.np"),
    },
    "birth_registration": {
        "keywords": (
            "birth", "janmadarta", "janma", "जन्म दर्ता", "जन्म",
            "जनमदता", "जनमदाता", "जनम दता", "जनमदर्ता", "जनम दर्ता",
            "जन्मदता", "जन्मदाता", "जन्म दता", "जन्मदरता", "जन्मदर्त",
            "जन्मदर्ल", "जन्मदार्त", "जन्मदार््त",
        ),
        "domains": ("donidcr.gov.np",),
    },
    "national_id": {
        "keywords": ("national id", "national", "identity", "id card", "परिचयपत्र", "राष्ट्रिय परिचयपत्र"),
        "domains": ("donidcr.gov.np",),
    },
    "vital_registration": {
        "keywords": (
            "vital registration", "civil registration", "event registration",
            "vital", "civil", "event", "events",
            "marriage", "death", "divorce", "separation",
            "relationship dissolution", "vivah", "mrityu", "panjikaran",
            "व्यक्तिगत घटना", "घटना दर्ता", "पञ्जीकरण", "पंजीकरण",
            "जन्मदर्ता", "मृत्युदर्ता", "विवाहदर्ता", "बसाइँसराइ",
            "जनमदता", "जनमदाता", "जनम दता", "जनमदर्ता", "जनम दर्ता",
            "जन्मदता", "जन्मदाता", "जन्म दता", "जन्मदरता", "जन्मदर्त",
            "जन्मदर्ल", "जन्मदार्त", "जन्मदार््त",
            "बसाईसराई", "सम्बन्धविच्छेद", "सम्बन्ध विच्छेद", "सम्बन्ध बिच्छेद", "विवाह", "मृत्यु",
        ),
        "domains": ("donidcr.gov.np",),
    },
    "company_registration": {
        "keywords": ("company", "ocr", "कम्पनी"),
        "domains": ("ocr.gov.np",),
    },
    "foreign_employment": {
        "keywords": (
            "foreign", "employment", "foreign employment", "shram", "labor",
            "labour", "labor permit", "labour permit", "वैदेशिक", "रोजगार",
            "वैदेशिक रोजगार", "श्रम", "श्रम स्वीकृति", "क्षतिपूर्ति",
            "मृत्युवरण", "manpower", "manpower agency", "recruitment agency",
            "recruiting agency", "employment agency", "complaint", "grievance",
            "ujuri", "म्यानपावर", "उजुरी", "गुनासो", "ठगी", "ठगिएको", "ठगेको",
        ),
        "domains": ("dofe.gov.np", "feb.gov.np"),
    },
    "consular": {
        "keywords": (
            "consular", "attestation", "attest", "document attestation",
            "power of attorney", "embassy", "कन्सुलर", "प्रमाणीकरण",
            "अधिकृत वारेशनामा", "राजदूतावास",
        ),
        "domains": ("mofa.gov.np", "nepalconsular.gov.np"),
    },
    "land": {
        "keywords": ("land", "jagga", "malpot", "जग्गा", "मालपोत"),
        "domains": ("dolma.gov.np", "molcpa.gov.np"),
    },
    "voter": {
        "keywords": ("voter", "matadata", "मतदाता"),
        "domains": ("election.gov.np",),
    },
    "police": {
        "keywords": ("police", "prahari", "clearance", "conduct", "character", "प्रहरी", "चालचलन", "चारित्रिक"),
        "domains": ("nepalpolice.gov.np",),
    },
    "banking": {
        "keywords": ("bank", "banking", "nrb", "remittance", "forex", "बैंक"),
        "domains": ("nrb.org.np",),
    },
        "municipality_contact": {
        "keywords": (
            "contact", "contact person", "person", "officials",
            "officer", "officers", "staff", "employee", "employees",
            "mayor", "deputy mayor", "information officer", "chief administrative",
            "phone", "email", "helpdesk", "help desk", "help-desk",
            "हेल्पडेस्क", "हेल्पडेष्क", "सहायता कक्ष", "सोधपुछ", "सोधपुछ कक्ष",
            "सम्पर्क", "फोन", "ईमेल", "पदाधिकारी",
            "कर्मचारी", "अधिकारी", "नगर प्रमुख", "उप प्रमुख", "सूचना अधिकारी", "प्रमुख प्रशासकीय",
        ),
        "domains": (),
    },
    "municipality_hours": {
        "keywords": (
            "office hours", "opening hours", "lunch break", "service hours",
            "कार्यालय समय", "सेवा समय", "खुल्ने समय",
        ),
        "domains": (),
    },
    "municipality_location": {
        "keywords": (
            "municipality office", "palika office", "nagarpalika office",
            "nagarpalika karyalaya", "office location", "office address",
            "नगरपालिका कार्यालय", "ठेगाना", "स्थान",
        ),
        "domains": (),
    },
    "municipality_services": {
        "keywords": (
            "municipality services", "available services", "what services",
            "main services", "service list", "नगरपालिका सेवा", "सेवा सूची",
            "सेवाहरु", "सेवाहरू",
        ),
        "domains": (),
    },
}

LOCALITY_DOMAIN_RULES: dict[str, tuple[str, ...]] = {
    "jiri": ("jirimun.gov.np",),
    "jirimun": ("jirimun.gov.np",),
    "जिरी": ("jirimun.gov.np",),
    "जिरि": ("jirimun.gov.np",),
    "dharmadevi": ("dharmadevimun.gov.np",),
    "dharmadevimun": ("dharmadevimun.gov.np",),
    "धर्मदेवी": ("dharmadevimun.gov.np",),
    "धर्मधेवी": ("dharmadevimun.gov.np",),
    "धर्मध्यपी": ("dharmadevimun.gov.np",),
    "धर्माधिपी": ("dharmadevimun.gov.np",),
    "धर्म देवी": ("dharmadevimun.gov.np",),
    "धर्मदेव": ("dharmadevimun.gov.np",),
    "धर्म देव": ("dharmadevimun.gov.np",),
}

ALL_LOCALITY_DOMAINS = tuple(
    dict.fromkeys(domain for domains in LOCALITY_DOMAIN_RULES.values() for domain in domains)
)

LOCALITY_DISPLAY_BY_DOMAIN: dict[str, dict[str, str]] = {
    "jirimun.gov.np": {
        "english": "Jiri Municipality",
        "roman_nepali": "Jiri Municipality",
        "devanagari": "जिरी नगरपालिका",
    },
    "dharmadevimun.gov.np": {
        "english": "Dharmadevi Municipality",
        "roman_nepali": "Dharmadevi Municipality",
        "devanagari": "धर्मदेवी नगरपालिका",
    },
}

LOCAL_TACIT_STRICT_TOPICS = frozenset({
    "municipality_hours",
    "municipality_location",
    "municipality_services",
})

LOCALITY_QUERY_TERMS = frozenset({
    "jiri", "jirimun", "जिरी", "dharmadevi", "dharmadevimun", "धर्मदेवी", "धर्मधेवी", "धर्मध्यपी", "धर्माधिपी", "धर्मदेव",
    "नगरपालिका", "nagarpalika", "municipality",
})

NOISY_URL_RE = re.compile(
    r"(annual[-_ ]?report|barshik|वार्षिक|report|प्रतिवेदन|press[-_ ]?release|"
    r"notice|career|vacancy|tender)",
    re.I,
)

TOPIC_STRONG_MARKERS: dict[str, tuple[str, ...]] = {
    "company_registration": (
        "ocr e-services",
        "online company registration",
        "new company registration",
        "create user",
        "office of company registrar",
    ),
    "driving_license": (
        "online driving license system",
        "applicant login",
        "age of an applicant",
        "trial",
        "re-trial",
    ),
    "national_id": (
        "pre-enrollment",
        "pre enrollment",
        "book an appointment",
        "biometric capture",
        "data collection",
        "विवरण संकलन",
        "दरखास्त",
        "जैविक",
    ),
    "municipality_contact": (
        "officials",
        "mayor",
        "deputy mayor",
        "chief administrative officer",
        "information officer",
        "contact no",
        "contact information",
        "पदाधिकारी",
        "नगर प्रमुख",
        "उप प्रमुख",
        "प्रमुख प्रशासकीय",
        "सूचना अधिकारी",
    ),
    "birth_registration": (
        "birth registration",
        "जन्म दर्ता",
        "जन्मदर्ता",
        "जनमदता",
        "जनमदाता",
        "जनमदर्ता",
        "जन्मदता",
        "जन्मदाता",
        "जन्मदर्ल",
        "जन्मदार्त",
        "व्यक्तिगत घटना",
        "घटना दर्ता",
        "स्थानीय पञ्जिकाधिकारी",
        "वडा कार्यालय",
    ),
    "vital_registration": (
        "vital registration",
        "civil registration",
        "event registration",
        "birth registration",
        "marriage registration",
        "death registration",
        "divorce",
        "जनमदता",
        "जनमदाता",
        "जनमदर्ता",
        "जन्मदता",
        "जन्मदाता",
        "जन्मदर्ल",
        "जन्मदार्त",
        "व्यक्तिगत घटना",
        "घटना दर्ता",
        "पञ्जीकरण",
        "विवाह दर्ता",
        "मृत्यु दर्ता",
        "सम्बन्ध विच्छेद",
        "सम्बन्ध बिच्छेद",
        "सम्बन्धविच्छेद",
        "स्थानीय पञ्जिकाधिकारी",
        "वडा कार्यालय",
    ),
    "municipality_hours": (
        "office hours",
        "10 am to 5 pm",
        "friday 10 am to 3 pm",
        "lunch break",
        "10:30",
        "कार्यालय समय",
        "सेवा समय",
    ),
    "municipality_location": (
        "jiri-1",
        "near the main bazaar",
        "old jiri hospital",
        "bus park",
        "signboard",
        "jiri nagarpalika karyalaya",
        "landmark",
        "ठेगाना",
        "स्थान",
    ),
    "municipality_services": (
        "main services",
        "citizenship recommendation",
        "birth, death, marriage",
        "land tax payment",
        "services offered",
        "service list",
        "सेवा सूची",
        "सेवाहरु",
        "सेवाहरू",
    ),
    "police": (
        "police clearance report",
        "police clearance",
        "clearance report",
        "character certificate",
        "चारित्रिक प्रमाणपत्र",
        "चारीत्रिक प्रमाणपत्र",
        "चालचलन प्रमाणपत्र",
        "अनलाईन निवेदन",
        "online application",
    ),
    "citizenship": (
        "duplicate citizenship",
        "citizenship duplicate",
        "lost citizenship",
        "नागरिकता प्रतिलिपि",
        "प्रतिलिपि नागरिकता",
        "नागरिकता हराएको",
        "हराएको",
        "बिग्रिएको",
        "झुत्रो",
        "वडा कार्यालयबाट प्रमाणित",
    ),
    "foreign_employment": (
        "foreign employment",
        "department of foreign employment",
        "dofe",
        "labor permit",
        "labour permit",
        "shram swikriti",
        "manpower",
        "manpower agency",
        "recruitment agency",
        "complaint",
        "grievance",
        "ujuri",
        "वैदेशिक रोजगार",
        "श्रम स्वीकृति",
        "म्यानपावर",
        "उजुरी",
        "गुनासो",
        "ठगी",
        "ठगिएको",
        "ठगेको",
    ),
}

TOPIC_NEGATIVE_MARKERS: dict[str, tuple[str, ...]] = {
    "birth_registration": (
        "national identity",
        "national id",
        "राष्ट्रिय परिचयपत्र",
        "परिचयपत्र विवरण",
    ),
    "vital_registration": (
        "national identity",
        "national id",
        "राष्ट्रिय परिचयपत्र",
        "परिचयपत्र विवरण",
    ),
}

TACIT_TOPIC_SERVICE_MARKERS: dict[str, tuple[str, ...]] = {
    "municipality_contact": (
        "municipality_contact",
        "contact_person",
        "official_contact",
        "सूचना अधिकारी",
        "पदाधिकारी",
    ),
    "birth_registration": (
        "birth_registration",
        "birth registration",
        "janma_darta",
        "janmadarta",
        "व्यक्तिगत घटना",
        "जन्म दर्ता",
        "panjikaran",
        "पञ्जीकरण",
    ),
    "vital_registration": (
        "vital_registration",
        "event_registration",
        "civil_registration",
        "birth_registration",
        "marriage_registration",
        "death_registration",
        "divorce_registration",
        "divorce",
        "panjikaran",
        "व्यक्तिगत घटना",
        "घटना दर्ता",
        "पञ्जीकरण",
        "सम्बन्ध विच्छेद",
        "सम्बन्ध बिच्छेद",
        "सम्बन्धविच्छेद",
    ),
    "citizenship": (
        "nagarikta",
        "citizenship",
        "नागरिकता",
    ),
    "passport": (
        "passport",
        "rahadani",
        "राहदानी",
    ),
    "pan_tax": (
        "pan",
        "vat",
        "ird",
        "taxpayer",
        "स्थायी लेखा",
        "करदाता",
    ),
    "driving_license": (
        "driving_license",
        "driving",
        "license",
        "licence",
        "सवारी",
        "चालक",
    ),
    "police": (
        "police",
        "prahari",
        "clearance",
        "conduct",
        "character",
        "प्रहरी",
    ),
    "land": (
        "land",
        "jagga",
        "malpot",
        "जग्गा",
        "मालपोत",
    ),
    "national_id": (
        "national_id",
        "national identity",
        "परिचयपत्र",
        "राष्ट्रिय परिचयपत्र",
    ),
    "company_registration": (
        "company",
        "company_registration",
        "ocr",
        "कम्पनी",
    ),
    "foreign_employment": (
        "foreign_employment",
        "employment",
        "labor",
        "labour",
        "shram",
        "manpower",
        "recruitment agency",
        "recruiting agency",
        "वैदेशिक",
        "श्रम",
    ),
    "voter": (
        "voter",
        "matadata",
        "मतदाता",
    ),
    "banking": (
        "bank",
        "banking",
        "nrb",
        "remittance",
        "बैंक",
    ),
    "municipality_hours": (
        "office_hours",
        "hours",
        "timing",
        "lunch",
        "staff arrival",
        "कार्यालय समय",
    ),
    "municipality_location": (
        "navigation",
        "location",
        "landmark",
        "address",
        "office_location",
        "ठेगाना",
        "स्थान",
    ),
    "municipality_services": (
        "services offered",
        "municipality_services",
        "service_list",
    ),
}


def _marker_hits(blob: str, markers: tuple[str, ...]) -> list[str]:
    return [m for m in markers if m.lower() in blob]


def _contact_query_role(question: str) -> str | None:
    q = question.lower()
    if "deputy mayor" in q or "उप प्रमुख" in question:
        return "Deputy Mayor"
    if "mayor" in q or "नगर प्रमुख" in question:
        return "Mayor"
    if "information officer" in q or "सूचना अधिकारी" in question:
        return "Information Officer"
    if "chief administrative" in q or "प्रमुख प्रशासकीय" in question:
        return "Chief Administrative Officer"
    return None


def _contact_query_wants_phone(question: str) -> bool:
    return bool(re.search(r"\b(phone|telephone|contact\s*no|number)\b", question, re.I)) or any(
        token in question for token in ("फोन", "नम्बर", "नंबर")
    )


def _contact_source_priority(query: str, row: dict | sqlite3.Row) -> int | None:
    topic = _detect_retrieval_topic(query)
    local_domains = _detect_local_domains(query)
    if topic != "municipality_contact" or not local_domains:
        return None
    host = (row["host"] if isinstance(row, sqlite3.Row) else row.get("host")) or ""
    if not _domain_matches(host, local_domains):
        return None
    url = (row["url"] if isinstance(row, sqlite3.Row) else row.get("url")) or ""
    text = (row["text"] if isinstance(row, sqlite3.Row) else row.get("text")) or ""
    url_l = urllib.parse.unquote(url).lower()
    text_l = text.lower()
    role = _contact_query_role(query)
    wants_phone = _contact_query_wants_phone(query)

    if wants_phone and ("/content/contact" in url_l or "contact no" in text_l):
        return 0
    if wants_phone and ("phone:" in text_l or "phone" in text_l or "फोन" in text):
        return 2
    if role == "Mayor" and (
        "mitra-bahadur-jirel" in url_l
        or ("mitra bahadur jirel" in text_l and "mayor" in text_l)
        or ("मित्र बहादुर जिरेल" in text and "नगर प्रमुख" in text)
    ):
        return 0
    if role == "Deputy Mayor" and (
        "krishnamaya-budhathoki" in url_l
        or ("krishnamaya" in text_l and "deputy mayor" in text_l)
        or ("कृष्णमाया" in text and "उप" in text)
    ):
        return 0
    if role == "Information Officer" and (
        "man-bahadur-jirel" in url_l
        or ("man bahadur jirel" in text_l and "information officer" in text_l)
        or ("मान बहादुर जिरेल" in text and "सूचना अधिकारी" in text)
    ):
        return 0
    if role == "Chief Administrative Officer" and (
        "raj-kumari-khatri" in url_l
        or ("raj kumari khatri" in text_l and "chief administrative" in text_l)
        or ("राज कुमारी खत्री" in text and "प्रमुख प्रशासकीय" in text)
    ):
        return 0
    if url_l.rstrip("/") in {
        "https://jirimun.gov.np",
        "https://jirimun.gov.np/en",
        "https://jirimun.gov.np/ne",
    }:
        return 1
    if "/content/contact" in url_l:
        return 1
    return None


def _foreign_employment_complaint_source_priority(row: dict | sqlite3.Row) -> int | None:
    host = (row["host"] if isinstance(row, sqlite3.Row) else row.get("host")) or ""
    url = (row["url"] if isinstance(row, sqlite3.Row) else row.get("url")) or ""
    text = (row["text"] if isinstance(row, sqlite3.Row) else row.get("text")) or ""
    blob = f"{host} {url} {text}".lower()
    if not _domain_matches(host, ("dofe.gov.np", "feb.gov.np", "moless.gov.np")):
        return None
    if _domain_matches(host, ("feb.gov.np",)) and (
        "आफू ठगिएको" in text
        or ("ठग" in text and "उजुरी" in text)
    ):
        if "inner_prawas_diary" in url.lower():
            return 0
        return 2
    if _domain_matches(host, ("feb.gov.np",)) and (
        "श्रमाधान कल सेन्टर नम्बर ११४१" in text
        or "श्रमाधान कल सेन्टर नम्बर 1141" in text
        or (("११४१" in text or "1141" in text) and ("गुनासो" in text or "समस्या" in text))
    ):
        return 1
    if _domain_matches(host, ("feb.gov.np",)) and ("उजुरी" in text or "गुनासो" in text):
        return 3
    if _domain_matches(host, ("dofe.gov.np",)) and ("कसुर" in text or "उजुरी" in text or "complaint" in blob):
        return 4
    if _domain_matches(host, ("moless.gov.np",)) and ("वैदेशिक रोजगार" in text and ("उजुरी" in text or "श्रम" in text)):
        return 5
    if _domain_matches(host, ("dofe.gov.np",)) and ("रसिद" in text or "public-important" in blob):
        return 6
    return None


def _tokenize_retrieval_text(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[\wऀ-ॿ]+", text) if t]


def _domain_matches(host: str | None, domains: tuple[str, ...]) -> bool:
    if not host:
        return False
    h = host.lower().strip()
    return any(h == d or h.endswith("." + d) for d in domains)


def _authority_domains_for_query(topic: str | None, query: str) -> tuple[str, ...]:
    domains = TOPIC_RULES.get(topic or "", {}).get("domains", ())
    q_l = query.lower()
    if topic == "passport":
        wants_abroad = any(marker in q_l for marker in (
            "abroad", "embassy", "consulate", "qatar", "doha", "foreign country",
            "outside nepal",
        )) or any(marker in query for marker in ("कतार", "दोहा", "विदेश", "राजदूतावास"))
        if wants_abroad:
            if "qatar" in q_l or "doha" in q_l or "कतार" in query or "दोहा" in query:
                return ("qa.nepalembassy.gov.np", "mofa.gov.np", "nepalpassport.gov.np")
            return ("mofa.gov.np", "nepalpassport.gov.np")
        return domains
    if topic == "driving_license":
        wants_pokhara = any(marker in q_l for marker in ("pokhara", "kaski", "gandaki")) or any(
            marker in query for marker in ("पोखरा", "कास्की", "गण्डकी")
        )
        if wants_pokhara:
            return ("tmolkaski.gandaki.gov.np", "dlo.gandaki.gov.np", "dotm.gov.np", "transportmanagement.gov.np")
        return domains
    if topic != "foreign_employment":
        return domains

    if _foreign_employment_query_wants_complaint(query):
        return ("dofe.gov.np", "feb.gov.np", "moless.gov.np")

    wants_welfare = any(marker in q_l for marker in (
        "welfare", "compensation", "death", "dead", "claim", "insurance",
        "body transport", "medical", "scholarship",
    )) or any(marker in query for marker in (
        "क्षतिपूर्ति", "मृत्यु", "अंगभंग", "कल्याण", "बीमा", "दाबी", "शव",
    ))
    wants_labor_permit = any(marker in q_l for marker in (
        "labor permit", "labour permit", "work permit", "shram swikriti",
        "shram sweekriti", "apply for a labor", "apply for labour", "permit",
    )) or any(marker in query for marker in (
        "श्रम स्वीकृति", "श्रमस्वीकृति", "वैदेशिक रोजगार अनुमति", "अनुमति",
    ))
    if wants_labor_permit and not wants_welfare:
        return ("dofe.gov.np", "feims.dofe.gov.np")
    if wants_welfare:
        return ("feb.gov.np", "dofe.gov.np")
    return domains


def _detect_retrieval_topic(query: str) -> str | None:
    q_lower = query.lower()
    q_tokens = set(_tokenize_retrieval_text(query))
    best_topic: str | None = None
    best_score = 0
    for topic, rule in TOPIC_RULES.items():
        score = 0
        for kw in rule["keywords"]:
            kw_l = kw.lower()
            has_devanagari = any("ऀ" <= c <= "ॿ" for c in kw_l)
            if has_devanagari or " " in kw_l:
                matched = kw_l in q_lower
            else:
                matched = kw_l in q_tokens
            if matched:
                # Longer/specific keywords beat short generic ones like "कर".
                if " " in kw_l:
                    score += 4
                elif has_devanagari:
                    score += max(1, min(4, len(kw_l) // 2))
                else:
                    score += 2 if len(kw_l) >= 5 else 1
        if score > best_score:
            best_topic = topic
            best_score = score
    return best_topic


def _detect_local_domains(query: str) -> tuple[str, ...]:
    q_lower = query.lower()
    q_tokens = set(_tokenize_retrieval_text(query))
    domains: list[str] = []
    for keyword, keyword_domains in LOCALITY_DOMAIN_RULES.items():
        kw_l = keyword.lower()
        if kw_l in q_tokens or keyword in query or kw_l in q_lower:
            for domain in keyword_domains:
                if domain not in domains:
                    domains.append(domain)
    for domain in re.findall(r"\b[a-z0-9.-]+\.(?:gov|org)\.np\b", q_lower):
        if domain not in domains:
            domains.append(domain)
    return tuple(domains)


def _retrieval_token_variants(token: str) -> list[str]:
    variants = [token]
    # Common Nepali postpositions attach directly to Devanagari nouns:
    # नागरिकताको -> नागरिकता, जन्मदर्ताको -> जन्मदर्ता.
    if any("ऀ" <= c <= "ॿ" for c in token):
        for suffix in ("को", "का", "की", "मा", "ले", "लाई", "बाट"):
            if token.endswith(suffix) and len(token) > len(suffix) + 1:
                stem = token[: -len(suffix)]
                if stem not in variants:
                    variants.append(stem)
    return variants


def _passport_query_wants_apply_process(query: str) -> bool:
    q = query.lower()
    if any(term in q for term in ("fee", "cost", "charge", "price", "renew", "renewal", "lost", "replace", "status")):
        return False
    if any(term in query for term in ("दस्तुर", "शुल्क", "नवीकरण", "नविकरण", "हराएको", "प्रतिलिपि", "स्थिति")):
        return False
    return any(term in q for term in ("how", "apply", "get", "make", "banaune", "banauna", "kasari")) or any(
        term in query for term in ("कसरी", "बनाउने", "बनाउन", "लिने", "आवेदन")
    )


def _foreign_employment_query_wants_complaint(query: str) -> bool:
    q = query.lower()
    return any(
        marker in q
        for marker in (
            "complaint", "complain", "grievance", "fraud", "cheat", "cheated",
            "scam", "thagi", "thagiyeko", "thageko", "thagyo", "thag", "ujuri",
            "gunaso",
        )
    ) or any(
        marker in query
        for marker in ("उजुरी", "गुनासो", "ठगी", "ठगिएको", "ठगेको", "ठग्यो", "ठग")
    )


def _expanded_retrieval_tokens(query: str) -> list[str]:
    raw_tokens = _tokenize_retrieval_text(re.sub(r"[^\w\sऀ-ॿ]+", " ", query))
    filtered: list[str] = []
    for raw in raw_tokens:
        for t in _retrieval_token_variants(raw):
            if len(t) >= 2 and t not in RETRIEVAL_STOPWORDS and t not in filtered:
                filtered.append(t)
    # If the user typed only generic words, keep a non-empty query rather than
    # making retrieval impossible.
    if not filtered:
        filtered = [t for t in raw_tokens if len(t) >= 2]

    expanded: list[str] = []
    for t in filtered:
        if t not in expanded:
            expanded.append(t)
        for extra in BILINGUAL_ANCHORS.get(t, ()):
            for sub in _tokenize_retrieval_text(extra):
                if len(sub) >= 2 and sub not in expanded:
                    expanded.append(sub)
    topic = _detect_retrieval_topic(query)
    if topic == "foreign_employment" and _foreign_employment_query_wants_complaint(query):
        for extra in (
            "foreign employment complaint",
            "department of foreign employment complaint",
            "foreign employment board grievance",
            "labor call center",
            "call center",
            "1141",
            "receipt evidence complaint",
            "वैदेशिक रोजगार उजुरी",
            "वैदेशिक रोजगार विभाग उजुरी",
            "वैदेशिक रोजगार बोर्ड गुनासो",
            "श्रम कल सेन्टर",
            "गुनासो समस्या",
            "११४१",
            "रसिद प्रमाण कागजात",
        ):
            for sub in _tokenize_retrieval_text(extra):
                if len(sub) >= 2 and sub not in expanded:
                    expanded.append(sub)
    if topic == "passport" and _passport_query_wants_apply_process(query):
        for extra in (
            "ordinary electronic passport",
            "pre enrolment form",
            "pre-enrolment form",
            "appointment",
            "enrolment centre",
            "online form",
            "साधारण विद्युतीय राहदानी",
            "अनलाइन फाराम",
            "आवेदन केन्द्र",
            "प्रक्रिया",
        ):
            for sub in _tokenize_retrieval_text(extra):
                if len(sub) >= 2 and sub not in expanded:
                    expanded.append(sub)
    if topic == "national_id":
        for extra in ("pre-enrollment", "appointment", "biometric", "capture", "विवरण", "संकलन", "दरखास्त"):
            for sub in _tokenize_retrieval_text(extra):
                if len(sub) >= 2 and sub not in expanded:
                    expanded.append(sub)
    return expanded


def _retrieval_rank_features(query: str, row: sqlite3.Row, initial_rank: int) -> dict:
    topic = _detect_retrieval_topic(query)
    expected_domains = _authority_domains_for_query(topic, query) if topic else ()
    local_domains = _detect_local_domains(query)
    host = row["host"] or ""
    url = row["url"] or ""
    title = row["title"] or ""
    text = row["text"] or ""
    blob = f"{host} {url} {title} {text}".lower()

    query_terms = [
        t.lower() for t in _expanded_retrieval_tokens(query)
        if t not in RETRIEVAL_STOPWORDS
    ]
    matched_terms = sorted({t for t in query_terms if t and t in blob})
    coverage_den = max(1, min(6, len(set(query_terms))))
    coverage = min(1.0, len(matched_terms) / coverage_den)

    domain_match = _domain_matches(host, expected_domains)
    domain_boost = 7.5 if domain_match else 0.0
    domain_penalty = -2.0 if topic and expected_domains and not domain_match else 0.0
    local_match = _domain_matches(host, local_domains)

    noisy_blob = f"{url} {title}"
    noisy_penalty = -1.5 if NOISY_URL_RE.search(noisy_blob) else 0.0
    strong_hits = _marker_hits(blob, TOPIC_STRONG_MARKERS.get(topic or "", ()))
    negative_hits = _marker_hits(blob, TOPIC_NEGATIVE_MARKERS.get(topic or "", ()))
    local_boost = 0.0
    if local_match:
        if not topic or topic in LOCAL_TACIT_STRICT_TOPICS or topic == "municipality_contact" or strong_hits:
            local_boost = 7.5
        else:
            # A municipality domain is useful context, but a random local PDF
            # must not outrank DONIDCR/MoHA/etc for a service procedure unless
            # it contains topic-specific markers.
            local_boost = 1.0
    topic_boost = 0.0
    if strong_hits:
        topic_boost += min(7.0, 3.5 + 1.25 * len(strong_hits))
    if topic == "municipality_contact":
        title_l = title.lower()
        url_l = url.lower()
        q_l = query.lower()
        role = _contact_query_role(query)
        wants_phone = _contact_query_wants_phone(query)
        if url_l.endswith(".pdf") or "/files/" in url_l:
            topic_boost -= 4.0
        if "contact" in title_l or "/content/contact" in url_l:
            topic_boost += 2.5
        if wants_phone:
            if "/content/contact" in url_l and ("contact no" in blob or "phone" in blob or "फोन" in text):
                topic_boost += 7.0
            elif "contact no" in blob:
                topic_boost += 5.0
            elif "phone:" in blob or "फोन" in text:
                topic_boost += 1.0
        if role == "Mayor":
            if "mayor" in blob or "नगर प्रमुख" in text or "mitra bahadur" in blob or "मित्र बहादुर" in text:
                topic_boost += 8.0
            elif "information officer" in blob or "सूचना अधिकारी" in text:
                topic_boost -= 3.0
        elif role == "Deputy Mayor":
            if "deputy mayor" in blob or "उप प्रमुख" in text or "krishnamaya" in blob or "कृष्णमाया" in text:
                topic_boost += 8.0
            elif "information officer" in blob or "सूचना अधिकारी" in text:
                topic_boost -= 2.0
        elif role == "Information Officer":
            if "information officer" in blob or "सूचना अधिकारी" in text or "man bahadur" in blob or "मान बहादुर" in text:
                topic_boost += 8.0
        elif role == "Chief Administrative Officer":
            if "chief administrative" in blob or "प्रमुख प्रशासकीय" in text or "raj kumari" in blob or "राज कुमारी" in text:
                topic_boost += 8.0
        if (
            role is None
            and (
                "contact person" in q_l
                or "who is" in q_l
                or "officer" in q_l
                or "official" in q_l
                or "पदाधिकारी" in query
                or "सूचना अधिकारी" in query
            )
        ):
            if (
                "information officer" in blob
                or "सूचना अधिकारी" in text
                or "officials" in blob
                or "पदाधिकारी" in text
                or "कर्मचारी" in text
            ):
                topic_boost += 6.0
        contact_priority = _contact_source_priority(query, row)
        if contact_priority is not None:
            topic_boost += 5.0 - contact_priority
        if url_l.rstrip("/") in {
            "https://jirimun.gov.np/en",
            "https://jirimun.gov.np",
            "https://jirimun.gov.np/ne",
        }:
            topic_boost += 2.0
    if topic == "passport" and (
        "fee" in query.lower()
        or "cost" in query.lower()
        or "charge" in query.lower()
        or "शुल्क" in query
        or "दस्तुर" in query
    ):
        if "/process/-41" in url or "राहदानी दस्तुर" in blob:
            topic_boost += 9.0
        elif ("दस्तुर" in blob or "शुल्क" in blob) and "राहदानी" in blob:
            topic_boost += 4.0
    if topic == "passport":
        q_l = query.lower()
        url_l = url.lower()
        if _passport_query_wants_apply_process(query):
            if (
                "/ne/process/-4" in url_l
                or "साधारण विद्युतीय राहदानी बनाउने प्रक्रिया" in blob
                or "pre-enrolment form" in blob
                or "pre-enrollment form" in blob
                or "enrolment centre" in blob
                or "enrollment centre" in blob
            ):
                topic_boost += 16.0
            elif "/process/-10" in url_l and ("समय" in blob or "time" in blob):
                topic_boost -= 5.0
        wants_abroad = any(marker in q_l for marker in (
            "abroad", "embassy", "consulate", "qatar", "doha", "outside nepal",
        )) or any(marker in query for marker in ("कतार", "दोहा", "विदेश", "राजदूतावास"))
        if wants_abroad:
            if "nepalembassy.gov.np" in host:
                topic_boost += 3.0
            elif "mofa.gov.np" in host:
                topic_boost += 2.0
            if ("qatar" in q_l or "doha" in q_l or "कतार" in query or "दोहा" in query) and host == "qa.nepalembassy.gov.np":
                topic_boost += 2.0
            if "pages/passport" in url_l or "राहदानी" in text:
                topic_boost += 14.0
            elif "pages/contact" in url_l or "contact-detail" in url_l or "सम्पर्क" in text:
                topic_boost += 12.0
            elif "consular" in url_l or "कन्सुलर" in text:
                topic_boost += 6.0
            if "/carousel-detail/" in url_l or "/gallery/" in url_l or "courtesy call" in blob:
                topic_boost -= 10.0
            if "sponsorship-change" in url_l:
                topic_boost -= 8.0
    if topic == "foreign_employment" and domain_match and _foreign_employment_query_wants_complaint(query):
        url_l = url.lower()
        if "1141" in blob or "११४१" in blob:
            topic_boost += 12.0
        if "उजुरी" in blob or "गुनासो" in blob or "complaint" in blob or "grievance" in blob:
            topic_boost += 8.0
        if "ठगी" in blob or "ठगे" in blob or "fraud" in blob or "cheat" in blob:
            topic_boost += 7.0
        if ("रसिद" in blob or "receipt" in blob) and ("प्रमाण" in blob or "evidence" in blob or "कागजात" in blob):
            topic_boost += 6.0
        if "feb.gov.np" in host and ("गुनासो" in blob or "1141" in blob or "११४१" in blob):
            topic_boost += 5.0
        if "dofe.gov.np" in host and ("public-important" in url_l or "कसुर" in blob):
            topic_boost += 4.0
        if urllib.parse.urlsplit(url_l).path.strip("/") in {"", "home"} and not ("1141" in blob or "११४१" in blob):
            topic_boost -= 4.0
    if topic == "driving_license":
        q_l = query.lower()
        wants_pokhara = any(marker in q_l for marker in ("pokhara", "kaski", "gandaki")) or any(
            marker in query for marker in ("पोखरा", "कास्की", "गण्डकी")
        )
        if wants_pokhara:
            if host in {"tmolkaski.gandaki.gov.np", "dlo.gandaki.gov.np"}:
                topic_boost += 10.0
            if "pokhara" in blob or "पोखरा" in text or "kaski" in blob or "कास्की" in text:
                topic_boost += 4.0
            if host.endswith(".moha.gov.np"):
                topic_boost -= 8.0
    if topic == "police" and domain_match:
        url_l = url.lower()
        if "clearance" in url_l or "चारित्रिक प्रमाणपत्र" in blob or "चारीत्रिक प्रमाणपत्र" in blob:
            topic_boost += 8.0
        if urllib.parse.urlsplit(url_l).path.strip("/") in {"", "home"}:
            topic_boost -= 5.0
    if topic == "citizenship" and domain_match:
        q_l = query.lower()
        wants_duplicate = (
            "lost" in q_l
            or "duplicate" in q_l
            or "replace" in q_l
            or "replacement" in q_l
            or "प्रतिलिपि" in query
            or "हराए" in query
            or "हराएको" in query
        )
        if wants_duplicate:
            url_l = url.lower()
            if (
                "नागरिकता प्रतिलिपि" in blob
                or "प्रतिलिपि नागरिकता" in blob
                or "नागरिकता हराएको" in blob
                or "duplicate citizenship" in blob
            ):
                topic_boost += 9.0
            if "/page/" in url_l or "/service/" in url_l:
                topic_boost += 3.0
            if (url_l.endswith(".pdf") or "/upload/" in url_l or "/files/" in url_l) and not (
                "प्रतिलिपि" in blob and "हराएको" in blob
            ):
                topic_boost -= 4.0
    if topic in {"birth_registration", "vital_registration"} and domain_match:
        if "registration" in url.lower() or "pajikaran" in url.lower():
            topic_boost += 1.5
        if negative_hits and not strong_hits:
            topic_boost -= 6.0
    if topic in LOCAL_TACIT_STRICT_TOPICS and local_match:
        if strong_hits:
            topic_boost += min(5.0, 2.0 + 1.0 * len(strong_hits))
        else:
            topic_boost -= 1.0

    # Preserve BM25's ordering signal without letting one generic token dominate.
    fts_order_bonus = max(0.0, 4.0 - 0.05 * (initial_rank - 1))
    lexical_bonus = 5.0 * coverage
    rank_score = (
        fts_order_bonus + lexical_bonus + domain_boost + domain_penalty
        + local_boost + noisy_penalty + topic_boost
    )

    if domain_match or local_match:
        relevance = "high"
    elif coverage >= 0.50 and rank_score >= 5.0:
        relevance = "medium"
    else:
        relevance = "low"

    return {
        "topic": topic,
        "expected_domains": list(expected_domains),
        "local_domains": list(local_domains),
        "domain_match": domain_match,
        "local_match": local_match,
        "matched_terms": matched_terms[:12],
        "coverage": round(coverage, 3),
        "domain_boost": domain_boost,
        "domain_penalty": domain_penalty,
        "local_boost": local_boost,
        "noisy_penalty": noisy_penalty,
        "topic_boost": round(topic_boost, 3),
        "strong_hits": strong_hits[:6],
        "negative_hits": negative_hits[:6],
        "rank_score": round(rank_score, 3),
        "relevance": relevance,
    }


# ---- Retrieval (SQLite + FTS5) --------------------------------------------


class Retriever:
    """Reads from the crawler_v2 SQLite db. Uses FTS5 over chunks.text.

    Schema (from crawler_v2):
        chunks(chunk_id PK TEXT, doc_id TEXT, chunk_index, text, language, ...)
        documents(doc_id PK TEXT, source_id TEXT, url, ...)
        sources(source_id PK TEXT, host TEXT, ...)
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        if not db_path.exists():
            raise FileNotFoundError(f"DB not found at {db_path}")
        self._ensure_fts()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _has_fts(self, c: sqlite3.Connection) -> bool:
        cur = c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
        )
        return cur.fetchone() is not None

    def _ensure_fts(self) -> None:
        with self._conn() as c:
            if self._has_fts(c):
                return
            LOG.info("FTS5 chunks_fts not found — building (one-time, may take a minute)")
            # Standalone FTS5 with chunk_id stored as UNINDEXED so we can join
            # back to chunks/documents. Skip the auto-sync triggers — the corpus
            # only changes via the crawler, and a manual /admin/reindex is fine.
            c.executescript("""
                CREATE VIRTUAL TABLE chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    text,
                    tokenize="unicode61 remove_diacritics 0"
                );
                INSERT INTO chunks_fts(chunk_id, text)
                    SELECT chunk_id, text FROM chunks;
            """)
            c.commit()
            LOG.info("FTS5 built.")

    def reindex(self) -> dict:
        """Drop and rebuild FTS5. Use for --admin/reindex."""
        with self._conn() as c:
            c.execute("DROP TABLE IF EXISTS chunks_fts")
            c.commit()
        self._ensure_fts()
        with self._conn() as c:
            n = c.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
        return {"chunks_in_fts": n}

    def search(self, query: str, top_k: int = TOP_K) -> list[dict]:
        """Return top-K chunks ranked by FTS5 bm25.

        Token strategy: lowercase ASCII, drop retrieval stopwords, wrap each
        token in double quotes (FTS5 phrase syntax) and OR them together.
        Wrapping in quotes neutralises FTS5 reserved chars in the token; OR
        means at least one token must match. We over-fetch by BM25, then apply
        a small topic/domain reranker so an IRD/PAN query does not lose to a
        random PDF that matched the word "number".

        Cross-language hack: the corpus is ~90% Devanagari but citizens type
        in English/Roman-NE too. We expand each English/Roman-NE token via a
        small anchor map to its Devanagari equivalent before FTS, so a query
        like "lost citizenship certificate" hits the same chunks as
        "नागरिकता प्रमाणपत्र हराएमा" by virtue of the OR-union."""
        search_topic = _detect_retrieval_topic(query)
        search_local_domains = _detect_local_domains(query)
        if search_topic == "municipality_contact" and search_local_domains:
            placeholders = ", ".join("?" for _ in search_local_domains)
            direct_sql = f"""
                SELECT chunks.chunk_id AS chunk_id, chunks.text AS text,
                       documents.url AS url, documents.title AS title,
                       documents.doc_type AS doc_type,
                       documents.source_id AS source_id,
                       sources.domain AS host, sources.tier AS tier,
                       0.0 AS score
                FROM chunks
                JOIN documents ON documents.doc_id = chunks.doc_id
                JOIN sources   ON sources.source_id = documents.source_id
                WHERE sources.domain IN ({placeholders})
                  AND documents.superseded_by IS NULL
                  AND documents.removed_at IS NULL
                  AND (
                    lower(documents.url) IN (
                      'https://' || lower(sources.domain),
                      'https://' || lower(sources.domain) || '/',
                      'https://' || lower(sources.domain) || '/en',
                      'https://' || lower(sources.domain) || '/ne'
                    )
                    OR lower(documents.url) LIKE '%contact%'
                    OR lower(documents.url) LIKE '%mitra-bahadur%'
                    OR lower(documents.url) LIKE '%krishnamaya%'
                    OR lower(documents.url) LIKE '%man-bahadur%'
                    OR lower(documents.url) LIKE '%raj-kumari%'
                    OR lower(documents.title) LIKE '%contact%'
                    OR lower(chunks.text) LIKE '%contact%'
                    OR lower(chunks.text) LIKE '%phone%'
                    OR lower(chunks.text) LIKE '%mayor%'
                    OR lower(chunks.text) LIKE '%deputy mayor%'
                    OR lower(chunks.text) LIKE '%information officer%'
                    OR lower(chunks.text) LIKE '%chief administrative%'
                    OR lower(chunks.text) LIKE '%mitra bahadur%'
                    OR lower(chunks.text) LIKE '%krishnamaya%'
                    OR lower(chunks.text) LIKE '%man bahadur%'
                    OR lower(chunks.text) LIKE '%raj kumari%'
                    OR chunks.text LIKE '%फोन%'
                    OR chunks.text LIKE '%सम्पर्क%'
                    OR chunks.text LIKE '%आधिकारिक मेल%'
                    OR chunks.text LIKE '%कर्मचारी%'
                    OR chunks.text LIKE '%सूचना अधिकारी%'
                    OR chunks.text LIKE '%पदाधिकारी%'
                    OR chunks.text LIKE '%नगर प्रमुख%'
                    OR chunks.text LIKE '%उप प्रमुख%'
                    OR chunks.text LIKE '%प्रमुख प्रशासकीय%'
                    OR chunks.text LIKE '%मित्र बहादुर%'
                    OR chunks.text LIKE '%कृष्णमाया%'
                    OR chunks.text LIKE '%मान बहादुर%'
                    OR chunks.text LIKE '%राज कुमारी%'
                  )
                ORDER BY
                  CASE
                    WHEN lower(documents.url) LIKE '%/content/contact%' AND lower(chunks.text) LIKE '%contact no%' THEN 0
                    WHEN lower(documents.url) LIKE '%/content/contact%' THEN 1
                    WHEN lower(documents.url) LIKE '%contact%' THEN 2
                    WHEN chunks.text LIKE '%आधिकारिक मेल%' THEN 3
                    WHEN chunks.text LIKE '%सूचना अधिकारी%' THEN 4
                    WHEN lower(chunks.text) LIKE '%phone%' THEN 5
                    WHEN chunks.text LIKE '%फोन%' THEN 5
                    ELSE 6
                  END,
                  documents.url,
                  chunks.chunk_index
                LIMIT ?
            """
            with self._conn() as c:
                direct_rows = c.execute(
                    direct_sql,
                    (*search_local_domains, max(top_k * 8, 24)),
                ).fetchall()
            if direct_rows:
                candidates: list[dict] = []
                for initial_rank, r in enumerate(direct_rows, 1):
                    features = _retrieval_rank_features(query, r, initial_rank)
                    candidates.append({
                        "chunk_id": r["chunk_id"],
                        "url": r["url"],
                        "host": r["host"],
                        "source_id": r["source_id"],
                        "title": r["title"],
                        "doc_type": r["doc_type"],
                        "tier": r["tier"],
                        "text": (r["text"] or "")[:CHUNK_TEXT_MAX_CHARS],
                        "rank": initial_rank,
                        "score": float(r["score"]) if r["score"] is not None else 0.0,
                        "rank_score": features["rank_score"],
                        "relevance": features["relevance"],
                        "features": features,
                    })
                candidates.sort(key=lambda r: (-r["rank_score"], r["score"], r["rank"]))
                out: list[dict] = []
                seen_urls: set[str] = set()
                for r in candidates:
                    url_key = normalize_url(r.get("url") or "") or r.get("chunk_id") or ""
                    if url_key in seen_urls:
                        continue
                    seen_urls.add(url_key)
                    r = dict(r)
                    r["rank"] = len(out) + 1
                    out.append(r)
                    if len(out) >= top_k:
                        break
                return out

        expanded = _expanded_retrieval_tokens(query)
        if not expanded:
            return []
        # quote tokens for FTS5 phrase syntax
        tokens: list[str] = []
        for t in expanded:
            t = t.replace('"', '""')
            tokens.append(f'"{t}"')
        if not tokens:
            return []
        fts_query = " OR ".join(tokens)
        candidate_limit = max(top_k * 64, 320)
        if search_topic == "municipality_contact" and search_local_domains:
            candidate_limit = max(candidate_limit, 768)
        with self._conn() as c:
            try:
                rows = c.execute(
                    """
                    SELECT
                        chunks.chunk_id  AS chunk_id,
                        chunks.text      AS text,
                        documents.url    AS url,
                        documents.title  AS title,
                        documents.doc_type AS doc_type,
                        documents.source_id AS source_id,
                        sources.domain   AS host,
                        sources.tier     AS tier,
                        bm25(chunks_fts) AS score
                    FROM chunks_fts
                    JOIN chunks    ON chunks.chunk_id = chunks_fts.chunk_id
                    JOIN documents ON documents.doc_id = chunks.doc_id
                    JOIN sources   ON sources.source_id = documents.source_id
                    WHERE chunks_fts MATCH ?
                      AND documents.superseded_by IS NULL
                      AND documents.removed_at IS NULL
                    ORDER BY score
                    LIMIT ?
                    """,
                    (fts_query, candidate_limit),
                ).fetchall()
            except sqlite3.OperationalError as e:
                cleaned = re.sub(r'[^\w\sऀ-ॿ]+', ' ', query).strip()
                LOG.warning("FTS5 query failed for %r: %s — falling back to LIKE", cleaned, e)
                rows = c.execute(
                    """
                    SELECT chunks.chunk_id AS chunk_id, chunks.text AS text,
                           documents.url AS url, documents.title AS title,
                           documents.doc_type AS doc_type,
                           documents.source_id AS source_id,
                           sources.domain AS host, sources.tier AS tier,
                           0.0 AS score
                    FROM chunks
                    JOIN documents ON documents.doc_id = chunks.doc_id
                    JOIN sources   ON sources.source_id = documents.source_id
                    WHERE chunks.text LIKE ?
                      AND documents.superseded_by IS NULL
                      AND documents.removed_at IS NULL
                    LIMIT ?
                    """,
                    (f"%{cleaned[:40]}%", candidate_limit),
                ).fetchall()

        candidates: list[dict] = []
        for initial_rank, r in enumerate(rows, 1):
            features = _retrieval_rank_features(query, r, initial_rank)
            candidates.append({
                "chunk_id": r["chunk_id"],
                "url": r["url"],
                "host": r["host"],
                "source_id": r["source_id"],
                "title": r["title"],
                "doc_type": r["doc_type"],
                "tier": r["tier"],
                "text": (r["text"] or "")[:CHUNK_TEXT_MAX_CHARS],
                "rank": initial_rank,
                "score": float(r["score"]) if r["score"] is not None else 0.0,
                "rank_score": features["rank_score"],
                "relevance": features["relevance"],
                "features": features,
            })

        expected_domains = _authority_domains_for_query(search_topic, query) if search_topic else ()
        if expected_domains:
            domain_clauses: list[str] = []
            params: list[Any] = [fts_query]
            for domain in expected_domains:
                d = domain.lower().strip()
                if not d:
                    continue
                domain_clauses.append("(lower(sources.domain) = ? OR lower(sources.domain) LIKE ?)")
                params.extend([d, f"%.{d}"])
            if domain_clauses:
                authority_sql = f"""
                    SELECT
                        chunks.chunk_id  AS chunk_id,
                        chunks.text      AS text,
                        documents.url    AS url,
                        documents.title  AS title,
                        documents.doc_type AS doc_type,
                        documents.source_id AS source_id,
                        sources.domain   AS host,
                        sources.tier     AS tier,
                        bm25(chunks_fts) AS score
                    FROM chunks_fts
                    JOIN chunks    ON chunks.chunk_id = chunks_fts.chunk_id
                    JOIN documents ON documents.doc_id = chunks.doc_id
                    JOIN sources   ON sources.source_id = documents.source_id
                    WHERE chunks_fts MATCH ?
                      AND ({' OR '.join(domain_clauses)})
                      AND documents.superseded_by IS NULL
                      AND documents.removed_at IS NULL
                    ORDER BY score
                    LIMIT ?
                """
                params.append(max(top_k * 8, 32))
                try:
                    with self._conn() as c:
                        authority_rows = c.execute(authority_sql, params).fetchall()
                except sqlite3.OperationalError as e:
                    LOG.warning("authority-domain supplement failed for %r: %s", query, e)
                    authority_rows = []
                seen_chunk_ids = {r["chunk_id"] for r in candidates}
                for extra_offset, r in enumerate(authority_rows, len(rows) + 1):
                    if r["chunk_id"] in seen_chunk_ids:
                        continue
                    seen_chunk_ids.add(r["chunk_id"])
                    features = _retrieval_rank_features(query, r, extra_offset)
                    candidates.append({
                        "chunk_id": r["chunk_id"],
                        "url": r["url"],
                        "host": r["host"],
                        "source_id": r["source_id"],
                        "title": r["title"],
                        "doc_type": r["doc_type"],
                        "tier": r["tier"],
                        "text": (r["text"] or "")[:CHUNK_TEXT_MAX_CHARS],
                        "rank": extra_offset,
                        "score": float(r["score"]) if r["score"] is not None else 0.0,
                        "rank_score": features["rank_score"],
                        "relevance": features["relevance"],
                        "features": features,
                    })

        if search_local_domains:
            root_urls: list[str] = []
            for domain in search_local_domains:
                d = domain.lower().strip("/")
                host_variants = [d]
                if not d.startswith("www."):
                    host_variants.append(f"www.{d}")
                for host in host_variants:
                    for path in ("", "/", "/en", "/en/", "/ne", "/ne/"):
                        root_urls.append(f"https://{host}{path}")
            domain_placeholders = ", ".join("?" for _ in search_local_domains)
            url_placeholders = ", ".join("?" for _ in root_urls)
            local_root_sql = f"""
                SELECT chunks.chunk_id AS chunk_id, chunks.text AS text,
                       documents.url AS url, documents.title AS title,
                       documents.doc_type AS doc_type,
                       documents.source_id AS source_id,
                       sources.domain AS host, sources.tier AS tier,
                       0.0 AS score
                FROM chunks
                JOIN documents ON documents.doc_id = chunks.doc_id
                JOIN sources   ON sources.source_id = documents.source_id
                WHERE sources.domain IN ({domain_placeholders})
                  AND lower(documents.url) IN ({url_placeholders})
                  AND documents.superseded_by IS NULL
                  AND documents.removed_at IS NULL
                ORDER BY documents.url, chunks.chunk_index
                LIMIT ?
            """
            with self._conn() as c:
                local_root_rows = c.execute(
                    local_root_sql,
                    (*search_local_domains, *root_urls, 24),
                ).fetchall()
            seen_chunk_ids = {r["chunk_id"] for r in candidates}
            for extra_offset, r in enumerate(local_root_rows, len(rows) + len(candidates) + 1):
                if r["chunk_id"] in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(r["chunk_id"])
                features = _retrieval_rank_features(query, r, extra_offset)
                candidates.append({
                    "chunk_id": r["chunk_id"],
                    "url": r["url"],
                    "host": r["host"],
                    "source_id": r["source_id"],
                    "title": r["title"],
                    "doc_type": r["doc_type"],
                    "tier": r["tier"],
                    "text": (r["text"] or "")[:CHUNK_TEXT_MAX_CHARS],
                    "rank": extra_offset,
                    "score": float(r["score"]) if r["score"] is not None else 0.0,
                    "rank_score": features["rank_score"],
                    "relevance": features["relevance"],
                    "features": features,
                })

        # Contact pages are often titled generically and may not share tokens
        # with fused/misspelled local queries such as "जिरिहेल्पडेष्क फोन".
        # When the intent and locality are clear, pull the municipality contact
        # page directly into the candidate pool so the reranker can use it.
        contact_role = _contact_query_role(query)
        if (
            search_topic == "municipality_contact"
            and search_local_domains
        ):
            root_urls: list[str] = []
            for domain in search_local_domains:
                d = domain.lower().strip("/")
                root_urls.extend([
                    f"https://{d}",
                    f"https://{d}/",
                    f"https://{d}/ne",
                    f"https://{d}/ne/",
                    f"https://{d}/en",
                    f"https://{d}/en/",
                ])
            domain_placeholders = ", ".join("?" for _ in search_local_domains)
            url_placeholders = ", ".join("?" for _ in root_urls)
            role_sql = f"""
                SELECT chunks.chunk_id AS chunk_id, chunks.text AS text,
                       documents.url AS url, documents.title AS title,
                       documents.doc_type AS doc_type,
                       documents.source_id AS source_id,
                       sources.domain AS host, sources.tier AS tier,
                       0.0 AS score
                FROM chunks
                JOIN documents ON documents.doc_id = chunks.doc_id
                JOIN sources   ON sources.source_id = documents.source_id
                WHERE sources.domain IN ({domain_placeholders})
                  AND lower(documents.url) IN ({url_placeholders})
                  AND documents.superseded_by IS NULL
                  AND documents.removed_at IS NULL
                ORDER BY documents.url, chunks.chunk_index
                LIMIT ?
            """
            with self._conn() as c:
                role_rows = c.execute(
                    role_sql,
                    (*search_local_domains, *root_urls, 18),
                ).fetchall()
            seen_chunk_ids = {r["chunk_id"] for r in candidates}
            for extra_offset, r in enumerate(role_rows, len(rows) + 1):
                if r["chunk_id"] in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(r["chunk_id"])
                features = _retrieval_rank_features(query, r, extra_offset)
                candidates.append({
                    "chunk_id": r["chunk_id"],
                    "url": r["url"],
                    "host": r["host"],
                    "source_id": r["source_id"],
                    "title": r["title"],
                    "doc_type": r["doc_type"],
                    "tier": r["tier"],
                    "text": (r["text"] or "")[:CHUNK_TEXT_MAX_CHARS],
                    "rank": extra_offset,
                    "score": float(r["score"]) if r["score"] is not None else 0.0,
                    "rank_score": features["rank_score"],
                    "relevance": features["relevance"],
                    "features": features,
                })

        if (
            search_topic == "municipality_contact"
            and search_local_domains
        ):
            contact_urls: list[str] = []
            for domain in search_local_domains:
                d = domain.lower().strip("/")
                host_variants = [d]
                if not d.startswith("www."):
                    host_variants.append(f"www.{d}")
                for host in host_variants:
                    for path in ("/content/contact", "/en/content/contact", "/ne/content/contact"):
                        contact_urls.append(f"https://{host}{path}")
                        contact_urls.append(f"https://{host}{path}/")
            contact_url_placeholders = ", ".join("?" for _ in contact_urls)
            direct_contact_sql = f"""
                SELECT chunks.chunk_id AS chunk_id, chunks.text AS text,
                       documents.url AS url, documents.title AS title,
                       documents.doc_type AS doc_type,
                       documents.source_id AS source_id,
                       sources.domain AS host, sources.tier AS tier,
                       0.0 AS score
                FROM chunks
                JOIN documents ON documents.doc_id = chunks.doc_id
                JOIN sources   ON sources.source_id = documents.source_id
                WHERE lower(documents.url) IN ({contact_url_placeholders})
                  AND documents.superseded_by IS NULL
                  AND documents.removed_at IS NULL
                ORDER BY
                  CASE
                    WHEN lower(chunks.text) LIKE '%contact no%' THEN 0
                    WHEN chunks.text LIKE '%फोन%' THEN 0
                    ELSE 1
                  END,
                  documents.url,
                  chunks.chunk_index
                LIMIT ?
            """
            with self._conn() as c:
                supplemental_rows = c.execute(
                    direct_contact_sql,
                    (*contact_urls, 8),
                ).fetchall()
                if not supplemental_rows:
                    placeholders = ", ".join("?" for _ in search_local_domains)
                    supplemental_sql = f"""
                        SELECT chunks.chunk_id AS chunk_id, chunks.text AS text,
                               documents.url AS url, documents.title AS title,
                               documents.doc_type AS doc_type,
                               documents.source_id AS source_id,
                               sources.domain AS host, sources.tier AS tier,
                               0.0 AS score
                        FROM chunks
                        JOIN documents ON documents.doc_id = chunks.doc_id
                        JOIN sources   ON sources.source_id = documents.source_id
                        WHERE sources.domain IN ({placeholders})
                          AND documents.superseded_by IS NULL
                          AND documents.removed_at IS NULL
                          AND (
                            lower(documents.url) LIKE '%/content/contact%'
                            OR lower(documents.title) LIKE '%contact%'
                            OR lower(documents.url) LIKE '%mitra-bahadur%'
                            OR lower(documents.url) LIKE '%krishnamaya%'
                            OR lower(documents.url) LIKE '%man-bahadur%'
                            OR lower(documents.url) LIKE '%raj-kumari%'
                            OR lower(chunks.text) LIKE '%contact no%'
                            OR lower(chunks.text) LIKE '%phone%'
                            OR lower(chunks.text) LIKE '%mitra bahadur%'
                            OR lower(chunks.text) LIKE '%krishnamaya%'
                            OR lower(chunks.text) LIKE '%man bahadur%'
                            OR lower(chunks.text) LIKE '%raj kumari%'
                            OR chunks.text LIKE '%फोन%'
                            OR chunks.text LIKE '%सम्पर्क%'
                            OR chunks.text LIKE '%नगर प्रमुख%'
                            OR chunks.text LIKE '%उप%'
                            OR chunks.text LIKE '%सूचना अधिकारी%'
                            OR chunks.text LIKE '%प्रमुख प्रशासकीय%'
                            OR chunks.text LIKE '%मित्र बहादुर%'
                            OR chunks.text LIKE '%कृष्णमाया%'
                            OR chunks.text LIKE '%मान बहादुर%'
                            OR chunks.text LIKE '%राज कुमारी%'
                          )
                        ORDER BY
                          CASE
                            WHEN chunks.text LIKE '%नगर प्रमुख%' THEN 0
                            WHEN lower(chunks.text) LIKE '%mitra bahadur%' THEN 0
                            WHEN lower(documents.url) LIKE '%/content/contact%'
                              AND lower(chunks.text) LIKE '%contact no%' THEN 0
                            WHEN lower(documents.url) LIKE '%/content/contact%' THEN 1
                            WHEN chunks.text LIKE '%सूचना अधिकारी%' THEN 1
                            WHEN chunks.text LIKE '%प्रमुख प्रशासकीय%' THEN 1
                            WHEN lower(chunks.text) LIKE '%contact no%' THEN 2
                            ELSE 3
                          END,
                          documents.url,
                          chunks.chunk_id
                        LIMIT ?
                    """
                    supplemental_rows = c.execute(
                        supplemental_sql,
                        (*search_local_domains, 24),
                    ).fetchall()
            seen_chunk_ids = {r["chunk_id"] for r in candidates}
            for extra_offset, r in enumerate(supplemental_rows, len(rows) + 1):
                if r["chunk_id"] in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(r["chunk_id"])
                features = _retrieval_rank_features(query, r, extra_offset)
                candidates.append({
                    "chunk_id": r["chunk_id"],
                    "url": r["url"],
                    "host": r["host"],
                    "source_id": r["source_id"],
                    "title": r["title"],
                    "doc_type": r["doc_type"],
                    "tier": r["tier"],
                    "text": (r["text"] or "")[:CHUNK_TEXT_MAX_CHARS],
                    "rank": extra_offset,
                    "score": float(r["score"]) if r["score"] is not None else 0.0,
                    "rank_score": features["rank_score"],
                    "relevance": features["relevance"],
                    "features": features,
                })

        if search_topic == "foreign_employment" and _foreign_employment_query_wants_complaint(query):
            complaint_domains = ("dofe.gov.np", "feb.gov.np", "moless.gov.np")
            placeholders = ", ".join("?" for _ in complaint_domains)
            complaint_sql = f"""
                SELECT chunks.chunk_id AS chunk_id, chunks.text AS text,
                       documents.url AS url, documents.title AS title,
                       documents.doc_type AS doc_type,
                       documents.source_id AS source_id,
                       sources.domain AS host, sources.tier AS tier,
                       0.0 AS score
                FROM chunks
                JOIN documents ON documents.doc_id = chunks.doc_id
                JOIN sources   ON sources.source_id = documents.source_id
                WHERE lower(sources.domain) IN ({placeholders})
                  AND documents.superseded_by IS NULL
                  AND documents.removed_at IS NULL
                  AND (
                    chunks.text LIKE '%११४१%'
                    OR chunks.text LIKE '%1141%'
                    OR chunks.text LIKE '%उजुरी%'
                    OR chunks.text LIKE '%गुनासो%'
                    OR chunks.text LIKE '%ठगी%'
                    OR chunks.text LIKE '%ठगे%'
                    OR lower(chunks.text) LIKE '%complaint%'
                    OR lower(chunks.text) LIKE '%grievance%'
                    OR lower(chunks.text) LIKE '%receipt%'
                    OR chunks.text LIKE '%रसिद%'
                    OR chunks.text LIKE '%प्रमाण%'
                    OR lower(documents.url) LIKE '%public-important%'
                  )
                ORDER BY
                  CASE
                    WHEN chunks.text LIKE '%११४१%' OR chunks.text LIKE '%1141%' THEN 0
                    WHEN chunks.text LIKE '%उजुरी%' AND chunks.text LIKE '%कागजात%' THEN 1
                    WHEN chunks.text LIKE '%गुनासो%' THEN 2
                    WHEN chunks.text LIKE '%ठगी%' OR chunks.text LIKE '%ठगे%' THEN 3
                    WHEN chunks.text LIKE '%रसिद%' OR lower(chunks.text) LIKE '%receipt%' THEN 4
                    WHEN lower(documents.url) LIKE '%public-important%' THEN 5
                    ELSE 6
                  END,
                  documents.url,
                  chunks.chunk_index
                LIMIT ?
            """
            with self._conn() as c:
                complaint_rows = c.execute(
                    complaint_sql,
                    (*complaint_domains, max(top_k * 12, 36)),
                ).fetchall()
            seen_chunk_ids = {r["chunk_id"] for r in candidates}
            for extra_offset, r in enumerate(complaint_rows, len(rows) + len(candidates) + 1):
                if r["chunk_id"] in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(r["chunk_id"])
                features = _retrieval_rank_features(query, r, extra_offset)
                candidates.append({
                    "chunk_id": r["chunk_id"],
                    "url": r["url"],
                    "host": r["host"],
                    "source_id": r["source_id"],
                    "title": r["title"],
                    "doc_type": r["doc_type"],
                    "tier": r["tier"],
                    "text": (r["text"] or "")[:CHUNK_TEXT_MAX_CHARS],
                    "rank": extra_offset,
                    "score": float(r["score"]) if r["score"] is not None else 0.0,
                    "rank_score": features["rank_score"],
                    "relevance": features["relevance"],
                    "features": features,
                })
        candidates.sort(key=lambda r: (-r["rank_score"], r["score"], r["rank"]))

        out: list[dict] = []
        per_url: dict[str, int] = {}
        priority_candidates: list[dict] = []
        topic = _detect_retrieval_topic(query)
        local_domains = _detect_local_domains(query)
        if topic == "foreign_employment" and _foreign_employment_query_wants_complaint(query):
            exact_complaint = next(
                (
                    r for r in candidates
                    if _domain_matches(r.get("host"), ("feb.gov.np",))
                    and ("आफू ठगिएको" in (r.get("text") or "") or ("ठग" in (r.get("text") or "") and "उजुरी" in (r.get("text") or "")))
                ),
                None,
            )
            clean_helpline = next(
                (
                    r for r in candidates
                    if _domain_matches(r.get("host"), ("feb.gov.np",))
                    and (("११४१" in (r.get("text") or "") or "1141" in (r.get("text") or "")))
                    and ("गुनासो" in (r.get("text") or "") or "समस्या" in (r.get("text") or ""))
                    and not ((r.get("url") or "").lower().endswith(".pdf"))
                ),
                None,
            )
            agency_proof = next(
                (
                    r for r in candidates
                    if _domain_matches(r.get("host"), ("dofe.gov.np", "feb.gov.np"))
                    and ("रसिद" in (r.get("text") or "") or "receipt" in (r.get("text") or "").lower())
                ),
                None,
            )
            for r in (exact_complaint, clean_helpline, agency_proof):
                if r and r not in priority_candidates:
                    priority_candidates.append(r)
        if local_domains:
            if topic == "municipality_contact":
                contact_matches = sorted(
                    (
                        (priority, r)
                        for r in candidates
                        if (priority := _contact_source_priority(query, r)) is not None
                        and not ((r.get("url") or "").lower().endswith(".pdf") or "/files/" in (r.get("url") or "").lower())
                    ),
                    key=lambda item: (item[0], -item[1].get("rank_score", 0), item[1].get("rank", 9999)),
                )
                for _, r in contact_matches[:2]:
                    if r not in priority_candidates:
                        priority_candidates.append(r)
            best_specific_local = next(
                (
                    r for r in candidates
                    if r.get("features", {}).get("local_match")
                    and r.get("features", {}).get("strong_hits")
                    and "/content/" in urllib.parse.unquote((r.get("url") or "").lower())
                    and not urllib.parse.unquote((r.get("url") or "").lower()).rstrip("/").endswith("/content/services")
                    and r.get("features", {}).get("coverage", 0) >= 0.5
                ),
                None,
            )
            if best_specific_local:
                priority_candidates.append(best_specific_local)
            if not topic or topic in LOCAL_TACIT_STRICT_TOPICS or topic == "municipality_contact":
                best_local = next(
                    (
                        r for r in candidates
                        if r.get("features", {}).get("local_match")
                        and r.get("features", {}).get("coverage", 0) >= 0.5
                    ),
                    None,
                )
                if best_local and best_local not in priority_candidates:
                    priority_candidates.append(best_local)
        expected_domains = _authority_domains_for_query(topic, query) if topic else ()
        if expected_domains:
            for domain in expected_domains:
                best_expected = next(
                    (r for r in candidates if _domain_matches(r.get("host"), (domain,))),
                    None,
                )
                if best_expected and best_expected not in priority_candidates:
                    priority_candidates.append(best_expected)

        for r in [*priority_candidates, *candidates]:
            url_key = normalize_url(r.get("url") or "") or r.get("chunk_id") or ""
            if per_url.get(url_key, 0) >= 1:
                continue
            per_url[url_key] = per_url.get(url_key, 0) + 1
            r = dict(r)
            r["rank"] = len(out) + 1
            out.append(r)
            if len(out) >= top_k:
                break
        return out

    def stats(self) -> dict:
        with self._conn() as c:
            stats: dict[str, Any] = {"db_path": str(self.db_path)}
            for tbl in ("sources", "documents", "chunks"):
                stats[f"{tbl}_count"] = c.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            if self._has_fts(c):
                stats["fts_count"] = c.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
            else:
                stats["fts_count"] = 0
            return stats


# ---- Tacit-knowledge retrieval (in-memory, priority over gov.np) ----------


class TacitRetriever:
    """Loads claims from `corpora/tacit/processed/<office>/<service>/*.jsonl`
    into memory at startup. Each record is one atomic claim with provenance.

    Retrieval is simple token-overlap scoring (BM25-like). Fast enough for
    the expected corpus size (≤10k claims) and avoids a separate FTS5/vector
    dependency for v0.1.

    Priority semantics: tacit claims always rank higher than gov.np chunks
    in the merged source list — they're shown to the model FIRST and labeled
    so the composer knows to weight citizen-experience facts as ground-truth
    practical info."""

    def __init__(self, tacit_dir: Path):
        self.tacit_dir = tacit_dir
        self.records: list[dict] = []
        self._load()

    def _load(self) -> None:
        if not self.tacit_dir.exists():
            LOG.info("tacit dir %s not present — running gov.np-only", self.tacit_dir)
            return
        for jsonl in self.tacit_dir.rglob("*.jsonl"):
            try:
                with jsonl.open(encoding="utf-8") as f:
                    for line in f:
                        try:
                            r = __import__("json").loads(line)
                        except Exception:
                            continue
                        # Skip synthetic_pilot records in production mode
                        if os.environ.get("EXCLUDE_SYNTHETIC", "false").lower() == "true":
                            if r.get("source", {}).get("method") == "synthetic_pilot":
                                continue
                        self.records.append(r)
            except Exception as e:
                LOG.warning("failed to load %s: %s", jsonl, e)
        LOG.info("loaded %d tacit claims from %s", len(self.records), self.tacit_dir)

    @staticmethod
    def _tokenize(s: str) -> list[str]:
        # cheap multilingual tokenizer: keep word chars + Devanagari, lowercase ASCII
        return [t.lower() for t in re.findall(r"[\wऀ-ॿ]+", s) if t]

    def search(self, query: str, top_k: int = TOP_K_TACIT) -> list[dict]:
        if not self.records:
            return []
        q_toks = set(_expanded_retrieval_tokens(query) or self._tokenize(query))
        if not q_toks:
            return []
        topic = _detect_retrieval_topic(query)
        expected_domains = _authority_domains_for_query(topic, query) if topic else ()
        local_domains = _detect_local_domains(query)
        compatible_service_markers = TACIT_TOPIC_SERVICE_MARKERS.get(topic or "", ())
        topic_markers = TOPIC_STRONG_MARKERS.get(topic or "", ())
        q_nonlocal = q_toks - LOCALITY_QUERY_TERMS
        scored: list[tuple[float, dict]] = []
        for r in self.records:
            claim = r.get("claim") or ""
            office = r.get("office", {})
            service_blob = " ".join([
                r.get("service") or "",
                " ".join(r.get("service_aliases") or []),
                " ".join(r.get("tags") or []),
                r.get("fact_type") or "",
                office.get("service_unit") or "",
            ]).lower()
            record_domain = office.get("domain") or ""
            if (
                topic
                and expected_domains
                and not local_domains
                and _domain_matches(record_domain, ALL_LOCALITY_DOMAINS)
            ):
                continue
            if compatible_service_markers and not _marker_hits(service_blob, compatible_service_markers):
                continue
            office_blob = " ".join([
                office.get("name_en") or "",
                office.get("name_ne") or "",
                office.get("service_unit") or "",
                r.get("service") or "",
                " ".join(r.get("service_aliases") or []),
                " ".join(r.get("tags") or []),
            ])
            topic_blob = f"{claim} {office_blob} {service_blob}".lower()
            strong_hits = _marker_hits(topic_blob, topic_markers)
            if topic in LOCAL_TACIT_STRICT_TOPICS and local_domains and not strong_hits:
                continue
            doc_toks = set(self._tokenize(claim + " " + office_blob))
            if not doc_toks:
                continue
            # token-overlap with mild length penalty to avoid favoring long claims
            overlap = len(q_toks & doc_toks)
            if overlap == 0:
                continue
            nonlocal_overlap = len(q_nonlocal & doc_toks)
            if q_nonlocal and nonlocal_overlap == 0:
                continue
            score = overlap * (1.0 + 0.3 * (1.0 - min(1.0, len(doc_toks) / 50)))
            score += 0.75 * nonlocal_overlap
            if local_domains and _domain_matches(record_domain, local_domains):
                score += 2.5
            if strong_hits:
                score += min(4.0, 1.25 * len(strong_hits))
            # confidence bump: 'high' wins ties over 'medium' / 'low'
            conf_bump = {"high": 0.5, "medium": 0.0, "low": -0.5}.get(
                r.get("confidence", "medium"), 0.0
            )
            scored.append((score + conf_bump, r))
        scored.sort(key=lambda x: -x[0])
        out: list[dict] = []
        for i, (sc, r) in enumerate(scored[:top_k], 1):
            office = r.get("office", {})
            out.append({
                "rank": i,
                "score": float(sc),
                "is_tacit": True,
                "claim_id": r.get("id"),
                "claim": r.get("claim"),
                "fact_type": r.get("fact_type"),
                "office_name": office.get("name_en") or "",
                "office_url": f"https://{office.get('domain', '')}" if office.get("domain") else "",
                "service": r.get("service"),
                "interviewee_role": r.get("source", {}).get("interviewee_role"),
                "confidence": r.get("confidence"),
                "method": r.get("source", {}).get("method"),
            })
        return out

    def stats(self) -> dict:
        from collections import Counter
        offices = Counter(r.get("office", {}).get("name_en") for r in self.records)
        types = Counter(r.get("fact_type") for r in self.records)
        methods = Counter(r.get("source", {}).get("method") for r in self.records)
        return {
            "total_claims": len(self.records),
            "by_office": dict(offices),
            "by_fact_type": dict(types),
            "by_method": dict(methods),
        }


# ---- Prompt building ------------------------------------------------------

_CONTACT_PROMPT_INTENT_RE = re.compile(
    r"\b(contact|phone|telephone|number|helpline|helpdesk|call|email|"
    r"kaslai|kasko|kaha|where|who)\b",
    re.I,
)


def _question_wants_contact_fact(question: str) -> bool:
    q = question or ""
    return bool(_CONTACT_PROMPT_INTENT_RE.search(q)) or any(
        token in q
        for token in ("सम्पर्क", "फोन", "नम्बर", "कसलाई", "कहाँ", "को हो", "सूचना अधिकारी")
    )


def _contact_facts_for_prompt(
    question: str,
    gov: list[dict],
    *,
    source_rank_start: int = 1,
) -> list[str]:
    """Extract clean contact hints to make small models surface retrieved contacts.

    This stays prompt-side: it does not generate the answer, but it prevents the
    composer from overlooking short helplines buried in long OCR/PDF chunks.
    """
    if not _question_wants_contact_fact(question):
        return []
    facts: list[str] = []
    seen: set[str] = set()
    for i, g in enumerate(gov, source_rank_start):
        source_ref = f"S{i}"
        text = (g.get("text") or "").translate(_DEVANAGARI_DIGITS)
        text_l = text.lower()
        if "1141" in text and any(marker in text_l or marker in text for marker in ("gunaso", "problem", "call center", "helpline", "सम्पर्क", "गुनासो", "समस्या", "कल सेन्टर")):
            fact = f"{source_ref}: 1141 is shown as an official/free helpline/contact for gunaso/problems."
            if fact not in seen:
                facts.append(fact)
                seen.add(fact)
        for email in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
            fact = f"{source_ref}: email {email}"
            if fact not in seen:
                facts.append(fact)
                seen.add(fact)
        for phone in re.findall(r"(?:\+?977[-\s]?)?0?\d{2,3}[-\s]\d{5,7}\b", text):
            digits = re.sub(r"\D", "", phone)
            if len(digits) < 7 or len(digits) > 13:
                continue
            phone_display = re.sub(r"\s+", " ", phone).strip()
            fact = f"{source_ref}: phone/contact {phone_display}"
            if fact not in seen:
                facts.append(fact)
                seen.add(fact)
    return facts[:5]


def _complaint_facts_for_prompt(
    question: str,
    gov: list[dict],
    *,
    source_rank_start: int = 1,
) -> list[str]:
    if _detect_retrieval_topic(question) != "foreign_employment":
        return []
    if not _foreign_employment_query_wants_complaint(question):
        return []
    facts: list[str] = []
    seen: set[str] = set()
    for i, g in enumerate(gov, source_rank_start):
        source_ref = f"S{i}"
        text = (g.get("text") or "").translate(_DEVANAGARI_DIGITS)
        text_l = text.lower()

        candidates: list[str] = []
        if "वैदेशिक रोजगार विभागमा उजुरी" in text or "dofe.gov.np" in text_l:
            candidates.append(
                f"{source_ref}: If the worker is sure they were cheated, the source says a complaint can be filed with the Department of Foreign Employment, including through family/representative where relevant."
            )
        if "वैदेशिक रोजगारीमा गएको अवस्थामा ठगीमा परे" in text or (
            "उजुरी" in text and "क्षतिपूर्ति" in text and "वैदेशिक रोजगार विभाग" in text
        ):
            candidates.append(
                f"{source_ref}: For fraud during foreign employment, the Department of Foreign Employment receives complaints, investigates, and handles compensation according to the source."
            )
        if "स्थानीय जिल्ला प्रशासन कार्यालय" in text and ("ठगी" in text or "इजाजतपत्र" in text):
            candidates.append(
                f"{source_ref}: For fraud by an individual or license-holder, the source says a complaint can also be filed at the local District Administration Office."
            )
        if "1141" in text and ("गुनासो" in text or "समस्या" in text or "कल सेन्टर" in text):
            candidates.append(
                f"{source_ref}: 1141 is listed as a call-center/free helpline for complaints or problems."
            )

        for fact in candidates:
            if fact not in seen:
                facts.append(fact)
                seen.add(fact)
    return facts[:6]


def build_user_prompt(
    question: str,
    tacit: list[dict],
    gov: list[dict],
    history: list[ChatHistoryTurn] | None = None,
    answer_language: str | None = None,
) -> str:
    """Tacit claims FIRST (high-priority practical knowledge from interviews),
    then gov.np chunks. Sources are labeled so the composer knows to surface
    citizen-experience facts even when gov.np doesn't mention them."""
    parts: list[str] = []
    history_text = _history_prompt(history)
    if history_text:
        parts.extend([history_text, ""])
    parts.extend([f"Current question: {question.strip()}", "", "Sources:"])
    topic = _detect_retrieval_topic(question)
    lang = answer_language or _detect_lang(question)
    if lang == "roman_nepali":
        parts.extend([
            "",
            "Answer language: Latin-script Roman Nepali only. Do not use Hindi or Devanagari sentences.",
            "Use natural Roman Nepali that people type in chat, not mechanical transliteration: short sentences, common words like tapai, garne, parcha, saknuhuncha, and readable official office names.",
            "Keep Roman Nepali answers compact: 2-4 short points, no repeated claim, and skip unrelated administrative/training details.",
        ])
    elif lang == "devanagari":
        parts.extend([
            "",
            "Answer language: Nepali in Devanagari script. Do not answer in Hindi.",
        ])
    local_domains = _detect_local_domains(question)
    if topic in {"birth_registration", "vital_registration"} and local_domains:
        parts.extend([
            "",
            "Retrieval guidance: this is a municipality-specific event-registration question. "
            "Use DONIDCR/national event-registration sources as authoritative for the procedure "
            "and use the local municipality source only for local office, timing, fee, or service context. "
            "Do not refuse merely because the national procedure page does not name the municipality.",
        ])
    if topic == "foreign_employment" and _foreign_employment_query_wants_complaint(question):
        parts.extend([
            "",
            "Retrieval guidance: this is a foreign-employment complaint/contact question. "
            "Use the exact complaint/ujuri source for where to file the case, and use a clean "
            "FEB/official helpline source for who to contact when available. If a source clearly "
            "shows ११४१/1141 for gunaso/problems, include it as a helpline/contact; do not assign "
            "garbled OCR phone numbers to offices.",
        ])
    if not tacit and not gov:
        parts.append("(no candidate sources surfaced)")
        parts.append("\nCompose a grounded answer following the rules.")
        return "\n".join(parts)

    rank = 0
    for t in tacit:
        rank += 1
        source_ref = f"S{rank}"
        role = t.get("interviewee_role") or "citizen"
        office = t.get("office_name") or ""
        confidence = t.get("confidence") or "medium"
        url = t.get("office_url") or ""
        parts.append(f"\n[{source_ref}] CITIZEN-EXPERIENCE INTERVIEW (priority practical knowledge)")
        parts.append(f"Role: {role}; office: {office}; confidence: {confidence}")
        if url:
            parts.append(f"URL: {url}")
        parts.append(f"Claim: {t.get('claim') or ''}")
    for g in gov:
        rank += 1
        source_ref = f"S{rank}"
        url = g.get("url") or ""
        excerpt = g.get("text") or ""
        parts.append(f"\n[{source_ref}] GOV.NP")
        if url:
            parts.append(f"URL: {url}")
        if g.get("title"):
            parts.append(f"Title: {g.get('title')}")
        parts.append(f"Excerpt: {excerpt}")
        if lang == "roman_nepali" and _script_counts(excerpt)[0] > 12:
            roman_excerpt = _romanize_devanagari(excerpt)
            if roman_excerpt and roman_excerpt != excerpt:
                parts.append(f"Romanized excerpt for understanding the source, not answer style: {roman_excerpt}")
    contact_facts = _contact_facts_for_prompt(question, gov, source_rank_start=len(tacit) + 1)
    if contact_facts:
        parts.append("\nContact facts detected from retrieved source text. If the user asks who to contact, phone, helpline, or email, include the relevant clean facts below with their source IDs:")
        parts.extend(f"- {fact}" for fact in contact_facts)
    complaint_facts = _complaint_facts_for_prompt(question, gov, source_rank_start=len(tacit) + 1)
    if complaint_facts:
        parts.append("\nComplaint-routing facts detected from retrieved source text. Use these as the English/normalized interpretation of the source when answering complaint questions:")
        parts.extend(f"- {fact}" for fact in complaint_facts)
    parts.append("\nCompose a grounded answer following the rules. When tacit knowledge "
                 "(citizen-interview sources) is more practically useful than gov.np text, "
                 "lead with it. For municipality-specific questions, if one official "
                 "local source confirms the municipality/service context and another "
                 "official national source gives the rule for that service at the local "
                 "ward/municipality level, answer the supported part and state any missing "
                 "local checklist plainly instead of refusing the whole question. For contact "
                 "questions, lead with the responsible office/contact path and do not omit clean "
                 "helplines, phone numbers, or emails shown in the retrieved sources. Cite "
                 "claims with source IDs such as [S1], [S2]. Do not cite raw URLs.")
    return "\n".join(parts)


# ---- Composer (MLX-LM) ----------------------------------------------------


_SENT_SPLIT_RE = re.compile(r"(?<=[।\.!?])\s+")

_DEDUP_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "on", "at", "for", "by", "with", "from", "into",
    "about", "as", "that", "this", "it", "its", "you", "your", "they",
    "their", "them", "we", "our", "us", "not", "no", "or", "and", "but",
    "if", "then", "than", "do", "does", "did", "doing", "done", "need",
    "needs", "needed", "also", "each", "every", "all", "any", "will",
    "can", "could", "should", "would", "may", "might", "must", "have",
    "has", "had", "go", "goes", "going", "give", "gives", "given",
})


def _content_tokens(s: str) -> frozenset[str]:
    """Lower-cased content-word multiset for near-duplicate detection.
    Strips citation brackets and common English stopwords so two sentences
    paraphrasing the same fact collapse to the same token set."""
    txt = re.sub(r"\[https?://[^\]]+\]", "", s.lower())
    txt = re.sub(r"[^\w\sऀ-ॿ]+", " ", txt)
    return frozenset(
        t for t in txt.split()
        if t and len(t) > 1 and t not in _DEDUP_STOPWORDS
    )


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _dedup_sentences(text: str, near_dup_threshold: float = 0.80) -> str:
    """Trim degenerate decode loops without touching legitimate output.

    Two layers:
    1. Exact: drop a sentence if its lowercased-stripped key already appeared.
    2. Near-dup: drop if its content-word Jaccard against any earlier sentence
       is ≥ near_dup_threshold (catches "X for citizenship" vs "X for citizenship,
       need to publish" same-fact paraphrases).

    Stops accumulating after 2 consecutive duplicates (the model is in a loop
    and won't recover)."""
    if not text:
        return text
    sents = _SENT_SPLIT_RE.split(text.strip())
    seen_keys: set[str] = set()
    seen_token_sets: list[frozenset[str]] = []
    out: list[str] = []
    consecutive_dups = 0
    for s in sents:
        key = re.sub(r"\s+", " ", s.lower()).strip()
        key = re.sub(r"\s*\[https?://[^\]]+\]\s*\.?\s*$", "", key).strip()
        if not key:
            out.append(s)
            continue
        s_tokens = _content_tokens(s)
        is_dup = key in seen_keys or any(
            _jaccard(s_tokens, prev) >= near_dup_threshold
            for prev in seen_token_sets
        )
        if is_dup:
            consecutive_dups += 1
            if consecutive_dups >= 2:
                break
            continue
        seen_keys.add(key)
        if s_tokens:
            seen_token_sets.append(s_tokens)
        consecutive_dups = 0
        out.append(s)
    return " ".join(out).strip()


def _clip_refusal_repetition(text: str) -> str:
    if not text:
        return text
    out: list[str] = []
    seen_refusals: set[str] = set()
    for s in _SENT_SPLIT_RE.split(text.strip()):
        clean = re.sub(r"\s+", " ", s).strip()
        if not clean:
            continue
        if is_refusal(clean):
            key = re.sub(r"[\W_]+", " ", clean.lower()).strip()
            if key in seen_refusals:
                continue
            seen_refusals.add(key)
        out.append(clean)
    return " ".join(out).strip()


def _has_refusal_repetition(text: str) -> bool:
    if not text:
        return False
    counts: dict[str, int] = {}
    for s in _SENT_SPLIT_RE.split(text.strip()):
        clean = re.sub(r"\s+", " ", s).strip()
        if not clean or not is_refusal(clean):
            continue
        key = re.sub(r"[\W_]+", " ", clean.lower()).strip()
        counts[key] = counts.get(key, 0) + 1
        if counts[key] >= 2:
            return True
    return False


def _clean_generated_answer(text: str) -> str:
    return _dedup_sentences(_clip_refusal_repetition(text.strip()))


class Composer:
    """Wraps transformers + PEFT for inference.

    Used to use mlx-lm but mlx-lm 0.31's gemma4_text architecture disagreed
    with the multimodal Gemma 4 safetensors (54 late-layer keys mismatch).
    Sticking with the same stack we used to TRAIN the adapter (torch +
    transformers + peft) avoids that whole class of incompatibilities and
    gives us 1:1 parity between training-time and serving-time behaviour.

    Slower than MLX (~2× on Apple Silicon via MPS) but works today."""

    def __init__(self, model_id: str, adapter_path: str | None):
        self.model_id = model_id
        self.adapter_path = adapter_path
        self._loaded = False
        self.model = None
        self.tokenizer = None
        self.device = None
        self._generation_lock = threading.Lock()

    @staticmethod
    def _unwrap_gemma4_clippable_linears(model) -> int:
        """Replace `Gemma4ClippableLinear` wrappers with their inner `nn.Linear`.

        Mirrors the trainer's pre-PEFT-injection step. Required so the saved
        v1 adapter (trained against unwrapped linears) loads cleanly here."""
        import torch.nn as nn  # type: ignore[import-not-found]
        n = 0
        for parent in list(model.modules()):
            for name, child in list(parent.named_children()):
                if type(child).__name__ == "Gemma4ClippableLinear":
                    inner = getattr(child, "linear", None)
                    if isinstance(inner, nn.Linear):
                        setattr(parent, name, inner)
                        n += 1
        return n

    def load(self) -> None:
        if self._loaded:
            return
        LOG.info("loading transformers: model=%s adapter=%s", self.model_id, self.adapter_path)
        t0 = time.time()
        import torch  # type: ignore[import-not-found]
        from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore[import-not-found]

        # Determine device. On Mac Studio, MPS is the right path. CUDA on Linux/GPU.
        if torch.cuda.is_available():
            self.device = "cuda"
            dtype = torch.bfloat16
        elif torch.backends.mps.is_available():
            self.device = "mps"
            dtype = torch.bfloat16
        else:
            self.device = "cpu"
            dtype = torch.float32
        LOG.info("device=%s dtype=%s", self.device, dtype)

        # Tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, token=HF_TOKEN)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id

        # Gemma 4's chat template ships separately (HF transformers issue
        # #45205 — separate chat_template.jinja file).
        if not getattr(self.tokenizer, "chat_template", None):
            try:
                from huggingface_hub import hf_hub_download  # type: ignore[import-not-found]
                tpl_path = hf_hub_download(
                    repo_id=self.model_id,
                    filename="chat_template.jinja",
                    token=HF_TOKEN,
                )
                self.tokenizer.chat_template = Path(tpl_path).read_text(encoding="utf-8")
                LOG.info("loaded chat_template.jinja from HF")
            except Exception as e:
                LOG.warning("could not fetch chat_template.jinja: %s", e)

        # Base model
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            token=HF_TOKEN,
            torch_dtype=dtype,
            device_map=self.device,
            attn_implementation="sdpa",
        )
        self.model.config.use_cache = True

        # Apply the same Gemma4ClippableLinear unwrap the trainer did.
        n = self._unwrap_gemma4_clippable_linears(self.model)
        if n:
            LOG.info("unwrapped %d Gemma4ClippableLinear → nn.Linear", n)

        # PEFT adapter on top
        if self.adapter_path:
            from peft import PeftModel  # type: ignore[import-not-found]
            self.model = PeftModel.from_pretrained(
                self.model, self.adapter_path, token=HF_TOKEN,
            )

        self.model.eval()
        self._loaded = True
        LOG.info("model loaded in %.1fs (device=%s)", time.time() - t0, self.device)

    def _build_generate_kwargs(
        self,
        system: str,
        user: str,
        max_tokens: int,
        seed: int | None,
        streamer: Any | None = None,
    ) -> tuple[dict[str, Any], int, str]:
        if not self._loaded:
            raise RuntimeError("composer not loaded — call .load() first")
        import torch  # type: ignore[import-not-found]

        msgs: list[dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": user})
        # Format text → encode (avoids the apply_chat_template tokenize=True
        # version-dependent return-type bug we hit in the trainer).
        prompt_text = self.tokenizer.apply_chat_template(
            msgs, tokenize=False, add_generation_prompt=True
        )
        encoded = self.tokenizer(
            prompt_text, return_tensors="pt", add_special_tokens=False
        )
        input_ids = encoded["input_ids"].to(self.model.device)
        attention_mask = encoded["attention_mask"].to(self.model.device)

        if seed is not None:
            torch.manual_seed(seed)

        generate_kwargs: dict[str, Any] = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "max_new_tokens": max_tokens,
            "do_sample": DECODE_DO_SAMPLE,
            "pad_token_id": self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
            "eos_token_id": self.tokenizer.eos_token_id,
        }
        if streamer is not None:
            generate_kwargs["streamer"] = streamer
        if DECODE_DO_SAMPLE:
            generate_kwargs["temperature"] = DECODE_TEMPERATURE
            generate_kwargs["top_p"] = DECODE_TOP_P
        if DECODE_REPETITION_PENALTY != 1.0:
            generate_kwargs["repetition_penalty"] = DECODE_REPETITION_PENALTY
        if DECODE_NO_REPEAT_NGRAM_SIZE > 0:
            generate_kwargs["no_repeat_ngram_size"] = DECODE_NO_REPEAT_NGRAM_SIZE
        return generate_kwargs, input_ids.size(1), prompt_text

    def generate(self, system: str, user: str, max_tokens: int = MAX_NEW_TOKENS,
                 seed: int | None = None) -> str:
        import torch  # type: ignore[import-not-found]

        generate_kwargs, input_len, prompt_text = self._build_generate_kwargs(
            system, user, max_tokens, seed,
        )
        with torch.no_grad():
            with self._generation_lock:
                out_ids = self.model.generate(**generate_kwargs)
        new_ids = out_ids[0, input_len:]
        raw = self.tokenizer.decode(new_ids, skip_special_tokens=True).strip()
        if os.environ.get("LOG_PROMPT", "").lower() in ("1", "true", "yes"):
            LOG.info("PROMPT_TEXT=\n%s\n----RAW_OUTPUT----\n%s\n----END----", prompt_text, raw)
        return _clean_generated_answer(raw)

    def generate_stream(
        self,
        system: str,
        user: str,
        max_tokens: int = MAX_NEW_TOKENS,
        seed: int | None = None,
    ):
        import torch  # type: ignore[import-not-found]
        from transformers import TextIteratorStreamer  # type: ignore[import-not-found]

        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
            timeout=1.0,
        )
        generate_kwargs, _, prompt_text = self._build_generate_kwargs(
            system, user, max_tokens, seed, streamer=streamer,
        )
        if os.environ.get("LOG_PROMPT", "").lower() in ("1", "true", "yes"):
            LOG.info("PROMPT_TEXT=\n%s\n----STREAMING----", prompt_text)
        errors: list[BaseException] = []

        def _worker() -> None:
            try:
                with torch.no_grad():
                    with self._generation_lock:
                        self.model.generate(**generate_kwargs)
            except BaseException as e:
                errors.append(e)
                try:
                    streamer.on_finalized_text("", stream_end=True)
                except Exception:
                    pass

        worker = threading.Thread(target=_worker, daemon=True)
        worker.start()
        while True:
            try:
                chunk = next(streamer)
            except StopIteration:
                break
            except Exception:
                if errors:
                    raise RuntimeError(str(errors[0])) from errors[0]
                if not worker.is_alive():
                    break
                continue
            if chunk:
                yield chunk
        worker.join(timeout=1.0)
        if errors:
            raise RuntimeError(str(errors[0])) from errors[0]


# ---- App lifespan ---------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = Path(DB_PATH).expanduser()
    if not db_path.exists():
        LOG.warning("DB at %s does not exist — gov.np retrieval disabled", db_path)
        app.state.retriever = None
    else:
        app.state.retriever = Retriever(db_path)

    tacit_dir = Path(TACIT_DIR).expanduser()
    app.state.tacit = TacitRetriever(tacit_dir)

    composer = Composer(MODEL_ID, ADAPTER_PATH)
    composer.load()
    app.state.composer = composer
    app.state.startup_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    LOG.info("server ready")
    yield
    LOG.info("server shutting down")


app = FastAPI(title="gemma-god helpdesk", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---- Auth helper ----------------------------------------------------------

def _check_bearer(request: Request) -> None:
    if not BEARER_TOKEN:
        return
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    if auth.split(" ", 1)[1].strip() != BEARER_TOKEN:
        raise HTTPException(403, "bad bearer token")


def _check_tailnet(request: Request) -> None:
    """Tailscale Funnel sets X-Tailscale-User on tailnet-only paths.
    For local dev where Funnel isn't in front, accept localhost."""
    if request.headers.get("x-tailscale-user"):
        return
    host = request.client.host if request.client else ""
    if host in ("127.0.0.1", "::1", "localhost"):
        return
    raise HTTPException(403, "tailnet-only endpoint")


# ---- Admin (HTTP Basic Auth) ---------------------------------------------

_basic_security = HTTPBasic(auto_error=False)


def admin_auth(credentials: HTTPBasicCredentials | None = Depends(_basic_security)) -> str:
    if not ADMIN_PASSWORD:
        raise HTTPException(503, "admin auth disabled (ADMIN_PASSWORD unset)")
    if credentials is None:
        raise HTTPException(
            status_code=401, detail="admin auth required",
            headers={"WWW-Authenticate": "Basic"},
        )
    user_ok = secrets.compare_digest(credentials.username.encode(), ADMIN_USERNAME.encode())
    pass_ok = secrets.compare_digest(credentials.password.encode(), ADMIN_PASSWORD.encode())
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401, detail="bad credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ---- Interview storage + rate limit --------------------------------------

INTERVIEW_PENDING = INTERVIEWS_DIR / "pending"
INTERVIEW_APPROVED = INTERVIEWS_DIR / "approved"
INTERVIEW_REJECTED = INTERVIEWS_DIR / "rejected"

_SUBMISSION_LOG: dict[str, list[float]] = {}
_SUBMISSION_ID_RE = re.compile(r"^[a-f0-9]{6,32}$")
_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_\-\.]{1,128}$")
_QID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")
_AUDIO_EXTS = {".webm", ".ogg", ".mp3", ".m4a", ".mp4", ".wav", ".flac"}
_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def _ensure_interview_dirs() -> None:
    for d in (INTERVIEW_PENDING, INTERVIEW_APPROVED, INTERVIEW_REJECTED):
        d.mkdir(parents=True, exist_ok=True)


def _rate_check(ip: str) -> None:
    now = time.time()
    cutoff = now - 86400
    log = _SUBMISSION_LOG.setdefault(ip, [])
    log[:] = [t for t in log if t > cutoff]
    if len(log) >= MAX_SUBMISSIONS_PER_IP_DAY:
        raise HTTPException(429, "too many submissions from your address; try again tomorrow")


def _rate_record(ip: str) -> None:
    _SUBMISSION_LOG.setdefault(ip, []).append(time.time())


def _safe_subpath(parent: Path, child: str) -> Path:
    p = (parent / child).resolve()
    parent_resolved = parent.resolve()
    if not str(p).startswith(str(parent_resolved) + os.sep) and p != parent_resolved:
        raise HTTPException(404)
    return p


def _find_submission_dir(sid: str) -> tuple[Path, str]:
    for parent, status in (
        (INTERVIEW_PENDING, "pending"),
        (INTERVIEW_APPROVED, "approved"),
        (INTERVIEW_REJECTED, "rejected"),
    ):
        d = parent / sid
        if d.exists() and d.is_dir():
            return d, status
    raise HTTPException(404, "submission not found")


def _list_submissions_in(dir_path: Path, status: str) -> list[dict]:
    if not dir_path.exists():
        return []
    out: list[dict] = []
    for entry in sorted(dir_path.iterdir()):
        if not entry.is_dir():
            continue
        meta_path = entry / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["status"] = status
            out.append(meta)
        except Exception as e:
            LOG.warning("bad metadata at %s: %s", meta_path, e)
    return out


# ---- Vertex / Gemini transcription ---------------------------------------

VERTEX_TRANSCRIBE_PROMPT = (
    "Transcribe this audio recorded at a Nepal government office. "
    "Output only the raw transcript text in the same script the speaker used "
    "(Devanagari Nepali, English, or code-mixed). "
    "Do not add preamble, JSON, headers, speaker labels, or commentary. "
    "If the audio is silent or unintelligible, return an empty string."
)

_AUDIO_MIME = {
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
}


def transcribe_audio_bytes_via_vertex(content: bytes, suffix: str) -> str:
    """Audio bytes -> text via Gemini-via-Vertex Express. Uses VERTEX_KEY."""
    if not VERTEX_KEY:
        raise HTTPException(500, "VERTEX_KEY not configured on server")
    if not content:
        return ""

    audio_b64 = base64.b64encode(content).decode("ascii")
    mime = _AUDIO_MIME.get(suffix.lower(), "audio/webm")
    body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"inline_data": {"mime_type": mime, "data": audio_b64}},
                {"text": VERTEX_TRANSCRIBE_PROMPT},
            ],
        }],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 4096},
    }
    url = f"https://aiplatform.googleapis.com/v1/publishers/google/models/{VERTEX_MODEL}:generateContent"
    with httpx.Client(timeout=180.0) as client:
        r = client.post(url, headers={
            "x-goog-api-key": VERTEX_KEY,
            "Content-Type": "application/json",
        }, json=body)
    if r.status_code != 200:
        LOG.warning("vertex transcribe failed: %s %s", r.status_code, r.text[:300])
        raise HTTPException(502, f"vertex transcribe failed ({r.status_code})")

    data = r.json()
    text = ""
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            if "text" in part:
                text += part["text"]
    return text.strip()


def transcribe_via_vertex(audio_path: Path) -> str:
    """Audio file -> text via Gemini-via-Vertex Express. Uses VERTEX_KEY."""
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)
    return transcribe_audio_bytes_via_vertex(
        audio_path.read_bytes(),
        audio_path.suffix,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _voice_script(name: str) -> str:
    return str(_repo_root() / "scripts" / name)


def _format_voice_command(template: str, values: dict[str, str]) -> list[str]:
    return [part.format(**values) for part in shlex.split(template)]


def _run_voice_json(cmd: list[str], *, timeout: float = VOICE_TIMEOUT_SECONDS) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "voice model timed out")
    except FileNotFoundError as e:
        raise HTTPException(503, f"voice command unavailable: {e.filename}")

    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        LOG.warning("voice command failed rc=%s: %s", proc.returncode, stderr[:500])
        raise HTTPException(502, f"voice model failed: {stderr[:300]}")

    raw = proc.stdout.strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"transcript": raw}


def _transcribe_audio_bytes_via_local_asr(content: bytes, suffix: str) -> tuple[str, str]:
    if VOICE_ASR_PROVIDER in {"fastconformer-worker", "asr-worker", "worker", "http-worker"}:
        filename = f"audio{suffix if suffix.startswith('.') else '.webm'}"
        mime = _AUDIO_MIME.get(Path(filename).suffix.lower(), "audio/webm")
        try:
            with httpx.Client(timeout=VOICE_TIMEOUT_SECONDS) as client:
                response = client.post(
                    f"{VOICE_ASR_WORKER_URL}/transcribe",
                    files={"audio": (filename, content, mime)},
                )
        except httpx.ConnectError:
            raise HTTPException(503, "local ASR worker is not running")
        except httpx.TimeoutException:
            raise HTTPException(504, "local ASR worker timed out")
        if response.status_code >= 400:
            raise HTTPException(response.status_code, response.text[:300])
        data = response.json()
        return str(data.get("transcript", "")).strip(), str(data.get("model_id", VOICE_ASR_MODEL_ID))

    with tempfile.TemporaryDirectory(prefix="speakgov-asr-") as tmp:
        audio_path = Path(tmp) / f"audio{suffix if suffix.startswith('.') else '.webm'}"
        audio_path.write_bytes(content)
        values = {
            "audio": str(audio_path),
            "model_id": VOICE_ASR_MODEL_ID,
            "nemo_file": VOICE_ASR_NEMO_FILE,
            "space_url": VOICE_ASR_SPACE_URL,
            "api_name": VOICE_ASR_SPACE_API_NAME,
            "python": sys.executable,
            "script": _voice_script("voice_fastconformer_asr.py"),
        }
        if VOICE_ASR_CMD:
            cmd = _format_voice_command(VOICE_ASR_CMD, values)
        else:
            cmd = [
                values["python"],
                values["script"],
                "--audio",
                values["audio"],
                "--model-id",
                values["model_id"],
                "--nemo-file",
                values["nemo_file"],
                "--json",
                "--timeout",
                str(VOICE_TIMEOUT_SECONDS),
            ]
            if VOICE_ASR_PROVIDER in {"fastconformer-space", "hf-space", "space"}:
                cmd.extend(["--space-url", values["space_url"], "--api-name", values["api_name"]])
        data = _run_voice_json(cmd)
        return str(data.get("transcript", "")).strip(), str(data.get("model_id", VOICE_ASR_MODEL_ID))


def _synthesize_speech_via_local_tts(req: VoiceSynthesizeRequest) -> tuple[bytes, dict[str, str]]:
    text = " ".join(req.text.split())
    if not text:
        raise HTTPException(400, "empty text")
    if len(text) > VOICE_TTS_MAX_CHARS:
        text = text[:VOICE_TTS_MAX_CHARS].rsplit(" ", 1)[0].strip() or text[:VOICE_TTS_MAX_CHARS]

    speaker = req.speaker or VOICE_TTS_SPEAKER
    if VOICE_TTS_PROVIDER in {"real-nepali-worker", "tts-worker", "worker", "http-worker"}:
        try:
            with httpx.Client(timeout=VOICE_TIMEOUT_SECONDS) as client:
                response = client.post(
                    f"{VOICE_TTS_WORKER_URL}/synthesize",
                    json={
                        "text": text,
                        "speaker": speaker,
                        "length_scale": req.length_scale,
                        "noise_scale": req.noise_scale,
                        "noise_scale_w": req.noise_scale_w,
                    },
                )
        except httpx.ConnectError:
            raise HTTPException(503, "local TTS worker is not running")
        except httpx.TimeoutException:
            raise HTTPException(504, "local TTS worker timed out")
        if response.status_code >= 400:
            raise HTTPException(response.status_code, response.text[:300])
        return response.content, {
            "provider": response.headers.get("X-Voice-Provider", VOICE_TTS_PROVIDER),
            "model_repo": response.headers.get("X-Voice-Model", VOICE_TTS_MODEL_REPO),
            "speaker": response.headers.get("X-Voice-Speaker", speaker),
            "sample_rate": response.headers.get("X-Voice-Sample-Rate", ""),
        }

    with tempfile.TemporaryDirectory(prefix="speakgov-tts-") as tmp:
        text_path = Path(tmp) / "input.txt"
        wav_path = Path(tmp) / "speech.wav"
        text_path.write_text(text, encoding="utf-8")
        values = {
            "text_file": str(text_path),
            "output": str(wav_path),
            "model_repo": VOICE_TTS_MODEL_REPO,
            "speaker": speaker,
            "space_url": VOICE_TTS_SPACE_URL,
            "api_name": VOICE_TTS_SPACE_API_NAME,
            "length_scale": str(req.length_scale),
            "noise_scale": str(req.noise_scale),
            "noise_scale_w": str(req.noise_scale_w),
            "python": sys.executable,
            "script": _voice_script("voice_real_nepali_tts.py"),
        }
        if VOICE_TTS_CMD:
            cmd = _format_voice_command(VOICE_TTS_CMD, values)
        else:
            cmd = [
                values["python"],
                values["script"],
                "--text-file",
                values["text_file"],
                "--output",
                values["output"],
                "--model-repo",
                values["model_repo"],
                "--speaker",
                values["speaker"],
                "--length-scale",
                values["length_scale"],
                "--noise-scale",
                values["noise_scale"],
                "--noise-scale-w",
                values["noise_scale_w"],
                "--json",
                "--timeout",
                str(VOICE_TIMEOUT_SECONDS),
            ]
            if VOICE_TTS_PROVIDER in {"real-nepali-space", "piper-space", "hf-space", "space"}:
                cmd.extend(["--space-url", values["space_url"], "--api-name", values["api_name"]])
        data = _run_voice_json(cmd)
        out_path = Path(str(data.get("output", wav_path)))
        if not out_path.exists():
            raise HTTPException(502, "tts model did not produce audio")
        return out_path.read_bytes(), {
            "provider": VOICE_TTS_PROVIDER,
            "model_repo": str(data.get("model_repo", VOICE_TTS_MODEL_REPO)),
            "speaker": str(data.get("speaker", speaker)),
            "sample_rate": str(data.get("sample_rate", "")),
        }


def _whatsapp_bridge_request(method: str, path: str, json_body: dict[str, Any] | None = None) -> Any:
    headers: dict[str, str] = {}
    if WHATSAPP_BRIDGE_TOKEN:
        headers["Authorization"] = f"Bearer {WHATSAPP_BRIDGE_TOKEN}"
    url = f"{WHATSAPP_BRIDGE_URL}{path}"
    try:
        with httpx.Client(timeout=WHATSAPP_BRIDGE_TIMEOUT_SECONDS) as client:
            response = client.request(method, url, headers=headers, json=json_body)
    except httpx.ConnectError:
        raise HTTPException(503, "WhatsApp bridge is not running")
    except httpx.TimeoutException:
        raise HTTPException(504, "WhatsApp bridge timed out")
    if response.status_code >= 400:
        detail = response.text[:500]
        raise HTTPException(response.status_code, detail)
    if not response.content:
        return {}
    return response.json()


def reload_tacit_retriever(app_obj: FastAPI) -> dict:
    tacit_dir = Path(TACIT_DIR).expanduser()
    new_tacit = TacitRetriever(tacit_dir)
    app_obj.state.tacit = new_tacit
    return new_tacit.stats()


# ---- Schemas --------------------------------------------------------------

class ChatHistoryTurn(BaseModel):
    role: str
    content: str = Field(..., min_length=1, max_length=2000)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    top_k_tacit: int = Field(default=TOP_K_TACIT, ge=0, le=10)
    top_k_gov: int = Field(default=TOP_K_GOV, ge=0, le=10)
    max_new_tokens: int = Field(default=MAX_NEW_TOKENS, ge=32, le=2048)
    seed: int | None = None
    history: list[ChatHistoryTurn] = Field(default_factory=list, max_length=8)
    response_language: str | None = Field(default=None, max_length=32)


class RetrieveRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    top_k_tacit: int = Field(default=TOP_K_TACIT, ge=0, le=10)
    top_k_gov: int = Field(default=TOP_K_GOV, ge=0, le=10)
    include_prompt: bool = False
    history: list[ChatHistoryTurn] = Field(default_factory=list, max_length=8)


class CitationOut(BaseModel):
    url: str
    rank: int
    snippet: str
    is_tacit: bool = False


class SourceOut(BaseModel):
    """All sources surfaced to the model (whether or not the answer cited them).
    Useful for the UI to show 'we considered these'."""
    rank: int
    source_ref: str
    is_tacit: bool
    label: str          # 'CITIZEN INTERVIEW' / 'GOV.NP'
    url: str | None = None
    snippet: str
    confidence: str | None = None
    interviewee_role: str | None = None


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    sources: list[SourceOut]   # everything fed to the model, in priority order
    did_refuse: bool
    retrieved_tacit: int
    retrieved_gov: int
    latency_ms: dict[str, int]
    detected_lang: str
    planner: dict[str, Any] | None = None


class RetrievedSourceOut(BaseModel):
    rank: int
    source_ref: str
    is_tacit: bool
    label: str
    url: str | None = None
    host: str | None = None
    snippet: str
    score: float | None = None
    rank_score: float | None = None
    relevance: str | None = None
    chunk_id: str | None = None
    source_id: str | None = None
    title: str | None = None
    doc_type: str | None = None
    tier: int | None = None
    confidence: str | None = None
    interviewee_role: str | None = None
    features: dict[str, Any] | None = None


class RetrievalQualityOut(BaseModel):
    passed: bool
    reason: str
    topic: str | None = None
    expected_domains: list[str] = Field(default_factory=list)
    best_gov_rank: int | None = None
    best_gov_host: str | None = None
    best_gov_rank_score: float | None = None


class RetrieveResponse(BaseModel):
    question: str
    sources: list[RetrievedSourceOut]
    quality: RetrievalQualityOut
    retrieved_tacit: int
    retrieved_gov: int
    latency_ms: dict[str, int]
    detected_lang: str
    prompt: str | None = None
    planner: dict[str, Any] | None = None


class VoiceTranscribeResponse(BaseModel):
    transcript: str
    latency_ms: dict[str, int]
    mime_type: str
    bytes: int
    provider: str = "vertex"
    model_id: str | None = None


class VoiceSynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    speaker: str | None = None
    length_scale: float = Field(default=1.0, ge=0.6, le=1.6)
    noise_scale: float = Field(default=0.667, ge=0.0, le=1.5)
    noise_scale_w: float = Field(default=0.8, ge=0.0, le=1.5)


class VoiceProvidersResponse(BaseModel):
    asr_provider: str
    asr_model_id: str | None = None
    asr_space_url: str | None = None
    tts_provider: str
    tts_model_repo: str | None = None
    tts_speaker: str | None = None
    tts_space_url: str | None = None
    tts_enabled: bool


class WhatsAppSendRequest(BaseModel):
    to: str = Field(..., min_length=3, max_length=80)
    text: str = Field(..., min_length=1, max_length=4000)


class WhatsAppClearHistoryRequest(BaseModel):
    jid: str | None = None


class OutreachDraftRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatHistoryTurn] = Field(default_factory=list, max_length=8)
    reason: str | None = Field(default=None, max_length=400)
    top_k_gov: int = Field(default=8, ge=1, le=10)


class OutreachContactCandidate(BaseModel):
    phone: str
    whatsapp_to: str
    source_url: str | None = None
    source_title: str | None = None
    source_host: str | None = None
    source_ref: str | None = None
    name: str | None = None
    role: str | None = None
    confidence: str = "official_source_mobile"


class OutreachDraftResponse(BaseModel):
    id: str
    status: str
    created_at: str
    question: str
    gap_reason: str
    contact: OutreachContactCandidate | None = None
    message: str
    planner: dict[str, Any]
    contact_query: str
    sources: list[dict[str, Any]]
    candidates: list[OutreachContactCandidate] = Field(default_factory=list)


class OutreachSendResponse(BaseModel):
    id: str
    status: str
    sent_at: str | None = None
    send_result: dict[str, Any] | None = None


# ---- Endpoints ------------------------------------------------------------


@app.get("/health")
def health(request: Request):
    composer: Composer = request.app.state.composer
    retriever: Retriever | None = request.app.state.retriever
    return {
        "status": "ok",
        "model_id": MODEL_ID,
        "adapter": ADAPTER_PATH,
        "model_loaded": composer._loaded,
        "db_loaded": retriever is not None,
        "startup_at": request.app.state.startup_at,
    }


@app.get("/admin/info")
def admin_info(request: Request):
    _check_tailnet(request)
    retriever: Retriever | None = request.app.state.retriever
    tacit: TacitRetriever = request.app.state.tacit
    return {
        "model_id": MODEL_ID,
        "adapter": ADAPTER_PATH,
        "max_new_tokens": MAX_NEW_TOKENS,
        "top_k_tacit": TOP_K_TACIT,
        "top_k_gov": TOP_K_GOV,
        "retriever_gov": retriever.stats() if retriever else None,
        "retriever_tacit": tacit.stats(),
        "startup_at": request.app.state.startup_at,
    }


@app.post("/admin/reindex")
def admin_reindex(request: Request):
    _check_tailnet(request)
    retriever: Retriever | None = request.app.state.retriever
    if retriever is None:
        raise HTTPException(503, "retriever not loaded")
    return retriever.reindex()


def _detect_lang(text: str) -> str:
    deva = sum(1 for c in text if "ऀ" <= c <= "ॿ")
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    if deva + latin == 0:
        return "english"
    if deva / (deva + latin) > 0.5:
        return "devanagari"
    # crude roman-NE marker check
    if re.search(
        r"\b(kasari|kun|kaha|ke|chha|cha|garna|garne|parcha|huncha|chaina|"
        r"hos|janu|garnu|hami|tapai|mero|tyo|yo|hoina|ho|nai)\b",
        text, re.I,
    ):
        return "roman_nepali"
    return "english"


def _script_counts(text: str) -> tuple[int, int]:
    devanagari = sum(1 for c in text if "ऀ" <= c <= "ॿ")
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    return devanagari, latin


_DEVANAGARI_VOWELS = {
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
}
_DEVANAGARI_MATRAS = {
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
}
_DEVANAGARI_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "ळ": "l",
}
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_ROMANIZATION_FIXES = (
    (re.compile(r"\bvaideshika\b", re.I), "vaideshik"),
    (re.compile(r"\brojagara\b", re.I), "rojgar"),
    (re.compile(r"\bvibhaga\b", re.I), "vibhag"),
    (re.compile(r"\bmantralaya\b", re.I), "mantralaya"),
)
_ROMAN_WORD_OVERRIDES = {
    "तपाईं": "tapai",
    "तपाइँ": "tapai",
    "आफू": "aafu",
    "परिवार": "pariwar",
    "मार्फत": "marfat",
    "कल सेन्टर": "call center",
    "म्यानपावर": "manpower",
    "वैदेशिक रोजगार": "baideshik rojgar",
    "वैदेशिक": "baideshik",
    "रोजगार": "rojgar",
    "विभाग": "bibhag",
    "बोर्ड": "board",
    "मन्त्रालय": "mantralaya",
    "गुनासो": "gunaso",
    "समस्या": "samasya",
    "उजुरी": "ujuri",
    "ठगिएको": "thagiyeko",
    "ठगेको": "thageko",
    "ठगी": "thagi",
    "सम्पर्क": "contact",
    "नम्बर": "number",
    "निशुल्क": "free",
    "अनलाइन": "online",
    "फाराम": "form",
    "राहदानी": "rahdani",
    "नागरिकता": "nagarikta",
    "प्रमाणपत्र": "pramanpatra",
    "कार्यालय": "karyalaya",
    "स्रोत": "source",
    "आधिकारिक": "adhikarik",
}
_ROMAN_OUTPUT_FIXES = (
    (re.compile(r"\baaple\b", re.I), "tapai le"),
    (re.compile(r"\btapaille\b", re.I), "tapai le"),
    (re.compile(r"\btapai\s+family\b", re.I), "tapai le family"),
    (re.compile(r"\bparivara\b", re.I), "pariwar"),
    (re.compile(r"\bmanpowerle\b", re.I), "manpower le"),
    (re.compile(r"\bmarphata\b", re.I), "marfat"),
    (re.compile(r"\bmargamarkha\b", re.I), "marfat"),
    (re.compile(r"\bYasaigari\b", re.I), "Yasai gari"),
    (re.compile(r"\bTathapara\b", re.I), "Tara"),
    (re.compile(r"\bkala sentara\b", re.I), "call center"),
    (re.compile(r"\bboardko\b", re.I), "board ko"),
    (re.compile(r"\bkaryalayama\b", re.I), "karyalaya ma"),
    (re.compile(r"\bujurika\b", re.I), "ujuri ko"),
    (re.compile(r"\bthagiko\b", re.I), "thagi ko"),
    (re.compile(r"\btyasako\b", re.I), "tyasko"),
    (re.compile(r"\bsambandhama\b", re.I), "sambandha ma"),
    (re.compile(r"\bpramukha\b", re.I), "pramukh"),
    (re.compile(r"\bijajatpatravalale\b", re.I), "ijajatpatra wala le"),
    (re.compile(r"\bvyakti va\b", re.I), "vyakti wa"),
    (re.compile(r"\b(v|b)aideshik rojgar vibhagma\s+ma\b", re.I), "Baideshik Rojgar Bibhag ma"),
    (re.compile(r"\b(v|b)ibhagma\s+ma\b", re.I), "Bibhag ma"),
    (re.compile(r"\b(v|b)ibhagma\b", re.I), "Bibhag ma"),
    (re.compile(r"\bpardachha\b", re.I), "parcha"),
    (re.compile(r"\bnumberma\b", re.I), "number ma"),
    (re.compile(r"\bsakinchha\b", re.I), "sakincha"),
    (re.compile(r"\bcontact garna sakinchha\b", re.I), "contact garna sakincha"),
    (re.compile(r"\bsaknu\s+hunchha\b", re.I), "saknuhuncha"),
    (re.compile(r"\bsaknu?hunchha\b", re.I), "saknuhuncha"),
    (re.compile(r"\bgarnu\s+parnuhuncha\b", re.I), "garnu parcha"),
    (re.compile(r"\b1141\s+garnuhos\b", re.I), "1141 ma phone garnuhos"),
    (re.compile(r"\bVyaktiyata\b", re.I), "Vyaktigat"),
)


def _romanize_devanagari(text: str) -> str:
    """Lightweight Nepali Devanagari -> Latin-script bridge for prompts/output.

    This is deliberately simple and dependency-free. It is not a canonical
    transliterator; it gives the model/readers a Roman-Nepali view of retrieved
    evidence while preserving citations, numbers, URLs, and existing Latin text.
    """
    text = text or ""
    for deva, roman in sorted(_ROMAN_WORD_OVERRIDES.items(), key=lambda item: len(item[0]), reverse=True):
        text = text.replace(deva, roman)
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in _DEVANAGARI_CONSONANTS:
            base = _DEVANAGARI_CONSONANTS[ch]
            if i + 1 < n and text[i + 1] == "्":
                out.append(base)
                i += 2
                continue
            if i + 1 < n and text[i + 1] in _DEVANAGARI_MATRAS:
                out.append(base + _DEVANAGARI_MATRAS[text[i + 1]])
                i += 2
                continue
            out.append(base + "a")
        elif ch in _DEVANAGARI_VOWELS:
            out.append(_DEVANAGARI_VOWELS[ch])
        elif ch in _DEVANAGARI_MATRAS:
            out.append(_DEVANAGARI_MATRAS[ch])
        elif ch in {"ं", "ँ"}:
            out.append("n")
        elif ch == "ः":
            out.append("h")
        elif ch == "्":
            pass
        elif ch == "।":
            out.append(".")
        else:
            out.append(ch.translate(_DEVANAGARI_DIGITS))
        i += 1
    romanized = "".join(out)
    for pattern, replacement in _ROMANIZATION_FIXES:
        romanized = pattern.sub(replacement, romanized)
    return _clean_roman_nepali_output(romanized)


def _clean_roman_nepali_output(text: str) -> str:
    out = re.sub(r"[ \t]+", " ", text or "").strip()
    for pattern, replacement in _ROMAN_OUTPUT_FIXES:
        out = pattern.sub(replacement, out)
    return out


def _answer_script_mismatch(answer: str, expected_lang: str) -> bool:
    devanagari, latin = _script_counts(answer or "")
    if expected_lang == "english":
        # Allow copied Nepali names/titles, but never a Devanagari-dominant
        # answer to an English question.
        return devanagari > 24 and devanagari > max(24, latin * 0.20)
    if expected_lang == "roman_nepali":
        # Roman Nepali must remain Latin script. A little Devanagari may appear
        # in copied official names, but full Devanagari sentences are blocked.
        return devanagari > 12 and devanagari > max(12, latin * 0.08)
    return False


def _language_guard_fallback_answer(
    lang: str,
    tacit_results: list[dict],
    gov_results: list[dict],
) -> str:
    has_sources = bool(tacit_results or gov_results)
    cite = " [S1]" if has_sources else ""
    if not has_sources:
        return _no_source_answer(lang)
    if lang == "roman_nepali":
        return (
            "Relevant official source bhetio, tara safe Roman-Nepali summary "
            f"banauna sakina. Source {cite.strip()} hernu, wa exact office/district "
            "dinu bhane ma narrower answer dinchu."
        )
    return (
        "I found a relevant official source, but I could not safely produce an "
        f"English source-backed summary from it. Please use the cited source{cite}, "
        "or ask with the exact office/district so I can narrow the answer."
    )


def _guard_answer_language(
    answer: str,
    expected_lang: str,
    tacit_results: list[dict],
    gov_results: list[dict],
) -> str:
    if expected_lang == "roman_nepali" and not _answer_script_mismatch(answer, expected_lang):
        if _script_counts(answer or "")[0] > 0:
            answer = _romanize_devanagari(answer)
        return _clean_roman_nepali_output(answer)
    if not _answer_script_mismatch(answer, expected_lang):
        return answer
    if expected_lang == "roman_nepali" and (
        SOURCE_ID_CITATION_RE.search(answer or "") or SOURCE_ID_GROUP_RE.search(answer or "")
    ):
        romanized = _romanize_devanagari(answer)
        if not _answer_script_mismatch(romanized, expected_lang):
            return _clean_generated_answer(_clean_roman_nepali_output(romanized))
    devanagari, latin = _script_counts(answer or "")
    LOG.warning(
        "blocked generated answer with wrong script expected_lang=%s devanagari=%s latin=%s",
        expected_lang,
        devanagari,
        latin,
    )
    return _language_guard_fallback_answer(expected_lang, tacit_results, gov_results)


def _repair_answer_language_with_composer(
    composer: "Composer",
    answer: str,
    expected_lang: str,
    *,
    max_tokens: int = 384,
    seed: int | None = None,
) -> str | None:
    if expected_lang != "english":
        return None
    if not _answer_script_mismatch(answer, expected_lang):
        return answer
    if not (
        SOURCE_ID_CITATION_RE.search(answer or "")
        or SOURCE_ID_GROUP_RE.search(answer or "")
    ):
        return None
    repair_prompt = (
        "Requested language: English.\n"
        "Rewrite the draft below into concise English for the user. Preserve every "
        "source citation ID that supports the same claim. Do not add any new claim, "
        "phone number, office name, fee, date, or document. If a Nepali office name "
        "appears, translate the role/office type when obvious and keep the personal "
        "or official name readable in Latin script when possible.\n\n"
        f"Draft answer:\n{answer.strip()}"
    )
    try:
        repaired = composer.generate(
            SYSTEM_LANGUAGE_REPAIR,
            repair_prompt,
            max_tokens=max_tokens,
            seed=seed,
        )
    except Exception:
        LOG.exception("language repair generation failed")
        return None
    repaired = _clean_generated_answer((repaired or "").strip())
    if not repaired:
        return None
    if _answer_script_mismatch(repaired, expected_lang):
        devanagari, latin = _script_counts(repaired)
        LOG.warning(
            "language repair still wrong script expected_lang=%s devanagari=%s latin=%s",
            expected_lang,
            devanagari,
            latin,
        )
        return None
    return repaired


IDENTITY_QUERY_RE = re.compile(
    r"\b("
    r"who\s+are\s+you|what\s+are\s+you|your\s+purpose|what\s+is\s+your\s+purpose|"
    r"are\s+you\s+(?:a\s+)?(?:sebon|passport|police|bank|nrb|ird).*chatbot|"
    r"sebon\s+chatbot|"
    r"timi\s+ko\s+ho|tapai\s+ko\s+ho|tapa[iy]\s+ko\s+ho|"
    r"timi\s+ke\s+ho|tapai\s+ke\s+ho|"
    r"timro\s+purpose|tapai(?:ko)?\s+purpose"
    r")\b",
    re.I,
)


def _is_identity_question(text: str) -> bool:
    if IDENTITY_QUERY_RE.search(text):
        return True
    return any(marker in text for marker in (
        "तिमी को", "तपाईं को", "तपाई को", "तिमी के", "तपाईं के", "तपाई के",
        "तिम्रो उद्देश्य", "तपाईंको उद्देश्य", "तपाईको उद्देश्य",
        "सेबोन च्याटबोट", "च्याटबोट हो",
    ))


def _identity_answer(lang: str) -> str:
    if lang == "devanagari":
        return (
            "म SpeakGov हुँ। म नेपालका सरकारी सेवाहरूबारे आधिकारिक स्रोतका "
            "आधारमा जानकारी खोज्न र बुझ्न सहयोग गर्ने स्वतन्त्र सहायक हुँ। "
            "म कुनै सरकारी निकायको प्रतिनिधि होइन।"
        )
    if lang == "roman_nepali":
        return (
            "Ma SpeakGov ho. Ma Nepal ko sarkari services bare official sources "
            "ko adhar ma information khojna ra bujhna help garne independent "
            "assistant ho. Ma kunai government agency ko representative haina."
        )
    return (
        "I am SpeakGov, an independent assistant for navigating Nepal government "
        "services. I use official government sources to help find and explain "
        "service information, but I do not represent any government agency."
    )


def _no_source_answer(lang: str) -> str:
    if lang == "devanagari":
        return "मलाई यो प्रश्नको आधिकारिक स्रोत भेटिनँ।"
    if lang == "roman_nepali":
        return "Yo prashnako adhikarik srot bhetina."
    return "I cannot find an authoritative source for this."


FOLLOWUP_CONTEXT_RE = re.compile(
    r"\b("
    r"this|that|it|they|them|those|above|previous|same|again|properly|"
    r"check|recheck|wrong|not right|no check|source|sources|citation|"
    r"yo|tyo|tesko|teslai|feri|paila|mathi"
    r")\b",
    re.I,
)

SHORT_FOLLOWUP_RE = re.compile(
    r"^\s*(?:"
    r"documents?|docs?|fees?|cost|price|process|procedure|requirements?|"
    r"how much|how long|where|when|"
    r"कागजात|शुल्क|दस्तुर|प्रक्रिया|कहाँ|कहिले"
    r")\b",
    re.I,
)

RECHECK_PREVIOUS_RE = re.compile(
    r"^\s*(?:no\s+)?(?:check|recheck|look|search|retrieve|answer)\s+"
    r"(?:it|this|that|again|properly|carefully)?\s*$|"
    r"\b(?:not\s+right|wrong|check\s+properly|no\s+check\s+properly)\b",
    re.I,
)


def _compact_history(history: list[ChatHistoryTurn] | None, max_turns: int = 6) -> list[ChatHistoryTurn]:
    out: list[ChatHistoryTurn] = []
    for h in (history or [])[-max_turns:]:
        role = (h.role or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        content = re.sub(r"\s+", " ", (h.content or "").strip())
        if not content:
            continue
        limit = 700 if role == "assistant" else 400
        out.append(ChatHistoryTurn(role=role, content=content[:limit]))
    return out


def _same_turn_text(a: str, b: str) -> bool:
    return re.sub(r"\s+", " ", (a or "").strip()) == re.sub(r"\s+", " ", (b or "").strip())


def _history_without_current_turn(
    history: list[ChatHistoryTurn] | None,
    question: str,
    *,
    max_turns: int = 8,
) -> list[ChatHistoryTurn]:
    turns = _compact_history(history, max_turns=max_turns)
    if turns and turns[-1].role == "user" and _same_turn_text(turns[-1].content, question):
        return turns[:-1]
    return turns


def _needs_history_for_retrieval(question: str) -> bool:
    topic = _detect_retrieval_topic(question)
    local_domains = _detect_local_domains(question)
    if topic or local_domains:
        return False
    if RECHECK_PREVIOUS_RE.search(question):
        return True
    if FOLLOWUP_CONTEXT_RE.search(question):
        return True
    if SHORT_FOLLOWUP_RE.search(question):
        return True
    return False


def _last_user_question(history: list[ChatHistoryTurn] | None) -> str:
    for h in reversed(_compact_history(history, max_turns=8)):
        if h.role == "user":
            return h.content
    return ""


def _response_language(payload: RetrieveRequest | QueryRequest) -> str:
    override = (getattr(payload, "response_language", None) or "").strip().lower()
    aliases = {
        "ne": "devanagari",
        "nepali": "devanagari",
        "devanagari": "devanagari",
        "roman": "roman_nepali",
        "roman-nepali": "roman_nepali",
        "roman_nepali": "roman_nepali",
        "en": "english",
        "english": "english",
    }
    return aliases.get(override) or _detect_lang(payload.question)


def _navigator_frame(payload: RetrieveRequest | QueryRequest) -> CaseFrame:
    history = _history_without_current_turn(payload.history, payload.question)
    frame = resolve_case(
        payload.question.strip(),
        history,
        registry_path=SOURCE_REGISTRY_PATH,
    )
    response_language = _response_language(payload)
    if response_language != frame.language:
        frame = replace(frame, language=response_language)
    return frame


def _retrieval_question(payload: RetrieveRequest | QueryRequest) -> str:
    frame = _navigator_frame(payload)
    if frame.retrieval_query:
        return frame.retrieval_query
    question = payload.question.strip()
    history = _history_without_current_turn(payload.history, question)
    previous_user = _last_user_question(history)
    if previous_user and _needs_history_for_retrieval(question):
        return f"{previous_user} {question}"
    return question


def _prompt_question(payload: RetrieveRequest | QueryRequest) -> str:
    frame = _navigator_frame(payload)
    question = payload.question.strip()
    history = _history_without_current_turn(payload.history, question)
    previous_user = _last_user_question(history)
    if previous_user and RECHECK_PREVIOUS_RE.search(question):
        return previous_user
    if previous_user and frame.contextual_followup:
        return (
            f"{previous_user}\n"
            f"Latest follow-up: {question}\n"
            "The latest follow-up fills missing case details. Answer the original service case using the updated details."
        )
    if previous_user and _needs_history_for_retrieval(question):
        return (
            f"{previous_user}\n"
            f"Latest follow-up: {question}\n"
            "Answer the latest follow-up using the previous question as the subject."
        )
    return question


def _prompt_history(payload: RetrieveRequest | QueryRequest) -> list[ChatHistoryTurn]:
    history = _history_without_current_turn(payload.history, payload.question)
    frame = _navigator_frame(payload)
    if _last_user_question(history) and RECHECK_PREVIOUS_RE.search(payload.question.strip()):
        return []
    if frame.contextual_followup:
        return history
    if not _needs_history_for_retrieval(payload.question.strip()):
        return []
    return history


def _history_prompt(history: list[ChatHistoryTurn] | None) -> str:
    turns = _compact_history(history, max_turns=6)
    if not turns:
        return ""
    lines = [
        "Conversation context for interpreting follow-up questions only.",
        "This context is NOT a source; factual claims must still come from Sources below.",
    ]
    for h in turns:
        label = "User" if h.role == "user" else "Assistant"
        lines.append(f"{label}: {h.content}")
    return "\n".join(lines)


def _run_retrieval(
    retriever: Retriever | None,
    tacit: TacitRetriever,
    payload: RetrieveRequest | QueryRequest,
) -> tuple[list[dict], list[dict], int]:
    t0 = time.time()
    frame = _navigator_frame(payload)
    retrieval_question = frame.retrieval_query or _retrieval_question(payload)
    tacit_results = tacit.search(retrieval_question, top_k=payload.top_k_tacit)
    tacit_results = filter_tacit_results_for_frame(frame, tacit_results)
    gov_results: list[dict] = []
    if retriever is not None and payload.top_k_gov > 0:
        gov_results = retriever.search(retrieval_question, top_k=payload.top_k_gov)
    gov_results = filter_gov_results_for_frame(frame, gov_results)
    return tacit_results, gov_results, int((time.time() - t0) * 1000)


def _build_source_out(tacit_results: list[dict], gov_results: list[dict]) -> list[SourceOut]:
    sources: list[SourceOut] = []
    rank = 0
    for t in tacit_results:
        rank += 1
        sources.append(SourceOut(
            rank=rank,
            source_ref=f"S{rank}",
            is_tacit=True,
            label="CITIZEN INTERVIEW",
            url=t.get("office_url") or None,
            snippet=(t.get("claim") or "")[:280],
            confidence=t.get("confidence"),
            interviewee_role=t.get("interviewee_role"),
        ))
    for g in gov_results:
        rank += 1
        feature_markers = tuple(g.get("features", {}).get("strong_hits") or ())
        sources.append(SourceOut(
            rank=rank,
            source_ref=f"S{rank}",
            is_tacit=False,
            label="GOV.NP",
            url=g.get("url"),
            snippet=_focused_snippet(
                g.get("text") or "",
                feature_markers or tuple(_expanded_retrieval_tokens(g.get("url") or "")),
                280,
            ),
        ))
    return sources


def _locality_display_from_domains(local_domains: tuple[str, ...], lang: str) -> str:
    for domain in local_domains:
        labels = LOCALITY_DISPLAY_BY_DOMAIN.get(domain)
        if labels:
            return labels.get(lang) or labels.get("english") or domain
    if lang == "devanagari":
        return "सम्बन्धित नगरपालिका"
    if lang == "roman_nepali":
        return "sambandhit municipality"
    return "the relevant municipality"


def _service_fallback_answer(question: str, gov_results: list[dict], lang: str) -> str | None:
    """Narrow extractive fallback for common local event-registration questions.

    v4b/E2B is over-trained to refuse when a national procedure source does not
    name the municipality. For birth registration, DONIDCR is the authoritative
    national source and the ward/local registrar rule is inherently local.
    """
    topic = _detect_retrieval_topic(question)
    if topic not in {"birth_registration", "vital_registration"} or not _detect_local_domains(question):
        return None
    if topic == "vital_registration":
        subtopic = _event_subtopic(question)
        if subtopic and subtopic[0] != "birth":
            return None
        if not subtopic and not _birth_registration_intent(question):
            return None

    if topic == "birth_registration" and not _birth_registration_intent(question):
        return None

    national = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("donidcr.gov.np",))
            and (
                "जन्म दर्ता" in (g.get("text") or "")
                or "घटना दर्ताको प्रमाणपत्र" in (g.get("text") or "")
                or "birth registration" in (g.get("text") or "").lower()
            )
        ),
        None,
    )
    if not national:
        return None

    local_domains = _detect_local_domains(question)
    local = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), local_domains)
            and (
                "वडा कार्यालय" in (g.get("text") or "")
                or "घटना दर्ता सेवा" in (g.get("text") or "")
            )
        ),
        None,
    )
    if not local:
        local = next(
            (g for g in gov_results if _domain_matches(g.get("host"), local_domains)),
            None,
        )

    national_url = national.get("url") or ""
    local_url = (local or {}).get("url") or ""
    local_cite = f" [{local_url}]" if local_url else ""
    local_text = (local or {}).get("text") or ""
    local_name = _locality_display_from_domains(local_domains, lang)
    local_event_context = (
        "वडा कार्यालय" in local_text
        or "घटना दर्ता सेवा" in local_text
        or "event registration" in local_text.lower()
    )

    if lang == "devanagari":
        local_sentence = (
            f"{local_name}को स्रोतले घटना दर्ता सेवा वडा/स्थानीय सेवा सन्दर्भमा देखाउँछ{local_cite}। "
            if local_event_context
            else f"{local_name}का लागि छुट्टै स्थानीय जन्मदर्ता जाँचसूची प्राप्त स्रोतमा स्पष्ट भेटिएन। "
        )
        local_confirm_cite = local_cite if local_event_context else ""
        return (
            f"{local_name}मा जन्म प्रमाणपत्रका लागि यसलाई जन्म दर्ता/घटना दर्ताको प्रमाणपत्रको प्रक्रियाका रूपमा लिनुहोस्। "
            f"DONIDCR का अनुसार जन्म/मृत्युको सूचना फाराम विभागको वेबसाइटबाट प्राप्त गर्न सकिन्छ र घटना दर्ताको प्रमाणपत्रका लागि सूचना फाराम तथा आवश्यक कागजातको सक्कलसहित स्थानीय पञ्जिकाधिकारीसमक्ष पेश गर्नुपर्छ [{national_url}]। "
            f"{local_sentence}"
            f"जन्म दर्ताका लागि DONIDCR ले बाबु वा आमाको नागरिकता/राहदानी प्रमाणपत्रको प्रतिलिपि, स्वास्थ्य संस्था/अस्पतालमा जन्म भए त्यहाँबाट जारी प्रमाण, घरमा जन्म भए पहिलो खोप दिएको प्रमाण, र जन्मको सूचना फाराम उल्लेख गरेको छ [{national_url}]। "
            f"{local_name}मा अन्तिम कागजात र शुल्क आफ्नो सम्बन्धित वडा कार्यालय/स्थानीय पञ्जिकाधिकारीसँग पुष्टि गर्नुहोस्{local_confirm_cite}।"
        )

    if lang == "roman_nepali":
        local_sentence = (
            f"{local_name} source le event-registration service ward/local service context ma dekhaucha{local_cite}. "
            if local_event_context
            else f"{local_name} ko separate birth-specific checklist retrieved source ma clear bhetiena. "
        )
        local_confirm_cite = local_cite if local_event_context else ""
        return (
            f"{local_name} ma birth certificate ko lagi birth registration/event-registration certificate process follow garnu parcha. "
            f"DONIDCR le birth/death notice form department ko website bata paune, ani event-registration certificate ko lagi notice form ra original supporting documents local registrar ma pesh garne bhaneko cha [{national_url}]. "
            f"{local_sentence}"
            f"Birth registration documents ma father/mother ko citizenship/passport copy, hospital/health institution ma janmeko bhaye tyahako proof, ghar ma janmeko bhaye first-vaccination proof, ra birth information form parcha [{national_url}]. "
            f"{local_name} ma final documents/fee afno ward office/local registrar ma confirm garnu{local_confirm_cite}."
        )

    local_sentence = (
        f"The {local_name} source gives the local ward/service context for event-registration services{local_cite}. "
        if local_event_context
        else f"I did not find a separate local birth-specific checklist for {local_name} in the retrieved sources. "
    )
    local_confirm_cite = local_cite if local_event_context else ""
    return (
        f"For {local_name}, treat this as birth registration / an event-registration certificate. "
        f"DONIDCR says the birth/death notice form is available from the department website, and an event-registration certificate is obtained by submitting the notice form with original supporting documents to the local registrar [{national_url}]. "
        f"{local_sentence}"
        f"For birth registration documents, DONIDCR lists: a copy of the father’s or mother’s citizenship/passport certificate; if the child was born in a health institution/hospital, proof issued by that institution; if born at home, proof of the first vaccination; and the birth information form [{national_url}]. "
        f"Confirm the final fee/documents at the relevant ward office or local registrar{local_confirm_cite}."
    )


def _police_clearance_fallback_answer(question: str, gov_results: list[dict], lang: str) -> str | None:
    if _detect_retrieval_topic(question) != "police":
        return None
    q = question.lower()
    if not (
        "clearance" in q
        or "police report" in q
        or "character" in q
        or "चालचलन" in question
        or "चारित्रिक" in question
    ):
        return None
    source = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("nepalpolice.gov.np",))
            and (
                "clearance" in (g.get("url") or "").lower()
                or "चारित्रिक प्रमाणपत्र" in (g.get("text") or "")
                or "चारीत्रिक प्रमाणपत्र" in (g.get("text") or "")
                or "चालचलन प्रमाणपत्र" in (g.get("text") or "")
            )
        ),
        None,
    )
    if not source:
        return None
    url = source.get("url") or ""

    if lang == "devanagari":
        return (
            f"नेपाल प्रहरीको स्रोतअनुसार चारित्रिक प्रमाणपत्र/Police Clearance Report का लागि अनलाइन निवेदन दिनुपर्छ [{url}]। "
            f"नेपालमै रहेका नेपाली नागरिकका लागि अनलाइन निवेदनसँग राहदानीको प्रतिलिपि, नागरिकताको प्रतिलिपि, विवाहित भए विवाह दर्ताको प्रतिलिपि, र हालसालै खिचिएको पासपोर्ट साइजको रंगीन फोटो पेश गर्नुपर्ने उल्लेख छ [{url}]। "
            f"विदेशमा रहेका नेपाली नागरिकका लागि राहदानीका तोकिएका पृष्ठ/नेपाल इमिग्रेसन departure stamp भएको पृष्ठ, नागरिकताको प्रतिलिपि, विवाहित भए विवाह दर्ता प्रतिलिपि, र पासपोर्ट साइज फोटो चाहिन्छ [{url}]। "
            f"थप सोधपुछका लागि स्रोतमा chalchalan@nepalpolice.gov.np, +977 01-5719865, 9851285920 उल्लेख छ [{url}]।"
        )
    if lang == "roman_nepali":
        return (
            f"Nepal Police ko source anusar Police Clearance Report/charitrik pramanpatra ko lagi online application dinu parcha [{url}]. "
            f"Nepal bhitra रहेका Nepali citizen ko lagi passport copy, citizenship copy, married bhaye marriage-registration copy, ra recent passport-size color photo upload/pesh garnu parcha [{url}]. "
            f"Bidesh ma रहेका Nepali citizen ko lagi passport ko specified pages, Nepal Immigration departure-stamp page, citizenship copy, married bhaye marriage-registration copy, ra passport-size photo chahinchha [{url}]. "
            f"Further inquiry: chalchalan@nepalpolice.gov.np, +977 01-5719865, 9851285920 [{url}]."
        )
    return (
        f"Nepal Police says a Police Clearance Report/character certificate is requested through an online application [{url}]. "
        f"For Nepali citizens in Nepal, the online application must include: a copy of the passport, a copy of citizenship, a copy of marriage registration if married, and one recent passport-size color photo [{url}]. "
        f"For Nepali citizens abroad, it asks for specified passport pages including the Nepal Immigration departure-stamp page, citizenship copy, marriage-registration copy if married, and a recent passport-size photo [{url}]. "
        f"For further inquiry, the Nepal Police page lists chalchalan@nepalpolice.gov.np, +977 01-5719865, and 9851285920 [{url}]."
    )


def _passport_fee_fallback_answer(question: str, gov_results: list[dict], lang: str) -> str | None:
    if _detect_retrieval_topic(question) != "passport":
        return None
    q = question.lower()
    if not (
        "fee" in q
        or "cost" in q
        or "charge" in q
        or "price" in q
        or "दस्तुर" in question
        or "शुल्क" in question
    ):
        return None
    source = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("nepalpassport.gov.np",))
            and (
                "राहदानीको शुल्क" in (g.get("text") or "")
                or "राहदानी दस्तुर" in (g.get("text") or "")
                or "दस्तुर" in (g.get("text") or "")
                or "शुल्क" in (g.get("text") or "")
            )
        ),
        None,
    )
    if not source:
        return None
    url = source.get("url") or ""

    if lang == "devanagari":
        return (
            f"प्राप्त Department of Passports स्रोतले एउटै निश्चित renewal fee रकम देखाउँदैन; "
            f"राहदानीको आवश्यक शुल्क दर्ता केन्द्र अनुसार फरक पर्छ भनी उल्लेख गर्छ [{url}]. "
            f"शुल्क अनलाइन, बैंक ट्रान्सफर वा नगद रूपमा बुझाउने व्यवस्था हुन सक्छ, त्यसैले आफ्नो आवेदन/दर्ता केन्द्रबाट अन्तिम रकम पुष्टि गर्नुहोस् [{url}]."
        )
    if lang == "roman_nepali":
        return (
            f"Retrieved Department of Passports source le single fixed renewal fee amount dekhaundaina; "
            f"passport ko required fee registration center anusar farak parcha bhaneko cha [{url}]. "
            f"Fee online, bank transfer, wa cash bata tirna milna sakcha, so final amount afno application/registration center bata confirm garnu [{url}]."
        )
    return (
        f"The retrieved Department of Passports source does not give one fixed passport-renewal fee amount; "
        f"it says the required passport fee varies by registration center [{url}]. "
        f"It also says payment may be arranged online, by bank transfer, or in cash, so confirm the final amount with your application/registration center [{url}]."
    )


def _passport_renewal_fallback_answer(question: str, gov_results: list[dict], lang: str) -> str | None:
    if _detect_retrieval_topic(question) != "passport":
        return None
    q = question.lower()
    if not (
        "renew" in q
        or "renewal" in q
        or "nawikaran" in q
        or "nabikaran" in q
        or "नवीकरण" in question
        or "नविकरण" in question
    ):
        return None
    if any(term in q for term in ("fee", "cost", "charge", "price")) or any(
        term in question for term in ("दस्तुर", "शुल्क")
    ):
        return None

    online = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("nepalpassport.gov.np",))
            and (
                "pre-enrollment" in (g.get("text") or "").lower()
                or "renewal" in (g.get("text") or "").lower()
                or "अनलाइनबाट फाराम" in (g.get("text") or "")
            )
        ),
        None,
    )
    normal = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("nepalpassport.gov.np",))
            and (
                "जिल्ला वा इलाका प्रशासन कार्यालय" in (g.get("text") or "")
                or "10 देखि 30 दिन" in (g.get("text") or "")
                or "द्रुत सेवा" in (g.get("text") or "")
            )
        ),
        None,
    )
    if not online and not normal:
        return None
    online_url = (online or normal or {}).get("url") or ""
    normal_url = (normal or online or {}).get("url") or ""

    if lang == "devanagari":
        return (
            f"राहदानी नवीकरणका लागि पहिले अनलाइन pre-enrollment फाराम भरी मिति/समय बुक गर्नुपर्छ; आवेदन प्रकारमा Renewal विकल्प छान्ने प्रक्रिया स्रोतमा उल्लेख छ [{online_url}]. "
            f"नेपालमा हुनुहुन्छ भने नागरिकता वा नाबालक परिचयपत्र जारी भएको जिल्ला/इलाका प्रशासन कार्यालयमा आवेदन दिन सकिन्छ [{normal_url}]. "
            f"सामान्य प्रक्रियामा जिल्ला/इलाका प्रशासन कार्यालयमा आवेदन दर्ता भएपछि प्रायः १० देखि ३० दिनभित्र राहदानी प्राप्त हुन्छ [{normal_url}]. "
            f"तत्काल चाहिएको अवस्थामा राहदानी विभाग, त्रिपुरेश्वर, काठमाडौंमा द्रुत सेवाका लागि आवेदन दिन सकिन्छ [{normal_url}]."
        )
    if lang == "roman_nepali":
        return (
            f"Passport renewal ko lagi pahila online pre-enrollment form bharera date/time book garnu parcha; application type ma Renewal option chhanne process source ma cha [{online_url}]. "
            f"Nepal bhitra hunuhunchha bhane citizenship/minor ID issue bhayeko District/Area Administration Office ma apply garna sakincha [{normal_url}]. "
            f"Normal process ma DAO/Area Administration Office ma application darta garepachi generally 10-30 din bhitra passport aauchha [{normal_url}]. "
            f"Urgent cha bhane Department of Passports, Tripureshwar, Kathmandu ma expedited service ko lagi apply garna sakincha [{normal_url}]."
        )
    return (
        f"To renew a passport, first fill the online pre-enrollment form and book the appointment date/time; the Department of Passports source shows Renewal as one of the application-type options [{online_url}]. "
        f"If you are in Nepal, apply through the District or Area Administration Office that issued your citizenship certificate or minor ID [{normal_url}]. "
        f"Under the normal process, a passport is usually received within 10 to 30 days after registration at the District/Area Administration Office [{normal_url}]. "
        f"If it is urgent, you can apply for expedited service at the Department of Passports, Tripureshwar, Kathmandu [{normal_url}]."
    )


def _passport_apply_fallback_answer(question: str, gov_results: list[dict], lang: str) -> str | None:
    if _detect_retrieval_topic(question) != "passport":
        return None
    q = question.lower()
    if any(term in q for term in ("fee", "cost", "charge", "price", "renew", "renewal", "lost", "replace", "status")) or any(
        term in question for term in ("दस्तुर", "शुल्क", "नवीकरण", "नविकरण", "हराएको", "प्रतिलिपि", "स्थिति")
    ):
        return None
    wants_process = any(term in q for term in ("how", "apply", "get", "make", "banaune", "banauna", "kasari")) or any(
        term in question for term in ("कसरी", "बनाउने", "बनाउन", "लिने", "आवेदन")
    )
    if not wants_process:
        return None

    process_source = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("nepalpassport.gov.np",))
            and (
                "साधारण विद्युतीय राहदानी बनाउने प्रक्रिया" in (g.get("text") or "")
                or "pre-enrolment" in (g.get("text") or "").lower()
                or "pre-enrollment" in (g.get("text") or "").lower()
                or "enrolment centre" in (g.get("text") or "").lower()
                or "enrollment centre" in (g.get("text") or "").lower()
            )
        ),
        None,
    )
    if not process_source:
        return None
    url = process_source.get("url") or ""

    if lang == "devanagari":
        return (
            f"साधारण विद्युतीय राहदानी बनाउन पहिले अनलाइन pre-enrolment फाराम भर्नुहोस्; फाराम घरमै कम्प्युटर वा मोबाइलबाट भर्न सकिने स्रोतमा छ [{url}]। "
            f"फाराम भर्दा सम्बन्धित जिल्ला/इलाका प्रशासन कार्यालय, राहदानी विभाग, वा विदेशमा भए सम्बन्धित दूतावास/कन्सुलेटलाई Enrolment Centre छानेर आफूलाई मिल्ने मिति र समयमा appointment तय गर्नुपर्छ [{url}]। "
            f"विवरण फरक नपर्ने गरी आफैं ठीकसँग भर्नुहोस्, अनि appointment का दिन आवश्यक कागजातसहित छानेको आवेदन केन्द्रमा उपस्थित हुनुहोस् [{url}]।"
        )
    if lang == "roman_nepali":
        return (
            f"Normal e-passport banauna pahila online pre-enrolment form bharnus; source le gharbatai computer wa mobile bata form bharna milcha bhancha [{url}]. "
            f"Form bharda afno District/Area Administration Office, Passport Department, wa bidesh ma bhaye embassy/consulate lai Enrolment Centre chhanera milne date/time ko appointment set garnu parcha [{url}]. "
            f"Details mistake nahune gari bharnus, ani appointment ko din required documents liyera chhaneko application center ma janu [{url}]."
        )
    return (
        f"To make an ordinary e-passport, first fill the online pre-enrolment form; the Department of Passports source says it can be filled from home by computer or mobile [{url}]. "
        f"While filling the form, choose the relevant District/Area Administration Office, Department of Passports, or embassy/consulate abroad as the enrolment centre, then book the suitable appointment date/time [{url}]. "
        f"Fill the details carefully, then go to the selected application centre on the appointment day with the required documents [{url}]."
    )


def _pan_registration_fallback_answer(question: str, gov_results: list[dict], lang: str) -> str | None:
    if _detect_retrieval_topic(question) != "pan_tax":
        return None
    q = question.lower()
    if not (
        "pan" in q
        or "taxpayer" in q
        or "kar" in q
        or "स्थायी लेखा" in question
        or "करदाता" in question
    ):
        return None

    source = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("ird.gov.np",))
            and (
                "PAN लिंदा" in (g.get("text") or "")
                or "PAN लिँदा" in (g.get("text") or "")
                or "स्थायी लेखा नम्बर" in (g.get("text") or "")
                or "permanent account" in (g.get("text") or "").lower()
            )
        ),
        None,
    )
    if not source:
        return None
    url = source.get("url") or ""

    if lang == "devanagari":
        return (
            f"व्यक्तिगत PAN लिन IRD स्रोतअनुसार आफ्नो परिचय खुलाउने प्रमाणको प्रतिलिपि, जस्तै नागरिकता प्रमाणपत्र वा राहदानी, र फोटो पेश गर्नुपर्छ [{url}]। "
            f"पेशा/व्यवसाय भए पेशागत प्रमाणपत्र वा फर्म दर्ता प्रमाणपत्रको प्रतिलिपि पनि चाहिन्छ [{url}]। "
            f"आफ्नै घरमा कारोबार भए त्यसको प्रमाण, वा भाडामा भए घरबहाल सम्झौता पत्रको प्रतिलिपि पेश गर्नुपर्ने स्रोतमा उल्लेख छ [{url}]। "
            f"आफू बसोबास गरेको, कारोबार गरेको, वा रोजगारी गरेको ठाउँसँग सम्बन्धित आन्तरिक राजस्व कार्यालय वा करदाता सेवा कार्यालयबाट स्थायी लेखा नम्बर लिनुपर्छ [{url}]।"
        )
    if lang == "roman_nepali":
        return (
            f"Individual PAN lina IRD source anusar afno identity proof ko copy, jastai citizenship certificate wa passport, ra photo pesh garnu parcha [{url}]. "
            f"Pesha/byabasaya cha bhane professional certificate wa firm-registration certificate ko copy pani chahinchha [{url}]. "
            f"Afnai ghar ma karobar garne bhaye tesko proof, wa rent ma bhaye house-rent agreement ko copy pesh garnu parcha [{url}]. "
            f"Afno basobas, karobar, wa rojgari bhayeko thau sanga sambandhit Inland Revenue Office/Taxpayer Service Office bata PAN line ho [{url}]."
        )
    return (
        f"For an individual PAN, the IRD source says to submit identity proof such as a citizenship certificate or passport, plus a photo [{url}]. "
        f"If you have a profession or business, submit the professional certificate or firm-registration certificate copy as applicable [{url}]. "
        f"If operating from your own house, provide proof of that; if renting, provide a house-rent agreement copy [{url}]. "
        f"Take the PAN from the Inland Revenue Office or Taxpayer Service Office related to where you live, operate, or work [{url}]."
    )


def _driving_license_fallback_answer(question: str, gov_results: list[dict], lang: str) -> str | None:
    if _detect_retrieval_topic(question) != "driving_license":
        return None
    q = question.lower()
    if "license" not in q and "licence" not in q and "driving" not in q and "सवारी" not in question:
        return None
    source = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("dotm.gov.np", "transportmanagement.gov.np"))
            and (
                "Online Driving License System" in (g.get("text") or "")
                or "Age of an applicant" in (g.get("text") or "")
                or "सवारी चालक अनुमतिपत्र" in (g.get("text") or "")
            )
        ),
        None,
    )
    if not source:
        return None
    age_source = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("dotm.gov.np", "transportmanagement.gov.np"))
            and (
                "Age of an applicant" in (g.get("text") or "")
                or "निवेदकको उमेर" in (g.get("text") or "")
            )
        ),
        None,
    )
    retrial_source = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("dotm.gov.np", "transportmanagement.gov.np"))
            and (
                "retrial exam" in (g.get("text") or "").lower()
                or "रि-ट्रायल" in (g.get("text") or "")
            )
        ),
        None,
    )
    docs_source = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("dotm.gov.np", "transportmanagement.gov.np"))
            and (
                "original citizenship" in (g.get("text") or "").lower()
                or "सक्कल नागरिकता" in (g.get("text") or "")
            )
        ),
        None,
    )
    url = source.get("url") or ""
    age_url = (age_source or source).get("url") or ""
    retrial_url = (retrial_source or source).get("url") or ""
    docs_url = (docs_source or source).get("url") or ""

    if lang == "devanagari":
        return (
            f"सवारी चालक अनुमतिपत्रका लागि यातायात व्यवस्था विभागको Online Driving License System प्रयोग गर्नुपर्छ [{url}]। "
            f"स्रोतअनुसार उमेर मापदण्ड: दुई पाङ्ग्रे सवारी A/K का लागि १६ वर्ष, साना सवारी B का लागि १८ वर्ष, र अन्य सवारीका लागि २१ वर्ष पूरा भएको हुनुपर्छ [{age_url}]। "
            f"ट्रायलमा असफल भए पहिलो असफल मितिले ९० दिनभित्र बढीमा ३ पटकसम्म re-trial दिन सकिने स्रोतमा छ [{retrial_url}]। "
            f"कार्यालय जाँदा मूल नागरिकता र category थप्ने भए मूल license साथमा राख्नुहोस् [{docs_url}]।"
        )
    if lang == "roman_nepali":
        return (
            f"Driving license apply garna Department of Transport Management ko Online Driving License System use garne ho [{url}]. "
            f"Source anusar age criteria: two-wheeler A/K ko lagi 16 barsa, small vehicle B ko lagi 18 barsa, ra aru vehicle ko lagi 21 barsa pura hunu parcha [{age_url}]. "
            f"Trial fail bhaye first fail date bata 90 din bhitra badima 3 patak re-trial dina milcha [{retrial_url}]. "
            f"Office jada original citizenship, ra category add garne ho bhane original license pani boknu [{docs_url}]."
        )
    return (
        f"Apply through the Department of Transport Management Online Driving License System [{url}]. "
        f"The source says the applicant must be 16 for two-wheelers A/K, 18 for small vehicles B, and 21 for other vehicles [{age_url}]. "
        f"If you fail the trial, the source says re-trial is allowed up to three times within 90 days from the first failure date [{retrial_url}]. "
        f"When visiting the office, carry your original citizenship and, if adding a category, your original license [{docs_url}]."
    )


def _company_registration_fallback_answer(question: str, gov_results: list[dict], lang: str) -> str | None:
    if _detect_retrieval_topic(question) != "company_registration":
        return None
    q = question.lower()
    if "company" not in q and "ocr" not in q and "कम्पनी" not in question:
        return None
    source = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("ocr.gov.np",))
            and (
                "OCR e-Services" in (g.get("text") or "")
                or "online company registration" in (g.get("text") or "").lower()
                or "New Company Registration" in (g.get("text") or "")
            )
        ),
        None,
    )
    if not source:
        return None
    url = source.get("url") or ""

    if lang == "devanagari":
        return (
            f"कम्पनी दर्ता Office of Company Registrar को OCR e-Services बाट अनलाइन गर्नुपर्छ [{url}]। "
            f"स्रोतको user manual अनुसार online company registration module ले कम्पनीको online registration र आफ्नो कम्पनीको details हेर्न मद्दत गर्छ [{url}]। "
            f"नयाँ कम्पनी दर्ताका लागि पहिले user create गर्ने चरण छ: browser खोलेर OCR e-Services मा जाने, new-user registration मा जाने, र user creation form भर्ने [{url}]। "
            f"त्यसपछि OCR e-Services भित्र नयाँ कम्पनी दर्ताको बाँकी module पूरा गर्नुहोस् [{url}]।"
        )
    if lang == "roman_nepali":
        return (
            f"Company registration Office of Company Registrar ko OCR e-Services bata online garne ho [{url}]. "
            f"Source ko user manual anusar online company registration module le company ko online registration garna ra company details herna help garcha [{url}]. "
            f"Naya company register garna pahila user create garne: browser ma OCR e-Services kholne, new-user registration ma jane, ani user creation form bharne [{url}]. "
            f"Tes pachi OCR e-Services bhitra new company registration ko baki module pura garnu [{url}]."
        )
    return (
        f"Register the company online through the Office of Company Registrar OCR e-Services [{url}]. "
        f"The OCR user manual says the online company registration module helps users register a company online and view company details [{url}]. "
        f"For new company registration, first create a user: open OCR e-Services in a browser, go to new-user registration, and fill the user creation form [{url}]. "
        f"Then continue through the new-company-registration module inside OCR e-Services [{url}]."
    )


def _national_id_fallback_answer(question: str, gov_results: list[dict], lang: str) -> str | None:
    if _detect_retrieval_topic(question) != "national_id":
        return None
    q = question.lower()
    if not (
        "national" in q
        or "identity" in q
        or "id" in q
        or "परिचयपत्र" in question
        or "राष्ट्रिय" in question
    ):
        return None

    pre = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("donidcr.gov.np",))
            and (
                "Pre-Enrollment" in (g.get("text") or "")
                or "book an appointment for Biometric capture" in (g.get("text") or "")
            )
        ),
        None,
    )
    method = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("donidcr.gov.np",))
            and (
                "विवरण संकलन" in (g.get("text") or "")
                or "दरखास्त" in (g.get("text") or "")
                or "data collection" in (g.get("text") or "").lower()
            )
        ),
        None,
    )
    check = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("donidcr.gov.np",))
            and "find your national id number" in (g.get("text") or "").lower()
        ),
        None,
    )
    if not pre and not method:
        return None

    pre_url = (pre or method or {}).get("url") or ""
    method_url = (method or pre or {}).get("url") or ""
    check_url = (check or {}).get("url") or ""

    if lang == "devanagari":
        answer = (
            f"राष्ट्रिय परिचयपत्रका लागि DONIDCR को NID Pre-Enrollment System मा demographic data online enroll गरी biometric capture का लागि appointment book गर्ने स्रोतमा छ [{pre_url}]। "
            f"विवरण संकलन चरणमा आवेदकले तोकिएको दरखास्त/फाराम भर्ने र व्यक्तिगत विवरण रुजु अधिकारीसमक्ष पेश गर्ने प्रक्रिया स्रोतमा उल्लेख छ [{method_url}]।"
        )
        if check_url:
            answer += f" पहिले नै नम्बर चाहिएको हो भने citizen portal मा citizenship details राखेर national ID number खोज्ने स्रोत पनि छ [{check_url}]।"
        return answer
    if lang == "roman_nepali":
        answer = (
            f"National ID ko lagi DONIDCR ko NID Pre-Enrollment System ma demographic data online enroll garera biometric capture ko appointment book garne ho [{pre_url}]. "
            f"Data collection step ma applicant le tokeko application/form bharera personal details verification officer samaksha pesh garne process source ma cha [{method_url}]."
        )
        if check_url:
            answer += f" Pahile nai national ID number khojnu cha bhane citizen portal ma citizenship details enter garne source cha [{check_url}]."
        return answer
    answer = (
        f"For a National ID, use DONIDCR's NID Pre-Enrollment System to enroll demographic data online and book an appointment for biometric capture [{pre_url}]. "
        f"The data-collection source says the applicant submits the required application/form and personal details to the verifying officer [{method_url}]."
    )
    if check_url:
        answer += f" If you already need to find a National ID number, the citizen portal says to enter citizenship details [{check_url}]."
    return answer


def _citizenship_duplicate_fallback_answer(question: str, gov_results: list[dict], lang: str) -> str | None:
    if _detect_retrieval_topic(question) != "citizenship":
        return None
    q = question.lower()
    if not (
        "lost" in q
        or "duplicate" in q
        or "replace" in q
        or "replacement" in q
        or "प्रतिलिपि" in question
        or "हराए" in question
        or "हराएको" in question
        or "बिग्रिएको" in question
        or "झुत्रो" in question
    ):
        return None
    source = next(
        (
            g for g in gov_results
            if _domain_matches(g.get("host"), ("moha.gov.np",))
            and (
                "नागरिकता प्रतिलिपि" in (g.get("text") or "")
                or "प्रतिलिपि नागरिकता" in (g.get("text") or "")
            )
            and (
                "नागरिकता हराएको" in (g.get("text") or "")
                or "हराएको" in (g.get("text") or "")
                or "बिग्रिएको" in (g.get("text") or "")
                or "झुत्रो" in (g.get("text") or "")
            )
        ),
        None,
    )
    if not source:
        return None
    url = source.get("url") or ""

    if lang == "devanagari":
        return (
            f"नागरिकता हराएको, बिग्रिएको वा झुत्रो भएको अवस्थामा प्रतिलिपि नागरिकताका लागि आफ्नो स्थायी बसोबास भएको सम्बन्धित वडा कार्यालयबाट प्रमाणित नागरिकता प्रतिलिपि अनुसूची फाराम पेश गर्नुपर्ने आधिकारिक DAO/MoHA स्रोतमा उल्लेख छ [{url}]। "
            f"नागरिकता बिग्रिएको वा झुत्रो भए सक्कल नागरिकता, हराएको भए नागरिकताको प्रतिलिपि/नागरिकता नम्बर वा जारी मिति खुलेको प्रमाण पेश गर्नुपर्छ [{url}]। "
            f"आवश्यक कागजातहरू सक्कलै लिएर जिल्ला प्रशासन कार्यालयमा जानुपर्छ; स्रोतमा प्रतिलिपिका लागि रु. २० बराबरको हुलाक टिकट उल्लेख छ [{url}]। "
            f"प्रतिलिपि बनाएपछि पुरानो नागरिकता भेटिएमा पुरानो नागरिकता प्रयोग नगरी जिल्ला प्रशासन कार्यालयमा बुझाउनुपर्छ [{url}]।"
        )
    if lang == "roman_nepali":
        return (
            f"Nagarikta harayeko, bigriyeko, wa jhutro bhayeko case ma duplicate citizenship ko lagi permanent address bhayeko ward office bata certified nagarikta-pratilipi schedule/form pesh garnu parcha [{url}]. "
            f"Bigriyeko/jhutro bhaye original citizenship, harayeko bhaye citizenship copy or citizenship number/issue date khuleko proof pesh garnu parcha [{url}]. "
            f"Original supporting documents liyera District Administration Office janu parcha; source ma duplicate ko lagi Rs. 20 ko postal ticket bhaneko cha [{url}]. "
            f"Duplicate banepachi old citizenship bhetiyo bhane old one use nagari DAO ma bujhaunu parcha [{url}]."
        )
    return (
        f"For a lost, damaged, or worn-out citizenship certificate, an official DAO/MoHA source says to apply for duplicate citizenship using the citizenship-duplicate schedule/form certified by the ward office of your permanent residence [{url}]. "
        f"If the certificate is damaged or worn out, bring the original; if it is lost, provide a copy of the citizenship certificate or proof showing the citizenship number or issue date [{url}]. "
        f"Take the original supporting documents to the District Administration Office; the source lists a Rs. 20 postal ticket for the duplicate copy [{url}]. "
        f"If the old citizenship certificate is later found after a duplicate is issued, do not use the old one and submit it to the District Administration Office [{url}]."
    )


def _citizenship_duplicate_practical_fallback_answer(
    question: str,
    tacit_results: list[dict],
    gov_results: list[dict],
    lang: str,
) -> str | None:
    """Answer the supported local step when official duplicate evidence is absent.

    This is deliberately narrower than a full procedure fallback: citizen
    interviews can support practical local routing, but not the full legal DAO
    checklist unless the official document was retrieved too.
    """
    if _detect_retrieval_topic(question) != "citizenship":
        return None
    q = question.lower()
    wants_duplicate = (
        "lost" in q
        or "duplicate" in q
        or "replace" in q
        or "replacement" in q
        or "hareyo" in q
        or "harayo" in q
        or "harayeko" in q
        or "pratilipi" in q
        or "प्रतिलिपि" in question
        or "हराए" in question
        or "हराएको" in question
        or "हरायो" in question
        or "बिग्रिएको" in question
        or "झुत्रो" in question
    )
    if not wants_duplicate or not tacit_results:
        return None
    if _citizenship_duplicate_fallback_answer(question, gov_results, lang):
        return None

    selected: list[tuple[tuple[int, int], int, dict]] = []
    for idx, t in enumerate(tacit_results):
        claim = re.sub(r"\s+", " ", (t.get("claim") or "").strip())
        if not claim:
            continue
        claim_l = claim.lower()
        service_l = (t.get("service") or "").lower()
        blob = " ".join([
            claim,
            t.get("fact_type") or "",
            t.get("service") or "",
            t.get("office_name") or "",
        ]).lower()
        has_citizenship_signal = (
            "citizenship" in claim_l
            or "nagarikta" in claim_l
            or "nagrita" in claim_l
            or "sifarish" in claim_l
            or ("recommendation" in claim_l and service_l == "citizenship")
            or "नागरिकता" in claim
        )
        if not has_citizenship_signal:
            continue
        priority = 5
        if "nagarikta sifarish" in blob or "citizenship recommendation" in blob:
            priority = 0
        elif ("ward" in blob or "वडा" in claim) and ("counter" in blob or "काउन्टर" in claim):
            priority = 1
        elif "sifarish" in blob or "recommendation" in blob:
            priority = 2
        elif service_l == "citizenship":
            priority = 3
        selected.append(((priority, idx), idx + 1, t))

    if not selected:
        return None

    selected.sort(key=lambda item: item[0])
    source_rank, source = selected[0][1], selected[0][2]
    claim = re.sub(r"\s+", " ", (source.get("claim") or "").strip())
    if not claim:
        return None
    claim = claim.rstrip(".")
    source_ref = f"S{source_rank}"
    office = (source.get("office_name") or "").strip()
    office_text = f" at {office}" if office and lang == "english" else ""

    if lang == "devanagari":
        return (
            f"तपाईंको हराएको/प्रतिलिपि नागरिकता केसमा जिरीको local practical note ले वडा सिफारिसको चरण मात्र support गर्छ: {claim} [{source_ref}]। "
            "हाल retrieved सरकारी कागजातमा DAO/MoHA को पूरा duplicate checklist खुलेको छैन, त्यसैले जाने अघि जिरी वडा कार्यालय वा जिल्ला प्रशासन कार्यालय दोलखामा कागजात/शुल्क पुष्टि गर्नुहोस्।"
        )
    if lang == "roman_nepali":
        return (
            f"Tapai ko harayeko/duplicate nagarikta case ma Jiri ko local practical note le ward sifarish step matra support garcha: {claim} [{source_ref}]. "
            "Aile retrieved official documents ma DAO/MoHA ko complete duplicate checklist khuleko chaina, tesaile janu aghi Jiri ward office wa DAO Dolakha ma kagajat/fee confirm garnu."
        )
    return (
        f"For your lost/duplicate citizenship case, the retrieved local practical note{office_text} supports the ward-recommendation step: {claim} [{source_ref}]. "
        "The retrieved official documents did not include the current DAO/MoHA duplicate-citizenship checklist, so confirm the exact documents and fee with the Jiri ward office or District Administration Office Dolakha before going."
    )


def _citizenship_certificate_fallback_answer(question: str, gov_results: list[dict], lang: str) -> str | None:
    if _detect_retrieval_topic(question) != "citizenship":
        return None
    q = question.lower()
    if not (
        "citizen certificate" in q
        or "citizenship certificate" in q
        or "nagarikta" in q
        or "नागरिकता" in question
    ):
        return None
    if any(term in q for term in ("lost", "duplicate", "replace", "replacement")):
        return None

    national = next(
        (g for g in gov_results if _domain_matches(g.get("host"), ("moha.gov.np",))),
        None,
    )
    if not national:
        return None
    url = national.get("url") or ""

    if lang == "devanagari":
        return (
            f"यदि तपाईंले \"citizen certificate\" भन्नाले नेपाली नागरिकता प्रमाणपत्र "
            f"(नागरिकता) भन्नुभएको हो भने, यसलाई नागरिकता प्रमाणपत्रको प्रक्रिया मान्नुपर्छ। "
            f"प्राप्त आधिकारिक MoHA स्रोत नागरिकता प्रमाणपत्रसम्बन्धी नियम/प्रक्रियाको स्रोत हो [{url}]। "
            f"स्थान वा वडा-विशेष सिफारिस चाहिएको हो भने नगरपालिका/वडा नामसहित सोध्नुहोस्।"
        )
    if lang == "roman_nepali":
        return (
            f"'Citizen certificate' bhannale Nepali citizenship certificate (nagarikta) ho bhane, "
            f"yo nagarikta certificate ko process ho. Retrieved MoHA source nagarikta certificate "
            f"rules/process ko official source ho [{url}]. Ward/municipality-specific sifarish chahiyeko ho bhane municipality/ward naam sahit sodhnu."
        )
    return (
        f"If by \"citizen certificate\" you mean Nepal's citizenship certificate "
        f"(नागरिकता प्रमाणपत्र), treat it as a citizenship-certificate question. "
        f"The retrieved Ministry of Home Affairs source is the official source for "
        f"citizenship-certificate rules/procedure [{url}]. If you need a local ward "
        f"or municipality recommendation step, ask with the municipality/ward name."
    )


EVENT_SUBTOPIC_MARKERS: dict[str, tuple[str, ...]] = {
    "birth": (
        "birth",
        "janma",
        "janmadarta",
        "जन्म",
        "जन्म दर्ता",
        "जन्मदर्ता",
        "जनमदता",
        "जनमदाता",
        "जनमदर्ता",
        "जन्मदता",
        "जन्मदाता",
        "जन्मदर्ल",
        "जन्मदार्त",
        "जन्मदार््त",
    ),
    "divorce": ("divorce", "separation", "सम्बन्ध विच्छेद", "सम्बन्ध बिच्छेद", "सम्बन्धविच्छेद"),
    "marriage": ("marriage", "vivah", "विवाह"),
    "death": ("death", "mrityu", "मृत्यु"),
    "migration": ("migration", "basai", "बसाइँसराइ", "बसाईसराई"),
}

EVENT_SERVICE_LABELS: tuple[tuple[str, str], ...] = (
    ("service_type", "सेवा प्रकार:"),
    ("time", "लाग्ने समय:"),
    ("responsible", "जिम्मेवार अधिकारी:"),
    ("office", "सेवा दिने कार्यालय:"),
    ("fee", "सेवा शुल्क:"),
    ("documents", "आवश्यक कागजातहरु:"),
    ("process", "प्रक्रिया:"),
)


def _event_subtopic(question: str) -> tuple[str, tuple[str, ...]] | None:
    q = question.lower()
    for name, markers in EVENT_SUBTOPIC_MARKERS.items():
        if any(m.lower() in q for m in markers):
            return name, markers
    return None


def _birth_registration_intent(question: str) -> bool:
    subtopic = _event_subtopic(question)
    return bool(subtopic and subtopic[0] == "birth")


def _extract_jiri_service_fields(text: str) -> dict[str, str]:
    compact = re.sub(r"\s+", " ", text or "")
    fields: dict[str, str] = {}
    for idx, (key, label) in enumerate(EVENT_SERVICE_LABELS):
        start = compact.find(label)
        if start < 0:
            continue
        start += len(label)
        end_candidates = [
            compact.find(next_label, start)
            for _, next_label in EVENT_SERVICE_LABELS[idx + 1:]
        ]
        end_candidates = [x for x in end_candidates if x >= 0]
        end = min(end_candidates) if end_candidates else min(len(compact), start + 520)
        value = compact[start:end].strip(" |:-")
        if value:
            fields[key] = value
    return fields


def _local_event_service_fallback_answer(question: str, gov_results: list[dict], lang: str) -> str | None:
    if _detect_retrieval_topic(question) != "vital_registration" or not _detect_local_domains(question):
        return None
    subtopic = _event_subtopic(question)
    if not subtopic:
        return None
    subtopic_name, markers = subtopic
    local_domains = _detect_local_domains(question)

    def has_marker(g: dict) -> bool:
        blob = " ".join([
            g.get("url") or "",
            g.get("title") or "",
            g.get("text") or "",
        ]).lower()
        return any(m.lower() in blob for m in markers)

    local = next(
        (g for g in gov_results if _domain_matches(g.get("host"), local_domains) and has_marker(g)),
        None,
    )
    if not local:
        return None
    fields = _extract_jiri_service_fields(local.get("text") or "")
    if not fields:
        return None

    local_url = local.get("url") or ""
    cite = f" [{local_url}]" if local_url else ""
    service_name = {
        "divorce": "divorce registration",
        "marriage": "marriage registration",
        "death": "death registration",
        "migration": "migration registration",
    }.get(subtopic_name, "event registration")

    if lang == "devanagari":
        lines = [f"जिरी नगरपालिकामा {service_name} का लागि स्थानीय सेवा पेजमा यस्तो छ:"]
        label_map = {
            "office": "सेवा दिने कार्यालय",
            "time": "लाग्ने समय",
            "responsible": "जिम्मेवार अधिकारी",
            "fee": "सेवा शुल्क",
            "documents": "आवश्यक कागजात",
            "process": "प्रक्रिया",
        }
    elif lang == "roman_nepali":
        lines = [f"Jiri Municipality ma {service_name} ko local service page anusar:"]
        label_map = {
            "office": "Office",
            "time": "Time",
            "responsible": "Responsible officer",
            "fee": "Fee",
            "documents": "Documents",
            "process": "Process",
        }
    else:
        lines = [f"For {service_name} in Jiri Municipality, the local service page says:"]
        label_map = {
            "office": "Office",
            "time": "Time",
            "responsible": "Responsible officer",
            "fee": "Fee",
            "documents": "Documents",
            "process": "Process",
        }

    if subtopic_name == "divorce" and lang == "english":
        if fields.get("office"):
            lines.append(f"- Office: {fields['office']}{cite}")
        if fields.get("time"):
            lines.append(f"- Time: {fields['time']}{cite}")
        if fields.get("responsible"):
            lines.append(f"- Responsible officer: {fields['responsible']}{cite}")
        if fields.get("fee"):
            lines.append(f"- Fee: {fields['fee']}{cite}")
        lines.append(
            "- Documents: application letter; certified copy of the court divorce decision; "
            "one copy each of the husband and wife's citizenship; and the male/husband's "
            f"permanent address should be in the relevant ward{cite}"
        )
        return "\n".join(lines)

    for key in ("office", "time", "responsible", "fee", "documents", "process"):
        value = fields.get(key)
        if not value:
            continue
        if key == "documents" and len(value) > 420:
            value = value[:420].rstrip() + "..."
        if key == "process" and len(value) > 260:
            value = value[:260].rstrip() + "..."
        lines.append(f"- {label_map[key]}: {value}{cite}")
    return "\n".join(lines) if len(lines) > 1 else None


def _foreign_employment_complaint_fallback_answer(question: str, gov_results: list[dict], lang: str) -> str | None:
    if lang != "english":
        return None
    if _detect_retrieval_topic(question) != "foreign_employment":
        return None
    if not _foreign_employment_query_wants_complaint(question):
        return None

    complaint_source: dict | None = None
    helpline_sources: list[dict] = []
    dao_source: dict | None = None

    for g in gov_results:
        text = (g.get("text") or "").translate(_DEVANAGARI_DIGITS)
        text_l = text.lower()
        if complaint_source is None and (
            "वैदेशिक रोजगार विभागमा उजुरी" in text
            or ("वैदेशिक रोजगार विभाग" in text and "उजुरी" in text and "ठग" in text)
            or ("department of foreign employment" in text_l and "complaint" in text_l)
        ):
            complaint_source = g
        if "1141" in text and (
            "गुनासो" in text or "समस्या" in text or "कल सेन्टर" in text or "helpline" in text_l
        ):
            helpline_sources.append(g)
        if dao_source is None and "स्थानीय जिल्ला प्रशासन कार्यालय" in text and (
            "ठगी" in text or "इजाजतपत्र" in text
        ):
            dao_source = g

    if not complaint_source and not helpline_sources and not dao_source:
        return None

    def cite(source: dict | None) -> str:
        url = (source or {}).get("url") or ""
        return f" [{url}]" if url else ""

    lines: list[str] = []
    if complaint_source:
        lines.append(
            "For manpower/foreign-employment cheating, the retrieved official source says "
            "a complaint can be filed with the Department of Foreign Employment; if the "
            f"worker is sure they were cheated, family/representative filing is also described{cite(complaint_source)}."
        )
    if helpline_sources:
        helpline_cites = " ".join(cite(g).strip() for g in helpline_sources[:2] if cite(g))
        lines.append(
            f"For complaints or problems, 1141 is listed as an official/free call-center or helpline contact {helpline_cites}."
        )
    if dao_source:
        lines.append(
            "For fraud by an individual or license-holder, the source also says a complaint "
            f"can be filed at the local District Administration Office{cite(dao_source)}."
        )
    return "\n".join(lines)


def _extract_jiri_officials(text: str) -> list[dict[str, str]]:
    compact = re.sub(r"\s+", " ", text or "")
    digit_trans = str.maketrans("०१२३४५६७८९", "0123456789")
    patterns: list[tuple[str, str, str]] = [
        ("Mitra Bahadur Jirel", "Mayor", ""),
        ("Krishnamaya Budhathoki", "Deputy Mayor", ""),
        ("Raj Kumari Khatri", "Chief Administrative Officer", ""),
        ("Man Bahadur Jirel", "Information Officer", ""),
        ("मित्र बहादुर जिरेल", "Mayor", "नगर प्रमुख"),
        ("कृष्णमाया बुढाथोकी", "Deputy Mayor", "उप"),
        ("राज कुमारी खत्री", "Chief Administrative Officer", "प्रमुख प्रशासकीय"),
        ("मान बहादुर जिरेल", "Information Officer", "सूचना अधिकारी"),
    ]
    officials: list[dict[str, str]] = []
    seen_roles: set[str] = set()
    for i, (name, role, role_marker) in enumerate(patterns):
        if role in seen_roles:
            continue
        start = compact.find(name)
        if start < 0:
            continue
        end_candidates = [compact.find(next_name, start + len(name)) for next_name, _, _ in patterns[i + 1:]]
        end_candidates = [x for x in end_candidates if x >= 0]
        end = min(end_candidates) if end_candidates else min(len(compact), start + 220)
        segment = compact[start:end]
        if role_marker and role_marker not in segment:
            continue
        contact_segment = re.sub(
            r"(?i)(\.[a-z]{2,6})(phone|status|section|weight|designation)\b",
            r"\1 \2",
            segment,
        )
        email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", contact_segment)
        phone_match = re.search(r"(?:\+?977[-\s]?)?(?:[9९][0-9०-९]{9}|[0०][0-9०-९]{8,9})", segment)
        seen_roles.add(role)
        display_name = {
            "मित्र बहादुर जिरेल": "Mitra Bahadur Jirel",
            "कृष्णमाया बुढाथोकी": "Krishnamaya Budhathoki",
            "राज कुमारी खत्री": "Raj Kumari Khatri",
            "मान बहादुर जिरेल": "Man Bahadur Jirel",
        }.get(name, name)
        officials.append({
            "name": display_name,
            "role": role,
            "email": email_match.group(0) if email_match else "",
            "phone": phone_match.group(0).translate(digit_trans) if phone_match else "",
        })
    return officials


def _municipality_contact_fallback_answer(question: str, gov_results: list[dict], lang: str) -> str | None:
    topic = _detect_retrieval_topic(question)
    if topic != "municipality_contact" or not _detect_local_domains(question):
        return None

    local_domains = _detect_local_domains(question)
    role_filter = _contact_query_role(question)
    wants_phone = _contact_query_wants_phone(question)
    local_sources = [g for g in gov_results if _domain_matches(g.get("host"), local_domains)]

    official_candidates: list[tuple[int, int, int, dict, list[dict[str, str]]]] = []
    for g in local_sources:
        officials_found = _extract_jiri_officials(g.get("text") or "")
        if officials_found:
            has_requested_role = 1 if role_filter and any(o["role"] == role_filter for o in officials_found) else 0
            has_info = 1 if any(o["role"] == "Information Officer" for o in officials_found) else 0
            official_candidates.append((has_requested_role, has_info, len(officials_found), g, officials_found))
    if role_filter:
        official_candidates.sort(key=lambda item: (-item[0], -item[2], -item[1]))
    else:
        official_candidates.sort(key=lambda item: (-item[1], -item[2]))
    if role_filter and official_candidates and official_candidates[0][0] == 0:
        return None
    official_source = official_candidates[0][3] if official_candidates else None

    contact_source = next(
        (
            g for g in local_sources
            if "Contact No" in (g.get("text") or "")
        ),
        None,
    )
    office_phone = ""
    if contact_source:
        phone_match = re.search(r"\+?\d[\d\s-]{7,}\d", contact_source.get("text") or "")
        if phone_match:
            office_phone = re.sub(r"\s+", " ", phone_match.group(0)).strip()

    if wants_phone and office_phone:
        contact_url = (contact_source or {}).get("url") or ""
        if lang == "devanagari":
            return f"जिरी नगरपालिकाको कार्यालय Contact No: {office_phone} [{contact_url}]"
        if lang == "roman_nepali":
            return f"Jiri Municipality ko office Contact No: {office_phone} [{contact_url}]"
        return f"Jiri Municipality office Contact No: {office_phone} [{contact_url}]"

    if not official_source:
        return None

    officials = official_candidates[0][4] if official_candidates else _extract_jiri_officials(official_source.get("text") or "")
    if not officials:
        return None

    official_url = official_source.get("url") or ""
    contact_url = (contact_source or {}).get("url") or ""

    info_officer = next((o for o in officials if o["role"] == "Information Officer"), None)
    if role_filter:
        selected_officials = [o for o in officials if o["role"] == role_filter]
    else:
        selected_officials = []
    other_officials = [o for o in officials if o is not info_officer]

    def english_line(o: dict[str, str]) -> str:
        parts = [f"{o['name']} - {o['role']}"]
        if o.get("email"):
            parts.append(o["email"])
        if o.get("phone"):
            parts.append(o["phone"])
        return ", ".join(parts)

    def contact_bits(o: dict[str, str]) -> str:
        parts = [o["name"]]
        if o.get("email"):
            parts.append(f"Email: {o['email']}")
        if o.get("phone"):
            parts.append(f"Phone: {o['phone']}")
        return ", ".join(parts)

    if selected_officials:
        o = selected_officials[0]
        if lang == "devanagari":
            role_label = {
                "Mayor": "नगर प्रमुख",
                "Deputy Mayor": "उप प्रमुख",
                "Information Officer": "सूचना अधिकारी",
                "Chief Administrative Officer": "प्रमुख प्रशासकीय अधिकृत",
            }.get(o["role"], o["role"])
            return f"जिरी नगरपालिकाको {role_label} {contact_bits(o)} हुनुहुन्छ [{official_url}]."
        if lang == "roman_nepali":
            return f"Jiri Municipality ko {o['role']}: {contact_bits(o)} [{official_url}]."
        return f"Jiri Municipality {o['role']}: {contact_bits(o)} [{official_url}]."

    if lang == "devanagari":
        lines = [
            f"जिरी नगरपालिकाको वेबसाइटमा सामान्य सम्पर्कका लागि सूचना अधिकारीका रूपमा {english_line(info_officer)} उल्लेख छ [{official_url}]."
            if info_officer else f"जिरी नगरपालिकाको वेबसाइटमा पदाधिकारीहरूको सम्पर्क विवरण छ [{official_url}]."
        ]
        for o in other_officials:
            lines.append(f"- {english_line(o)} [{official_url}]")
        if office_phone and contact_url:
            lines.append(f"कार्यालयको Contact No: {office_phone} [{contact_url}]")
        return "\n".join(lines)

    if lang == "roman_nepali":
        lines = [
            f"Jiri Municipality ko general contact person ko lagi site ma Information Officer: {english_line(info_officer)} dekhiyeko cha [{official_url}]."
            if info_officer else f"Jiri Municipality site ma officials ko contact details dekhiyeko cha [{official_url}]."
        ]
        for o in other_officials:
            lines.append(f"- {english_line(o)} [{official_url}]")
        if office_phone and contact_url:
            lines.append(f"Office Contact No: {office_phone} [{contact_url}]")
        return "\n".join(lines)

    lines = [
        f"For a general Jiri Municipality contact person, the site lists {english_line(info_officer)} [{official_url}]."
        if info_officer else f"The Jiri Municipality site lists these officials [{official_url}]."
    ]
    for o in other_officials:
        lines.append(f"- {english_line(o)} [{official_url}]")
    if office_phone and contact_url:
        lines.append(f"Office Contact No: {office_phone} [{contact_url}]")
    return "\n".join(lines)


def _generic_contact_fallback_answer(question: str, gov_results: list[dict], lang: str) -> str | None:
    topic = _detect_retrieval_topic(question)
    if topic != "municipality_contact":
        return None
    if _contact_query_role(question):
        return None
    local_domains = _detect_local_domains(question)
    if not local_domains:
        inferred: list[str] = []
        for g in gov_results:
            host = (g.get("host") or "").lower()
            if (host.startswith("dao") and host.endswith(".moha.gov.np")) or host.endswith("mun.gov.np"):
                if host not in inferred:
                    inferred.append(host)
        local_domains = tuple(inferred)
    if not local_domains:
        return None
    local_sources = [g for g in gov_results if _domain_matches(g.get("host"), local_domains)]
    if not local_sources:
        return None

    digit_trans = str.maketrans("०१२३४५६७८९", "0123456789")
    phone_re = re.compile(r"(?:\+?977[-\s]?)?(?:0\d{1,2}[-\s]?\d{5,7}|9\d{9})")
    email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

    def contact_label(source: dict) -> str:
        host = (source.get("host") or "").lower()
        title = (source.get("title") or "").strip()
        if lang != "english" and title:
            return title
        if host.endswith("mun.gov.np"):
            prefix = host.split(".", 1)[0]
            name = re.sub(r"mun$", "", prefix, flags=re.I)
            name = re.sub(r"[^a-z0-9]+", " ", name).strip()
            if name:
                return f"{name.title()} Municipality"
        if title and _script_counts(title)[0] <= max(8, _script_counts(title)[1]):
            return title
        return host or "the official source"

    for source in local_sources:
        text = re.sub(r"\s+", " ", source.get("text") or "")
        normalized_text = text.translate(digit_trans)
        phones = list(dict.fromkeys(
            re.sub(r"\s+", " ", m.group(0).strip())
            for m in phone_re.finditer(normalized_text)
        ))
        emails = list(dict.fromkeys(m.group(0).strip() for m in email_re.finditer(text)))
        if not phones and not emails:
            continue
        url = source.get("url") or ""
        label = contact_label(source)
        bits: list[str] = []
        if phones:
            bits.append(("फोन " if lang == "devanagari" else "phone ") + ", ".join(phones[:3]))
        if emails:
            bits.append(("इमेल " if lang == "devanagari" else "email ") + ", ".join(emails[:2]))
        detail = "; ".join(bits)
        if lang == "devanagari":
            return f"{label} मा {detail} उल्लेख छ [{url}]।"
        if lang == "roman_nepali":
            return f"{label} ma {detail} mention cha [{url}]."
        return f"{label} lists {detail} [{url}]."

    source = local_sources[0]
    url = source.get("url") or ""
    label = contact_label(source)
    if lang == "devanagari":
        return f"मैले {label} को आधिकारिक स्रोत भेटेँ, तर retrieved अंशमा फोन/इमेल नम्बर देखिएन [{url}]।"
    if lang == "roman_nepali":
        return f"{label} ko official source bhete, tara retrieved text ma phone/email number dekhiyena [{url}]."
    return f"I found the official source for {label}, but the retrieved text did not include a phone or email number [{url}]."


def _tacit_municipality_fallback_answer(question: str, tacit_results: list[dict], lang: str) -> str | None:
    topic = _detect_retrieval_topic(question)
    if topic not in LOCAL_TACIT_STRICT_TOPICS or not _detect_local_domains(question):
        return None
    if not tacit_results:
        return None

    markers = TOPIC_STRONG_MARKERS.get(topic or "", ())
    selected: list[dict] = []
    for t in tacit_results:
        blob = " ".join([
            t.get("claim") or "",
            t.get("fact_type") or "",
            t.get("service") or "",
        ]).lower()
        if _marker_hits(blob, markers):
            selected.append(t)
    if not selected:
        return None

    def priority(t: dict) -> tuple[int, int]:
        claim_l = (t.get("claim") or "").lower()
        fact_type = (t.get("fact_type") or "").lower()
        if topic == "municipality_location":
            if fact_type == "navigation" or "jiri municipality office is" in claim_l:
                return (0, int(t.get("rank") or 99))
            return (2, int(t.get("rank") or 99))
        if topic == "municipality_hours":
            if "office hours" in claim_l:
                return (0, int(t.get("rank") or 99))
            if "lunch break" in claim_l:
                return (1, int(t.get("rank") or 99))
            return (2, int(t.get("rank") or 99))
        if topic == "municipality_services":
            if "main services" in claim_l:
                return (0, int(t.get("rank") or 99))
            return (1, int(t.get("rank") or 99))
        return (9, int(t.get("rank") or 99))

    selected.sort(key=priority)
    max_claims = 1 if topic in {"municipality_location", "municipality_services"} else 2
    lines: list[str] = []
    if lang == "devanagari":
        lines.append("जिरी नगरपालिकाबारे citizen-experience स्रोत अनुसार:")
    elif lang == "roman_nepali":
        lines.append("Jiri Municipality bare citizen-experience source anusar:")
    for t in selected[:max_claims]:
        rank = int(t.get("rank") or (tacit_results.index(t) + 1))
        claim = re.sub(r"\s+", " ", (t.get("claim") or "").strip())
        if not claim:
            continue
        if lines:
            lines.append(f"- {claim} [{rank}]")
        else:
            lines.append(f"{claim} [{rank}]")
    return "\n".join(lines) if lines else None


def _build_query_response(
    *,
    answer: str,
    tacit_results: list[dict],
    gov_results: list[dict],
    retrieval_ms: int,
    generation_ms: int,
    total_ms: int,
    detected_lang: str,
    planner: dict[str, Any] | None = None,
) -> QueryResponse:
    answer = _repair_citation_urls(answer, tacit_results, gov_results)
    # Build the unified `sources` list (everything we showed the model), in priority order.
    sources = _build_source_out(tacit_results, gov_results)
    answer = _replace_known_url_citations_with_source_refs(answer, sources)

    citations: list[CitationOut] = []
    seen_citation_keys: set[tuple[str, int]] = set()

    def add_citation_from_source_rank(rank: int) -> None:
        if rank < 1 or rank > len(sources):
            return
        src = sources[rank - 1]
        citation_url = src.url or ""
        key = (normalize_url(citation_url) or src.source_ref, rank)
        if key in seen_citation_keys:
            return
        citations.append(CitationOut(
            url=citation_url,
            rank=rank,
            snippet=src.snippet[:200],
            is_tacit=src.is_tacit,
        ))
        seen_citation_keys.add(key)

    # v5 RAG contract: the model cites source IDs ([S1], [S2]) and the server
    # resolves IDs to URLs/snippets. Grouped IDs like [S1, S2] are valid too.
    # Keep URL + numeric support for older adapters and deterministic fallbacks.
    for rank in _extract_source_ref_ranks(answer):
        add_citation_from_source_rank(rank)

    # Pull URLs the model actually cited.
    cited_urls = extract_citations(answer)
    gov_by_norm = {normalize_url(g.get("url") or ""): g for g in gov_results}
    for u in cited_urls:
        tacit_rank = _tacit_rank_from_citation_url(u)
        if tacit_rank and 1 <= tacit_rank <= len(tacit_results):
            tacit_match = tacit_results[tacit_rank - 1]
            citation_url = tacit_match.get("office_url") or normalize_url(u)
            key = (normalize_url(citation_url), tacit_rank)
            if key not in seen_citation_keys:
                citations.append(CitationOut(
                    url=citation_url,
                    rank=tacit_rank,
                    snippet=(tacit_match.get("claim") or "")[:200],
                    is_tacit=True,
                ))
                seen_citation_keys.add(key)
            continue
        nu = normalize_url(u)
        gov_chunk = gov_by_norm.get(nu)
        if gov_chunk:
            rank = gov_chunk["rank"] + len(tacit_results)
            key = (normalize_url(u), rank)
            if key not in seen_citation_keys:
                citations.append(CitationOut(
                    url=u, rank=rank,
                    snippet=(gov_chunk["text"] or "")[:200], is_tacit=False,
                ))
                seen_citation_keys.add(key)
            continue
        # Might be a tacit citation if model used the office_url.
        tacit_match = next(
            (t for t in tacit_results if normalize_url(t.get("office_url") or "") == nu),
            None,
        )
        if tacit_match:
            key = (normalize_url(u), tacit_match["rank"])
            if key not in seen_citation_keys:
                citations.append(CitationOut(
                    url=u, rank=tacit_match["rank"],
                    snippet=(tacit_match.get("claim") or "")[:200], is_tacit=True,
                ))
                seen_citation_keys.add(key)
        else:
            try:
                if not urllib.parse.urlsplit(normalize_url(u)).path.strip("/"):
                    continue
            except Exception:
                pass
            key = (normalize_url(u), 0)
            if key not in seen_citation_keys:
                citations.append(CitationOut(url=u, rank=0, snippet="", is_tacit=False))
                seen_citation_keys.add(key)

    return QueryResponse(
        answer=answer,
        citations=citations,
        sources=sources,
        did_refuse=is_refusal(answer),
        retrieved_tacit=len(tacit_results),
        retrieved_gov=len(gov_results),
        latency_ms={
            "retrieval": retrieval_ms,
            "generation": generation_ms,
            "total": total_ms,
        },
        detected_lang=detected_lang,
        planner=planner,
    )


def _model_to_dict(value: Any) -> Any:
    if isinstance(value, list):
        return [_model_to_dict(v) for v in value]
    if isinstance(value, dict):
        return {k: _model_to_dict(v) for k, v in value.items()}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _sse(event: str, data: Any) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(_model_to_dict(data), ensure_ascii=False)}\n\n"
    )


def _build_retrieved_source_out(
    tacit_results: list[dict],
    gov_results: list[dict],
) -> list[RetrievedSourceOut]:
    sources: list[RetrievedSourceOut] = []
    rank = 0
    for t in tacit_results:
        rank += 1
        sources.append(RetrievedSourceOut(
            rank=rank,
            source_ref=f"S{rank}",
            is_tacit=True,
            label="CITIZEN INTERVIEW",
            url=t.get("office_url") or None,
            host=urllib.parse.urlparse(t.get("office_url") or "").netloc or None,
            snippet=(t.get("claim") or "")[:500],
            score=t.get("score"),
            rank_score=t.get("score"),
            relevance="high" if t.get("score", 0) >= 1 else "medium",
            confidence=t.get("confidence"),
            interviewee_role=t.get("interviewee_role"),
            features={"service": t.get("service"), "fact_type": t.get("fact_type")},
        ))
    for g in gov_results:
        rank += 1
        feature_markers = tuple(g.get("features", {}).get("strong_hits") or ())
        sources.append(RetrievedSourceOut(
            rank=rank,
            source_ref=f"S{rank}",
            is_tacit=False,
            label="GOV.NP",
            url=g.get("url"),
            host=g.get("host"),
            snippet=_focused_snippet(g.get("text") or "", feature_markers, 500),
            score=g.get("score"),
            rank_score=g.get("rank_score"),
            relevance=g.get("relevance"),
            chunk_id=g.get("chunk_id"),
            source_id=g.get("source_id"),
            title=g.get("title"),
            doc_type=g.get("doc_type"),
            tier=g.get("tier"),
            features=g.get("features"),
        ))
    return sources


def _assess_retrieval_quality(question: str, tacit_results: list[dict], gov_results: list[dict]) -> RetrievalQualityOut:
    topic = _detect_retrieval_topic(question)
    expected_domains = list(_authority_domains_for_query(topic, question)) if topic else []
    best_gov = gov_results[0] if gov_results else None

    if tacit_results and not gov_results:
        return RetrievalQualityOut(
            passed=True,
            reason="tacit_only",
            topic=topic,
            expected_domains=expected_domains,
        )
    if not tacit_results and not gov_results:
        return RetrievalQualityOut(
            passed=False,
            reason="no_sources",
            topic=topic,
            expected_domains=expected_domains,
        )

    if topic is None and _detect_local_domains(question):
        return RetrievalQualityOut(
            passed=False,
            reason="locality_without_service_topic",
            topic=topic,
            expected_domains=expected_domains,
            best_gov_rank=best_gov.get("rank") if best_gov else None,
            best_gov_host=best_gov.get("host") if best_gov else None,
            best_gov_rank_score=best_gov.get("rank_score") if best_gov else None,
        )

    if tacit_results and topic in LOCAL_TACIT_STRICT_TOPICS and _detect_local_domains(question):
        return RetrievalQualityOut(
            passed=True,
            reason="local_tacit_topic_match",
            topic=topic,
            expected_domains=expected_domains,
        )

    if topic and expected_domains:
        for g in gov_results[:3]:
            if _domain_matches(g.get("host"), tuple(expected_domains)):
                return RetrievalQualityOut(
                    passed=True,
                    reason="expected_domain_in_top3",
                    topic=topic,
                    expected_domains=expected_domains,
                    best_gov_rank=g.get("rank"),
                    best_gov_host=g.get("host"),
                    best_gov_rank_score=g.get("rank_score"),
                )
        return RetrievalQualityOut(
            passed=False,
            reason="topic_expected_domain_missing_top3",
            topic=topic,
            expected_domains=expected_domains,
            best_gov_rank=best_gov.get("rank") if best_gov else None,
            best_gov_host=best_gov.get("host") if best_gov else None,
            best_gov_rank_score=best_gov.get("rank_score") if best_gov else None,
        )

    if best_gov and best_gov.get("relevance") in ("high", "medium"):
        return RetrievalQualityOut(
            passed=True,
            reason=f"top_gov_relevance_{best_gov.get('relevance')}",
            topic=topic,
            expected_domains=expected_domains,
            best_gov_rank=best_gov.get("rank"),
            best_gov_host=best_gov.get("host"),
            best_gov_rank_score=best_gov.get("rank_score"),
        )

    return RetrievalQualityOut(
        passed=False,
        reason="low_relevance",
        topic=topic,
        expected_domains=expected_domains,
        best_gov_rank=best_gov.get("rank") if best_gov else None,
        best_gov_host=best_gov.get("host") if best_gov else None,
        best_gov_rank_score=best_gov.get("rank_score") if best_gov else None,
    )


OUTREACH_PENDING = OUTREACH_DIR / "pending"
OUTREACH_SENT = OUTREACH_DIR / "sent"
OUTREACH_FAILED = OUTREACH_DIR / "failed"
_OUTREACH_ID_RE = re.compile(r"^[0-9TZ\-]{16,24}-[a-f0-9]{8}$")
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def _ensure_outreach_dirs() -> None:
    for d in (OUTREACH_PENDING, OUTREACH_SENT, OUTREACH_FAILED):
        d.mkdir(parents=True, exist_ok=True)


def _outreach_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _outreach_status_dir(status: str) -> Path:
    if status == "sent":
        return OUTREACH_SENT
    if status == "failed":
        return OUTREACH_FAILED
    return OUTREACH_PENDING


def _outreach_record_path(outreach_id: str, status: str = "pending") -> Path:
    if not _OUTREACH_ID_RE.match(outreach_id):
        raise HTTPException(404, "outreach record not found")
    return _safe_subpath(_outreach_status_dir(status), f"{outreach_id}.json")


def _save_outreach_record(record: dict[str, Any], status: str = "pending") -> None:
    _ensure_outreach_dirs()
    path = _outreach_record_path(str(record["id"]), status)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_outreach_record(outreach_id: str) -> tuple[dict[str, Any], str, Path]:
    _ensure_outreach_dirs()
    for status in ("pending", "sent", "failed"):
        path = _outreach_record_path(outreach_id, status)
        if not path.exists():
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8")), status, path
        except json.JSONDecodeError as exc:
            raise HTTPException(500, "outreach record is corrupted") from exc
    raise HTTPException(404, "outreach record not found")


def _list_outreach_records(status: str = "pending") -> list[dict[str, Any]]:
    _ensure_outreach_dirs()
    status_dir = _outreach_status_dir(status)
    records: list[dict[str, Any]] = []
    for path in sorted(status_dir.glob("*.json"), reverse=True):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        records.append({
            "id": record.get("id"),
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "sent_at": record.get("sent_at"),
            "question": record.get("question"),
            "gap_reason": record.get("gap_reason"),
            "contact": record.get("contact"),
            "source_count": len(record.get("sources") or []),
        })
    return records


def _nepal_mobile_msisdn(phone: str) -> str | None:
    digits = re.sub(r"\D", "", (phone or "").translate(_DEVANAGARI_DIGITS))
    if digits.startswith("977") and len(digits) == 13 and digits[3] == "9":
        return digits
    if len(digits) == 10 and digits.startswith("9"):
        return f"977{digits}"
    return None


def _extract_nepal_mobile_numbers(text: str) -> list[tuple[str, str]]:
    normalized = (text or "").translate(_DEVANAGARI_DIGITS)
    mobile_re = re.compile(r"(?:\+?977[-.\s]*)?9\d{9}")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in mobile_re.finditer(normalized):
        raw = match.group(0).strip()
        msisdn = _nepal_mobile_msisdn(raw)
        if not msisdn or msisdn in seen:
            continue
        seen.add(msisdn)
        out.append((f"+{msisdn}", msisdn))
    return out


def _outreach_role_from_context(context: str) -> str | None:
    context_l = (context or "").lower()
    role_markers = (
        ("Information Officer", ("information officer", "सूचना अधिकारी")),
        ("Helpdesk", ("helpdesk", "हेल्पडेस्क", "हेल्पडेष्क")),
        ("Grievance Officer", ("grievance", "complaint", "गुनासो", "उजुरी")),
        ("Chief Administrative Officer", ("chief administrative", "प्रमुख प्रशासकीय")),
        ("Mayor", ("mayor", "नगर प्रमुख")),
        ("Deputy Mayor", ("deputy mayor", "उप प्रमुख", "उपमेयर")),
        ("Office contact", ("contact", "phone", "सम्पर्क", "फोन")),
    )
    for label, markers in role_markers:
        if any(marker in context_l or marker in context for marker in markers):
            return label
    return None


def _outreach_name_from_context(context: str) -> str | None:
    context = re.sub(r"\s+", " ", context or "").strip()
    if not context:
        return None
    latin_match = re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4}\b", context)
    if latin_match:
        candidate = latin_match.group(0).strip()
        if candidate.lower() not in {"Contact No", "Phone No", "Mobile No"}:
            return candidate
    deva_match = re.search(r"[\u0900-\u097F]{2,}(?:\s+[\u0900-\u097F]{2,}){1,4}", context)
    if deva_match:
        return deva_match.group(0).strip()
    return None


def _outreach_context_window(text: str, needle: str, chars: int = 180) -> str:
    text = re.sub(r"\s+", " ", text or "")
    normalized = text.translate(_DEVANAGARI_DIGITS)
    needle_digits = re.sub(r"\D", "", needle)
    forms = [needle, needle.replace("+", ""), needle_digits, needle_digits[-10:]]
    start = -1
    matched = needle
    for form in dict.fromkeys(f for f in forms if f):
        start = normalized.find(form)
        if start >= 0:
            matched = form
            break
    if start < 0:
        return text[:chars]
    left = max(0, start - chars // 2)
    right = min(len(text), start + len(matched) + chars // 2)
    return text[left:right].strip()


def _outreach_candidates_from_source(
    source: dict[str, Any],
    source_ref: str,
) -> list[OutreachContactCandidate]:
    text = source.get("text") or ""
    candidates: list[OutreachContactCandidate] = []
    seen: set[str] = set()

    for official in _extract_jiri_officials(text):
        msisdn = _nepal_mobile_msisdn(official.get("phone") or "")
        if not msisdn or msisdn in seen:
            continue
        seen.add(msisdn)
        candidates.append(OutreachContactCandidate(
            phone=f"+{msisdn}",
            whatsapp_to=msisdn,
            source_url=source.get("url"),
            source_title=source.get("title"),
            source_host=source.get("host"),
            source_ref=source_ref,
            name=official.get("name") or None,
            role=official.get("role") or None,
        ))

    for display_phone, msisdn in _extract_nepal_mobile_numbers(text):
        if msisdn in seen:
            continue
        seen.add(msisdn)
        context = _outreach_context_window(text, msisdn)
        candidates.append(OutreachContactCandidate(
            phone=display_phone,
            whatsapp_to=msisdn,
            source_url=source.get("url"),
            source_title=source.get("title"),
            source_host=source.get("host"),
            source_ref=source_ref,
            name=_outreach_name_from_context(context),
            role=_outreach_role_from_context(context),
        ))
    return candidates


def _rank_outreach_candidate(candidate: OutreachContactCandidate) -> tuple[int, int, int, str]:
    role = (candidate.role or "").lower()
    source_url = (candidate.source_url or "").lower()
    role_score = 0
    if "information officer" in role or "helpdesk" in role:
        role_score = 4
    elif "grievance" in role:
        role_score = 3
    elif "chief administrative" in role or "office contact" in role:
        role_score = 2
    elif role:
        role_score = 1
    contact_url_score = 1 if "contact" in source_url or "staff" in source_url else 0
    named_score = 1 if candidate.name else 0
    return (-role_score, -contact_url_score, -named_score, candidate.whatsapp_to)


def _build_outreach_contact_query(frame: CaseFrame, question: str) -> str:
    parts = ["contact information information officer helpdesk mobile phone"]
    parts.extend(frame.expected_domains)
    parts.extend(frame.local_domains)
    if frame.district:
        parts.append(frame.district)
    if frame.municipality:
        parts.append(frame.municipality)
    if frame.office:
        parts.append(frame.office)
    if not frame.district and not frame.municipality and not frame.office:
        parts.append(frame.retrieval_query or frame.resolved_question or question)
    return " ".join(dict.fromkeys(part for part in parts if part))


def _source_summary(source: dict[str, Any], rank: int) -> dict[str, Any]:
    feature_markers = tuple(source.get("features", {}).get("strong_hits") or ())
    return {
        "rank": rank,
        "source_ref": f"O{rank}",
        "url": source.get("url"),
        "host": source.get("host"),
        "title": source.get("title"),
        "snippet": _focused_snippet(source.get("text") or "", feature_markers, 360),
        "rank_score": source.get("rank_score"),
        "relevance": source.get("relevance"),
    }


def _build_outreach_message(
    question: str,
    frame: CaseFrame,
    contact: OutreachContactCandidate,
    reason: str,
) -> str:
    service_labels = {
        "citizenship": "नागरिकता",
        "passport": "राहदानी",
        "national_id": "राष्ट्रिय परिचयपत्र",
        "vital_registration": "घटना दर्ता",
        "pan_tax": "प्यान/कर",
        "driving_license": "सवारी चालक अनुमतिपत्र",
        "police_clearance": "प्रहरी चारित्रिक प्रमाणपत्र",
        "foreign_employment": "वैदेशिक रोजगार",
        "municipality_service": "पालिका सेवा",
        "embassy_consular": "दूतावास/कन्सुलर सेवा",
    }
    action_labels = {
        "apply": "सेवा लिन",
        "renew": "नवीकरण गर्न",
        "replace": "प्रतिलिपि/बदली सेवा लिन",
        "lost": "हराएको कागजातको प्रतिलिपि लिन",
        "correct": "विवरण सच्याउन",
        "check_status": "अवस्था बुझ्न",
        "find_office": "सम्बन्धित कार्यालय/सम्पर्क पत्ता लगाउन",
        "fee": "शुल्क बुझ्न",
        "required_documents": "चाहिने कागजात बुझ्न",
        "complaint": "उजुरी वा गुनासो दर्ता गर्न",
        "deadline": "समयसीमा बुझ्न",
        "contact_person": "सम्पर्क व्यक्ति पत्ता लगाउन",
    }
    place_labels = {
        "sankhuwasabha": "संखुवासभा",
        "dharmadevi": "धर्मदेवी",
        "jiri": "जिरी",
        "dolakha": "दोलखा",
        "khandbari": "खाँदबारी",
        "chainpur": "चैनपुर",
        "dhankuta": "धनकुटा",
        "mahalaxmi": "महालक्ष्मी",
    }

    def place_label(value: str | None) -> str | None:
        if not value:
            return None
        return place_labels.get(str(value).strip().lower(), value)

    service_label = service_labels.get(frame.service, frame.service or "सरकारी सेवा")
    action_label = action_labels.get(frame.action, "सेवा सम्बन्धी जानकारी लिन")
    location_bits = [
        f"{place_label(frame.district)} जिल्ला" if frame.district else "",
        f"{place_label(frame.municipality)} पालिका" if frame.municipality else "",
        f"वडा {frame.ward}" if frame.ward else "",
    ]
    location_text = ", ".join(bit for bit in location_bits if bit)
    summary_parts = [
        f"नागरिकले {service_label} सम्बन्धी {action_label} चाहनुभएको छ।",
        f"स्थान: {location_text}।" if location_text else "",
    ]
    q_lower = question.lower()
    detail_needs: list[str] = []
    if any(token in q_lower for token in ("document", "documents", "कागजात")):
        detail_needs.append("चाहिने कागजात")
    if any(token in q_lower for token in ("fee", "charge", "शुल्क", "रकम")):
        detail_needs.append("शुल्क")
    if any(token in q_lower for token in ("time", "deadline", "कति दिन", "लाग्ने समय")):
        detail_needs.append("लाग्ने समय")
    if any(token in q_lower for token in ("contact", "phone", "number", "सम्पर्क", "फोन", "नम्बर")):
        detail_needs.append("सम्पर्क व्यक्ति/फोन")
    if detail_needs:
        summary_parts.append(f"कृपया {', '.join(dict.fromkeys(detail_needs))} पुष्टि गरिदिनुहोस्।")
    question_summary = " ".join(part for part in summary_parts if part)
    service_bits = [
        f"सेवा={service_labels.get(frame.service, frame.service)}" if frame.service else "",
        f"जिल्ला={place_label(frame.district)}" if frame.district else "",
        f"पालिका={place_label(frame.municipality)}" if frame.municipality else "",
        f"वडा={frame.ward}" if frame.ward else "",
    ]
    service_context = ", ".join(bit for bit in service_bits if bit) or "सेवा/स्थान स्पष्ट छैन"
    reason_text = str(reason or "").strip()
    reason_lower = reason_text.lower()
    if "source gap" in reason_lower or "refusal" in reason_lower:
        reason_text = "यो केसमा उत्तर दिन चाहिने भरपर्दो आधिकारिक स्रोत अपुग भयो।"
    elif "demo auto-outreach" in reason_lower:
        reason_text = "नागरिकको प्रश्न सम्बन्धित कार्यालयबाट पुष्टि गर्नुपर्ने देखियो।"
    return (
        "नमस्ते। SpeakGov ले नागरिकको सरकारी सेवा सम्बन्धी प्रश्नको उत्तर दिन खोजिरहेको छ, "
        "तर यो खास केसका लागि हालको भरपर्दो आधिकारिक स्रोत स्पष्ट भेटिएको छैन।\n\n"
        f"नागरिकको प्रश्नको सार: {question_summary}\n"
        f"बुझेको सन्दर्भ: {service_context}\n"
        f"स्रोत/जानकारीको कमी: {reason_text}\n\n"
        "कृपया सही कार्यालय/प्रक्रिया, चाहिने कागजात, शुल्क/लाग्ने समय, "
        "र उपलब्ध भए आधिकारिक स्रोत लिंक वा सम्पर्क पुष्टि गरी पठाइदिनुहुन्छ? "
        "यस सन्देशमा नागरिकको निजी विवरण साझा गरिएको छैन।"
    )


def _create_outreach_draft(
    request: Request,
    payload: OutreachDraftRequest,
) -> OutreachDraftResponse:
    retriever: Retriever | None = request.app.state.retriever
    tacit: TacitRetriever = request.app.state.tacit
    query_payload = QueryRequest(question=payload.question, history=payload.history)
    frame = _navigator_frame(query_payload)
    planner = planner_contract(frame)
    contact_query = _build_outreach_contact_query(frame, payload.question)
    contact_payload = RetrieveRequest(
        question=contact_query,
        top_k_tacit=0,
        top_k_gov=payload.top_k_gov,
        history=payload.history,
    )
    _, gov_results, _ = _run_retrieval(retriever, tacit, contact_payload)

    sources = [_source_summary(source, i + 1) for i, source in enumerate(gov_results)]
    candidates: list[OutreachContactCandidate] = []
    seen_msisdn: set[str] = set()
    for i, source in enumerate(gov_results):
        for candidate in _outreach_candidates_from_source(source, f"O{i + 1}"):
            if candidate.whatsapp_to in seen_msisdn:
                continue
            seen_msisdn.add(candidate.whatsapp_to)
            candidates.append(candidate)
    candidates.sort(key=_rank_outreach_candidate)

    gap_reason = (
        (payload.reason or "").strip()
        or ";".join(planner.get("gaps") or [])
        or "no authoritative answer found in retrieved sources"
    )
    contact = candidates[0] if candidates else None
    message = _build_outreach_message(payload.question, frame, contact, gap_reason) if contact else ""
    status = "draft_ready" if contact else "no_whatsapp_mobile_found"
    record = {
        "id": _outreach_id(),
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "question": payload.question,
        "gap_reason": gap_reason,
        "contact": _model_to_dict(contact) if contact else None,
        "message": message,
        "planner": planner,
        "contact_query": contact_query,
        "sources": sources,
        "candidates": _model_to_dict(candidates),
    }
    _save_outreach_record(record, "pending")
    return OutreachDraftResponse(**record)


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve(request: Request, payload: RetrieveRequest):
    retriever: Retriever | None = request.app.state.retriever
    tacit: TacitRetriever = request.app.state.tacit
    nav_frame = _navigator_frame(payload)
    planner = planner_contract(nav_frame)

    tacit_results, gov_results, retrieval_ms = _run_retrieval(retriever, tacit, payload)
    if not tacit_results and not gov_results and retriever is None:
        raise HTTPException(503, "no retrieval source available — neither DB nor tacit corpus loaded")

    prompt = None
    if payload.include_prompt:
        prompt = build_user_prompt(
            _prompt_question(payload),
            tacit_results,
            gov_results,
            _prompt_history(payload),
            _response_language(payload),
        )

    return RetrieveResponse(
        question=payload.question,
        sources=_build_retrieved_source_out(tacit_results, gov_results),
        quality=_assess_retrieval_quality(nav_frame.retrieval_query or payload.question, tacit_results, gov_results),
        retrieved_tacit=len(tacit_results),
        retrieved_gov=len(gov_results),
        latency_ms={"retrieval": retrieval_ms, "total": retrieval_ms},
        detected_lang=_response_language(payload),
        prompt=prompt,
        planner=planner,
    )


@app.post("/query", response_model=QueryResponse)
def query(request: Request, payload: QueryRequest):
    composer: Composer = request.app.state.composer
    retriever: Retriever | None = request.app.state.retriever
    tacit: TacitRetriever = request.app.state.tacit

    t0 = time.time()
    detected_lang = _response_language(payload)
    if _is_identity_question(payload.question):
        elapsed_ms = int((time.time() - t0) * 1000)
        return QueryResponse(
            answer=_identity_answer(detected_lang),
            citations=[],
            sources=[],
            did_refuse=False,
            retrieved_tacit=0,
            retrieved_gov=0,
            latency_ms={"retrieval": 0, "generation": 0, "total": elapsed_ms},
            detected_lang=detected_lang,
        )

    nav_frame = _navigator_frame(payload)
    planner = planner_contract(nav_frame)
    if nav_frame.off_domain_answer:
        elapsed_ms = int((time.time() - t0) * 1000)
        return QueryResponse(
            answer=nav_frame.off_domain_answer,
            citations=[],
            sources=[],
            did_refuse=False,
            retrieved_tacit=0,
            retrieved_gov=0,
            latency_ms={"retrieval": 0, "generation": 0, "total": elapsed_ms},
            detected_lang=detected_lang,
            planner=planner,
        )
    pre_retrieval_followup = followup_answer(nav_frame, [])
    if pre_retrieval_followup and (
        nav_frame.memory_only or "service" in (planner.get("missing_slots") or [])
    ):
        elapsed_ms = int((time.time() - t0) * 1000)
        return QueryResponse(
            answer=pre_retrieval_followup,
            citations=[],
            sources=[],
            did_refuse=False,
            retrieved_tacit=0,
            retrieved_gov=0,
            latency_ms={"retrieval": 0, "generation": 0, "total": elapsed_ms},
            detected_lang=detected_lang,
            planner=planner,
        )

    tacit_results, gov_results, retrieval_ms = _run_retrieval(retriever, tacit, payload)
    t_retr = time.time()

    if not tacit_results and not gov_results and retriever is None:
        raise HTTPException(503, "no retrieval source available — neither DB nor tacit corpus loaded")

    prompt_question = _prompt_question(payload)
    if should_force_no_source_for_location(nav_frame, gov_results):
        t_gen = time.time()
        return _build_query_response(
            answer=location_no_source_answer(nav_frame),
            tacit_results=tacit_results,
            gov_results=[],
            retrieval_ms=retrieval_ms,
            generation_ms=0,
            total_ms=int((t_gen - t0) * 1000),
            detected_lang=detected_lang,
            planner=planner,
        )
    followup = followup_answer(nav_frame, gov_results)
    if followup:
        t_gen = time.time()
        return _build_query_response(
            answer=followup,
            tacit_results=tacit_results,
            gov_results=gov_results,
            retrieval_ms=retrieval_ms,
            generation_ms=0,
            total_ms=int((t_gen - t0) * 1000),
            detected_lang=detected_lang,
            planner=planner,
        )

    pre_quality_fallback = _citizenship_duplicate_practical_fallback_answer(
        prompt_question, tacit_results, gov_results, detected_lang,
    )
    if pre_quality_fallback:
        t_gen = time.time()
        return _build_query_response(
            answer=pre_quality_fallback,
            tacit_results=tacit_results,
            gov_results=gov_results,
            retrieval_ms=retrieval_ms,
            generation_ms=0,
            total_ms=int((t_gen - t0) * 1000),
            detected_lang=detected_lang,
            planner=planner,
        )

    retrieval_quality = _assess_retrieval_quality(prompt_question, tacit_results, gov_results)
    if not retrieval_quality.passed:
        t_gen = time.time()
        return _build_query_response(
            answer=_no_source_answer(detected_lang),
            tacit_results=tacit_results,
            gov_results=gov_results,
            retrieval_ms=retrieval_ms,
            generation_ms=0,
            total_ms=int((t_gen - t0) * 1000),
            detected_lang=detected_lang,
            planner=planner,
        )

    fallback_answer = (
        _foreign_employment_complaint_fallback_answer(prompt_question, gov_results, detected_lang)
        or
        _service_fallback_answer(prompt_question, gov_results, detected_lang)
        or _passport_fee_fallback_answer(prompt_question, gov_results, detected_lang)
        or _passport_renewal_fallback_answer(prompt_question, gov_results, detected_lang)
        or _passport_apply_fallback_answer(prompt_question, gov_results, detected_lang)
        or _pan_registration_fallback_answer(prompt_question, gov_results, detected_lang)
        or _driving_license_fallback_answer(prompt_question, gov_results, detected_lang)
        or _company_registration_fallback_answer(prompt_question, gov_results, detected_lang)
        or _national_id_fallback_answer(prompt_question, gov_results, detected_lang)
        or _police_clearance_fallback_answer(prompt_question, gov_results, detected_lang)
        or _citizenship_duplicate_fallback_answer(prompt_question, gov_results, detected_lang)
        or _citizenship_duplicate_practical_fallback_answer(prompt_question, tacit_results, gov_results, detected_lang)
        or _citizenship_certificate_fallback_answer(prompt_question, gov_results, detected_lang)
        or _local_event_service_fallback_answer(prompt_question, gov_results, detected_lang)
        or _municipality_contact_fallback_answer(prompt_question, gov_results, detected_lang)
        or _generic_contact_fallback_answer(prompt_question, gov_results, detected_lang)
        or _tacit_municipality_fallback_answer(prompt_question, tacit_results, detected_lang)
    )
    if fallback_answer:
        t_gen = time.time()
        return _build_query_response(
            answer=fallback_answer,
            tacit_results=tacit_results,
            gov_results=gov_results,
            retrieval_ms=retrieval_ms,
            generation_ms=0,
            total_ms=int((t_gen - t0) * 1000),
            detected_lang=detected_lang,
            planner=planner,
        )

    user_prompt = build_user_prompt(
        prompt_question,
        tacit_results,
        gov_results,
        _prompt_history(payload),
        detected_lang,
    )
    answer = composer.generate(
        SYSTEM_GROUNDED, user_prompt, max_tokens=payload.max_new_tokens, seed=payload.seed,
    )
    if _answer_script_mismatch(answer, detected_lang):
        repaired = _repair_answer_language_with_composer(
            composer,
            answer,
            detected_lang,
            max_tokens=min(384, payload.max_new_tokens),
            seed=payload.seed,
        )
        if repaired:
            answer = repaired
    answer = _guard_answer_language(answer, detected_lang, tacit_results, gov_results)
    t_gen = time.time()

    return _build_query_response(
        answer=answer,
        tacit_results=tacit_results,
        gov_results=gov_results,
        retrieval_ms=retrieval_ms,
        generation_ms=int((t_gen - t_retr) * 1000),
        total_ms=int((t_gen - t0) * 1000),
        detected_lang=detected_lang,
        planner=planner,
    )


@app.post("/query/stream")
def query_stream(request: Request, payload: QueryRequest):
    composer: Composer = request.app.state.composer
    retriever: Retriever | None = request.app.state.retriever
    tacit: TacitRetriever = request.app.state.tacit

    t0 = time.time()
    detected_lang = _response_language(payload)

    if _is_identity_question(payload.question):
        elapsed_ms = int((time.time() - t0) * 1000)
        response = QueryResponse(
            answer=_identity_answer(detected_lang),
            citations=[],
            sources=[],
            did_refuse=False,
            retrieved_tacit=0,
            retrieved_gov=0,
            latency_ms={"retrieval": 0, "generation": 0, "total": elapsed_ms},
            detected_lang=detected_lang,
        )

        def identity_events():
            yield _sse("final", response)

        return StreamingResponse(
            identity_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    nav_frame = _navigator_frame(payload)
    planner = planner_contract(nav_frame)
    early_followup = followup_answer(nav_frame, [])
    early_answer = nav_frame.off_domain_answer or (
        early_followup
        if nav_frame.memory_only or "service" in (planner.get("missing_slots") or [])
        else None
    )
    if early_answer:
        elapsed_ms = int((time.time() - t0) * 1000)
        response = QueryResponse(
            answer=early_answer,
            citations=[],
            sources=[],
            did_refuse=False,
            retrieved_tacit=0,
            retrieved_gov=0,
            latency_ms={"retrieval": 0, "generation": 0, "total": elapsed_ms},
            detected_lang=detected_lang,
            planner=planner,
        )

        def early_events():
            yield _sse("final", response)

        return StreamingResponse(
            early_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    tacit_results, gov_results, retrieval_ms = _run_retrieval(retriever, tacit, payload)
    t_retr = time.time()

    if not tacit_results and not gov_results and retriever is None:
        raise HTTPException(503, "no retrieval source available — neither DB nor tacit corpus loaded")

    prompt_question = _prompt_question(payload)
    retrieval_quality = _assess_retrieval_quality(prompt_question, tacit_results, gov_results)
    user_prompt = build_user_prompt(
        prompt_question,
        tacit_results,
        gov_results,
        _prompt_history(payload),
        detected_lang,
    )
    sources = _build_source_out(tacit_results, gov_results)
    pre_quality_fallback = _citizenship_duplicate_practical_fallback_answer(
        prompt_question, tacit_results, gov_results, detected_lang,
    )
    navigator_answer = None
    if should_force_no_source_for_location(nav_frame, gov_results):
        navigator_answer = location_no_source_answer(nav_frame)
    else:
        navigator_answer = followup_answer(nav_frame, gov_results)
    fallback_answer = (
        _foreign_employment_complaint_fallback_answer(prompt_question, gov_results, detected_lang)
        or
        _service_fallback_answer(prompt_question, gov_results, detected_lang)
        or _passport_fee_fallback_answer(prompt_question, gov_results, detected_lang)
        or _passport_renewal_fallback_answer(prompt_question, gov_results, detected_lang)
        or _passport_apply_fallback_answer(prompt_question, gov_results, detected_lang)
        or _pan_registration_fallback_answer(prompt_question, gov_results, detected_lang)
        or _driving_license_fallback_answer(prompt_question, gov_results, detected_lang)
        or _company_registration_fallback_answer(prompt_question, gov_results, detected_lang)
        or _national_id_fallback_answer(prompt_question, gov_results, detected_lang)
        or _police_clearance_fallback_answer(prompt_question, gov_results, detected_lang)
        or _citizenship_duplicate_fallback_answer(prompt_question, gov_results, detected_lang)
        or _citizenship_duplicate_practical_fallback_answer(prompt_question, tacit_results, gov_results, detected_lang)
        or _citizenship_certificate_fallback_answer(prompt_question, gov_results, detected_lang)
        or _local_event_service_fallback_answer(prompt_question, gov_results, detected_lang)
        or _municipality_contact_fallback_answer(prompt_question, gov_results, detected_lang)
        or _generic_contact_fallback_answer(prompt_question, gov_results, detected_lang)
        or _tacit_municipality_fallback_answer(prompt_question, tacit_results, detected_lang)
    )

    def stream_events():
        yield _sse("meta", {
            "sources": sources,
            "retrieved_tacit": len(tacit_results),
            "retrieved_gov": len(gov_results),
            "latency_ms": {"retrieval": retrieval_ms},
            "detected_lang": detected_lang,
            "planner": planner,
        })
        parts: list[str] = []
        generation_started = time.time()
        try:
            if navigator_answer:
                for chunk in re.findall(r"\S+\s*", navigator_answer):
                    parts.append(chunk)
                    yield _sse("token", {"text": chunk})
                t_gen = time.time()
                response = _build_query_response(
                    answer="".join(parts).strip(),
                    tacit_results=tacit_results,
                    gov_results=[] if should_force_no_source_for_location(nav_frame, gov_results) else gov_results,
                    retrieval_ms=retrieval_ms,
                    generation_ms=0,
                    total_ms=int((t_gen - t0) * 1000),
                    detected_lang=detected_lang,
                    planner=planner,
                )
                yield _sse("final", response)
                return

            if pre_quality_fallback:
                for chunk in re.findall(r"\S+\s*", pre_quality_fallback):
                    parts.append(chunk)
                    yield _sse("token", {"text": chunk})
                t_gen = time.time()
                response = _build_query_response(
                    answer="".join(parts).strip(),
                    tacit_results=tacit_results,
                    gov_results=gov_results,
                    retrieval_ms=retrieval_ms,
                    generation_ms=0,
                    total_ms=int((t_gen - t0) * 1000),
                    detected_lang=detected_lang,
                    planner=planner,
                )
                yield _sse("final", response)
                return

            if not retrieval_quality.passed:
                response = _build_query_response(
                    answer=_no_source_answer(detected_lang),
                    tacit_results=tacit_results,
                    gov_results=gov_results,
                    retrieval_ms=retrieval_ms,
                    generation_ms=0,
                    total_ms=int((time.time() - t0) * 1000),
                    detected_lang=detected_lang,
                    planner=planner,
                )
                yield _sse("final", response)
                return

            if fallback_answer:
                for chunk in re.findall(r"\S+\s*", fallback_answer):
                    parts.append(chunk)
                    yield _sse("token", {"text": chunk})
                t_gen = time.time()
                response = _build_query_response(
                    answer="".join(parts).strip(),
                    tacit_results=tacit_results,
                    gov_results=gov_results,
                    retrieval_ms=retrieval_ms,
                    generation_ms=0,
                    total_ms=int((t_gen - t0) * 1000),
                    detected_lang=detected_lang,
                    planner=planner,
                )
                yield _sse("final", response)
                return

            for chunk in composer.generate_stream(
                SYSTEM_GROUNDED,
                user_prompt,
                max_tokens=payload.max_new_tokens,
                seed=payload.seed,
            ):
                candidate = "".join(parts) + chunk
                if _has_refusal_repetition(candidate):
                    cleaned = _clean_generated_answer(candidate)
                    prior = "".join(parts)
                    delta = cleaned[len(prior):] if cleaned.startswith(prior) else ""
                    if delta:
                        yield _sse("token", {"text": delta})
                    parts = [cleaned]
                    break
                parts.append(chunk)
            t_gen = time.time()
            answer = _clean_generated_answer("".join(parts).strip())
            if _answer_script_mismatch(answer, detected_lang):
                repaired = _repair_answer_language_with_composer(
                    composer,
                    answer,
                    detected_lang,
                    max_tokens=min(384, payload.max_new_tokens),
                    seed=payload.seed,
                )
                if repaired:
                    answer = repaired
            answer = _guard_answer_language(answer, detected_lang, tacit_results, gov_results)
            for chunk in re.findall(r"\S+\s*", answer):
                yield _sse("token", {"text": chunk})
            response = _build_query_response(
                answer=answer,
                tacit_results=tacit_results,
                gov_results=gov_results,
                retrieval_ms=retrieval_ms,
                generation_ms=int((t_gen - generation_started) * 1000),
                total_ms=int((t_gen - t0) * 1000),
                detected_lang=detected_lang,
                planner=planner,
            )
            yield _sse("final", response)
        except Exception as e:
            LOG.exception("streaming query failed")
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---- Voice demo: public ASR/TTS ------------------------------------------


@app.get("/voice/providers", response_model=VoiceProvidersResponse)
def voice_providers():
    return VoiceProvidersResponse(
        asr_provider=VOICE_ASR_PROVIDER,
        asr_model_id=VOICE_ASR_MODEL_ID if VOICE_ASR_PROVIDER != "vertex" else VERTEX_MODEL,
        asr_space_url=VOICE_ASR_SPACE_URL if VOICE_ASR_PROVIDER in {"fastconformer-space", "hf-space", "space"} else None,
        tts_provider=VOICE_TTS_PROVIDER,
        tts_model_repo=VOICE_TTS_MODEL_REPO if VOICE_TTS_PROVIDER != "disabled" else None,
        tts_speaker=VOICE_TTS_SPEAKER if VOICE_TTS_PROVIDER != "disabled" else None,
        tts_space_url=VOICE_TTS_SPACE_URL if VOICE_TTS_PROVIDER in {"real-nepali-space", "piper-space", "hf-space", "space"} else None,
        tts_enabled=VOICE_TTS_PROVIDER not in {"", "disabled", "none", "off"},
    )


@app.post("/voice/transcribe", response_model=VoiceTranscribeResponse)
async def voice_transcribe(audio: UploadFile = File(...)):
    started = time.time()
    content = await audio.read()
    if not content:
        raise HTTPException(400, "empty audio")
    if len(content) > MAX_AUDIO_FILE_BYTES:
        raise HTTPException(400, f"audio too large ({len(content)} bytes)")

    filename = audio.filename or "recording.webm"
    suffix = Path(filename).suffix.lower() or ".webm"
    if suffix not in _AUDIO_MIME:
        suffix = ".webm"
    if VOICE_ASR_PROVIDER in {
        "fastconformer",
        "nemo",
        "local",
        "fastconformer-space",
        "hf-space",
        "space",
        "fastconformer-worker",
        "asr-worker",
        "worker",
        "http-worker",
    }:
        transcript, model_id = _transcribe_audio_bytes_via_local_asr(content, suffix)
        provider = VOICE_ASR_PROVIDER
    elif VOICE_ASR_PROVIDER in {"vertex", "gemini"}:
        transcript = transcribe_audio_bytes_via_vertex(content, suffix)
        model_id = VERTEX_MODEL
        provider = "vertex"
    else:
        raise HTTPException(503, f"unsupported ASR provider: {VOICE_ASR_PROVIDER}")
    elapsed_ms = int((time.time() - started) * 1000)
    return VoiceTranscribeResponse(
        transcript=transcript,
        latency_ms={"transcription": elapsed_ms, "total": elapsed_ms},
        mime_type=_AUDIO_MIME.get(suffix, audio.content_type or "audio/webm"),
        bytes=len(content),
        provider=provider,
        model_id=model_id,
    )


@app.post("/voice/synthesize")
def voice_synthesize(req: VoiceSynthesizeRequest):
    if VOICE_TTS_PROVIDER in {"", "disabled", "none", "off"}:
        raise HTTPException(503, "local TTS is not configured")
    started = time.time()
    if VOICE_TTS_PROVIDER not in {
        "real-nepali",
        "piper-plus",
        "piper",
        "local",
        "real-nepali-space",
        "piper-space",
        "hf-space",
        "space",
        "real-nepali-worker",
        "tts-worker",
        "worker",
        "http-worker",
    }:
        raise HTTPException(503, f"unsupported TTS provider: {VOICE_TTS_PROVIDER}")
    audio, meta = _synthesize_speech_via_local_tts(req)
    elapsed_ms = int((time.time() - started) * 1000)
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "X-Voice-Provider": meta["provider"],
            "X-Voice-Model": meta["model_repo"],
            "X-Voice-Speaker": meta["speaker"],
            "X-Voice-Sample-Rate": meta["sample_rate"],
            "X-Voice-Latency-Ms": str(elapsed_ms),
        },
    )


# ---- WhatsApp bridge proxy -----------------------------------------------


@app.post("/admin/outreach/draft", response_model=OutreachDraftResponse, dependencies=[Depends(admin_auth)])
def admin_outreach_draft(request: Request, payload: OutreachDraftRequest):
    return _create_outreach_draft(request, payload)


@app.get("/admin/outreach", dependencies=[Depends(admin_auth)])
def admin_outreach_list(status: str = "pending"):
    if status not in {"pending", "sent", "failed"}:
        raise HTTPException(400, "status must be pending, sent, or failed")
    return {"status": status, "items": _list_outreach_records(status)}


@app.get("/admin/outreach/{outreach_id}", dependencies=[Depends(admin_auth)])
def admin_outreach_get(outreach_id: str):
    record, status, _ = _load_outreach_record(outreach_id)
    record["storage_status"] = status
    return record


@app.post(
    "/admin/outreach/{outreach_id}/send",
    response_model=OutreachSendResponse,
    dependencies=[Depends(admin_auth)],
)
def admin_outreach_send(outreach_id: str):
    record, storage_status, path = _load_outreach_record(outreach_id)
    if storage_status == "sent":
        return OutreachSendResponse(
            id=outreach_id,
            status="already_sent",
            sent_at=record.get("sent_at"),
            send_result=record.get("send_result"),
        )
    contact = record.get("contact") or {}
    recipient = contact.get("whatsapp_to")
    message = record.get("message")
    if not recipient or not message:
        raise HTTPException(400, "outreach record has no WhatsApp-capable contact/message")
    try:
        send_result = _whatsapp_bridge_request("POST", "/send", {"to": recipient, "text": message})
    except HTTPException:
        record["status"] = "send_failed"
        record["failed_at"] = datetime.now(timezone.utc).isoformat()
        _save_outreach_record(record, "failed")
        failed_path = _outreach_record_path(outreach_id, "failed")
        if path != failed_path:
            try:
                path.unlink()
            except OSError:
                pass
        raise
    record["status"] = "sent"
    record["sent_at"] = datetime.now(timezone.utc).isoformat()
    record["send_result"] = send_result
    _save_outreach_record(record, "sent")
    sent_path = _outreach_record_path(outreach_id, "sent")
    if path != sent_path:
        try:
            path.unlink()
        except OSError:
            pass
    return OutreachSendResponse(
        id=outreach_id,
        status="sent",
        sent_at=record["sent_at"],
        send_result=send_result,
    )


@app.get("/whatsapp/status", dependencies=[Depends(admin_auth)])
def whatsapp_status():
    return _whatsapp_bridge_request("GET", "/status")


@app.post("/whatsapp/connect", dependencies=[Depends(admin_auth)])
def whatsapp_connect():
    return _whatsapp_bridge_request("POST", "/connect")


@app.get("/whatsapp/qr", dependencies=[Depends(admin_auth)])
def whatsapp_qr():
    return _whatsapp_bridge_request("GET", "/qr")


@app.post("/whatsapp/send", dependencies=[Depends(admin_auth)])
def whatsapp_send(req: WhatsAppSendRequest):
    return _whatsapp_bridge_request("POST", "/send", _model_to_dict(req))


@app.post("/whatsapp/logout", dependencies=[Depends(admin_auth)])
def whatsapp_logout():
    return _whatsapp_bridge_request("POST", "/logout")


@app.post("/whatsapp/history/clear", dependencies=[Depends(admin_auth)])
def whatsapp_history_clear(req: WhatsAppClearHistoryRequest):
    payload = _model_to_dict(req)
    payload = {k: v for k, v in payload.items() if v is not None}
    return _whatsapp_bridge_request("POST", "/history/clear", payload)


# ---- Interview: public submission ----------------------------------------


@app.get("/interview/questionnaire")
def interview_questionnaire():
    qpath = WEB_DIR / "interview" / "questionnaire.json"
    if qpath.exists():
        try:
            return json.loads(qpath.read_text(encoding="utf-8"))
        except Exception as e:
            LOG.warning("bad questionnaire.json: %s", e)
    return {"questions": []}


@app.post("/interview/submit")
async def interview_submit(
    request: Request,
    name: str = Form(...),
    office: str = Form(...),
    question_ids: list[str] = Form(default=[]),
    audio_files: list[UploadFile] = File(default=[]),
    photo_files: list[UploadFile] = File(default=[]),
):
    ip = request.client.host if request.client else "unknown"
    _rate_check(ip)
    _ensure_interview_dirs()

    name = (name or "").strip()
    office = (office or "").strip()
    if not name or not office:
        raise HTTPException(400, "name and office are required")
    if len(name) > 200 or len(office) > 200:
        raise HTTPException(400, "name or office too long (max 200 chars)")
    if not audio_files:
        raise HTTPException(400, "no audio files submitted")
    if len(audio_files) != len(question_ids):
        raise HTTPException(400, "audio_files and question_ids count mismatch")
    if len(audio_files) > MAX_AUDIO_FILES:
        raise HTTPException(400, f"too many audio files (max {MAX_AUDIO_FILES})")
    if len(photo_files) > MAX_PHOTO_FILES:
        raise HTTPException(400, f"too many photos (max {MAX_PHOTO_FILES})")

    submission_id = uuid.uuid4().hex[:12]
    sub_dir = INTERVIEW_PENDING / submission_id
    audio_dir = sub_dir / "audio"
    photo_dir = sub_dir / "photos"
    audio_dir.mkdir(parents=True)
    photo_dir.mkdir(parents=True)

    audio_records: list[dict] = []
    try:
        for upload, qid in zip(audio_files, question_ids):
            qid = (qid or "").strip()
            if not _QID_RE.match(qid):
                raise HTTPException(400, f"invalid question_id: {qid}")
            content = await upload.read()
            if len(content) > MAX_AUDIO_FILE_BYTES:
                raise HTTPException(400, f"audio too large for {qid} ({len(content)} bytes)")
            if len(content) == 0:
                continue
            ext = (Path(upload.filename or "").suffix or ".webm").lower()
            if ext not in _AUDIO_EXTS:
                ext = ".webm"
            path = audio_dir / f"{qid}{ext}"
            path.write_bytes(content)
            audio_records.append({"question_id": qid, "filename": path.name, "bytes": len(content)})

        if not audio_records:
            raise HTTPException(400, "all audio files were empty")

        photo_records: list[dict] = []
        for i, upload in enumerate(photo_files):
            content = await upload.read()
            if len(content) == 0:
                continue
            if len(content) > MAX_PHOTO_FILE_BYTES:
                continue
            ext = (Path(upload.filename or "").suffix or ".jpg").lower()
            if ext not in _PHOTO_EXTS:
                ext = ".jpg"
            path = photo_dir / f"photo_{i:02d}{ext}"
            path.write_bytes(content)
            photo_records.append({"filename": path.name, "bytes": len(content)})
    except Exception:
        shutil.rmtree(sub_dir, ignore_errors=True)
        raise

    metadata = {
        "id": submission_id,
        "name": name,
        "office": office,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "ip": ip,
        "user_agent": request.headers.get("user-agent", "")[:500],
        "status": "pending",
        "audio": audio_records,
        "photos": photo_records,
    }
    (sub_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    _rate_record(ip)
    LOG.info(
        "interview submission accepted: id=%s name=%s office=%s audio=%d photos=%d ip=%s",
        submission_id, name, office, len(audio_records), len(photo_records), ip,
    )
    return {
        "id": submission_id,
        "status": "pending",
        "audio_count": len(audio_records),
        "photo_count": len(photo_records),
    }


# ---- Admin: list / detail / serve / approve / reject --------------------


@app.get("/admin/submissions", dependencies=[Depends(admin_auth)])
def admin_list():
    items: list[dict] = []
    items.extend(_list_submissions_in(INTERVIEW_PENDING, "pending"))
    items.extend(_list_submissions_in(INTERVIEW_APPROVED, "approved"))
    items.extend(_list_submissions_in(INTERVIEW_REJECTED, "rejected"))
    items.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)
    return {"submissions": items}


@app.get("/admin/submission/{sid}", dependencies=[Depends(admin_auth)])
def admin_submission_detail(sid: str):
    if not _SUBMISSION_ID_RE.match(sid):
        raise HTTPException(404)
    sub_dir, status = _find_submission_dir(sid)
    meta = json.loads((sub_dir / "metadata.json").read_text(encoding="utf-8"))
    meta["status"] = status
    transcripts_path = sub_dir / "transcripts.json"
    if transcripts_path.exists():
        meta["transcripts"] = json.loads(transcripts_path.read_text(encoding="utf-8"))
    return meta


@app.get("/admin/audio/{sid}/{filename}", dependencies=[Depends(admin_auth)])
def admin_audio(sid: str, filename: str):
    if not _SUBMISSION_ID_RE.match(sid) or not _FILENAME_RE.match(filename):
        raise HTTPException(404)
    sub_dir, _ = _find_submission_dir(sid)
    path = _safe_subpath(sub_dir / "audio", filename)
    if not path.exists() or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/admin/photo/{sid}/{filename}", dependencies=[Depends(admin_auth)])
def admin_photo(sid: str, filename: str):
    if not _SUBMISSION_ID_RE.match(sid) or not _FILENAME_RE.match(filename):
        raise HTTPException(404)
    sub_dir, _ = _find_submission_dir(sid)
    path = _safe_subpath(sub_dir / "photos", filename)
    if not path.exists() or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


@app.post("/admin/submission/{sid}/approve", dependencies=[Depends(admin_auth)])
def admin_approve(sid: str, request: Request):
    if not _SUBMISSION_ID_RE.match(sid):
        raise HTTPException(404)
    sub_dir, status = _find_submission_dir(sid)
    if status != "pending":
        raise HTTPException(409, f"submission already {status}")

    meta = json.loads((sub_dir / "metadata.json").read_text(encoding="utf-8"))

    transcripts: dict[str, str] = {}
    transcribe_errors: dict[str, str] = {}
    for rec in meta.get("audio", []):
        qid = rec["question_id"]
        ap = sub_dir / "audio" / rec["filename"]
        try:
            transcripts[qid] = transcribe_via_vertex(ap)
        except HTTPException as e:
            transcribe_errors[qid] = str(e.detail)
            transcripts[qid] = ""
        except Exception as e:
            LOG.exception("transcribe failed for %s/%s", sid, qid)
            transcribe_errors[qid] = repr(e)
            transcripts[qid] = ""

    (sub_dir / "transcripts.json").write_text(
        json.dumps(transcripts, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    qmap: dict[str, str] = {}
    qpath = WEB_DIR / "interview" / "questionnaire.json"
    if qpath.exists():
        try:
            for q in json.loads(qpath.read_text(encoding="utf-8")).get("questions", []):
                qmap[q.get("id", "")] = q.get("question", "")
        except Exception:
            pass

    # Write JSONL matching the schema TacitRetriever._load() expects.
    claims: list[dict] = []
    audio_by_qid = {r["question_id"]: r for r in meta.get("audio", [])}
    today = datetime.now(timezone.utc).date().isoformat()
    office_name = meta.get("office", "").strip()
    interviewee_name = meta.get("name", "").strip()
    for qid, text in transcripts.items():
        if not text.strip():
            continue
        rec = audio_by_qid.get(qid)
        audio_url = f"/admin/audio/{sid}/{rec['filename']}" if rec else ""
        claims.append({
            "id": f"tacit_submission_{sid}_{qid}",
            "office": {
                "name_en": office_name,
                "name_ne": "",
                "domain": "",
                "service_unit": "",
                "address": "",
            },
            "service": "interview_response",
            "service_aliases": [],
            "fact_type": "interview_response",
            "claim": text.strip(),
            "claim_lang": "auto",
            "confidence": "medium",
            "triangulation": {"supporting_interviews": [], "contradicting_interviews": []},
            "source": {
                "interview_id": sid,
                "interviewee_role": interviewee_name or "interviewee",
                "office_visit_date": today,
                "method": "interview_v1",
                "audio_url": audio_url,
                "question_id": qid,
                "question": qmap.get(qid, qid),
            },
            "validity": {"as_of": today, "expected_stale_after_days": 180, "last_verified": today},
            "tags": ["interview", qid],
            "anonymization": {"names_redacted": False, "redacted_spans": []},
        })

    tacit_dir = Path(TACIT_DIR).expanduser()
    out_dir = tacit_dir / "submissions"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sid}.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for c in claims:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    new_dir = INTERVIEW_APPROVED / sid
    sub_dir.rename(new_dir)
    meta["status"] = "approved"
    meta["approved_at"] = datetime.now(timezone.utc).isoformat()
    meta["transcribe_errors"] = transcribe_errors or None
    (new_dir / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    stats = reload_tacit_retriever(request.app)
    return {
        "status": "approved",
        "transcripts": transcripts,
        "claims": len(claims),
        "transcribe_errors": transcribe_errors,
        "tacit_after_reload": stats,
    }


@app.post("/admin/submission/{sid}/reject", dependencies=[Depends(admin_auth)])
def admin_reject(sid: str):
    if not _SUBMISSION_ID_RE.match(sid):
        raise HTTPException(404)
    sub_dir, status = _find_submission_dir(sid)
    if status != "pending":
        raise HTTPException(409, f"submission already {status}")
    new_dir = INTERVIEW_REJECTED / sid
    sub_dir.rename(new_dir)
    meta = json.loads((new_dir / "metadata.json").read_text(encoding="utf-8"))
    meta["status"] = "rejected"
    meta["rejected_at"] = datetime.now(timezone.utc).isoformat()
    (new_dir / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return {"status": "rejected"}


@app.post("/admin/tacit/reload", dependencies=[Depends(admin_auth)])
def admin_tacit_reload(request: Request):
    return reload_tacit_retriever(request.app)


# ---- Static + SPA fallback ----------------------------------------------
#
# WEB_DIR points at the Vite build output (frontend/dist/). The hashed JS/CSS
# bundles live under WEB_DIR/assets/, mounted directly. Everything else falls
# back to index.html so React Router handles client-side routing — including
# unknown paths, which the SPA renders as its own 404.

if (WEB_DIR / "assets").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(WEB_DIR / "assets")),
        name="assets",
    )


@app.get("/whatsapp", include_in_schema=False, dependencies=[Depends(admin_auth)])
def whatsapp_spa():
    index = WEB_DIR / "index.html"
    if not index.exists():
        raise HTTPException(503, "frontend not deployed (index.html missing)")
    return FileResponse(index, media_type="text/html")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    # First: real static files in dist/ (favicon, robots.txt, vite.svg etc).
    # Refuse path traversal.
    if full_path:
        candidate = (WEB_DIR / full_path).resolve()
        try:
            candidate.relative_to(WEB_DIR.resolve())
        except ValueError:
            raise HTTPException(404)
        if candidate.is_file():
            return FileResponse(candidate)
    # Otherwise serve the SPA shell. React Router takes it from here.
    index = WEB_DIR / "index.html"
    if not index.exists():
        raise HTTPException(503, "frontend not deployed (index.html missing)")
    return FileResponse(index, media_type="text/html")
