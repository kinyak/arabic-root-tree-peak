"""Run the handoff's REVISED §7 extract_morph_labels() against real CALIMA output.

Question: does it actually separate wazan from clitic and case, as it claims?
"""
import collections
import re

from camel_tools.morphology.database import MorphologyDB
from camel_tools.morphology.analyzer import Analyzer
from camel_tools.disambig.mle import MLEDisambiguator

from paths import PADT_TRAIN as PADT, QAC_TXT

# ---------------------------------------------------------------- their code, verbatim
def extract_morph_labels(analysis: dict):
    if analysis.get("source") != "lex" or not analysis.get("root"):
        return None

    root = analysis.get("root")
    raw_pattern = analysis.get("pattern")
    cas_code = analysis.get("cas")

    case_target_map = {"n": "NOMINATIVE", "a": "ACCUSATIVE", "g": "GENITIVE",
                       "u": None, "na": None}
    case_label = case_target_map.get(cas_code, None)

    proclitics = [analysis.get("prc3"), analysis.get("prc2"),
                  analysis.get("prc1"), analysis.get("prc0")]
    active_clitics = [p for p in proclitics if p and p != "0"]

    if raw_pattern and raw_pattern != "None":
        translation_table = str.maketrans({"1": "ف", "2": "ع", "3": "ل", "4": "ل"})
        wazan = raw_pattern.translate(translation_table)
    else:
        wazan = "NON_TEMPLATIC"

    return {"root": root, "wazan": wazan, "case_label": case_label, "clitics": active_clitics}


# ---------------------------------------------------------------- sample
tokens = []
with open(PADT, encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#") or not line.strip():
            if len(tokens) >= 2000:
                break
            continue
        c = line.rstrip("\n").split("\t")
        if len(c) < 10 or "-" in c[0] or "." in c[0] or c[3] == "PUNCT":
            continue
        if not re.search(r"[\u0621-\u064a]", c[1]):
            continue
        tokens.append(c[1])
tokens = tokens[:2000]

mle = MLEDisambiguator.pretrained("calima-msa-r13")
dis = [d for d in mle.disambiguate(tokens) if d.analyses]

kept, dropped = [], 0
for d in dis:
    r = extract_morph_labels(d.analyses[0].analysis)
    if r is None:
        dropped += 1
    else:
        kept.append(r)

print("=" * 78)
print(f"tokens in        : {len(dis)}")
print(f"kept by filter   : {len(kept)}  ({100*len(kept)/len(dis):.1f}%)")
print(f"dropped entirely : {dropped}  ({100*dropped/len(dis):.1f}%)  <- case label lost too")

print()
print("=" * 78)
print("PROBLEM A — is the clitic actually REMOVED from the wazan?")
print("=" * 78)
ARTIC = "\u0627\u0644"          # ال
with_al = [r for r in kept if r["wazan"].startswith(ARTIC) and "\u0627\u0644" in r["wazan"][:2]]
print(f"  wazan values still starting with 'ال': {len(with_al)}")
for r in with_al[:8]:
    print(f"     wazan={r['wazan']!r:26} clitics={r['clitics']}")
print()
print("  -> the function returns clitics in a separate LIST but never strips them from")
print("     the wazan string. Head 3's target is still contaminated by the article.")

print()
print("=" * 78)
print("PROBLEM B — is the CASE VOWEL still inside the wazan?")
print("=" * 78)
DIAC = re.compile(r"[\u064b-\u0652\u0670]")
raised = [r for r in kept if r["case_label"] and DIAC.sub("", r["wazan"]) != r["wazan"].rstrip("".join("ًٌٍَُِْ"))]
# simpler: does the wazan end with a diacritic AND have a case label?
end_diac = [r for r in kept if r["wazan"] and r["wazan"][-1] in "ًٌٍَُِْ" and r["case_label"]]
print(f"  wazan ending in a diacritic while case_label is set: {len(end_diac)} / {len(kept)}")
for r in end_diac[:6]:
    print(f"     wazan={r['wazan']!r:24} case={r['case_label']}")
print()
print("  -> Head 5's answer is still sitting inside Head 3's target. The two heads")
print("     remain entangled, which is exactly what §4.1 says must be avoided.")

print()
print("=" * 78)
print("PROBLEM C — do the junk patterns survive?")
print("=" * 78)
junk = [r for r in kept if not re.search(r"[فعل]", r["wazan"])]
print(f"  wazan with no ف/ع/ل after translation (no radical digits were present): {len(junk)}")
print(f"     ({100*len(junk)/len(kept):.1f}% of kept)  examples: "
      f"{[r['wazan'] for r in junk[:8]]}")

print()
print("=" * 78)
print("PROBLEM D — how many DISTINCT wazan values does Head 3 get?")
print("=" * 78)
raw_w = collections.Counter(r["wazan"] for r in kept)
stripped = collections.Counter(DIAC.sub("", r["wazan"]).strip("ًٌٍَُِْ") for r in kept)
print(f"  distinct as returned by §7      : {len(raw_w)}")
print(f"  distinct after removing diacritics: {len(stripped)}")
print(f"  top 8 as returned: {[w for w, _ in raw_w.most_common(8)]}")

# ---------------------------------------------------------------- permutation test
print()
print("=" * 78)
print("CLAIM CHECK — §2.1 'naturally captures الاشتقاق الأكبر (consonant permutations)'")
print("=" * 78)
roots = set()
with open(str(QAC_TXT), encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("LOCATION"):
            continue
        pts = line.split("\t")
        if len(pts) < 4:
            continue
        for t in pts[3].split("|"):
            if t.startswith("ROOT:"):
                roots.add(t[5:])

pairs = []
seen = set()
for r in roots:
    if len(r) != 3:
        continue
    for p in (r[1] + r[0] + r[2], r[0] + r[2] + r[1], r[2] + r[1] + r[0], r[1] + r[2] + r[0],
              r[2] + r[0] + r[1]):
        if p in roots and p != r and (p, r) not in seen:
            seen.add((r, p))
            pairs.append((r, p))
print(f"  Quranic roots that are PERMUTATIONS of another Quranic root: {len(pairs)} pairs")
print(f"  examples: {pairs[:10]}")
print()
print("  Under the factorization e(C1) | e(C2) | e(C3) with a SEPARATE table per position,")
print("  two permutations share at most one position's embedding -> no enforced similarity.")
print("  So the mechanism does NOT produce the claimed effect; capturing it would need a")
print("  position-agnostic radical embedding plus an explicit permutation term.")
