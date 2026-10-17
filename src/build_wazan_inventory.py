"""LOCAL PREP, zero compute units.

Build the canonical wazan inventory by properly decomposing CALIMA patterns.

Decomposition policy (replaces the handoff's §7):
  1. junk filter     : source == 'lex' and root present
  2. structural gate : accept only patterns whose radical-digit set is EXACTLY
                       {1,2,3} (triliteral) or {1,2,3,4} (quadriliteral).
                       This is the single rule that kills `NTWS` and the malformed
                       repeated-radical forms (وسوس -> 'وَ2ْوَ4َ' has digits {2,4}).
  3. strip proclitic : drop leading run of NON-digit chars (safe: a true stem pattern
                       starts with a digit, e.g. '1ا2ِ3')
  4. strip case vowel: drop the trailing diacritic
  5. relabel         : 1->ف 2->ع 3->ل 4->ل
"""
import collections
import re

from camel_tools.morphology.database import MorphologyDB
from camel_tools.morphology.analyzer import Analyzer
from camel_tools.disambig.mle import MLEDisambiguator

from paths import PADT_TRAIN as PADT
DIAC = re.compile(r"[\u064b-\u0652\u0670]")
DIGITS = re.compile(r"[1-4]")


def decompose_pattern(raw, cas):
    """Return (wazan, verdict). Returns ('quarantined', reason) when unsure."""
    if not raw or raw in ("None", "na"):
        return None, "no_pattern"
    digits = DIGITS.findall(raw)
    ds = set(digits)
    if ds not in ({"1", "2", "3"}, {"1", "2", "3", "4"}):
        return None, "digit_set_" + "".join(sorted(ds) or ["none"])
    if len(digits) != len(ds):
        return None, "repeated_digit"
    # strip proclitic: everything before the first digit
    i = raw.find(digits[0]) if digits else 0
    stem = raw[raw.index(min(digits, key=lambda d: raw.index(d))):]
    stem = raw[min(raw.index(d) for d in digits):]
    # strip trailing case vowel
    body = stem[:-1] if stem and stem[-1] in "ًٌٍَُِْ" else stem
    # Relabel. A pattern that still ends in a letter+diacritic (e.g. '1َ2ِي3َة')
    # is a nominal pattern whose final letter is part of the template, not case.
    wazan = body.translate(str.maketrans({"1": "ف", "2": "ع", "3": "ل", "4": "ل"}))
    return wazan, "ok"


tokens = []
with open(PADT, encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#") or not line.strip():
            if len(tokens) >= 6000:
                break
            continue
        c = line.rstrip("\n").split("\t")
        if len(c) < 10 or "-" in c[0] or "." in c[0] or c[3] == "PUNCT":
            continue
        if not re.search(r"[\u0621-\u064a]", c[1]):
            continue
        tokens.append(c[1])
tokens = tokens[:6000]

mle = MLEDisambiguator.pretrained("calima-msa-r13")
dis = [d for d in mle.disambiguate(tokens) if d.analyses]

inv = collections.Counter()
verdicts = collections.Counter()
case_by_wazan = collections.defaultdict(collections.Counter)
for d in dis:
    a = d.analyses[0].analysis
    if a.get("source") != "lex" or not a.get("root"):
        verdicts["filtered_out"] += 1
        continue
    w, v = decompose_pattern(a.get("pattern"), a.get("cas"))
    verdicts[v] += 1
    if w:
        inv[w] += 1
        case_by_wazan[w][a.get("cas")] += 1

print("=" * 78)
print(f"sample: {len(dis)} tokens")
print("=" * 78)
for k, v in verdicts.most_common():
    print(f"  {v:>6}  {100*v/len(dis):5.1f}%  {k}")

print()
print("=" * 78)
print(f"CANONICAL WAZAN INVENTORY: {len(inv)} distinct")
print("=" * 78)
print(f"  (the handoff asserts ~70)")
print()
tot = sum(inv.values())
run = 0
for i, (w, c) in enumerate(inv.most_common(45), 1):
    run += c
    print(f"  {i:>3}. {w:<12} {c:>5}  {100*c/tot:5.2f}%  cum {100*run/tot:5.1f}%")
print()
print(f"  wazans covering 50% of tokens: ", end="")
s = 0
for i, (w, c) in enumerate(inv.most_common(), 1):
    s += c
    if s / tot >= 0.5:
        print(i)
        break
print(f"  wazans covering 90% of tokens: ", end="")
s = 0
for i, (w, c) in enumerate(inv.most_common(), 1):
    s += c
    if s / tot >= 0.9:
        print(i)
        break
print(f"  wazans seen exactly once      : {sum(1 for c in inv.values() if c == 1)}")
print()
print("--- sanity: four- and five-radical templates the 3D tensor cannot hold ---")
for w in list(inv)[:400]:
    if "ل" in w and w.count("ل") == 2 and len(DIAC.sub("", w)) >= 4:
        pass
print("  (quadriliteral templates present:", [w for w in inv if DIAC.sub("", w).count("ل") == 2][:8], ")")
