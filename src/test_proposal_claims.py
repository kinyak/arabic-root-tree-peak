"""Test the four claims from the user's proposal against real data.

C1. Does `source == 'lex'` remove the CALIMA junk (NTWS / backoff)?
C2. Does the proposed regex `isolate_pure_wazan_and_case` work on quadriliteral patterns?
C3. What are the real `cas` values? (user claims 'u'=Damma, 'a'=Fatha, 'i'=Kasra)
C4. What is the actual `source` distribution in CALIMA output?
"""
import collections
import re

from camel_tools.morphology.database import MorphologyDB
from camel_tools.morphology.analyzer import Analyzer
from camel_tools.disambig.mle import MLEDisambiguator

from paths import PADT_TRAIN as PADT

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

# ---------------------------------------------------------------- C4 + C1
src = collections.Counter()
for d in dis:
    src[d.analyses[0].analysis.get("source", "?")] += 1

print("=" * 74)
print("C4. `source` distribution in CALIMA output (best-ranked analysis)")
print("=" * 74)
for k, v in src.most_common():
    print(f"  {v:>6}  {100*v/len(dis):5.1f}%  {k}")

print()
print("=" * 74)
print("C1. Does filtering source=='lex' remove the junk?")
print("=" * 74)


def junk_scan(records, label):
    pats = collections.Counter()
    n = 0
    for a in records:
        p = a.get("pattern")
        if not p or p in ("None", "na"):
            continue
        n += 1
        pats[p] += 1
    if not n:
        print(f"  {label}: no patterns at all")
        return
    junk = sum(c for p, c in pats.items() if p == "backoff" or not re.search(r"[1-4]", p))
    print(f"  {label}: {n} with a pattern, {len(pats)} distinct, "
          f"junk(no digit/backoff) = {junk} ({100*junk/n:.1f}%)")
    print(f"     top 6: {[p for p, _ in pats.most_common(6)]}")


junk_scan([d.analyses[0].analysis for d in dis], "ALL sources")
junk_scan([d.analyses[0].analysis for d in dis
           if d.analyses[0].analysis.get("source") == "lex"], "source=='lex' only")
junk_scan([a for d in dis for a in [d.analyses[0].analysis]
           if a.get("root") and a.get("source") == "lex"], "lex AND has root")

# ---------------------------------------------------------------- C3
print()
print("=" * 74)
print("C3. Real `cas` values (user claims u=Damma, a=Fatha, i=Kasra)")
print("=" * 74)
cas = collections.Counter(d.analyses[0].analysis.get("cas", "?") for d in dis)
for k, v in cas.most_common():
    print(f"  {v:>6}  {100*v/len(dis):5.1f}%  cas={k!r}")
print()
print("  Official docs say: n=Nominative  a=Accusative  g=Genitive")
print("                     u=UNDEFINED   na=Not applicable")
print("  NOTE: 'i' is not a cas value at all.")

# ---------------------------------------------------------------- C2
print()
print("=" * 74)
print("C2. Testing the proposed regex on real quadriliteral patterns")
print("=" * 74)

ARABIC_DIACRITICS = re.compile(r"[\u064B-\u0652]")


def isolate_pure_wazan_and_case(raw_pattern: str):
    """Verbatim from the user's proposal."""
    if not raw_pattern or raw_pattern == "None":
        return None, None, None
    terminal_vowel = ""
    if raw_pattern[-1] in "ًٌٍَُِْ":
        terminal_vowel = raw_pattern[-1]
        pattern_body = raw_pattern[:-1]
    else:
        pattern_body = raw_pattern
    proclitic_match = re.match(r"^(ال|وَ|فَ|بِ|لِ|كَ|سَ|و|ف|ب|ل|ك|س)*", pattern_body)
    proclitic = proclitic_match.group(0) if proclitic_match else ""
    stem_pattern = pattern_body[len(proclitic):]
    translation_table = str.maketrans({"1": "ف", "2": "ع", "3": "ل", "4": "ل"})
    pure_wazan = stem_pattern.translate(translation_table)
    return proclitic, pure_wazan, terminal_vowel


TESTS = [
    ("ال1ا2ِ3ُ",      "الطالب — expect prog='ال', wazan='فَاعِل', case='ُ'"),
    ("1َ2َ3َ",        "كتب — no proclitic expected"),
    ("1َ2ِي3َةُ",     "مدينة — expect wazan='فَعِيلَة'"),
    ("وَ2ْوَ4َ",      "وسوس — ⚠️ starts with و; is it a clitic or pattern material?"),
    ("1َ2َ3",        "no terminal vowel"),
    ("1ُ2ْ3ُ",       "stem starts with 1, not a proclitic letter"),
    ("NTWS",         "the 17.9% junk value — what does the regex do?"),
    ("ال1َ2ِي3َةِ",   "المدينة"),
]
print(f"{'input':<16} {'proclitic':<10} {'wazan':<12} {'case':<5} note")
print("-" * 96)
for raw, note in TESTS:
    p, w, c = isolate_pure_wazan_and_case(raw)
    print(f"{raw:<16} {str(p):<10} {str(w):<12} {str(c):<5} {note}")
