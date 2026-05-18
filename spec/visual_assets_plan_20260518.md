# PreVillage Visual Assets Plan - 2026-05-18

## Existing Kiosk Footage

Use:

```text
footage/selects/govspeak-2/kiosk.mp4
analysis/gemini/govspeak-2/clip_md/kiosk.md
```

Gemini summary:

```text
A user demonstrates Nepali ASR on a tablet, with Raspberry Pi visible as part of local deployment.
```

Best beats:

```text
00:00-00:01   hand taps tablet
00:03-00:05   Nepali speech appears as live transcription
```

Use this for the 2:42-2:55 voice/kiosk section or the 2:55-3:00 local office helpdesk close. No in-person kiosk reaction footage is required for the current cut.

## New Graphics

Editable SVG + rendered PNG files:

```text
assets/graphics/previllage_evolution_v1_v6_1920x1080.svg
assets/graphics/previllage_evolution_v1_v6_1920x1080.png
assets/graphics/previllage_system_architecture_1920x1080.svg
assets/graphics/previllage_system_architecture_1920x1080.png
```

### Evolution Card

Use during the Gemma/SFT section, around 1:12-1:35 or as a very fast 3-4 second insert immediately after training footage.

Purpose:

```text
show that the team iterated honestly:
v1 grounded but too trusting
v2 refusal + Roman repair
v3 anti-template but regressions
v4 corpus discipline
v5 low loss, bad product, do not deploy
v6 planner/composer split
```

Voice line that matches:

```text
The win was not a magic adapter. The win was resolver, RAG, evals, and human review around Gemma.
```

Editing idea:

```text
Start on v5 red card for 0.5s.
Pull back to reveal v1-v6.
Land on v6 green card.
```

### System Architecture Diagram

Use during the RAG/human-loop section, around 1:35-2:42.

Purpose:

```text
make the whole system legible:
entry points -> ASR/fixer -> resolver/planner -> official RAG + practical sources -> Gemma composer -> human loop -> folded-back source
```

Best edit pattern:

```text
1. Full diagram for 0.5s.
2. Push into entry points while saying "A citizen speaks..."
3. Pan to resolver while saying "first job is to understand the case."
4. Pan to official RAG + practical sources while saying "official websites give the law; interviews give the route."
5. Pan to human loop while saying "when PreVillage does not know, it asks the right officer."
6. End on bottom line: "A small local model runs the helpdesk onsite."
```

## Current Missing Visual

The only missing optional visual is a compact animated version of the architecture diagram. The static SVG already supports the edit, but a build-on animation would make it stronger.
