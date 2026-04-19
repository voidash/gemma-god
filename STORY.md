# gemma-god — the story, told plainly

A plain-English account of what we've been building. Written so a curious
10-year-old could follow. The technical engineering log is in `DOCUMENT.md`;
this file is the story.

---

## What we're trying to do

In Nepal, when a regular person needs to do something with the government —
register a company, get a passport, pay a tax, replace a lost citizenship
certificate — they often don't know which office to go to or what papers to
bring. The information exists, but it's scattered across dozens of government
websites (many of which are broken), hidden inside PDFs that computers can't
even read, or simply passed around by word of mouth.

This creates a problem: people end up paying middlemen hundreds or thousands
of rupees just to learn what *should* be public information. The guy who
started this project lost about 7 000 rupees and three weeks to middlemen
during company and PAN registration because nobody had written the actual
steps down anywhere a normal person could find them.

So we're building an **engine that reads all those government websites and
PDFs, understands Nepali questions (even when people type them badly or in
English-Nepali mix), and gives answers with proof** — a direct link to the
page of the PDF where the answer came from. That way, you don't just trust
the engine; you can double-check it yourself.

---

## Little dictionary (read this first)

Anything you don't recognize later, look it up here.

| Word | What it means |
|---|---|
| **Model** (or LLM) | A computer program that has read a lot of text and learned to write like a human. "Gemma 3 4B" is the specific model Google made that we're using. The "4B" means it has about 4 billion knobs inside it that were set during training. |
| **Token** | A small piece of text. Roughly a word or a word-fragment. 42 million tokens is about the size of 30 novels. |
| **Corpus** | A huge pile of text used to teach a model. Like a library you feed to the computer. |
| **Training** (or fine-tuning) | Showing the model lots of examples so it gets better at a task. During training, those billion+ knobs inside the model shift a little bit in response to every example. |
| **CPT (Continued Pre-Training)** | Training where you just show the model lots of regular text — no questions, no answers, no tasks. The model just learns "this is what the language sounds like." Goal: make the model write Nepali more naturally. |
| **SFT (Supervised Fine-Tuning)** | Training where you show the model specific question-and-answer examples. Goal: teach the model HOW to respond — to answer questions, refuse rudely-posed ones, ask clarifying questions when unclear. |
| **LoRA** | A clever trick. Instead of changing all 4 billion knobs during training (slow, memory-hungry), you stick a small add-on module on the side (a few million extra knobs) and only change those. Result is almost as good as changing everything, but uses 1/100th the resources. |
| **Baseline** | A "before" measurement. You test the model, write down its score, then try to improve it and measure again. If the score goes up, your work helped. |
| **Benchmark** | A standardized test. We use benchmarks like "Belebele" (900 reading-comprehension questions in Nepali) to measure the model. If a random monkey would get 25% on a four-choice test, and our model gets 63%, that's a real signal. |
| **Devanagari** | The Nepali alphabet: क, ख, ग, घ, and so on. Same script Hindi uses. |
| **Preeti** | An OLD way Nepal's computers used to store Nepali text, before Unicode (the modern standard). Preeti text LOOKS like random English letters — `g]kfn` — but when displayed with a special font, it shows as Nepali letters. A lot of older Nepali government PDFs were made with Preeti, so the text inside is encoded like this. If we want to read those PDFs, we have to convert Preeti → Unicode first. |
| **OCR** | "Optical Character Recognition." When a document is a SCANNED IMAGE (not real text), a computer needs OCR to read the pixels and guess what letters they represent. Many gov PDFs are literally photos of paper, so we need OCR to get at the text. |
| **Romanized Nepali** | Writing Nepali words using English letters. "नमस्ते" → "namaste". This is what most young Nepalis actually type on their phones because Devanagari keyboards are a pain. Our engine needs to understand this too. |
| **Code-mixed** | Mixing languages in one sentence. "Yes ma, yo kitab dherai ramro cha" (mixing English + Nepali). Very common on Nepali social media. |
| **Retrieval / RAG** | "Retrieval-Augmented Generation." Instead of the model trying to remember everything, we give it a search engine. When someone asks a question, we first search for relevant documents, hand those to the model, and then the model answers using what it found. Better citations, fewer made-up answers. |
| **Checkpoint** | A snapshot of the model during training, saved to disk. Like saving your video game. If something goes wrong, you can reload from a checkpoint instead of starting over. |
| **Fast-eval** | A quick version of the benchmark tests. Runs in ~10 minutes instead of 2 hours. Useful for "is this checkpoint getting better or worse?" without waiting forever. |
| **Chat template** | The specific way you wrap a question before sending it to an instruction-tuned model. Something like `<start_of_turn>user\nyour question\n<end_of_turn>`. Models trained to be chat assistants expect this format; models that weren't, don't. |
| **Catastrophic forgetting** | When a model that was good at one thing learns something new and FORGETS the original thing. Like teaching someone French so hard that they forget how to speak English. A real risk in our kind of training. |
| **k2** | The nickname for the beefy Mac Studio computer where all the heavy model-training runs. Has a powerful chip called "M2 Ultra" and 64 GB of memory. Connected over Tailscale (a secure network tunnel) so we can run stuff on it from anywhere. |
| **T9** | The nickname for the 2 TB external hard drive attached to k2. Where we keep all the downloaded models, data, and training outputs. |
| **GPL-3.0** | A type of open-source license. Says: anyone can use and modify this code, but they have to share any changes they publish. Chosen because one important piece of code we use (the Preeti-to-Unicode converter) is GPL-3.0, and that choice propagates. |

---

## The story, in order

### Day 1 morning — "What's even on the Nepal gov websites?"

We started by poking at 15 major Nepal government websites. Immediately hit
surprises:

- **4 of them had broken security certificates.** A browser would show a
  scary warning; our code has to know how to ignore these. About 27% of
  Nepal's gov sites have broken TLS.
- **`nepal.gov.np`** — the national portal itself — was flat-out dead.
  Ironic.
- **Most gov PDFs live on one shared server**: `giwmscdnone.gov.np/media/…`.
  If you crawl that one server you get many ministries' documents at once.

We downloaded 10 sample PDFs and opened them up. Four of them looked like
gibberish — `cfly{s jif{ @)*@÷*#` — because they were **Preeti-encoded**.
Including *the central bank's current monetary policy*, which is the Nepali
equivalent of the Fed's financial rule-book. The bank is publishing it in a
40-year-old encoding that modern computers can't read out-of-the-box.

### Day 1 afternoon — "Teach the computer to tell what kind of PDF this is"

For every PDF we find, we need to know: is it normal Unicode text? Is it
Preeti-encoded (needs conversion)? Is it a scanned image (needs OCR)? Is it
just English? Is it mixed?

We wrote a **classifier in Rust** that looks at every PDF and puts it into
one of seven bins:
- **A** — normal Nepali text (Unicode, good)
- **BPreeti** — old Preeti encoding, needs conversion
- **BLegacyUnknown** — some other weird legacy encoding we haven't mapped
- **C** — scanned image, needs OCR
- **E** — English-only (we skip for Nepali purposes)
- **Mixed** — part Preeti, part Unicode (hardest case)
- **XInvalid** — not actually a PDF (sometimes servers return an error page pretending to be a PDF)

The classifier has to be careful. We got it wrong twice: once it marked
Nepal Building Code English docs as "Preeti" because they had lots of `{`
and `[` characters in technical tables. We fixed that by requiring the
Preeti-style signals to really add up before calling a doc Preeti.

### Day 1 evening — "Make Preeti readable"

We ported a Preeti → Unicode converter from an existing open-source Python
library into Rust. The basic idea: each English letter maps to a specific
Nepali character. `g` becomes `न`, `]` becomes `े`, and so on. Plus a few
regex-based cleanup rules to handle the order consonants and vowels go in.

This converter unlocks about 16% of our corpus that was previously
unreadable. Validated on 13 real PDFs — every one came out as legible
Nepali afterward.

Special care needed for **mixed documents** (some Preeti + some English +
some Unicode all in the same PDF). The naive approach — running Preeti
conversion on the whole thing — corrupts the English. We wrote a token-level
converter: look at each word, decide whether it's Preeti or English, convert
only what needs converting.

### Day 1 night — "OCR for the scanned documents"

Some government docs are literal photos. A clerk scanned a paper form on a
Canon scanner and uploaded the result. The "PDF" has no text inside, just
pixels.

Installed **Tesseract** (an open-source OCR engine) plus the Nepali language
pack. Ran it against our 5 scanned documents. 9 minutes of compute, out
came 65 000+ Devanagari characters of readable text. Not perfect — some
ornate headers got misrecognized — but the core content is usable.

Examples recovered:
- A district court notice to the Office of Company Registrar about an auction
- A Ministry of Home Affairs annual report
- Small notices and forms

### Day 2 morning — "Also, let's be able to find new PDFs"

Wrote a **crawler** that visits gov websites and collects any `.pdf` links
it sees. Uses curl (with `-k` to ignore broken certificates), extracts
links with a regular expression, and handles both relative and absolute
URLs. Ran it against 22 known index pages (notices, publications, acts).

Result: **65 new gov PDFs discovered** (mostly from SEBON — the securities
board — and the Nepal Law Commission).

Also double-checked some of our earlier URLs are still alive. 3 of them had
already 404'd (disappeared) — which hints at about a 21% "link rot" rate
across gov websites within a few weeks.

### Day 2 afternoon — "A tiny search engine"

At this point we had maybe 100 PDFs, some converted, some OCR'd. We used a
classic search-ranking algorithm called **BM25** to build an index over
all the text.

Now you can type a query and get relevant chunks back with source URLs:
- Ask `"company registration"` → get the Office of Company Registrar's
  official manual, with a link
- Ask `"आर्थिक वर्ष"` (Nepali: "fiscal year") → get the central bank's
  monetary policy document with a link
- Ask `"PAN tax"` → get the securities board's policy on mandatory PAN
  for large transactions

This is a kind of primitive search engine — NOT smart, but it works.

### Day 2 late night — "Wait, what exactly are we building?"

Had a conversation about scope. This was supposed to be a hackathon project,
but the person building it has about a month. What should the engine actually
do?

Four decisions made:

1. **Page-level citations.** Every answer points to the exact page of the
   PDF where the answer came from. Users can double-check.
2. **Ask clarifying questions.** If someone types "malai nagarikta kaha...?"
   (vague: "where do I... citizenship?"), the engine should ask back:
   "do you want a new citizenship, or replace a lost one?" rather than
   guessing.
3. **Reach out when stuck.** If the engine genuinely doesn't have info,
   it should be able to dispatch a helper agent that actually WhatsApps or
   emails the relevant government office to ask. (Not immediately — only
   after a human reviews each such outreach.)
4. **Nepali keyboard reality.** A lot of Nepalis type "mero nagarikta
   banauna…" (Romanized) not "मेरो नागरिकता बनाउन…" (Devanagari), or they
   mix both with English. The engine must understand all three.

### Day 2 — Testing Gemma 3 4B on Nepali

Before trying to improve the model, we needed to know how good it is
already. Ran three benchmarks:

- **Belebele** (reading comprehension, 200 multiple-choice Nepali questions)
  → Gemma 3 got **63%**. Random guessing would be 25%. So the model does
  "understand" Nepali reasonably well.
- **FLORES** (translation, 100 sentences each direction)
  → Nepali-to-English: **55.9 chrF++** (decent).
  → English-to-Nepali: **38.2 chrF++** (weak — real translation models hit 50+).
- **Write Nepali from scratch** (we asked a few simple questions and graded)
  → Failed hard. Asked "What's the capital of Nepal?" and it spelled
  Kathmandu as `काठोका` instead of `काठमाडौं`. On Romanized Nepali questions,
  it collapsed into repetition loops or randomly switched to Indonesian.

Clear picture: **Gemma 3 can READ Nepali but can't WRITE it well**. The
thing we need to fix is Nepali generation, not Nepali understanding.

### Day 3 — "Let's teach it Nepali"

Built the training corpus (about 42 million tokens). Pieces:

- Old /r/Nepal Reddit archive (10 years of real user content, real Roman-
  Nepali)
- Nepali Wikipedia (formal encyclopedic Nepali)
- Our scraped+converted gov documents
- Saugatkafley/alpaca-nepali-sft (a ready-made Nepali instruction dataset)
- English replay (so the model doesn't FORGET English during training)

Tried training on k2. Two configuration mistakes cost us time:

1. Tried batch size 8 — slower, not faster. The memory-saving trick called
   grad_checkpoint has overhead that doubles with batch size. Back to batch 4.
2. Tried removing grad_checkpoint — memory jumped from 26 GB to 57 GB, MLX
   (the training engine) got confused with memory pressure, tokens/sec
   dropped by half. Back to original config.

**Settled on**: batch 4, grad_checkpoint on, rank-16 LoRA, 10 000 iterations.
Ran overnight. About 7 hours wall time, 7.6 million tokens processed (which
is actually less than a full pass through our corpus — we only got through
~20% of it once).

### Day 3 morning — "Oh no"

Tested the trained model. **Every benchmark went DOWN.**

- Belebele: 63% → **52%**
- FLORES English-to-Nepali: 38.2 → **33.5**
- Roman-Nepali: went from ~25% broken to ~30% broken

The model literally lost the ability to answer questions. When asked a
Roman-Nepali question, it just echoes the question back over and over:

> Q: mero nagarikta banauna ko lagi kun office janu parcha?
> A: Mero nagarikta banauna ko lagi kun office janu parcha?
>    Mero nagarikta banauna ko lagi kun office janu parcha?
>    Mero nagarikta banauna ko lagi kun office janu parcha? [...]

### Why it failed — the diagnosis

We trained on an "instruction-tuned" model (`gemma-3-4b-it-bf16`). An
instruction-tuned model has been SPECIFICALLY taught to follow a chat
format, answer questions, etc.

When we showed it 42 million tokens of raw Nepali text (Reddit posts,
Wikipedia articles, government documents) during CPT, it learned the Nepali
language modelling distribution. But it also **forgot how to respond to
chat-format questions**. Only 9.5% of our training data had instruction
format; the rest was raw text. The raw-text training swamped the chat signal.

This is a textbook failure mode in the ML literature (a paper from late
2024 reported the same effect: continued-pretraining Llama 3 on Nepali
dropped MMLU — a knowledge test — from 61% to 35%). We should have caught
it before running.

### Where we are right now (Day 3 afternoon)

**Plan B**: start from the PRETRAINED (non-instruction-tuned) Gemma 3 4B,
which doesn't have instruction behavior to trample. Then CPT on it. Then SFT
with instruction data on top to RESTORE chat behavior — but this time
properly, as a separate stage.

- Step 1: Download `mlx-community/gemma-3-4b-pt-bf16` (the pretrained variant).
- Step 2: Baseline the PT model on our benchmarks (the numbers will look
  different from the IT baseline).
- Step 3: CPT from PT, same config as before (7 hours on k2).
- Step 4: SFT with Alpaca-NE + any chat-format data we generate.
- Step 5: Eval the combined result.

Total time budget: ~11 hours. Next overnight run.

### What's in the repo

The code is at https://github.com/voidash/gemma-god. It's about:

- 600 lines of Rust for classifying / converting / OCR / crawling / searching
  gov PDFs
- 1 500 lines of Python scripts for corpus assembly, training, and evaluation
- A chunk of mapping data (GPL-3.0) that knows how Preeti → Unicode works
- Documentation — this file, `PLAN.md` for the future plan, and `DOCUMENT.md`
  for the engineering log

### What worked, what didn't

**Worked:**
- Rust corpus pipeline — fast, tolerates broken gov servers, classifies
  accurately
- Preeti converter — unlocks 16% of content that's otherwise unreadable
- OCR — scanned PDFs now yield usable Nepali text
- Fetching + crawling gov sites — found 65 new PDFs, flagged 3 dead URLs
- BM25 retrieval — sub-second search over 46 000 chunks with real citations
- The Reddit pipeline — 100 000 real user Nepali/Roman/code-mixed records

**Didn't work (yet):**
- CPT on instruction-tuned base — regressed the model. Redoing on the
  pretrained base.
- IndicXlit (synthetic Roman-Nepali generator) — Python dependency hell.
  Abandoned; natural Reddit Roman-Nepali is better anyway.

**Learned the hard way:**
- Shell quoting with nested SSH and Python f-strings and escape sequences
  is a recurring pain. Use `scp` + Python script files instead of inline
  heredocs.
- Don't confuse IT (instruction-tuned) vs PT (pretrained) base models when
  doing CPT. Matters a lot.
- Double-check data classifiers before running at scale. Short substring
  matches on Nepali marker words false-positive on common English words.
  Use word boundaries.
- Hugging Face gated datasets: the `datasets` library doesn't honor the
  `HF_TOKEN` env variable reliably for gate checks. Bypass with
  `hf_hub_download` directly.

### How a regular person would use this, eventually

The plan is a website (or WhatsApp/Viber bot) where:

1. You type your question in Nepali, Romanized Nepali, English, or any mix.
2. The engine asks a clarifying question if it's vague.
3. It searches the government document corpus + pings the right model.
4. It gives you the answer in Nepali with:
   - The specific ministry/department
   - Exactly which page of which PDF the answer came from (link included
     with `#page=N` jump)
   - A confidence level ("high" / "medium" / "low")
   - A freshness warning if the source is more than a year old
   - A phone number to call to verify
5. If the engine really doesn't know, it says so, tells you which office to
   ask, and logs the question so we can add that info to the knowledge base.

Goal: zero rupees to middlemen. Verify everything.
