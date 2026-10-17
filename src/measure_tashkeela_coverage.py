"""measure_tashkeela_coverage.py — G5: the number that sets the usable corpus size.

WHY THIS IS THE DECISIVE MEASUREMENT
    Tashkeela is the only large corpus available (75M vocalized *words*). It carries
    no gold roots, so every root on it must come from a dictionary built on gold.
    How much of it that dictionary actually covers sets the usable silver-corpus
    size, and therefore the model size the paper may claim (SPEC-REV6 §3.1, G5).
    Everything measured before this was PADT→PADT — same domain, same conventions.

THE REQUIRED PROTOCOL — report ALL THREE together (SPEC-REV6 §3.1)
    1. VOCABULARY TYPE coverage   |Tashkeela types ∩ dict keys| / |Tashkeela types|
    2. TOKEN coverage             covered tokens / all tokens
    3. MASKED TOKEN FRACTION      the two are not interchangeable
    Types systematically UNDERSTATE token coverage (rare words dominate types), so
    reporting type coverage alone misrepresents the result. Both are printed.

THE JOIN KEY, DECLARED (SPEC-REV6 §3.1 demands this explicitly)
    Key        : the diacritic-stripped token surface.
    Precedence : PADT (gold `Root=`) first, then arramooz (lexicon `root`).
    Rationale  : arramooz keys on its own `unvocalized` column and PADT on the
                 unvocalized surface — those are the same object, but they are not
                 guaranteed identical, so the precedence is stated rather than
                 assumed. Two normalisations are reported: diacritics-only, and
                 diacritics + alef/hamza/ya/ta-marbuta folding, because the second
                 is what a real matcher usually needs and the gap is informative.

QAC AND EQTB ARE NOT USED — they are held-out eval sources (SPEC-REV6 §3.1).

USAGE
    python src/measure_tashkeela_coverage.py --limit-tokens 200000     # smoke
    python src/measure_tashkeela_coverage.py                          # full 75M
    python src/measure_tashkeela_coverage.py --wazan-sample 0         # skip CALIMA
"""
from __future__ import annotations

import argparse
import collections
import glob
import os
import re
import sqlite3
import sys
import time

from paths import PADT_TRAIN, OUT, require

DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
ARABIC_LETTER = re.compile(r"[\u0621-\u064a]")
NOT_ARABIC_EDGE = re.compile(r"^[^\u0621-\u064a]+|[^\u0621-\u064a]+$")

# folding for the second (looser) normalisation
FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي",
                      "ة": "ه", "ؤ": "و", "ئ": "ي"})


def strip_diac(s: str) -> str:
    return DIAC.sub("", s or "")


def norm_token(raw: str) -> str:
    """Whitespace token -> bare Arabic letters (edges trimmed). '' if not a word."""
    t = NOT_ARABIC_EDGE.sub("", raw or "")
    return strip_diac(t)


def fold(s: str) -> str:
    return s.translate(FOLD)


def build_key_set() -> tuple[set, set, dict]:
    """(exact keys, folded keys, provenance counts). PADT first, then arramooz."""
    keys: set[str] = set()
    prov = collections.Counter()

    # --- PADT gold surfaces
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from reconcile import RootDictionary
    dic = RootDictionary.build_from_padt([str(require(PADT_TRAIN))])
    for k in dic.mapping:
        keys.add(k)
    prov["padt_surfaces"] = len(dic.mapping)

    # --- arramooz lexicon
    try:
        import arramooz
        base = os.path.dirname(arramooz.__file__)
        db = glob.glob(os.path.join(base, "**", "arabicdictionary.sqlite"), recursive=True)[0]
        con = sqlite3.connect(db)
        n0 = len(keys)
        for table in ("nouns", "verbs"):
            for (w,) in con.execute(
                    f"select unvocalized from {table} "
                    f"where root is not null and root<>'' and unvocalized is not null"):
                k = norm_token(w)
                if k:
                    keys.add(k)
        prov["arramooz_added"] = len(keys) - n0
    except Exception as ex:                                   # pragma: no cover
        prov["arramooz_error"] = f"{type(ex).__name__}: {ex}"

    return keys, {fold(k) for k in keys}, dict(prov)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-tokens", type=int, default=None)
    ap.add_argument("--limit-docs", type=int, default=None)
    ap.add_argument("--wazan-sample", type=int, default=20000,
                    help="tokens to run CALIMA on for the Head-3 rate (0 = skip)")
    ap.add_argument("--source", choices=("auto", "parquet", "api"), default="auto",
                    help="auto: parquet if present, else the HF rows API")
    ap.add_argument("--rows", type=int, default=None,
                    help="books to fetch in api mode (default 97 = the whole corpus)")
    args = ap.parse_args()

    print("=" * 88)
    print("G5 — Tashkeela coverage against a gold-keyed dictionary")
    print("=" * 88)
    keys, folded, prov = build_key_set()
    print(f"\ndictionary: {len(keys):,} exact keys ({prov})")
    print(f"            {len(folded):,} after alef/hamza/ya/ta folding")
    print("join key  : diacritic-stripped surface · precedence PADT -> arramooz")
    print("excluded  : QAC, EQTB (held-out eval sources, SPEC-REV6 §3.1)")

    print("\nloading Tashkeela…")
    # COLAB.md §1.2 names the HF dataset `community-datasets/tashkeela`. Two ways in,
    # and the difference is not academic on this host:
    #   parquet — the payload is 3 parquet files (~417 MB). The CDN throttles this
    #             connection to ~25 KB/s, i.e. HOURS, so it is only used when the
    #             files happen to be present already.
    #   api     — the dataset's own rows endpoint. Same dataset, ~1 MB/s, gzip. The
    #             corpus is 97 rows = the 97 books (verified: num_rows_total 97),
    #             so the WHOLE corpus is reachable this way in minutes.
    # --source auto picks parquet when the files exist, else the API.
    import requests

    HF_DS = "community-datasets/tashkeela"
    local = require(PADT_TRAIN).parent / "tashkeela"
    parquet_files = sorted(local.glob("*.parquet")) if local.exists() else []

    if args.source == "parquet" or (args.source == "auto" and parquet_files):
        import pyarrow.parquet as pq
        print(f"  source: parquet ({len(parquet_files)} file(s), "
              f"{sum(f.stat().st_size for f in parquet_files)/1e6:.0f} MB)")
        if not parquet_files:
            print("  no parquet files present — run without --source parquet")
            return 2

        def iter_docs():
            for path in parquet_files:
                pf = pq.ParquetFile(path)
                names = pf.schema_arrow.names
                col = "text" if "text" in names else names[0]
                for batch in pf.iter_batches(batch_size=2000, columns=[col]):
                    for text in batch.column(0).to_pylist():
                        if text:
                            yield text
    else:
        rows_url = "https://datasets-server.huggingface.co/rows"

        def fetch_row(off: int):
            for attempt in range(4):
                try:
                    r = requests.get(rows_url, timeout=180, params={
                        "dataset": HF_DS, "config": "plain_text", "split": "train",
                        "offset": off, "length": 1})
                    if r.status_code == 429:            # rate limited
                        time.sleep(5 * (attempt + 1))
                        continue
                    r.raise_for_status()
                    return r.json()["rows"][0]["row"]
                except Exception as ex:
                    if attempt == 3:
                        print(f"    FAIL offset {off}: {type(ex).__name__}: {ex}")
                        return None
                    time.sleep(3 * (attempt + 1))
            return None

        probe = fetch_row(0)
        if probe is None:
            print("  could not reach the rows API")
            return 2
        first_text = probe.get("text") or ""
        n_books = args.rows or 97        # num_rows_total = 97 = the 97 books
        print(f"  source: rows API · fetching up to {n_books} book(s)")

        def iter_docs():
            buf = [first_text]
            done = 1
            while True:
                if buf:
                    yield buf.pop(0)
                if done >= n_books:
                    break
                row = fetch_row(done)
                done += 1
                if row is None:
                    continue
                y = row.get("text")
                if y:
                    buf.append(y)
                    if done % 10 == 0:
                        print(f"    book {done}/{n_books}…", flush=True)

    ds = iter_docs()

    types = collections.Counter()
    n_tok = n_cov_exact = n_cov_folded = n_nonarabic = 0
    docs = 0
    t0 = time.time()
    wazan_buf: list[str] = []

    for text in ds:
        docs += 1
        for raw in (text or "").split():
            if not ARABIC_LETTER.search(raw):
                n_nonarabic += 1
                continue
            tok = norm_token(raw)
            if not tok:
                n_nonarabic += 1
                continue
            n_tok += 1
            types[tok] += 1
            if tok in keys:
                n_cov_exact += 1
            elif fold(tok) in folded:
                n_cov_folded += 1
            if args.wazan_sample and len(wazan_buf) < args.wazan_sample:
                wazan_buf.append(raw)
        if args.limit_docs and docs >= args.limit_docs:
            break
        if args.limit_tokens and n_tok >= args.limit_tokens:
            break
        if docs % 500 == 0:
            print(f"  {docs:>6,} docs  {n_tok:>12,} tokens  "
                  f"{100*n_cov_exact/max(n_tok,1):5.1f}% covered  "
                  f"({time.time()-t0:.0f}s)", flush=True)

    t_cov_types = sum(1 for t in types if t in keys)
    t_cov_types_f = sum(1 for t in types if fold(t) in folded)

    print("\n" + "=" * 88)
    print("RESULTS — report all three together; type alone misrepresents token coverage")
    print("=" * 88)
    print(f"  documents                     : {docs:,}")
    print(f"  tokens (Arabic-containing)    : {n_tok:,}")
    print(f"  non-Arabic units (skipped)    : {n_nonarabic:,}")
    print(f"  distinct types                : {len(types):,}")
    print(f"  elapsed                       : {time.time()-t0:.0f}s")
    print()
    print("  1. TYPE coverage")
    print(f"       exact  : {t_cov_types:>9,} / {len(types):,} = {100*t_cov_types/max(len(types),1):5.1f}%")
    print(f"       folded : {t_cov_types_f:>9,} / {len(types):,} = {100*t_cov_types_f/max(len(types),1):5.1f}%")
    print("  2. TOKEN coverage")
    print(f"       exact  : {n_cov_exact:>9,} / {n_tok:,} = {100*n_cov_exact/max(n_tok,1):5.1f}%")
    print(f"       exact+folded : {n_cov_exact+n_cov_folded:>9,} / {n_tok:,} = "
          f"{100*(n_cov_exact+n_cov_folded)/max(n_tok,1):5.1f}%")
    print("  3. MASKED TOKEN FRACTION (Head 2 loss = 0)")
    print(f"       exact  : {100*(1-n_cov_exact/max(n_tok,1)):5.1f}%")
    print(f"       folded : {100*(1-(n_cov_exact+n_cov_folded)/max(n_tok,1)):5.1f}%")

    # coverage by frequency band — shows where the misses actually live
    bands = [(1, 1, "hapax"), (2, 4, "2-4"), (5, 99, "5-99"), (100, 10**9, "100+")]
    print("\n  token coverage by type-frequency band (the misses are not uniform):")
    for lo, hi, label in bands:
        ts = [t for t, c in types.items() if lo <= c <= hi]
        if not ts:
            continue
        tot = sum(types[t] for t in ts)
        cov = sum(types[t] for t in ts if t in keys or fold(t) in folded)
        print(f"    {label:6} {len(ts):>9,} types  {tot:>12,} tokens  "
              f"{100*cov/max(tot,1):5.1f}% covered")

    if args.wazan_sample and wazan_buf:
        print("\n  HEAD-3 (wazān) on Tashkeela — BOUNDED SAMPLE, not corpus-wide")
        from camel_tools.disambig.mle import MLEDisambiguator
        from wazan_normalizer import normalize_from_analysis
        mle = MLEDisambiguator.pretrained("calima-msa-r13")
        ok = 0
        reasons = collections.Counter()
        n = 0
        B = 500
        for i in range(0, len(wazan_buf), B):
            chunk = wazan_buf[i:i + B]
            try:
                dis = mle.disambiguate(chunk)
            except Exception:
                continue
            for d in dis:
                n += 1
                a = d.analyses[0].analysis if d.analyses else {}
                rec = normalize_from_analysis(a) if a else {"wellformed_strict": False,
                                                            "reason": "no_analysis"}
                if rec.get("wellformed_strict") and rec.get("reason") == "ok" and rec.get("label"):
                    ok += 1
                else:
                    # name the failure precisely: reason 'ok' with a non-strict label is
                    # a DIFFERENT failure from an alignment refusal, and lumping them
                    # under 'ok' in a failure counter is how a number stops meaning
                    # anything. Same labelling as build_training_jsonl.py.
                    rr = rec.get("reason", "?")
                    if rr == "ok":
                        rr = "not_strict"
                    reasons[rr] += 1
        print(f"    sample size     : {n:,} tokens "
              f"({'SAMPLE — quote the sample size with it' if n < n_tok else 'full'})")
        print(f"    strict labels   : {ok:,} = {100*ok/max(n,1):.1f}%  (COVERAGE, not accuracy)")
        print(f"    masked fraction : {100*(1-ok/max(n,1)):5.1f}%")
        print(f"    reasons         : {dict(reasons.most_common(6))}")
        print("    Finding D applies here: quadrilateral (4-digit) labels are ~never")
        print("    produced by the MLE, so this masks them out rather than mislabelling.")

    (OUT / "tashkeela_coverage.json").write_text(__import__("json").dumps({
        "docs": docs, "tokens": n_tok, "non_arabic": n_nonarabic,
        "types": len(types), "type_cov_exact": t_cov_types,
        "token_cov_exact": n_cov_exact, "token_cov_folded": n_cov_exact + n_cov_folded,
        "dict_keys": len(keys), "provenance": prov,
        "limit_tokens": args.limit_tokens, "wazan_sample": args.wazan_sample,
    }, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT / 'tashkeela_coverage.json'}")
    print("REPORT AS COVERAGE. No gold wazān exists, so nothing here is an accuracy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
