PreVillage started from a simple failure mode: the law is public, the form is public, and the office exists.
What is not public is the route through the office.



Government here have decided to go full e-governanace mode but the scope seems to be just to tick another checkmark without focus on UX at all
and scrutiny of such websites is not present at all. Yes, there are forms... but no, those forms don't work seamlessly.  You have to visit the office only to be told later what you did was wrong and you need to do it another way.

Following image encapsulates my pain point.
![The route through 4 office](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F6860066%2F33eb2f55cc3c2129e76a3432f2ee1cd5%2Fhidden_route_four_offices.png?generation=1779121995452927&alt=media)
*fig: a month, four offices, four forms and lots of hassle*

The route is held by middlemen, officers and people who had already failed once. For most part citizens are not just paying for the form. They are paying for the sequence: which office, which counter, which document gets rejected, which phone number still works, and if the form works or not. And when i ask people about this they really have normalized this. They say it's how things are here. But i don't like that answer so i built **PreVillage**

## What is it

SpeakGov(PreVillage) is a government-service navigator built for Nepal. Internet is full of buttons and forms which is not the correct UX for Nepal. This Agrarian economy exports not rice but it's labor. So in it's heart it's the migrants who power Nepal. And whatsapp is what their wives and parents use. Android and internet is almost everywhere in Nepal. So it makes sense to have a whatsapp centric navigator. You use your voice to converse with the bot.

![](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F6860066%2F602da32f36681e309cd19d3e10198ff7%2Fwhatsapp_annotated_followup_flow.jpg?generation=1779122298973431&alt=media)
*fig: whatsapp flow*

The first output is not an answer; it is a resolved service frame: user intent, office and it's jurisdiction, document, situation, language, and the source type that should be trusted for that question. And i really feel that mostly right system do more harm than good because wrong answers have real consequences. I don't want someone waiting for 3 hours in line because of this system.

## Architecture

![What speakgov is about](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F6860066%2F24ce2ec510822c39acfb8c4f9b882663%2Fspeakgov_architecture_tldraw_board_2560x1440.png?generation=1779122205308830&alt=media)
*fig: RAG architecture*

The core pipeline is resolver-first RAG.
People can use
- kiosk
- whatsapp voice
- webchat

and it all passes through same server boundary. There is a planner phase which needs to fix : ASR word errors, map out questions (maybe contact questions, eligilibily qn, form filling question etc). After that source router decides retrieves from FTS5 retrieval index and decides which domain to route to. For example: A "where do I go" question prefers local office routing and practical counter notes whereas a fee, form, or date question prefers dated official pages.

we now need to talk about
- corpus
- what self healing and self learning means

### Corpus

The current corpus is maintained as infrastructure, not as a pile of files. We started from the [digobikas website](http://digobikas.gov.np/2019-08-21-05-14-56) which has list of all the gov websites in nepal then we crawled all the public facing documents. Mostly website content and pdfs... The latest hardening snapshot has 1,071 sources, 46,051 live documents, and 272,718 searchable chunks. The crawler/source registry handles official pages, PDFs, duplicate URLs, stale pages, dead pages, zero-text documents etc..
The messy details were the work: broken government sites, old PDF encodings, scanned notices, pages that fetched but produced no chunks, and duplicated documents that looked like coverage but gave the same answer repeatedly.

### Self Healing capacity

"Self-healing" is the **"evidence-path repair"**. If the system finds that a source is missing, not searchable, stale, weakly ranked, or only practically knowable, that gap becomes crawl, parsing, review, or interview work. Official websites give the legal facts. Named, reviewed officers, staff, and citizens who completed the process give practical facts. The answer should say what is known, what is uncertain, who to contact, and which source supports the claim.

| | |
|--------|-------|
|![self healing path](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F6860066%2F4047c2fb87b5199dccf64c8aab07081c%2Fself_healing_evidence_repair_board_2560x1440.png?generation=1779124494150051&alt=media)|![whatsapp loop](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F6860066%2F8efbf8d97784a305ce2951938e91512f%2Fwhatsapp_self_heal_flow.png?generation=1779124571782668&alt=media)|
|*fig: self healing path*|*fig: whatsapp automated messages for tacit knowledge capture*|

## Why Gemma matters

Gemma matters because government facts should not be memorized into weights.  Contacts, fees, office holders, and URLs change. They must come from retrieval, structured source packs, or deterministic extraction. In PreVillage, Gemma is used where an open model is actually useful: repairing noisy Nepali and Roman-Nepali input, planning the service case, preserving the user's language, asking follow-up questions, and composing from provided evidence. This also makes local deployment realistic. The heavy work can build the knowledge base, while the office can run the intake and answer layer.

## The finetuning


### CPT(Continous pre training)

![CPT](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F6860066%2Fd5beca87d3323f0ea6d6be0d86611a2f%2Fimage-5.png?generation=1779123103071079&alt=media)
*fig: CPT behavior*


I learnt the model lesson the hard way.  First i got some corpus from already scraped pdfs, and websites which were in Pure nepali then mixed with some english corpus. 80% of them was Nepali and 20% was English. Then ran CPT on an instruction-tuned model but it damaged the chat behavior: more Nepali tokens did not magically become a public-service helpdesk. i carefully chose some bechmarks and this is how the first finetune performed

![CPT Table](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F6860066%2Ff7570f92ea0784180ae288e2ed7d6c29%2Fimage-3.png?generation=1779123109871474&alt=media)
*fig: CPT benchmarks*

---------------------

### SFT Path

For v2, SFT used 11,896 supervised records built from the signals we actually expected users to produce like Reddit `r/Nepal` questions and answers with help tag, Hello
Sarkar complaints,  government-source snippets, and DeepSeek V4 synthetic supervision. The goal was not just Nepali fluency. It was to teach the model to answer citizen-service questions, refuse unsupported claims, and survive Roman-Nepali input.

I started with Gemma 4 E2B-IT and trained with rsLoRA r64/alpha128 for 2 epochs on an L40S `g6e.xlarge` run. v2 fixed one visible product failure: Roman-Nepaliprompts stopped collapsing in the small degeneration test. Refusal behavior also improved, but it was still far from reliable. v3a expanded the mix to 13,763 records, but the result made the lesson clearer: adding more rows did not solve the problem. General capability regressed, eval fragility showed up, and the model was still being trained as if the task were “write an answer” rather than “navigate a service case.” E2B was useful only when constrained by the pipeline, not as a standalone public chatbot.

![SFT Image](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F6860066%2F0e5bbe6802113af704c0efdb4dab20fc%2Fimage-4.png?generation=1779122941751286&alt=media)
fig: SFT path

For v5, we moved to Gemma 4 E4B and the training run looked successful on paper. Validation loss dropped sharply, but the product failed. The checkpoint invented
a phone number, answered ambiguous citizenship questions with generic checklists, misrouted manpower-agency complaints, and failed direct contact questions that
should have come from sources. We did not deploy it. The mistake was treating SFT as government-answer memorization instead of training the model to ask, route,
check answerability, and compose from retrieved sources.

The useful SFT direction was v6: planner/composer behavior over provided source packs. A source pack is the set of retrieved snippets shown to the model as
`[S1]`, `[S2]`, and so on. The planner decides what the user is asking, what office or source class is relevant, whether a follow-up is needed, and whether the
provided sources are enough. The composer then writes the final answer using only those sources.

v6.0 and v6.1 were tiny pilots. v6.2 improved the citation contract so the model used source IDs instead of raw URLs or fake numeric citations. v6.3 looked good
on URL recall, but failed the product: 79.2% wrong refusals and 10/10 Roman-Nepali loops. A wrong refusal means the source pack actually contained enough
information, but the model still said it could not answer. v6.4 fixed the task design by splitting planner JSON, answerability JSON, and final composition. On
`quick48`, a fast 48-case source-backed gold eval plus judge and Roman-Nepali checks, it reached URL recall 0.94, wrong refusals 2/48, source-ID citations in
45/48 rows, and 0/10 Roman-Nepali degeneration, loops, or mojibake. That made it the first serious RAG-backed composer candidate. The caveat is important: it is
not a naked factual chatbot. It is useful behind resolver, retrieval, and source routing, which is exactly our use case.

![Full SFT table](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F6860066%2Fa51da98e1d515a2dd8e89f9235ae4eb6%2Fimage-7.png?generation=1779122972839936&alt=media)
*fig: table for the complete SFT run*

Evals became the product spec. A pass was no longer “the answer sounds fluent.” A pass meant the system did the job: ask for municipality when
location matters, avoid Hindi drift when the user uses Nepali or Roman-Nepali, cite `[S1]` source IDs instead of raw or invented URLs, route a manpower-agency
complaint to the right labor authority, answer contact questions from sources, and refuse only when the retrieved source pack truly does not support the
answer. The smoke set also included easy arithmetic, random hi hello questions because a public helpdesk should not panic at harmless out-of-domain questions. It should answer briefly or explain that it is primarily built for government-service navigation.

![Finetuned versions](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F6860066%2F53650faa67bb06eb8c23c632786eb514%2Fimage-6.png?generation=1779123001142984&alt=media)
*fig: different SFT finetuned versions and their progression*

The live product path was validated as a pipeline, not a model memory contest. The planner-first service pipeline passed 8/8, navigator smoke passed 7/7, and RAG
query audit passed 15/15 with one expected refusal, zero bad citations, zero loops, and zero slow-generation failures. That is the result that matters: resolver,
retrieval, source routing, contacts, compact follow-ups, language control, answerability checks, and refusal-tail guards working together. The user should not see
“I don’t know” because retrieval fetched the wrong page, Hindi because the model ignored language context, or a fake phone number because the model wanted to be
helpful.

## The voice aka TTS and ASR Training

Voice is part of UX. Along with web chat there is also a real Baileys WhatsApp
bridge, and a kiosk. The voice stack uses local ASR/TTS workers where
possible: speech becomes ASR text, Gemma repairs the noisy question, the
navigator resolves the case, RAG retrieves sources, and TTS speaks back a
compact answer.

### ASR
For the ASR work i used openSLR54 + other datasets fom internet to create around 509.54-hour training base and prepared a FastConformer ladder for finetuning.

https://huggingface.co/spaces/voidash/nepali-fastconformer-demo

### TTS
The TTS work includes Piper Plus base finetuned on around 3000+ utterances of my sisters along with openslr43 data. z

https://huggingface.co/spaces/ampixa/real-nepali-tts


![Kiosk mode](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F6860066%2F6601eca329f84e1ca7980f5f19a26b39%2Fkiosk_voice_mode.png?generation=1779123516057332&alt=media)
*fig: kiosk mode*

### Gemma on raspberry pi on llamma.cpp

Gemma also gives an edge lane. Quantized Gemma E2B through llama.cpp ran on a
Raspberry Pi 5, with short-prompt generation measured around 7.5 tokens/sec.
That does not mean the Pi runs the full national RAG, ASR, and TTS stack. It
means a local office can have an open model for intake and composition instead
of sending every interaction away. For government service, that distinction
matters: common questions can be handled close to the counter, while sensitive
or difficult cases can stay inside the office network.

![pi on ipad](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F6860066%2F4c3448fc5a4ab1dc8c34bc02506244a1%2Fpi_gemma_llamacpp_smoke.png?generation=1779123574188183&alt=media)
*fig: raspberry pi llama inference on ipad*

### The cost
The cost was real. For May 2026 month-to-date, project-attributable GPU-ish EC2 compute on AWS was $363.63. Taining EBS volumes add roughly $38.48. But what we have built doesn't require every office to own an L40s. The heavy training and crawling can be centralized; the office-facing helpdesk can run smaller open models and retrieved source packs.

## What is next

PreVillage is not finished. Coverage is uneven. Some offices have weak sites.  Some Nepali and Roman-Nepali questions still need better resolver normalization.  ASR still needs confirmation loops for names, wards, and municipalities. v6.4 needs more real pipeline testing before public composer exposure. But the architecture is now honest: resolver first, source packs second, Gemma composer last, and human-reviewed practical knowledge when websites are silent.

I used privilege to find the path. PreVillage exists so the next person does not need privilege to use their own government.
