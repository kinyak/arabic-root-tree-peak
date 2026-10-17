"""Verify SPEC-REV5 claims: root counts, 3-slot adequacy, and the new §6 code."""
import arramooz, os, sqlite3, glob, collections, re, sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from camel_tools.disambig.mle import MLEDisambiguator

from paths import RAW as PD
DIAC = re.compile(r"[\u064b-\u0652\u0670]")

print("=" * 76)
print("CLAIM 1 — §3.1 calls 20,614 the count of 'gold surface roots' from PADT")
print("=" * 76)
surf, roots = set(), set()
with open(f"{PD}/ar_padt-ud-train.conllu", encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#"):
            continue
        c = line.rstrip("\n").split("\t")
        if len(c) < 10 or "-" in c[0] or "." in c[0]:
            continue
        surf.add(DIAC.sub("", c[1]))
        m = re.search(r"(?:^|\|)Root=([^|]+)", c[9])
        if m:
            roots.add(m.group(1).strip())
print(f"  distinct SURFACES : {len(surf):,}")
print(f"  distinct ROOTS    : {len(roots):,}")
print(f"  -> 20,614 is the SURFACE count. The root count is {len(roots):,}, i.e. "
      f"{len(surf)/len(roots):.1f}x smaller.")
print(f"  -> §3.1 mislabels it. The dictionary keyed on surfaces is fine, but calling it")
print(f"     'surface roots' conflates two different quantities.")

print()
print("=" * 76)
print("CLAIM 2 — §2.1's 28x28x28 tensor (3 slots) vs the settled arramooz lexicon")
print("=" * 76)
base = os.path.dirname(arramooz.__file__)
db = glob.glob(os.path.join(base, "**", "arabicdictionary.sqlite"), recursive=True)[0]
c = sqlite3.connect(db)
allroots = set()
for t in ("nouns", "verbs"):
    for (r,) in c.execute("select root from " + t + " where root is not null and root<>''"):
        allroots.add(r.strip())
lens = collections.Counter(len(r) for r in allroots)
print("  root lengths in arramooz:")
for L in sorted(lens):
    print(f"    {L} radicals: {lens[L]:,}  ({100*lens[L]/len(allroots):.1f}%)")
quad = [r for r in allroots if len(r) == 4]
print(f"\n  sample 4-radical roots: {sorted(quad)[:10]}")
print(f"\n  -> {lens.get(4,0):,} roots ({100*lens.get(4,0)/len(allroots):.1f}%) need a FOURTH slot.")
print(f"     A 3-coordinate tensor cannot index them at all.")

print()
print("  --- and the wazan inventory itself contains 4-slot templates ---")
wz = [w for (w,) in c.execute("select distinct wazn from nouns where wazn is not null and wazn<>''")]
four = []
for w in wz:
    plain = DIAC.sub("", w)
    if plain.count("ل") >= 2:
        four.append(w)
print(f"  wazan strings with 2+ lam slots (quadriliteral templates): {len(four)}")
for w in sorted(four)[:10]:
    print(f"     {w!r}")
print(f"\n  -> the target vocabulary itself is not 3-slot. §2.1 and §4 (Predict (C1,C2,C3))")
print(f"     must become 4-slot, or those {lens.get(4,0):,} roots are unrepresentable.")

print()
print("=" * 76)
print("CLAIM 3 — §6 strip_case_from_wazan: does it over-strip a radical alif?")
print("=" * 76)
def strip_case(pat):
    pat = re.sub(r'ً?اً?$', '', pat)
    pat = re.sub(r'[ًٌٍَُِْ]+$', '', pat)
    return pat
TESTS = [("1َ2َ3ُ", "nominal, damma"), ("1َ2َ3ً", "tanween fath"),
         ("1َ2َ3ًا", "tanween fath + alif"), ("1َ2َا", "defective: alif IS radical 3"),
         ("1َ2ا", "defective, bare"), ("1َ2َى", "defective: alef maqsura"),
         ("1َ2ِي3َةُ", "nominal with ta marbuta"), ("1َ2َّ", "geminate"),
         ("1َ2ُّ", "geminate with vowel")]
for p, note in TESTS:
    print(f"  {p:12} -> {strip_case(p):12}  {note}")

print()
print("  ORDER DEPENDENCY (unspecified in the spec):")
def expand(pat):
    def f(m):
        v = m.group(2) or m.group(4) or ''
        return f"{m.group(1)}{v}3{v}"
    return re.sub(r'(2)([َُِْ]*)(ّ)([َُِْ]*)', f, pat)
for p in ["1َ2َّ", "1َ2ُّ"]:
    a = strip_case(expand(p))
    b = expand(strip_case(p))
    print(f"  {p:8}  expand->strip = {a:10}   strip->expand = {b:10}  "
          f"{'SAME' if a==b else '*** DIFFERENT ***'}")

print()
print("=" * 76)
print("CLAIM 4 — §6 extract_clean_lemma_from_lex on real lex values")
print("=" * 76)
mle = MLEDisambiguator.pretrained("calima-msa-r13")
def clean(raw):
    assert raw and isinstance(raw, str), "empty!"
    s = DIAC.sub('', raw).replace('ـ', '').strip()
    assert len(s) > 0, "empty after strip"
    return s
for w in ["كتاب", "مدرسة", "اليوم", "رأى", "قال", "علم"]:
    d = mle.disambiguate([w])[0]
    if not d.analyses:
        continue
    raw = d.analyses[0].analysis.get("lex")
    try:
        print(f"  {w:8} lex={raw!r:16} -> key={clean(raw)!r}")
    except AssertionError as e:
        print(f"  {w:8} lex={raw!r:16} -> ASSERT {e}")
print()
print("  -> stripping works now. But note رأى -> 'راووند' is CALIMA GARBAGE that passes")
print("     the non-empty assertion. The assertion catches empty, not wrong.")
