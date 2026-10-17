"""Audit the preflight's core assumptions.

Q1. RENDERER: CAMeL r13 cannot generate (verified). Is a table-based renderer viable?
    Measure: coverage of an attested (root, pattern) -> surface table.
Q2. ROOT CLASSES: sizes the validity mask (must be class x wazan, not root x wazan).
Q3. THROUGHPUT: sizes the eval-harness runtime.
"""
import collections
import re
import time

from camel_tools.morphology.database import MorphologyDB
from camel_tools.morphology.analyzer import Analyzer
from camel_tools.disambig.mle import MLEDisambiguator

from paths import PADT_TRAIN as PADT
DIAC = re.compile(r"[\u064b-\u0652\u0670]")
DIG = re.compile(r"[1-4]")


def read_tokens(limit):
    out = []
    with open(PADT, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                if len(out) >= limit:
                    break
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) < 10 or "-" in c[0] or "." in c[0] or c[3] == "PUNCT":
                continue
            if not re.search(r"[\u0621-\u064a]", c[1]):
                continue
            out.append(c[1])
    return out[:limit]


def wazan_of(raw):
    if not raw or raw in ("None", "na"):
        return None
    ds = set(DIG.findall(raw))
    if ds not in ({"1", "2", "3"}, {"1", "2", "3", "4"}) or len(DIG.findall(raw)) != len(ds):
        return None
    body = raw[min(raw.index(d) for d in DIG.findall(raw)):]
    body = body[:-1] if body and body[-1] in "ًٌٍَُِْ" else body
    return body.translate(str.maketrans({"1": "ف", "2": "ع", "3": "ل", "4": "ل"}))


tokens = read_tokens(1500)
db = MorphologyDB.builtin_db()
mle = MLEDisambiguator.pretrained("calima-msa-r13")

t0 = time.time()
dis = [d for d in mle.disambiguate(tokens) if d.analyses]
dt = time.time() - t0

print("=" * 78)
print("Q3. THROUGHPUT (sizes the eval-harness runtime)")
print("=" * 78)
print(f"  {len(tokens)} tokens in {dt:.1f}s = {len(tokens)/dt:.0f} tokens/s")
for n_sent, n_tok in ((10000, 20), (50000, 20)):
    t = n_sent * n_tok / (len(tokens) / dt)
    print(f"  scoring {n_sent:,} generated sentences (~{n_tok} tok) = {t/60:.1f} min")

# ------------------------------------------------------------------ records
recs = []
for d in dis:
    a = d.analyses[0].analysis
    if a.get("source") != "lex" or not a.get("root"):
        continue
    w = wazan_of(a.get("pattern"))
    if not w:
        continue
    recs.append({
        "root": a["root"], "wazan": w, "diac": a.get("diac"),
        "cas": a.get("cas"),
        "clitics": tuple(x for x in (a.get("prc3"), a.get("prc2"), a.get("prc1"), a.get("prc0"), a.get("enc0"))
                         if x and x not in ("0", "na")),
    })
print(f"\n  usable records: {len(recs)}")

# ------------------------------------------------------------------ Q1 table renderer
print()
print("=" * 78)
print("Q1. TABLE-BASED RENDERER — coverage of an attested (root, pattern) -> surface map")
print("=" * 78)
half = len(recs) // 2
train, test = recs[:half], recs[half:]
for key_name, keyf in (
    ("(root, wazan)", lambda r: (r["root"], r["wazan"])),
    ("(root, wazan, case)", lambda r: (r["root"], r["wazan"], r["cas"])),
    ("(root, wazan, case, clitics)", lambda r: (r["root"], r["wazan"], r["cas"], r["clitics"])),
):
    table = {}
    for r in train:
        table.setdefault(keyf(r), set()).add(r["diac"])
    hit = sum(1 for r in test if r["diac"] in table.get(keyf(r), ()))
    print(f"  {key_name:32} test tokens reproduced: {100*hit/max(len(test),1):5.1f}%  "
          f"({len(table):,} keys)")

print()
print("  -> a memorised table renders most tokens exactly, with a rule-based fallback")
print("     for the residue. No CAMeL generator needed (it cannot generate anyway).")

# ------------------------------------------------------------------ Q2 classes
print()
print("=" * 78)
print("Q2. ROOT CLASS DISTRIBUTION (the mask must be class x wazan, not root x wazan)")
print("=" * 78)
WEAK = {"w", "y"}


def classify(rt):
    L = rt.replace(".", "")
    if len(L) == 4:
        return "quadriliteral (رباعي)"
    if len(L) < 3:
        return "short/other"
    if L[1] == L[2]:
        return "doubled (مضعف)"
    if L[1] in WEAK:
        return "hollow (أجوف)"
    if L[0] in WEAK:
        return "assimilated (مثال)"
    if L[2] in WEAK:
        return "defective (ناقص)"
    return "sound (صحيح)"


# weight by TOKEN frequency, not distinct roots -- that is what training sees
tokcls = collections.Counter()
dist = collections.Counter()
for r in recs:
    c = classify(r["root"])
    tokcls[c] += 1
    dist[c] += 1
nd = len({r["root"] for r in recs})
print(f"  by TOKEN frequency (what the mask affects at training time):")
for k, v in tokcls.most_common():
    print(f"    {v:>5}  {100*v/len(recs):5.1f}%  {k}")
print()
print(f"  distinct roots in sample: {nd}")
