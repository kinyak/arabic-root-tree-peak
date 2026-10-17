"""Execute the proposed solutions verbatim against real data and report what breaks."""
import collections
import re

from camel_tools.morphology.database import MorphologyDB
from camel_tools.disambig.mle import MLEDisambiguator

from paths import RAW as PD
DIAC = re.compile(r"[\u064b-\u0652\u0670]")
DIG = re.compile(r"[1-4]")

# ======================================================= their R1 code, verbatim
def render_sound(root, wazan, proclitic="", case_vowel=""):
    radicals = root.split(".") if "." in root else list(root.replace("-", ""))
    if len(radicals) != 3:
        return ""
    c1, c2, c3 = radicals
    stem = []
    for ch in wazan:
        if ch == "ف": stem.append(c1)
        elif ch == "ع": stem.append(c2)
        elif ch == "ل": stem.append(c3)
        else: stem.append(ch)
    return f"{proclitic}{''.join(stem)}{case_vowel}"

# ======================================================= their M1 code, verbatim
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

def normalize_wazan_pattern(raw_pattern, root):
    if not raw_pattern or raw_pattern == "None" or not root:
        return "NON_TEMPLATIC", False
    rads = root.split(".") if "." in root else list(root.replace("-", ""))
    if len(rads) != 3:
        return raw_pattern, False
    c1, c2, c3 = rads
    w = raw_pattern.replace("1", "ف").replace("2", "ع").replace("3", "ل")
    if c2 == c3 and c2 in w:
        idx = w.rfind(c2)
        w = w[:idx] + "ل" + w[idx + 1:]
    return w, True

# ======================================================= their M2 code, verbatim
def normalize_root_canonical(root_str):
    if not root_str: return ""
    rads = root_str.split(".") if "." in root_str else list(root_str.replace("-", ""))
    out = []
    for r in rads:
        if r in "أإآؤئء": out.append("ء")
        elif r == "ى": out.append("ي")
        elif r == "ة": out.append("ه")
        else: out.append(r)
    return ".".join(out)

def evaluate_root_agreement(calima_root, gold_qac_root):
    return normalize_root_canonical(calima_root) == normalize_root_canonical(gold_qac_root)

print("=" * 78)
print("TEST 1 — does M2's comparison work at all?  (CALIMA = Arabic, QAC = Buckwalter)")
print("=" * 78)
for cal, qac in [("ك.ت.ب", "ktb"), ("ط.ل.ب", "Tlb"), ("ع.ل.م", "Elm"), ("ق.و.ل", "qwl"),
                 ("س.أ.ل", "sAl"), ("ز.ل.ز.ل", "zlzl")]:
    print(f"  CALIMA={cal:12} QAC={qac:6} -> agreement={evaluate_root_agreement(cal, qac)}")
print()
print("  -> QAC roots are in BUCKWALTER (ktb, Tlb, Elm). normalize_root_canonical() never")
print("     transliterates, so it can only ever return False. T5 cannot run as written.")

print()
print("=" * 78)
print("TEST 2 — M1: does CALIMA actually omit the 3rd digit on geminate roots?")
print("=" * 78)
mle = MLEDisambiguator.pretrained("calima-msa-r13")
for w in ["مَدَّ", "رَدَّ", "شَدَّ", "جَلَّ", "حَبَّ", "عَلَّمَ", "زَلْزَلَ"]:
    d = mle.disambiguate([w])[0]
    if not d.analyses:
        print(f"  {w}: no analysis"); continue
    a = d.analyses[0].analysis
    pat = a.get("pattern")
    digits = "".join(sorted(set(DIG.findall(pat or ""))))
    print(f"  {w:10} root={a.get('root','?'):12} pattern={str(pat):16} digits={{{digits}}}")

print()
print("=" * 78)
print("TEST 3 — M1's normalize_wazan_pattern: digit 4 is not handled")
print("=" * 78)
for pat, rt in [("1َ2ْ3َ4َ", "ز.ل.ز.ل"), ("1َ2َ3َ", "ك.ت.ب"), ("1َ2َّ3َ", "ع.ل.م")]:
    w, ok = normalize_wazan_pattern(pat, rt)
    print(f"  {pat:14} root={rt:12} -> wazan={w!r:20} is_valid={ok}")
print()
print("  -> digit '4' survives into the wazan as a literal '4'. Inconsistent with the")
print("     proposed tuple, which maps 4->ل. Quadriliteral roots are dropped earlier anyway")
print("     (classify_root returns IRREGULAR for 4 radicals).")

print()
print("=" * 78)
print("TEST 4 — R1 render_sound on quadriliteral and hamzated roots")
print("=" * 78)
cases = [
    ("ز.ل.ز.ل", "فَعْلَل", "quadriliteral زلزل"),
    ("و.س.و.س", "فَعْلَل", "quadriliteral وسوس"),
    ("ك.ت.ب", "فَعَل", "sound ك-ت-ب (control)"),
    ("م.د.ر.س", "فَعْلَل", "quadriliteral-ish"),
    ("س.أ.ل", "مَفْعُول", "hamzated, needs مَسْؤُول not مَسْأُول"),
    ("ق.ر.أ", "مَفْعُول", "hamzated, needs مَقْرُوء"),
]
for rt, wz, note in cases:
    out = render_sound(rt, wz)
    print(f"  root={rt:12} wazān={wz:10} -> {out!r:16} {note}")
print()
print("  -> quadriliteral: BOTH ل slots get c3, so the 4th radical is lost.")
print("  -> hamzated: the seat is chosen by pure substitution, so hamza-seat rules")
print("     (همزة على واو/ي/ألف/سطر) are violated. MAHMUZ does not belong in the 'sound' set.")

print()
print("=" * 78)
print("TEST 5 — the real coverage question: does render_sound reproduce CALIMA's own stem?")
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

per_class = collections.defaultdict(lambda: [0, 0])
for d in dis:
    a = d.analyses[0].analysis
    if a.get("source") != "lex" or not a.get("root"): continue
    raw = a.get("pattern")
    stem = a.get("stem")
    if not raw or not stem or stem in ("None", "na"): continue
    w, ok = normalize_wazan_pattern(raw, a["root"])
    if not ok or DIG.search(w): continue
    cls = classify_root(a["root"])
    per_class[cls][0] += 1
    try:
        got = render_sound(a["root"], w)
    except Exception:
        continue
    if DIAC.sub("", got) == DIAC.sub("", stem):
        per_class[cls][1] += 1

print(f"  {'class':<12} {'attempted':>10} {'matched stem':>13} {'rate':>8}")
tot_a = tot_m = 0
for cls, (a_, m_) in sorted(per_class.items(), key=lambda x: -x[1][0]):
    tot_a += a_; tot_m += m_
    print(f"  {cls:<12} {a_:>10} {m_:>13} {100*m_/max(a_,1):7.1f}%")
print(f"  {'TOTAL':<12} {tot_a:>10} {tot_m:>13} {100*tot_m/max(tot_a,1):7.1f}%")
print()
print("  NOTE: this compares only consonant skeletons (diacritics stripped), so it is a")
print("  LENIENT test. A stricter test would compare the vocalization too.")
