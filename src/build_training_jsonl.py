"""build_training_jsonl.py — TASK 3 / G1: the merged per-token training records.

WHAT THIS IS
    One JSONL record per token, carrying a TARGET and a MASK for every head in
    SPEC-REV6 §4.  `data/out/` was empty; this is the file the Kaggle notebook
    uploads (COLAB.md §2). No schema was documented anywhere in the repo, so the
    one below is defined here and is the reference.

NON-LEAKAGE (SPEC-REV6 §3.1, enforced in code, not prose)
    TRAINING  : PADT only (this script). Tashkeela silver is a separate pass.
    HELD OUT  : NYUAD (Track 1, syntax/case) and QAC + EQTB (Track 2, classical
                morphology). Neither is written to any output here — QAC and EQTB
                are not even read. --assert-no-eval refuses to run if a held-out
                path is passed to --splits.
    Root supervision for PADT comes from PADT's own gold `Root=` column, filtered
    by `is_gold_root` (POS + radical count + translit); the reviser dictionary is
    for TASHKEELA, which has no gold. Never the other way round.

THE FIVE HEADS (SPEC-REV6 §4)
    Head 1  NTP            t_ntp      = next token's lemma          m_ntp
    Head 2  Root           t_root     = [C1,C2,C3,C4] null-padded   m_root
                                        ^ null-padded in THIS artifact, but the TARGET built from it
                                        must NOT be: an empty slot of a supervised root becomes
                                        <pad> = 0 (model_arms.make_batch), because training it as
                                        IGNORE gave slot 4 no gradient on 97.4% of lettered roots and
                                        every triliteral root decoded to length 4 (CHALLENGES 2x.14).
                                        A fully unsupervised token stays all-IGNORE. smoke_test
                                        asserts the invariant over 600 real PADT records.
    Head 3  Wazan          t_wazan    = canonical 3/4-slot label    m_wazan
    Head 4  Syntax         t_dep      = UD deprel / head distance   m_syn
    Head 5  Case           t_case     = 0 NOM / 1 ACC / 2 GEN       m_case

MASKING RULES — each one is a documented measurement, not a preference
    root   : 0 unless PADT's `Root=` survives `is_gold_root` (~50% of the column,
             SPEC-REV6 §3.1).
    wazan  : 0 when CALIMA reports no pattern, or `NTWS`/`backoff`, or the label
             is not strict-well-formed (each radical digit exactly once), or the
             strip refused alignment. This implements the Finding D decision:
             never train Head 3 on the MLE's substitute reading.
    case   : 0 unless PADT has `Case=`, and `u` (= undefined, NOT damma) is
             masked rather than treated as a class (SPEC-REV6 §4.1).
    syn    : 1 for every PADT token (its own annotation, 100%).
    ntp    : 0 for the last token of a sentence.

RESUMABLE BY DESIGN
    MLE disambiguation dominates the runtime, so the run is long and must survive
    a kill: output is appended per sentence and progress is recorded per split, so
    re-running continues instead of restarting. --limit sets tokens per split.

Splits and leakage
  PADT      : the treebank's own train/dev/test files.
  Tashkeela : assigned BY BOOK, and the assignment is deliberately NOT uniform:
              books 0-7  -> DEV   (the human-gold sample was drawn from the first
                                   8 books, so this is where it must live, or the
                                   gold would be inside the silver TRAIN split and
                                   the ablation would measure memorisation)
              books 8-89 -> TRAIN
              books 90-96 -> TEST
              Books are the corpus's own rows (97 of them), so a split never cuts a
              book in half and no book contributes to two splits.

USAGE
    python src/build_training_jsonl.py --split train --limit 2000   # smoke
    python src/build_training_jsonl.py                            # all splits
    python src/build_training_jsonl.py --source tashkeela --limit 200000
"""
from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import json
import os
import random
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests
from camel_tools.disambig.mle import MLEDisambiguator

from paths import (OUT, PADT_DEV, PADT_TEST, PADT_TRAIN, RAW, require)
from reconcile import (ARABIC, PREFIXES, ROOT_FIELD, is_gold_root,
                       padt_to_arabic, strip_diacritics)
from wazan_normalizer import normalize_from_analysis

DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")

# Held out entirely (SPEC-REV6 §3.1). Refuse to train on these.
EVAL_FILES = ("nyuad", "qac", "qrtb", "pud", "quranic")

SPLITS = {"train": PADT_TRAIN, "dev": PADT_DEV, "test": PADT_TEST}

CASE_MAP = {"nom": 0, "acc": 1, "gen": 2}

# UD UPOS -> an int index is built at run time from the observed inventory, so the
# vocabulary is the corpus's own rather than an assumption.
UPOS_VOCAB: dict[str, int] = {}
DEPREL_VOCAB: dict[str, int] = {}
LEMMA_VOCAB: dict[str, int] = {}


def _feat(feats: str, name: str) -> str | None:
    m = re.search(rf"(?:^|\|){name}=([^|]+)", feats or "")
    return m.group(1) if m else None


def _case_target(feats: str) -> tuple[int | None, str]:
    raw = _feat(feats, "Case")
    if not raw:
        return None, "no_case_feature"
    key = raw.strip().lower()
    if key in CASE_MAP:
        return CASE_MAP[key], "ok"
    if key == "u":
        return None, "undefined_u_masked"      # NOT damma — SPEC-REV6 §4.1
    return None, f"unmapped_case:{raw}"


def _root_slots(root: str | None) -> list:
    """Gold root -> a 4-slot list of ARABIC radicals, null-padded (Head 2 is 4-slot).

    PADT's `Root=` column is SPACE-SEPARATED LATIN TRANSLIT (`r f .d`, `'amrIk`), not
    Arabic script, so filtering it for Arabic characters yields an EMPTY list for
    every token — which silently produced all-null Head-2 targets for 96,671
    "unmasked" tokens in the first build of data/out. The mask was right; the
    targets were empty. Caught by model_arms.py reporting `radical: 1` (a
    one-entry vocabulary: <pad> only).

    So: convert first with the pinned PADT translit table (`reconcile.padt_to_arabic`,
    derived from 2,046 aligned pairs), and only treat the value as Arabic-script
    radicals when it actually contains Arabic letters (QAC/EQTB-style sources).
    """
    if not root:
        return [None, None, None, None]
    if ARABIC.search(root):                      # already Arabic radicals
        units = [c for c in root if ARABIC.match(c)]
    else:
        from reconcile import padt_to_arabic
        ar = padt_to_arabic(root)                # None if a unit is unmappable
        units = list(ar) if ar else []
    return (units + [None, None, None, None])[:4]


def read_sentences(path: Path):
    """Yield (sent_index, [token dicts]). Skips multiword ranges and empty nodes."""
    si = -1
    toks: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                if toks:
                    yield si, toks
                toks = []
                continue
            if line.startswith("#"):
                if line.startswith("# sent_id"):
                    si += 1
                continue
            c = line.split("\t")
            if len(c) < 10 or "-" in c[0] or "." in c[0]:
                continue
            # CoNLL-U: 1 ID, 2 FORM, 3 LEMMA, 4 UPOS, 5 XPOS, 6 FEATS, 7 HEAD,
            # 8 DEPREL, 9 DEPS, 10 MISC. Verified on this file: `Root=` occurs in
            # column 9 (MISC; 193,012 hits) and `Case=` in column 5 (FEATS;
            # 116,741 hits). They are NOT in the same column — conflating them
            # silently loses every case label.
            toks.append({"form": c[1], "lemma": c[2], "upos": c[3],
                         "feats": c[5], "head": c[6], "deprel": c[7],
                         "misc": c[9]})
        if toks:
            yield si, toks


def build(split: str, limit: int | None, out_path: Path, resume: bool) -> dict:
    path = require(SPLITS[split])
    if any(e in str(path).lower() for e in EVAL_FILES):
        raise SystemExit(f"REFUSING: {path} is a held-out source (SPEC-REV6 §3.1)")

    mle = MLEDisambiguator.pretrained("calima-msa-r13")

    # ---- resume: count what is already on disk, skip that many tokens
    done = 0
    if resume and out_path.exists():
        with open(out_path, encoding="utf-8") as fh:
            done = sum(1 for _ in fh)
    mode = "a" if (resume and out_path.exists()) else "w"

    stats = collections.Counter()
    per_head = {"ntp": [0, 0], "root": [0, 0], "wazan": [0, 0],
                "syn": [0, 0], "case": [0, 0]}   # [unmasked, total]
    wazan_reasons = collections.Counter()
    root_reasons = collections.Counter()
    case_reasons = collections.Counter()
    t0 = time.time()
    written = 0
    seen = 0        # tokens consumed in THIS run, including ones already on disk
    skipped = 0

    with open(out_path, mode, encoding="utf-8") as out:
        for si, toks in read_sentences(path):
            forms = [t["form"] for t in toks]
            try:
                dis = mle.disambiguate(forms)
            except Exception:
                dis = [None] * len(toks)

            for ti, (t, d) in enumerate(zip(toks, dis)):
                seen += 1
                # RESUME: the first `done` tokens are already in the file. Skip
                # them regardless of --limit — skipping only inside the limit
                # branch would re-append them and silently duplicate records.
                if seen <= done:
                    skipped += 1
                    continue
                if limit is not None and written >= limit:
                    break
                stats["tokens"] += 1

                a = {}
                if d is not None and d.analyses:
                    a = d.analyses[0].analysis

                # ---- Head 2: root from PADT gold (never from CALIMA for PADT)
                gold = None
                m = ROOT_FIELD.search(t["misc"])      # MISC (col 9), verified
                if m:
                    gold = m.group(1).strip()
                rreason = "missing"
                if gold:
                    if is_gold_root(gold, t["upos"]):
                        rreason = "ok"
                    else:
                        from reconcile import gold_root_reason
                        rreason = gold_root_reason(gold, t["upos"])
                root_reasons[rreason] += 1
                slots = _root_slots(gold) if rreason == "ok" else [None] * 4
                m_root = 1 if rreason == "ok" else 0
                # GUARD: mask=1 must imply a USABLE TARGET, or the mask is a lie.
                # The first build set m_root=1 on 96,671 tokens while writing all-null
                # slots (the translit was never converted), so the model would have
                # been trained to predict nothing and scored as if supervised.
                if m_root and sum(1 for s in slots if s) < 3:
                    stats["root_target_empty"] += 1
                    m_root = 0
                    rreason = "target_empty"

                # ---- Head 3: wazan from CALIMA silver, strict-well-formed only
                rec = normalize_from_analysis(a) if a else None
                if rec is None:
                    lab, m_wazan, wr = None, 0, "no_analysis"
                else:
                    lab = rec["label"]
                    m_wazan = 1 if (rec["wellformed_strict"] and rec["reason"] == "ok"
                                    and lab) else 0
                    wr = rec["reason"] if m_wazan else (
                        "not_strict" if lab and not rec["wellformed_strict"] else rec["reason"])
                wazan_reasons[wr] += 1

                # ---- Head 5: case from PADT gold
                cval, creason = _case_target(t["feats"])
                case_reasons[creason] += 1
                m_case = 1 if cval is not None else 0

                # ---- Head 4: syntax, and arity over the sentence
                upos_i = UPOS_VOCAB.setdefault(t["upos"], len(UPOS_VOCAB))
                dep_i = DEPREL_VOCAB.setdefault(t["deprel"], len(DEPREL_VOCAB))
                head_i = int(t["head"]) if t["head"].isdigit() else None
                head_dist = (head_i - (ti + 1)) if head_i else None
                arity = sum(1 for u in toks
                            if u["head"].isdigit() and int(u["head"]) == ti + 1)

                # ---- Head 1: next lemma
                nxt = toks[ti + 1]["lemma"] if ti + 1 < len(toks) else None
                nxt_i = LEMMA_VOCAB.setdefault(nxt, len(LEMMA_VOCAB)) if nxt else None

                rec_out = {
                    "id": f"{split}/{si}/{ti}",
                    "src": "padt", "split": split, "si": si, "ti": ti,
                    "form": t["form"], "form_bare": strip_diacritics(t["form"]),
                    "lemma": t["lemma"], "upos": upos_i, "deprel": dep_i,
                    "t_root": slots, "m_root": m_root, "root_from": rreason,
                    "t_wazan": lab, "m_wazan": m_wazan, "wazan_reason": wr,
                    "wazan_render": (rec["render"] if rec else None),
                    "proclitic": (rec["proclitic"] if rec else ""),
                    "enclitic": (rec["enclitic_surface"] if rec else ""),
                    "t_case": cval, "m_case": m_case,
                    "m_syn": 1, "head_dist": head_dist, "arity": arity,
                    "t_ntp": nxt_i, "m_ntp": 0 if nxt is None else 1,
                    # provenance of the SILVER side, so a reviewer can audit it
                    "calima_root": a.get("root"), "calima_cas": a.get("cas"),
                    "calima_source": a.get("source"),
                }
                out.write(json.dumps(rec_out, ensure_ascii=False) + "\n")
                written += 1

                per_head["ntp"][0] += 1 if nxt is not None else 0
                per_head["root"][0] += m_root
                per_head["wazan"][0] += m_wazan
                per_head["syn"][0] += 1
                per_head["case"][0] += m_case
                for k, v in zip(per_head, (1, 1, 1, 1, 1)):
                    per_head[k][1] += v

            if written and written % 2000 < len(toks):
                el = time.time() - t0
                print(f"  [{split}] {done+written:,} tokens  {el:5.0f}s  "
                      f"({written/max(el,1e-9):.0f} tok/s)", flush=True)
            if limit is not None and written >= limit:
                break

    el = time.time() - t0
    return {"split": split, "file": str(out_path), "written": written,
            "already_present": done, "skipped_this_run": skipped,
            "seconds": round(el, 1),
            "rate_tok_s": round(written / max(el, 1e-9), 1),
            "per_head_unmasked": {k: v[0] for k, v in per_head.items()},
            "per_head_total": {k: v[1] for k, v in per_head.items()},
            "root_reasons": dict(root_reasons.most_common()),
            "wazan_reasons": dict(wazan_reasons.most_common()),
            "case_reasons": dict(case_reasons.most_common())}


# ============================================================================
# TASHKEELA SILVER RECORDS  (--source tashkeela)
#
# WHAT IS SILVER HERE, HEAD BY HEAD — stated because "silver" is not one thing:
#   Head 2 root  : the GOLD-DERIVED dictionary (PADT `Root=` first, arramooz second).
#                  Tashkeela has no root annotation at all.
#   Head 3 wazān : CALIMA MLE. This is the SAME source the PADT records already use
#                  (PADT has no wazān column either), so on this head the ablation
#                  varies the CORPUS, not the label source.
#   Head 5 case  : CALIMA `cas` (n/a/g) — genuinely silver, and the ONE head where
#                  the ablation is a clean gold-vs-silver contrast, because the PADT
#                  records take case from the treebank's human `Case=`.
#   Head 4 syn   : ABSENT (Tashkeela has no dependency annotation) -> m_syn = 0.
#   Head 1 ntp   : ABSENT (no lemma annotation; CALIMA `lex` is stored for provenance
#                  but is NOT used as a target) -> m_ntp = 0.
# Masking is not "missing data": train.py computes every head's CE with ignore_index,
# so a masked head contributes exactly zero. But note that row_targets now writes
# deprel through m_syn — before that fix the baseline would have been trained to
# predict dependency class 0 for every Tashkeela token.
# ============================================================================

MAX_LEN = 96                       # matches config/shared.yaml data.max_len

# books 0-7 -> dev (the human-gold sample lives there), 8-89 -> train, 90-96 -> test
TASHKEELA_BOOKS = {"train": (8, 90), "dev": (0, 8), "test": (90, 97)}

BOOK_CACHE = RAW / "tashkeela-books.jsonl"

# THE APPROVED CORPUS, PINNED — and the pin is the point. This file is a NETWORK input fetched from the
# HF rows API, and until now it was only RECORDED (line ~828), never verified. Measured cost of that
# omission on 2026-10-13: the cloud re-fetched it, got a file 97 BYTES different from this one, built for
# 35.4 min INSIDE a GPU-metered session, and only THEN failed the output-hash gate — 0.59 GPU-h for
# nothing. **An output-hash gate is only as strong as the pinning of its inputs.**
#
#   approved: 1,082,800,469 bytes  sha256 5985d366f39d4ba336a9ddb5b905d392c869b803f926be437194faa512132007
#   drifted : 1,082,800,372 bytes  (what the v17 kernel fetched)
#
# Set BOOKS_APPROVED_SHA256 = None to accept any corpus — correct ONLY for a deliberate re-derivation,
# and then the approved OUTPUT hashes must be re-approved in the SAME commit or the gate below will
# reject the build for the wrong reason.
BOOKS_APPROVED_SHA256 = "5985d366f39d4ba336a9ddb5b905d392c869b803f926be437194faa512132007"
BOOKS_APPROVED_BYTES = 1082800469


def assert_corpus_approved(cache: Path = BOOK_CACHE) -> None:
    """Refuse the corpus unless its sha256 is the approved one — BEFORE any tokenisation.

    Why it must be here and not only on the outputs: a drifted corpus silently produces a different
    sample while every COUNT still matches (record totals, per-book windows, mask coverage), because
    the sampler re-slices the same budget over different text. The output hashes then differ for a
    reason that takes an hour of forensics to find and 0.59 GPU-h to discover. This fails in seconds.
    """
    if BOOKS_APPROVED_SHA256 is None:
        print("  corpus: UNPINNED (BOOKS_APPROVED_SHA256=None) — accepting whatever was fetched")
        return
    h = hashlib.sha256()
    with open(cache, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    got, n = h.hexdigest(), cache.stat().st_size
    if got != BOOKS_APPROVED_SHA256:
        raise SystemExit(
            "CORPUS DRIFT — REFUSING TO BUILD (%s)\n"
            "  approved: %s  (%d bytes)\n"
            "  got     : %s  (%d bytes)\n"
            "The corpus is fetched from the network and is the SOURCE of every label, so a drifted\n"
            "corpus produces a different sample while every count still matches — which is exactly how\n"
            "a 97-byte drift cost 0.59 GPU-h inside a metered session (2026-10-13). Ship the approved\n"
            ".jsonl.gz artifacts instead of rebuilding, or re-approve this hash AND the output hashes\n"
            "together in one commit."
            % (cache, BOOKS_APPROVED_SHA256[:16], BOOKS_APPROVED_BYTES, got[:16], n))
    print("  corpus: APPROVED sha256 %s (%d bytes)" % (got[:16], n))
HF_DS = "community-datasets/tashkeela"
ROWS_URL = "https://datasets-server.huggingface.co/rows"
TASH_CASE = {"n": 0, "a": 1, "g": 2}          # CALIMA `cas` -> case index
SENT_END = re.compile(r"[.؟!؛\n]+")
BARE_ALEF = str.maketrans({"\u0623": "\u0627", "\u0625": "\u0627",
                           "\u0622": "\u0627", "\u0621": "\u0627",
                           "\u0671": "\u0627"})


def to_bare_root(s: str) -> str:
    """Root -> the HUMAN GOLD's convention (Rule 7): bare alef, no separators.

    MEASURED DISAGREEMENT, and it is not cosmetic: PADT's translit table and arramooz
    write a hamzated radical as ء/أ ('ءخذ' for أخذ) while the human gold writes a bare
    alef ('ابو', 'ارض', 'اله'). Without this mapping a model can be right about the
    root and still score 0% against the 278 human patterns, for an orthographic reason
    that has nothing to do with grammar. The gold scorer applies the same function to
    the model's prediction, so the comparison is convention-free.
    """
    if not s:
        return ""
    return "".join(c for c in s if ARABIC.match(c)).translate(BARE_ALEF)


def fetch_books(n_books: int, cache: Path = BOOK_CACHE) -> list[str]:
    """Book texts 0..n_books-1 via the HF rows API, cached to disk.

    Two ways into the dataset and the difference matters on this host: the parquet
    payload (~417 MB) is throttled to ~25 KB/s, i.e. hours, while the rows endpoint
    runs at ~1 MB/s (COLAB.md §1.2). The cache is append-only and flushed per book,
    so a killed fetch RESUMES instead of re-downloading 400 MB.
    """
    books: list[str] = []
    if cache.exists():
        with open(cache, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    break                       # truncated tail: stop, re-fetch it
                if r.get("i") != len(books) or not r.get("text"):
                    break
                books.append(r["text"])
    if len(books) >= n_books:
        print(f"  book cache: {len(books)} book(s) at {cache} "
              f"({sum(len(b) for b in books)/1e6:.0f} M chars)")
        assert_corpus_approved(cache)
        return books[:n_books]

    print(f"  fetching books {len(books)}..{n_books-1} via the HF rows API (cache {cache})")
    cache.parent.mkdir(parents=True, exist_ok=True)
    with open(cache, "a", encoding="utf-8") as out:
        for off in range(len(books), n_books):
            row = None
            for attempt in range(4):
                try:
                    r = requests.get(ROWS_URL, timeout=300, params={
                        "dataset": HF_DS, "config": "plain_text", "split": "train",
                        "offset": off, "length": 1})
                    if r.status_code == 429:
                        time.sleep(5 * (attempt + 1))
                        continue
                    r.raise_for_status()
                    row = r.json()["rows"][0]["row"]
                    break
                except Exception as ex:
                    if attempt == 3:
                        raise SystemExit(f"book {off} unreachable after 4 tries: "
                                         f"{type(ex).__name__}: {ex}")
                    time.sleep(3 * (attempt + 1))
            text = (row or {}).get("text") or ""
            books.append(text)
            out.write(json.dumps({"i": off, "chars": len(text), "text": text},
                                 ensure_ascii=False) + "\n")
            out.flush()
            if off % 5 == 0 or off == n_books - 1:
                print(f"    book {off+1}/{n_books} ({len(text):,} chars)", flush=True)
    assert_corpus_approved(cache)
    return books[:n_books]


def tokenize_book(text: str) -> list[list[str]]:
    """Book text -> pseudo-sentences of Arabic tokens, windows capped at MAX_LEN.

    Tashkeela has NO sentence boundaries (one row IS a book), so the MLE has to be
    given windows. Two constraints set the cut: sentence punctuation, then a hard cap
    at MAX_LEN because (a) an unbounded 'sentence' makes each MLE call slower for no
    gain and (b) max_len is what the trainer chunks at anyway.
    """
    sents = []
    for chunk in SENT_END.split(text or ""):
        toks = [t for t in (w.strip() for w in chunk.split()) if ARABIC.search(t)]
        for i in range(0, len(toks), MAX_LEN):
            win = toks[i:i + MAX_LEN]
            if len(win) >= 2:
                sents.append(win)
    return sents


def padt_half_of_silver_dict() -> tuple[dict, int]:
    """The PADT (human `Root=`) half of the silver root dictionary: key -> bare root.

    EXISTS SEPARATELY because the cloud build cannot read the raw treebank: `data/raw/`
    is deliberately not in the run bundle (copyleft), and a build cell that needs
    `ar_padt-ud-train.conllu` dies with FileNotFoundError — which is exactly how round 17
    lost a run. So this half is computed HERE and shipped as a small JSON beside the code,
    which has the side benefit that the cloud dictionary cannot drift from this one.
    """
    from reconcile import RootDictionary
    dic = RootDictionary.build_from_padt([str(require(PADT_TRAIN))])
    out: dict[str, str] = {}
    for key, root in dic.mapping.items():
        ar = root if ARABIC.search(root) else (padt_to_arabic(root) or "")
        ar = to_bare_root(ar)
        if len(ar) in (3, 4):
            out[key] = ar
    return out, len(dic.mapping)


def build_silver_root_dict(padt_dict_path: Path | None = None) -> tuple[dict, dict]:
    """key (diacritic-stripped surface) -> bare-Arabic root, for Tashkeela.

    Precedence PADT (human `Root=`) then arramooz (GPL lexicon) — `setdefault`, so a
    lexicon entry can never overwrite a gold one. QAC and EQTB are NOT read: they are
    held-out evaluation sources (SPEC-REV6 §3.1), and EQTB re-annotates the same
    Qur'anic tokens as QAC.

    NOTHING DERIVED FROM THE PADT TEST SPLIT IS READ EITHER. An earlier revision merged
    a `data/recoverable_roots.json` that had been HARVESTED FROM PADT TEST (196 forms,
    `source: padt_test_gold`) into this dictionary — which put evaluation-split labels
    into the Tashkeela training targets *and* into the renderer's measurement
    dictionary. That is a §3.1 / red-line-4 violation. The path was removed 2026-10-10;
    the measured cost is 1 root-recovery in 12,454 on PADT test, so the fix is free.

    `padt_dict_path` supplies the PADT half from a JSON file (see
    padt_half_of_silver_dict). Without it the raw treebank is read, which only works
    where that corpus exists.
    """
    mapping: dict[str, str] = {}
    prov = collections.Counter()
    if padt_dict_path is not None:
        payload = json.loads(Path(padt_dict_path).read_text(encoding="utf-8"))
        mapping = dict(payload["mapping"])
        prov["padt_from"] = str(padt_dict_path)
        prov["padt_kept"] = len(mapping)
        prov["padt_surfaces"] = payload.get("padt_surfaces", len(mapping))
    else:
        mapping, surfaces = padt_half_of_silver_dict()
        prov["padt_surfaces"] = surfaces
        prov["padt_kept"] = len(mapping)
    try:
        import arramooz
        base = os.path.dirname(arramooz.__file__)
        db = glob.glob(os.path.join(base, "**", "arabicdictionary.sqlite"),
                       recursive=True)[0]
        con = sqlite3.connect(db)
        n0 = len(mapping)
        for table in ("nouns", "verbs"):
            for w, r in con.execute(
                    f"select unvocalized, root from {table} "
                    f"where root is not null and root<>'' and unvocalized is not null"):
                k = strip_diacritics(w or "")
                ar = to_bare_root(r or "")
                if k and len(ar) in (3, 4):
                    mapping.setdefault(k, ar)
        prov["arramooz_added"] = len(mapping) - n0
    except Exception as ex:                                   # pragma: no cover
        prov["arramooz_error"] = f"{type(ex).__name__}: {ex}"
    return mapping, dict(prov)


def lookup_root(mapping: dict, surface_bare: str) -> tuple[str | None, str]:
    """(bare root, route exact|prefix|miss). Same prefix rule as RootDictionary."""
    if not surface_bare:
        return None, "miss"
    if surface_bare in mapping:
        return mapping[surface_bare], "exact"
    for p in PREFIXES:
        if surface_bare.startswith(p) and len(surface_bare) - len(p) >= 2:
            k2 = surface_bare[len(p):]
            if k2 in mapping:
                return mapping[k2], "prefix"
    return None, "miss"


def build_tashkeela(split: str, limit: int | None, out_path: Path, resume: bool,
                    books: list[str], mapping: dict, mle,
                    allocate: str = "in-order", sampler_seed: int = 0) -> dict:
    """Build one silver split.

    `allocate='in-order'` (default) reproduces the original behaviour: stream books in
    order until the token budget is spent. That is what produced a 120k "training set"
    that was entirely the OPENING OF BOOK 8 and covered 0 of the 126 OOV gold words
    (CHALLENGES 2ae) -- because --limit counts TOKENS and one book exceeds it.

    `allocate='spread'` divides the budget across every book in the split and starts each
    book at a seeded random window, so no single book (nor its preface) can dominate.
    """
    lo, hi = TASHKEELA_BOOKS[split]
    # A SPREAD SAMPLE CANNOT RESUME. The per-book allocation and the seeded start window
    # make "records already on disk" meaningless, so a partial spread file would silently
    # become neither the allocated nor the seeded sample.
    if allocate == "spread" and resume and out_path.exists():
        raise SystemExit(
            f"{out_path} already exists and a SPREAD sample cannot resume: the per-book "
            "allocation and the seeded start window make 'records already on disk' "
            "meaningless. Remove the file, or pass --no-resume with a fresh --outdir.")
    if allocate == "spread":
        resume = False
    done = 0
    if resume and out_path.exists():
        with open(out_path, encoding="utf-8") as fh:
            done = sum(1 for _ in fh)
    mode = "a" if (resume and out_path.exists()) else "w"

    stats = collections.Counter()
    per_head = {k: [0, 0] for k in ("ntp", "root", "wazan", "syn", "case")}
    root_reasons = collections.Counter()
    wazan_reasons = collections.Counter()
    case_reasons = collections.Counter()
    t0 = time.time()
    written = seen = skipped = 0
    si = -1
    empty = 0

    # THE ALLOCATION. Recorded per book, including what was NOT used, so the manifest can
    # say what the sample actually is rather than what it was meant to be.
    n_books = hi - lo
    alloc: dict[int, int | None] = {}
    if allocate == "spread" and limit is not None:
        base, rem = divmod(limit, n_books)
        for k, b in enumerate(range(lo, hi)):
            alloc[b] = base + (1 if k < rem else 0)
    else:
        for b in range(lo, hi):
            alloc[b] = None
    per_book_stats: list[dict] = []

    with open(out_path, mode, encoding="utf-8") as out:
        for bi in range(lo, hi):
            # IN SPREAD MODE THE PLAN GOVERNS, NOT THE RUNNING TOTAL. Breaking on
            # `written >= limit` here would re-create the 2ae defect: the first few books
            # (window granularity makes each slightly overshoot) would spend the whole
            # budget and the remaining books would never be opened at all.
            if allocate != "spread" and limit is not None and written >= limit:
                break
            book_start = written
            wins = tokenize_book(books[bi])
            start_win = 0
            if alloc[bi] is not None:
                if len(wins) > 1:
                    # seeded and per-book: reproducible, and independent of book order
                    start_win = random.Random(sampler_seed * 1_000_003 + bi).randrange(len(wins))
                wins = wins[start_win:] + wins[:start_win]   # wrap, so the budget can fill
            for win in wins:
                if allocate != "spread" and limit is not None and written >= limit:
                    break
                # A WINDOW IS ATOMIC (the MLE disambiguates one window at a time), so fill
                # each allocation to the nearest window and never exceed it: stop BEFORE the
                # window that would overshoot. The cost is at most one window per book.
                if (alloc[bi] is not None and written > book_start
                        and written - book_start + len(win) > alloc[bi]):
                    break
                # RESUME: skip whole windows WITHOUT calling the MLE. The MLE is the
                # entire runtime, so a resumed run must not pay for it twice — and
                # `seen`/`si` advance for skipped windows too, so the sentence indices
                # stay contiguous with the records already on disk.
                if seen + len(win) <= done:
                    seen += len(win)
                    skipped += len(win)
                    si += 1
                    continue
                si += 1
                try:
                    dis = mle.disambiguate(win)
                except Exception:
                    dis = [None] * len(win)
                    stats["mle_errors"] += 1

                for ti, (raw, d) in enumerate(zip(win, dis)):
                    seen += 1
                    if seen <= done:
                        skipped += 1
                        continue
                    if limit is not None and written >= limit:
                        break
                    bare = strip_diacritics(raw)
                    if not bare:
                        empty += 1
                        continue
                    stats["tokens"] += 1
                    a = d.analyses[0].analysis if (d is not None and d.analyses) else {}

                    # ---- Head 2: root from the gold-derived dictionary
                    root, route = lookup_root(mapping, bare)
                    rreason = route if root else "miss"
                    if root and len(root) not in (3, 4):
                        rreason = "radical_count"
                    slots = ([c for c in root] + [None] * 4)[:4] if root else [None] * 4
                    m_root = 1 if rreason in ("exact", "prefix") else 0
                    if m_root and sum(1 for s in slots if s) < 3:
                        m_root, rreason = 0, "target_empty"     # mask must not lie
                    root_reasons[rreason] += 1

                    # ---- Head 3: wazān from CALIMA silver, strict-well-formed only
                    rec_w = normalize_from_analysis(a) if a else None
                    if rec_w is None:
                        lab, m_wazan, wr = None, 0, "no_analysis"
                    else:
                        lab = rec_w["label"]
                        m_wazan = 1 if (rec_w["wellformed_strict"]
                                        and rec_w["reason"] == "ok" and lab) else 0
                        wr = rec_w["reason"] if m_wazan else (
                            "not_strict" if lab and not rec_w["wellformed_strict"]
                            else rec_w["reason"])
                    wazan_reasons[wr] += 1

                    # ---- Head 5: case from CALIMA `cas` (SILVER; n/a/g only)
                    raw_cas = (a.get("cas") or "").strip().lower()
                    cval = TASH_CASE.get(raw_cas)
                    m_case = 1 if cval is not None else 0
                    case_reasons["ok" if m_case else f"calima_cas:{raw_cas or 'none'}"] += 1

                    rec_out = {
                        "id": f"{split}/{si}/{ti}", "src": "tashkeela", "split": split,
                        "book": bi, "si": si, "ti": ti,
                        "form": raw, "form_bare": bare,
                        "lemma": a.get("lex") or "", "upos": 0, "deprel": 0,
                        "t_root": slots, "m_root": m_root, "root_from": rreason,
                        "t_wazan": lab, "m_wazan": m_wazan, "wazan_reason": wr,
                        "wazan_render": (rec_w["render"] if rec_w else None),
                        "proclitic": (rec_w["proclitic"] if rec_w else ""),
                        "enclitic": (rec_w["enclitic_surface"] if rec_w else ""),
                        "t_case": cval, "m_case": m_case,
                        # ABSENT on this corpus, and masked rather than invented
                        "m_syn": 0, "head_dist": None, "arity": 0,
                        "t_ntp": None, "m_ntp": 0,
                        "calima_root": a.get("root"), "calima_cas": a.get("cas"),
                        "calima_source": a.get("source"),
                    }
                    out.write(json.dumps(rec_out, ensure_ascii=False) + "\n")
                    written += 1
                    per_head["ntp"][0] += 0
                    per_head["root"][0] += m_root
                    per_head["wazan"][0] += m_wazan
                    per_head["syn"][0] += 0
                    per_head["case"][0] += m_case
                    for k in per_head:
                        per_head[k][1] += 1
                if written and written % 5000 < len(win):
                    el = time.time() - t0
                    print(f"  [{split}] {done+written:,} tokens  {el:5.0f}s  "
                          f"({written/max(el,1e-9):.0f} tok/s)", flush=True)
            per_book_stats.append({
                "book": bi, "allocated": alloc[bi],
                "consumed": written - book_start,
                "unused": (alloc[bi] - (written - book_start)
                           if alloc[bi] is not None else None),
                "start_window": start_win, "windows": len(wins)})

    el = time.time() - t0
    return {"split": split, "source": "tashkeela", "file": str(out_path),
            "written": written, "already_present": done, "skipped_this_run": skipped,
            "sampler": {"mode": allocate, "seed": sampler_seed,
                        "tokens_requested": limit, "tokens_written": written,
                        "books_available": n_books,
                        "books_used": sum(1 for b in per_book_stats if b["consumed"]),
                        # Two NON-NEGATIVE numbers. A book whose first window is larger than
                        # its allocation necessarily overshoots it (a window is atomic for
                        # the MLE), and netting the two would hide that behind a tidy zero.
                        "allocation_unused": sum(max(b["unused"] or 0, 0)
                                                 for b in per_book_stats),
                        "allocation_overshoot": sum(-min(b["unused"] or 0, 0)
                                                    for b in per_book_stats),
                        "per_book": per_book_stats},
            "empty_form": empty, "seconds": round(el, 1),
            "rate_tok_s": round(written / max(el, 1e-9), 1),
            "per_head_unmasked": {k: v[0] for k, v in per_head.items()},
            "per_head_total": {k: v[1] for k, v in per_head.items()},
            "root_reasons": dict(root_reasons.most_common()),
            "wazan_reasons": dict(wazan_reasons.most_common()),
            "case_reasons": dict(case_reasons.most_common())}


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _camel_data_versions() -> dict:
    """CALIMA is part of the preprocessing, so its package versions belong in the manifest."""
    try:
        from camel_tools.data import CT_DATA_DIR
        v = Path(CT_DATA_DIR) / "versions.json"
        if v.exists():
            return json.loads(v.read_text(encoding="utf-8"))
    except Exception as exc:                      # never fail a build over provenance
        return {"error": repr(exc)}
    return {}


def main_tashkeela(args) -> int:
    splits = list(TASHKEELA_BOOKS) if args.split == "all" else [args.split]
    for s in splits:
        if s not in TASHKEELA_BOOKS:
            raise SystemExit(f"unknown split {s!r}; have {list(TASHKEELA_BOOKS)}")
    li = {"train": args.limit, "dev": args.limit_eval, "test": args.limit_eval}

    print("=" * 84)
    print(f"TASK 3b — building SILVER training JSONL from Tashkeela ({', '.join(splits)})")
    print("root : gold-derived dictionary (PADT `Root=` then arramooz)")
    print("wazan: CALIMA MLE · case: CALIMA `cas` · syntax/NTP: ABSENT -> masked")
    print("held out, never read: NYUAD, QAC, EQTB (SPEC-REV6 §3.1)")
    print("=" * 84)

    mapping, prov = build_silver_root_dict(
        Path(args.root_dict) if args.root_dict else None)
    print(f"\nsilver root dictionary: {len(mapping):,} keys  ({prov})")
    if prov.get("arramooz_error"):
        print("  *** ARRAMOOZ FAILED TO LOAD. The dictionary is PADT-only, roughly a third"
              " of its size, and root supervision WILL be worse — this is a broken"
              " environment, not a result. ***")
    mle = MLEDisambiguator.pretrained("calima-msa-r13")
    books = fetch_books(max(TASHKEELA_BOOKS[s][1] for s in splits))

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for s in splits:
        print(f"\n--- {s} (books {TASHKEELA_BOOKS[s][0]}..{TASHKEELA_BOOKS[s][1]-1}, "
              f"limit {li[s]}) ---")
        m = build_tashkeela(s, li[s], outdir / f"tashkeela-{s}.jsonl",
                            not args.no_resume, books, mapping, mle,
                            allocate=args.allocate, sampler_seed=args.sampler_seed)
        manifest.append(m)
        print(f"  wrote {m['written']:,} records to {m['file']} ({m['rate_tok_s']} tok/s)")
        smp = m["sampler"]
        print(f"  sample: mode={smp['mode']} seed={smp['seed']} "
              f"books_used={smp['books_used']}/{smp['books_available']} "
              f"unused_allocation={smp['allocation_unused']:,}")
        for head in ("ntp", "root", "wazan", "syn", "case"):
            u, t = m["per_head_unmasked"][head], m["per_head_total"][head]
            print(f"    {head:6} unmasked {u:>7,} / {t:>7,}  ({100*u/max(t,1):5.1f}%)")

    # A SEPARATE manifest: the PADT one describes the PADT artifact and must not be
    # overwritten by a silver build (that is how a number stops being attributable).
    #
    # It must describe THE SAMPLE THAT WAS ACTUALLY BUILT, not the one that was intended:
    # sampler mode and seed, per-book allocated vs consumed (including unused allocation),
    # the source files' hashes, the preprocessing versions, and each output file's own
    # sha256. Without those, "a 2M-token spread sample" is a claim rather than a record.
    _rd = Path(args.root_dict) if args.root_dict else (RAW / "ar_padt-ud-train.conllu")
    outputs = {}
    for m in manifest:
        p = Path(m["file"])
        outputs[p.name] = {"bytes": p.stat().st_size if p.exists() else None,
                           "sha256": _sha256(p), "records": m["written"],
                           "sampler": m["sampler"]}
    body = {
        "splits": manifest,
        "dictionary": prov,
        "books": {s: list(TASHKEELA_BOOKS[s]) for s in splits},
        "limit": {"train": args.limit, "dev": args.limit_eval, "test": args.limit_eval},
        "max_len": MAX_LEN,
        "sampler": {"mode": args.allocate, "seed": args.sampler_seed},
        "preprocessing": {"mle": "calima-msa-r13",
                          "camel_tools_data_versions": _camel_data_versions(),
                          "diacritic_class": "[\\u064b-\\u0652\\u0670\\u0640]",
                          "max_len": MAX_LEN},
        "source": {
            "books": {"path": str(BOOK_CACHE), "sha256": _sha256(BOOK_CACHE),
                      "books_used": sorted({b["book"] for m in manifest
                                            for b in m["sampler"]["per_book"]
                                            if b["consumed"]})},
            "root_dict": {"path": str(_rd), "sha256": _sha256(_rd)},
        },
        "outputs": outputs,
    }
    body["manifest_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    man = outdir / "build_manifest_tashkeela.json"
    man.write_text(json.dumps(body, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nmanifest -> {man}")
    print(f"  sample mode={args.allocate} seed={args.sampler_seed}  "
          f"books_used={len(body['source']['books']['books_used'])}")
    for name, o in sorted(outputs.items()):
        print(f"  {name:26} {o['records']:>8,} records  sha256 {str(o['sha256'])[:16]}…")
    print(f"  manifest_sha256 {body['manifest_sha256'][:16]}…")
    print("REPORT THE MASKS: syntax and NTP are 0% supervised on this corpus by design.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=("padt", "tashkeela"), default="padt",
                    help="padt = the gold treebank records; tashkeela = SILVER records")
    ap.add_argument("--split", default="train", help="train | dev | test | all")
    ap.add_argument("--limit", type=int, default=None, help="tokens (train split)")
    ap.add_argument("--limit-eval", type=int, default=40000,
                    help="tokens for dev/test when --source tashkeela")
    ap.add_argument("--root-dict", default=None,
                    help="JSON holding the PADT half of the silver root dictionary "
                         "(padt_half_of_silver_dict). Needed where data/raw is absent "
                         "(the cloud bundle), and it pins the dictionary to the local "
                         "artifact. Omit to read the raw treebank.")
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--allocate", choices=("in-order", "spread"), default="in-order",
                    help="spread = divide --limit across EVERY book in the split and start "
                         "each book at a seeded random window. in-order reproduces the "
                         "original behaviour, where --limit was spent inside the FIRST book "
                         "and covered 0 of the 126 OOV gold words (CHALLENGES 2ae)")
    ap.add_argument("--sampler-seed", type=int, default=0,
                    help="seed for the per-book start windows under --allocate spread")
    ap.add_argument("--outdir", default=str(OUT))
    args = ap.parse_args()

    if args.source == "tashkeela":
        return main_tashkeela(args)

    splits = list(SPLITS) if args.split == "all" else [args.split]
    for s in splits:
        if s not in SPLITS:
            raise SystemExit(f"unknown split {s!r}; have {list(SPLITS)}")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    manifest = []

    print("=" * 84)
    print(f"TASK 3 — building training JSONL from PADT ({', '.join(splits)})")
    print("held out, never read: NYUAD, QAC, EQTB (SPEC-REV6 §3.1)")
    print("=" * 84)
    for s in splits:
        print(f"\n--- {s} ---")
        m = build(s, args.limit, outdir / f"padt-{s}.jsonl", not args.no_resume)
        manifest.append(m)
        print(f"  wrote {m['written']:,} records to {m['file']} "
              f"({m['rate_tok_s']} tok/s)")
        for head in ("ntp", "root", "wazan", "syn", "case"):
            u = m["per_head_unmasked"][head]
            t = m["per_head_total"][head]
            print(f"    {head:6} unmasked {u:>7,} / {t:>7,}  ({100*u/max(t,1):5.1f}%)")

    # vocabularies are part of the artifact: the model needs stable indices
    (outdir / "vocab.json").write_text(json.dumps({
        "upos": UPOS_VOCAB, "deprel": DEPREL_VOCAB, "lemma": LEMMA_VOCAB,
        "case": {"NOM": 0, "ACC": 1, "GEN": 2},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (outdir / "build_manifest.json").write_text(
        json.dumps({"splits": manifest, "limit": args.limit}, indent=1), encoding="utf-8")
    print(f"\nvoca: upos {len(UPOS_VOCAB)} · deprel {len(DEPREL_VOCAB)} · "
          f"next-lemma {len(LEMMA_VOCAB)}")
    print(f"manifest -> {outdir / 'build_manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
