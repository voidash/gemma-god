#!/usr/bin/env python3
"""Build deterministic Roman-Nepali no-chunk service Q&A for v4b.

Purpose: v4 regressed to 8/10 degeneration on short Roman-Nepali prompts such
as "passport renew garna kaha janu parcha?" The model has plenty of grounded
Roman-NE examples, but too little bare prompt -> stable Roman-NE answer signal.

This script intentionally avoids API generation. The slice is not meant to add
new facts; it teaches format, script, and concise procedural behavior for the
same no-source setup used by the Roman-NE degen eval.

Usage:
    python scripts/build_v4_roman_ne_open_qa.py \\
        --n 400 \\
        --out corpora/sft_v4_roman_ne_open_qa.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


TOPICS: list[dict] = [
    {
        "name": "citizenship_new",
        "questions": [
            "mero nagarikta banauna ko lagi kun office janu parcha?",
            "naya nagarikta banauna kaha jane?",
            "nagarikta card banauna k k chahinchha?",
            "nagarikta banaune process kasari suru garne?",
            "nagarikta ko lagi DAO janu parcha ki wada?",
            "first time nagarikta lina ke garne?",
            "nagarikta banauna document k k lagcha?",
            "nagarikta ko form bharera kaha bujhaune?",
        ],
        "answers": [
            "Nagarikta ko lagi suruma aafno wada bata sifaris ra chahine kagaj milayera jilla prashasan karyalaya ma janu parchha. Exact document list aafno ward/DAO ma confirm garnu.",
            "Yo kaam samanyata wada sifaris pachi District Administration Office bata process huncha. Janma darta, pariwaar ko nagarikta jasta kagaj lagna sakcha, tara final list office ma hernu.",
            "Pahila wada karyalaya ma bujhera sifaris linu, ani DAO ma application bujhaunu. Current form, fee, ra appointment ko kura official office bata confirm garnu.",
            "Nagarikta ko process local ward ko sifaris bata suru huncha. Tespachi aafno jilla prashasan karyalaya ma kagaj sahit janu.",
        ],
    },
    {
        "name": "passport_renewal",
        "questions": [
            "passport renew garna kaha janu parcha?",
            "passport renewal garna ke ke lagcha?",
            "mero passport expire bhayo, aba k garne?",
            "passport naya banauna online form pachi kaha jane?",
            "old passport renew garna DAO jane ki passport office?",
            "passport ko appointment liyepachi k garnu parcha?",
            "passport renewal process kasari huncha?",
            "emergency passport banauna kaha bujhne?",
        ],
        "answers": [
            "Passport renewal ya naya passport ko lagi official online form/appointment pachi application slip le dekhayeko passport office, DAO, wa Department of Passports ko counter ma janu parchha. Purano passport/identity document jasta kagaj tayar rakhnus.",
            "Pahila passport ko official online form bharne, appointment line, ani biometrics/document verification ko lagi tokiye ko office ma jane. Current fee, timing, ra eligibility official portal ma confirm garnu.",
            "Passport sambandhi process ma form, appointment, document verification, biometrics, ra collection/update ko step huna sakcha. Kun office jane bhanne kura appointment slip ra official notice ma hernu.",
            "Renewal, emergency, wa naya passport anusar required document, fee, ra time farak huna sakcha. Latest detail passport office/official portal bata confirm garnu.",
        ],
    },
    {
        "name": "company_registration",
        "questions": [
            "company registration kasari garne?",
            "naya company darta garna k k chaincha?",
            "company register garna online process cha?",
            "business company banauna kaha apply garne?",
            "company ko naam reserve kasari garne?",
            "private company registration ko step k ho?",
            "company darta garna kati document chahincha?",
            "company registration start garna kaha bata jane?",
        ],
        "answers": [
            "Company registration ko lagi pahila naam reserve garne, required documents tayar garne, ani official company registrar system/office ma application bujhaune. Exact forms ra fee official portal ma confirm garnu.",
            "Naya company darta garda proposed name, shareholder/director details, memorandum/articles jasta kagaj chahin sakcha. Current checklist Office of Company Registrar bata confirm garnu.",
            "Process dherai jaso online suru huncha, tara verification/document submission ko step huna sakcha. Official OCR portal ma account banayera latest instruction hernu.",
            "Company darta garna name approval pachi company registrar ko system ma details upload garnu parchha. Confusion bhaye OCR helpdesk ya professional advisor sanga bujhnu.",
        ],
    },
    {
        "name": "pan",
        "questions": [
            "PAN number kasari banaune?",
            "personal PAN lina ke garne?",
            "PAN card ko lagi online apply garna milcha?",
            "PAN banauna k k document chahinchha?",
            "tax office nagai PAN banauna milcha?",
            "PAN registration process ke ho?",
            "business ko PAN kasari line?",
            "PAN number lina kaha jane?",
        ],
        "answers": [
            "PAN ko lagi tax office ko official system bata application bharne ra identity/document details submit garne process huncha. Personal ra business PAN ko requirements farak huna sakcha.",
            "Personal PAN lina nagarikta/identity details sahit online form bharna parcha. Verification ko lagi tax office le bhane anusar follow garnu.",
            "Business PAN ko lagi business registration sambandhi kagaj pani chahin sakcha. Current checklist Inland Revenue ko official portal ya tax office ma confirm garnu.",
            "PAN number banauda form bharne, document upload/submit garne, ra verification pachi number issue huncha. Exact process office anusar update huna sakcha.",
        ],
    },
    {
        "name": "driving_license",
        "questions": [
            "driving license ko lagi k k chaine?",
            "license naya banauna kasari apply garne?",
            "driving license form bharera pachi k garne?",
            "license trial ko lagi kaha jane?",
            "bike license lina process ke ho?",
            "driving license renew garna k garnu parcha?",
            "license ko written test kasari huncha?",
            "smart license apply garna kaha bata suru garne?",
        ],
        "answers": [
            "Driving license ko kaam online application, document verification, medical/biometric, written test, trial, ra office verification jasta step ma huncha. Required documents, date, ra center transport office ko portal ma confirm garnu.",
            "License ko lagi identity document, photo/medical details, application slip, ra office le mageka kagaj tayar rakhnus. Naya, renewal, ra category anusar process farak huna sakcha.",
            "Form bhare pachi slip/appointment ma dekhayeko transport office wa test center ma follow-up garnu parchha. Written/trial date ra current rule official system ma hernu.",
            "Driving license sambandhi exact fee, trial date, ra document list update huna sakcha. Aafno transport office ko portal/notice herera process follow garnu.",
        ],
    },
    {
        "name": "vat_pan_difference",
        "questions": [
            "VAT ra PAN ma k farak cha?",
            "PAN bhaye VAT pani chahincha?",
            "business ko lagi PAN matra pugcha ki VAT?",
            "VAT registration kahile garna parcha?",
            "PAN ra VAT confuse bhayo, ke difference ho?",
            "small business lai VAT chaincha ki chaina?",
            "VAT number ra PAN number eutai ho?",
            "tax ko lagi PAN/VAT kasari chhutaune?",
        ],
        "answers": [
            "PAN tax identity number jasto ho; VAT chai value added tax collect/report garne registration ho. Sabai PAN holder lai VAT chahincha bhanne hudaina, threshold ra business type anusar confirm garnu.",
            "Business suru garda PAN darta basic tax identity ko lagi chahin sakcha. VAT registration chai turnover/service type anusar mandatory huna sakcha, so tax office ma current rule bujhnu.",
            "PAN ra VAT ko purpose farak cha. VAT chahincha ki chaina bhanne kura business ko prakriti, turnover, ra tax rule anusar decide huncha.",
            "Small business lai pani situation anusar VAT chahin sakcha. Exact threshold ra requirement Inland Revenue office/portal bata confirm garnu.",
        ],
    },
    {
        "name": "lost_certificate",
        "questions": [
            "nagarikta certificate hareyo, kaha janu parcha?",
            "nagarikta harayo bhane naya kasari line?",
            "lost citizenship certificate ko copy kasari paune?",
            "nagarikta duplicate banauna k k chaincha?",
            "certificate harayo bhane police report chahincha?",
            "purano nagarikta gumyo, aba k garne?",
            "nagarikta ko pratilipi lina kaha jane?",
            "lost certificate ko lagi application kaha bujhaune?",
        ],
        "answers": [
            "Nagarikta harayo bhane pratilipi/duplicate ko lagi aafno District Administration Office ma bujhnu. Wada sifaris, identity proof, ra loss report jasta kagaj chahin sakcha.",
            "Duplicate nagarikta ko process DAO bata huncha. Required documents district anusar confirm garera matra application bujhaunu.",
            "Pahila najik ko wada/DAO ma lost certificate ko procedure sodhnus. Police report ya sifaris chahincha ki chaina official office le confirm garcha.",
            "Pratilipi lina purano record verify garna parcha. Aafno nagarikta issue bhayeko district ko prashasan karyalaya ma samparka garnu.",
        ],
    },
    {
        "name": "land_revenue",
        "questions": [
            "jagga ko malpot kaha tirne?",
            "malpot tirna k k document chahinchha?",
            "jagga ko tax online tirna milcha?",
            "land revenue payment kasari garne?",
            "malpot baki cha ki chaina kasari herne?",
            "jagga ko kitta number bata malpot tirna milcha?",
            "malpot office ma ke liyera jane?",
            "jagga ko rasid harayo bhane k garne?",
        ],
        "answers": [
            "Jagga ko malpot sambandhit malpot/land revenue office wa available bhaye official online system bata tirne process huncha. Lalpurja, kitta details, owner identity, ra purano receipt tayar rakhnus.",
            "Malpot ko record herna wa tirna kitta number, owner details, ra jagga sambandhi kagaj chahin sakcha. Online facility district anusar farak hunchha, so office/portal ma confirm garnu.",
            "Malpot sambandhi payment, baki, receipt, wa duplicate ko lagi aafno malpot office ma record verify garna milcha. Exact requirement office le nai confirm garcha.",
            "Jagga tax/malpot ko amount ra deadline thau anusar farak huna sakcha. Current detail official portal ya malpot office bata hernu.",
        ],
    },
    {
        "name": "birth_registration",
        "questions": [
            "bachhako janmadarta kasari garne?",
            "birth certificate banauna kaha janu parcha?",
            "naya baby ko janma darta ko lagi k chaincha?",
            "janmadarta late bhayo bhane k garne?",
            "child birth registration ward bata huncha?",
            "janma darta online garna milcha?",
            "birth certificate copy kasari paune?",
            "janmadarta ko form kaha bujhaune?",
        ],
        "answers": [
            "Janma darta/certificate ko kaam samanyata aafno ward wa local registrar office bata huncha. Parents ko identity, hospital paper, family details, ra required form tayar rakhnus.",
            "Birth registration, late entry, wa certificate copy ko lagi record bhayeko ward/local registrar office ma bujhnu. Time limit, fee, ra document list local office le confirm garcha.",
            "Online facility bhaye pani verification ward/palika bata huna sakcha. Current process, copy, ra late registration rule aafno local office ma confirm garnu.",
            "Janmadarta sambandhi application ward karyalaya/local registrar ma bujhaune ho. Exact kagaj, fee, ra deadline palika anusar farak huna sakcha.",
        ],
    },
    {
        "name": "online_tax",
        "questions": [
            "online tax file kasari garne?",
            "tax return online submit garna ke garne?",
            "IRD ma online login kasari banaune?",
            "income tax return file garna kaha bata suru garne?",
            "business tax online tirna milcha?",
            "tax filing deadline confirm kaha garne?",
            "online tax payment ko receipt kasari paune?",
            "tax file garna PAN chahincha?",
        ],
        "answers": [
            "Online tax filing/payment ko lagi Inland Revenue ko official system ma login garera taxpayer details, PAN, return form, ra payment step follow garnu. Deadline ra current rule portal/tax office ma confirm garnu.",
            "Tax return submit garnu aghi income/sales records, PAN details, ra applicable form tayar rakhnus. Taxpayer type anusar process farak huna sakcha.",
            "Business tax, return filing, ra payment receipt ko step official tax portal bata huncha. Confusion bhaye najik ko tax office ya accountant sanga bujhnu.",
            "Online tax kaam garda submission proof/receipt save garnu. Exact deadline, payable amount, ra form latest notice anusar confirm garnu.",
        ],
    },
    {
        "name": "nid",
        "questions": [
            "NID banauna process k ho?",
            "national ID card ko lagi kaha jane?",
            "NID form bharera Singha Durbar jane ki DAO?",
            "NID appointment kasari line?",
            "national identity card banauna k k chaincha?",
            "NID biometric ko lagi kaha janu parcha?",
            "NID status kasari check garne?",
            "NID number lina first step ke ho?",
        ],
        "answers": [
            "NID ko lagi official system ma form/appointment bhare pachi tokiye ko enrollment center ya DAO ma biometric dinu parchha. Kun office jane bhanne appointment details ma confirm garnu.",
            "National ID banauda identity documents, personal details, ra biometric enrollment chahin sakcha. Current requirement official NID portal/office ma hernu.",
            "Singha Durbar direct jane ki DAO jane bhanne kura appointment/enrollment location le decide garcha. Form bhare pachi dekhayeko location follow garnu.",
            "Status check garna official NID portal ya sambandhit office ko channel use garnu. Exact timing office workload anusar farak huna sakcha.",
        ],
    },
    {
        "name": "marriage_registration",
        "questions": [
            "bibaha darta kasari garne?",
            "marriage registration ko lagi kaha janu parcha?",
            "bihe darta garna k k document chaincha?",
            "marriage certificate lina process ke ho?",
            "late marriage registration bhayo bhane k garne?",
            "bibaha darta ward bata huncha?",
            "marriage certificate ko copy kasari paune?",
            "bibaha darta ko form kaha bujhaune?",
        ],
        "answers": [
            "Bibaha darta/certificate ko kaam samanyata ward wa local registrar office bata huncha. Duwai jana ko identity, photo, witness/details, ra required form tayar rakhnus.",
            "Marriage registration, late entry, wa certificate copy ko lagi record bhayeko ward/palika ma application bujhaunu. Exact document list ra fee local office ma confirm garnu.",
            "Bibaha darta sambandhi process local registrar office le handle garcha. Time limit, copy, ra late registration requirement palika anusar farak huna sakcha.",
            "Marriage certificate ko lagi aafno ward/local registrar ma record verify garera apply garnu. Current form, fee, ra document checklist office bata confirm garnu.",
        ],
    },
    {
        "name": "death_registration",
        "questions": [
            "mrityu darta kasari garne?",
            "death certificate banauna kaha janu parcha?",
            "ghar ma mrityu bhayo bhane kati din bhitra darta garne?",
            "death registration ko lagi k k document chaincha?",
            "mrityu darta ward bata huncha?",
            "death certificate ko copy kasari paune?",
            "late death registration bhayo bhane k garne?",
            "mrityu darta ko form kaha bujhaune?",
        ],
        "answers": [
            "Mrityu darta/certificate ko kaam samanyata ward wa local registrar office bata huncha. Death confirmation, family identity, ra required details/document tayar rakhnus.",
            "Death registration, late entry, wa certificate copy ko lagi sambandhit ward/palika ma application bujhaunu. Time limit, fee, ra checklist local office ma confirm garnu.",
            "Mrityu darta sambandhi process local registrar office le handle garcha. Exact document, copy process, ra late registration rule palika anusar farak huna sakcha.",
            "Death certificate ko lagi record bhayeko ward/local registrar office ma verify garera apply garnu. Current form ra requirement office bata confirm garnu.",
        ],
    },
]


def build_records(n: int, seed: int) -> list[dict]:
    pool: list[dict] = []
    for topic in TOPICS:
        for q in topic["questions"]:
            for a in topic["answers"]:
                pool.append(
                    {
                        "question": q,
                        "answer": a,
                        "topic": topic["name"],
                    }
                )

    rng = random.Random(seed)
    rng.shuffle(pool)
    if n > len(pool):
        raise ValueError(f"requested {n} records but only {len(pool)} unique template pairs exist")

    out: list[dict] = []
    seen_q: set[str] = set()
    # Prefer question diversity first, then allow alternate answers only if
    # n exceeds the unique-question count.
    for item in pool:
        q_norm = item["question"].lower()
        if q_norm in seen_q:
            continue
        seen_q.add(q_norm)
        out.append(item)
        if len(out) >= n:
            break
    if len(out) < n:
        used_pairs = {(r["question"], r["answer"]) for r in out}
        for item in pool:
            key = (item["question"], item["answer"])
            if key in used_pairs:
                continue
            used_pairs.add(key)
            out.append(item)
            if len(out) >= n:
                break
    return [
        {
            "id": f"sft_v4_rn_open_{i:05d}",
            "source": "v4_roman_ne_open_qa",
            "question": item["question"],
            "question_lang": "roman_nepali",
            "category": "roman_ne_open_qa",
            "chunks": [],
            "answer": item["answer"],
            "skip": False,
            "skip_reason": None,
            "gold_chunk_id": None,
            "topic": item["topic"],
        }
        for i, item in enumerate(out, 1)
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--out", default="corpora/sft_v4_roman_ne_open_qa.jsonl")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    records = build_records(args.n, args.seed)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    by_topic: dict[str, int] = {}
    for r in records:
        by_topic[r["topic"]] = by_topic.get(r["topic"], 0) + 1
    print("\n=== build_v4_roman_ne_open_qa ===", file=sys.stderr)
    print(f"  records: {len(records)}", file=sys.stderr)
    print(f"  output : {out_path}", file=sys.stderr)
    print("  by topic:", file=sys.stderr)
    for topic, count in sorted(by_topic.items()):
        print(f"    {topic:<24s} {count}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
