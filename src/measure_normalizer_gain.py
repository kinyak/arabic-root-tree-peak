"""Measure the corrected normalizer against the SPEC-REV5 version on real data.

Usage:
    .venv/Scripts/python.exe src/measure_normalizer_gain.py [--limit 6000]

The default --limit is 6000, which is the sample the published 31.7% / 53.6%
figures were measured on — keep it the default so those numbers stay comparable.
This project's rule: quote the limit with the number, because smaller limits shift
the corpus-scale values by ~2pp (START-HERE.md §9).

REQUIRES the PADT corpora (CC BY-NC-SA, deliberately untracked). Run
    cd data/raw && sha256sum -c CHECKSUMS.sha256
after re-fetching.
"""
import argparse
import re
import sys, collections

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from wazan_normalizer import (normalize_wazan, normalize_from_analysis,
                              expand_geminate_ungated_rev8,
                              _map_missing_slot_literal, strip_case,
                              strip_proclitic)
from camel_tools.disambig.mle import MLEDisambiguator

from paths import PADT_TRAIN, require

_ap = argparse.ArgumentParser()
_ap.add_argument("--limit", type=int, default=6000,
                 help="tokens to probe (6000 = the published protocol)")
_args = _ap.parse_args()
LIMIT = _args.limit
PD = str(require(PADT_TRAIN).parent)
DIAC = re.compile(r"[\u064b-\u0652\u0670]")
DIG = re.compile(r"[1-4]")

# ---- SPEC-REV5 version, verbatim
def spec_strip_case(pat):
    pat = re.sub(r"ً?اً?$", "", pat)
    pat = re.sub(r"[ًٌٍَُِْ]+$", "", pat)
    return pat

def spec_expand(pat):
    def f(m):
        v = m.group(2) or m.group(4) or ""
        return f"{m.group(1)}{v}3{v}"
    return re.sub(r"(2)([َُِْ]*)(ّ)([َُِْ]*)", f, pat)

mle = MLEDisambiguator.pretrained("calima-msa-r13")
toks = []
with open(f"{PD}/ar_padt-ud-train.conllu", encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#") or not line.strip():
            if len(toks) >= LIMIT: break
            continue
        c = line.rstrip("\n").split("\t")
        if len(c) < 10 or "-" in c[0] or "." in c[0] or c[3] == "PUNCT": continue
        if not re.search(r"[\u0621-\u064a]", c[1]): continue
        toks.append(c[1])
toks = toks[:LIMIT]
dis = mle.disambiguate(toks)

rows = []
for s, d in zip(toks, dis):
    if not d.analyses: continue
    a = d.analyses[0].analysis
    if a.get("source") != "lex": continue
    rows.append((s, a.get("root") or "", a.get("pattern") or "",
                 a.get("d3tok") or "", a.get("enc0") or "0"))

def clean(lab):
    if not lab: return None
    ds = set(DIG.findall(lab))
    if ds not in ({"1","2","3"}, {"1","2","3","4"}): return None
    if len(DIG.findall(lab)) != len(ds): return None
    if lab[-1] in "ًٌٍَُِْ": return None          # case vowel still present
    return lab

old_ok = new_ok = both_bad = n = 0
gated_ok = 0                    # rev 9: geminate expansion gated on C2 == C3
prc_ok = 0                      # + proclitic strip
full_ok = 0                     # + enclitic strip (normalize_from_analysis)
rev8_only = []                  # labels rev-8 accepted that the gate rejects
lost_to_prc = []                # labels accepted pre-strip, rejected post-strip
n_with_prc = n_with_enc = 0
prc_unstripped = enc_unstripped = 0
examples = []
proclitic_examples = []
for s, root, pat, d3tok, enc0 in rows:
    n += 1
    o = clean(spec_strip_case(spec_expand(pat)))
    # ---- rev 8 reference: UNGATED geminate expansion, reproduced locally so the
    # published 53.6% stays comparable instead of being silently replaced.
    rev8 = clean(strip_case(_map_missing_slot_literal(
        expand_geminate_ungated_rev8(pat), root), root))
    gated_lab, _ = normalize_wazan(pat, root)
    gated = clean(gated_lab)
    rec = normalize_from_analysis({"pattern": pat, "root": root, "d3tok": d3tok,
                                   "enc0": enc0})
    # row 4: proclitic stripped, enclitic NOT
    prc_lab = clean(normalize_wazan(pat, root, proclitic=rec["proclitic"])[0]
                    if rec["proclitic"] else gated_lab)
    # row 5: the full pipeline (proclitic + enclitic)
    pipe_lab = clean(rec["label"])
    if rec["proclitic"]: n_with_prc += 1
    if rec["enclitic"]: n_with_enc += 1
    if rec["proclitic"] and not rec["proclitic_stripped"]: prc_unstripped += 1
    if rec["enclitic_surface"] and not rec["enclitic_stripped"]: enc_unstripped += 1
    if o: old_ok += 1
    if rev8: new_ok += 1
    if gated: gated_ok += 1
    if prc_lab: prc_ok += 1
    if pipe_lab: full_ok += 1
    # WHY does adding the proclitic strip LOSE tokens? Row 3 counts labels that pass
    # `clean()` while STILL CARRYING the proclitic, and _map_missing_slot_literal
    # rewrites the pattern's LAST weak literal -- which, when the stem has none, is a
    # letter of the proclitic itself. That injects a radical digit OUTSIDE the stem
    # and the label passes the gate by accident. Record the cases instead of asserting.
    if gated and not prc_lab and len(lost_to_prc) < 10:
        lost_to_prc.append((s, pat, root, rec["proclitic"], gated_lab, prc_lab))
    if rev8 and not gated and len(rev8_only) < 8:
        rev8_only.append((s, pat, root, rev8, gated_lab))
    if not gated and pipe_lab and len(proclitic_examples) < 8:
        proclitic_examples.append((s, pat, rec["proclitic"], pipe_lab))
    if not o and rev8 and len(examples) < 8:
        examples.append((s, pat, rev8))

def pct(k):
    return f"{k:>6}  ({100*k/max(n,1):5.1f}%)"

print("=" * 84)
print(f"LABEL COVERAGE LADDER — {n} lex-backed PADT tokens (--limit {LIMIT})")
print("=" * 84)
print(f"  1. SPEC-REV5  (strip -> expand)          : {pct(old_ok)}")
print(f"  2. rev 8      (ungated geminate)         : {pct(new_ok)}   <- the published 53.6% row")
print(f"  3. rev 9      (geminate GATED on C2==C3) : {pct(gated_ok)}")
print(f"  4. + proclitic strip                     : {pct(prc_ok)}")
print(f"  5. + enclitic strip  (full pipeline)     : {pct(full_ok)}")
print()
print("  COVERAGE OF WELL-FORMED LABELS. Never accuracy: no public gold wazan exists.")
print()
print("  label entanglement, measured (not assumed):")
print(f"    pattern carries a proclitic  : {n_with_prc:>6}  ({100*n_with_prc/max(n,1):.1f}%)")
print(f"    pattern carries an ENCLITIC  : {n_with_enc:>6}  ({100*n_with_enc/max(n,1):.1f}%)")
print(f"    proclitic present, strip refused : {prc_unstripped}")
print(f"    enclitic  present, strip refused : {enc_unstripped}")

if rev8_only:
    print()
    print("  labels the rev-8 UNGATED expansion accepted and the gate now REJECTS")
    print("  (templatic shadda on a non-geminate root — the defect it fixes):")
    for s, pat, root, r8, g in rev8_only[:8]:
        print(f"    {s:12} pattern={pat:14} root={root:12} rev8={r8!r} gated={g!r}")

if examples:
    print()
    print("  usable only under the corrected order:")
    for s, pat, lab in examples:
        print(f"    {s:12} pattern={pat:12} -> label={lab!r}")

if proclitic_examples:
    print()
    print("  unusable until the PROCLITIC / ENCLITIC is stripped:")
    for s, pat, prc, lab in proclitic_examples:
        print(f"    {s:12} pattern={pat:14} proclitic={prc!r:6} -> label={lab!r}")

if lost_to_prc:
    print()
    print(f"  row 3 MINUS row 4 = {gated_ok - prc_ok} tokens. Row 3 accepted these labels")
    print("  ONLY because the proclitic was still in the pattern and a proclitic letter had")
    print("  been mapped into a radical slot (a digit OUTSIDE the stem, passing the gate by")
    print("  accident). Stripping the clitic removes the false positive:")
    for s, pat, root, prc, g, f in lost_to_prc:
        print(f"    {s:12} pattern={pat:14} root={root:11} prc={prc!r:6} "
              f"pre={g!r:14} post={f!r}")

print()
print("  NOTE: this measures LABEL usability on CALIMA output. It does not measure")
print("  morphological correctness -- that needs gold wazan labels, which do not exist")
print("  as a public resource. Same validation barrier as SPEC-REV5 Tier C.")
