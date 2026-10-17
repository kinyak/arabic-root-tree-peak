"""Corrected re-test: render against the FULL vocalized form, not the stem."""
import collections
import re

from camel_tools.disambig.mle import MLEDisambiguator

from paths import RAW as PD
DIAC = re.compile(r"[\u064b-\u0652\u0670]")
DIG = re.compile(r"[1-4]")


def render_sound(root, wazan, proclitic="", case_vowel=""):
    radicals = root.split(".") if "." in root else list(root.replace("-", ""))
    if len(radicals) != 3: return ""
    c1, c2, c3 = radicals
    stem = []
    for ch in wazan:
        if ch == "ف": stem.append(c1)
        elif ch == "ع": stem.append(c2)
        elif ch == "ل": stem.append(c3)
        else: stem.append(ch)
    return f"{proclitic}{''.join(stem)}{case_vowel}"


def normalize_wazan_pattern(raw_pattern, root):
    if not raw_pattern or raw_pattern == "None" or not root:
        return "NON_TEMPLATIC", False
    rads = root.split(".") if "." in root else list(root.replace("-", ""))
    if len(rads) != 3: return raw_pattern, False
    c1, c2, c3 = rads
    w = raw_pattern.replace("1", "ف").replace("2", "ع").replace("3", "ل")
    if c2 == c3 and c2 in w:
        idx = w.rfind(c2); w = w[:idx] + "ل" + w[idx + 1:]
    return w, True


def classify_root(root):
    rads = root.split(".") if "." in root else list(root.replace("-", ""))
    if len(rads) != 3: return "IRREGULAR"
    c1, c2, c3 = rads
    if c2 == c3: return "MUDAAF"
    if c1 in "وي": return "MITHAL"
    if c2 in "ويا": return "AJWAF"
    if c3 in "ويى": return "NAQIS"
    if "ء" in (c1, c2, c3) or "أ" in (c1, c2, c3): return "MAHMUZ"
    return "SALIM"


mle = MLEDisambiguator.pretrained("calima-msa-r13")

print("=" * 78)
print("A. Their geminate fix, on the ACTUAL CALIMA output for مضعّف roots")
print("=" * 78)
for w in ["مَدَّ", "رَدَّ", "شَدَّ", "جَلَّ", "حَبَّ", "عَلَّمَ"]:
    a = mle.disambiguate([w])[0].analyses[0].analysis
    raw = a.get("pattern"); rt = a.get("root")
    out, ok = normalize_wazan_pattern(raw, rt)
    n_slots = sum(out.count(x) for x in "فع")
    print(f"  {w:9} root={rt:9} raw={str(raw):10} -> wazan={out!r:12} ok={ok}  "
          f"radical-slots={n_slots}/3")
print()
print("  -> for مُضاعَف roots CALIMA emits digits {1,2} only and marks the doubling with a")
print("     SHADDA. It does NOT write a literal consonant. So the guard `c2 in w` looks for")
print("     a letter that is never there, the branch never fires, and the result has only")
print("     TWO radical slots. The proposed fix does not fix geminates.")

print()
print("=" * 78)
print("B. render_sound vs the FULL vocalized form (corrected comparison)")
print("=" * 78)
toks = []
with open(f"{PD}/ar_padt-ud-train.conllu", encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#") or not line.strip():
            if len(toks) >= 1500: break
            continue
        c = line.rstrip("\n").split("\t")
        if len(c) < 10 or "-" in c[0] or "." in c[0] or c[3] == "PUNCT": continue
        if not re.search(r"[\u0621-\u064a]", c[1]): continue
        toks.append(c[1])
toks = toks[:1500]
dis = [d for d in mle.disambiguate(toks) if d.analyses]

per = collections.defaultdict(lambda: [0, 0, 0])
examples = []
for d in dis:
    a = d.analyses[0].analysis
    if a.get("source") != "lex" or not a.get("root"): continue
    raw, full = a.get("pattern"), a.get("diac")
    if not raw or not full or full in ("None", "na"): continue
    w, ok = normalize_wazan_pattern(raw, a["root"])
    if not ok or DIG.search(w): continue
    cls = classify_root(a["root"])
    per[cls][0] += 1
    try:
        got = render_sound(a["root"], w)
    except Exception:
        continue
    if got == full:
        per[cls][1] += 1
    elif DIAC.sub("", got) == DIAC.sub("", full):
        per[cls][2] += 1
    elif len(examples) < 10:
        examples.append((full, got, a["root"], raw))

print(f"  {'class':<10} {'tried':>7} {'EXACT':>8} {'exact%':>8} {'skeleton%':>10}")
ta = te = ts = 0
for cls, (a_, e_, s_) in sorted(per.items(), key=lambda x: -x[1][0]):
    ta += a_; te += e_; ts += s_
    print(f"  {cls:<10} {a_:>7} {e_:>8} {100*e_/max(a_,1):7.1f}% {100*(e_+s_)/max(a_,1):9.1f}%")
print(f"  {'TOTAL':<10} {ta:>7} {te:>8} {100*te/max(ta,1):7.1f}% {100*(te+ts)/max(ta,1):9.1f}%")
print()
print("  sample mismatches (CALIMA said -> rule produced):")
for full, got, rt, raw in examples[:8]:
    print(f"    want {full!r:16} got {got!r:16} root={rt:10} raw={raw!r}")
