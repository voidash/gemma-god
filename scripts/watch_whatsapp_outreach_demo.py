#!/usr/bin/env python3
import json
import os
import sys
import time


def contact_label(contact):
    contact = contact or {}
    role = str(contact.get("role") or "").strip()
    phone = str(contact.get("phone") or contact.get("whatsapp_to") or "").strip()
    source = str(contact.get("source_host") or "").strip()
    parts = [part for part in [role, phone, source] if part]
    return " | ".join(parts) or "official contact"


def print_event(event):
    kind = event.get("kind") or "event"
    ts = event.get("at") or ""
    remote = event.get("remoteJid") or ""
    question = str(event.get("question") or "").strip()

    if kind == "incoming":
        text = str(event.get("text") or question).strip()
        print(f"\n[{ts}] INCOMING from {remote}")
        print(f"> {text}")
    elif kind == "decision":
        decision = event.get("decision") or {}
        status = "ROUTE" if decision.get("ok") else "SKIP"
        print(f"[{ts}] {status}: {decision.get('reason') or 'no reason'}")
        if question:
            print(f"> {question}")
    elif kind == "draft":
        print(f"[{ts}] DRAFT {event.get('outreachId') or ''}")
        print(f"to: {contact_label(event.get('contact'))}")
        preview = str(event.get("messagePreview") or "").strip()
        if preview:
            print(preview)
    elif kind == "sent":
        print(f"[{ts}] SENT {event.get('outreachId') or ''}")
        print(f"to: {contact_label(event.get('contact'))}")
    elif kind == "error":
        print(f"[{ts}] ERROR: {event.get('error') or 'unknown error'}")
        if question:
            print(f"> {question}")
    else:
        print(f"[{ts}] {kind}: {json.dumps(event, ensure_ascii=False)}")
    sys.stdout.flush()


def follow(path):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    open(path, "a", encoding="utf-8").close()
    with open(path, "r", encoding="utf-8") as handle:
        handle.seek(0, os.SEEK_END)
        while True:
            line = handle.readline()
            if not line:
                time.sleep(0.2)
                continue
            try:
                print_event(json.loads(line))
            except Exception as exc:
                print(f"[parse-error] {exc}: {line.strip()}")
                sys.stdout.flush()


if __name__ == "__main__":
    log_path = sys.argv[1] if len(sys.argv) > 1 else "/Volumes/T9/gemma-god/logs/whatsapp-outreach-demo.jsonl"
    print("SpeakGov WhatsApp proactive outreach demo", flush=True)
    print("Waiting for incoming WhatsApp prompts...\n", flush=True)
    follow(log_path)
