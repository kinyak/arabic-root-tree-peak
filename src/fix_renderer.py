"""Diagnose the render_sound bug and test the minimal fix.

Diagnosis: render_sound round-trips the pattern through ف/ع/ل and then substitutes
those three ARABIC LETTERS back to radicals. But real Arabic affixes contain the same
letters — most obviously the definite article ال. So `ل` in "ال" is overwritten by c3.

Fix: never round-trip. Substitute the DIGITS directly in the raw pattern.
    'ال1ا2ِ3ِ'  ->  replace 1,2,3 with the radicals  ->  'الصادِرِ'   (exact)
"""
import collections
import re

from camel_tools.disambig.mle import MLEDisambiguator

from paths import RAW as PD
DIAC = re.compile(r"[\u064b-\u0652\u0670]")
DIG = re.compile(r"[1-4]")
mle = MLEDisambiguator.pretrained("calima-msa-r13")

SLOT = {"1": 0, "2": 1, "3": 2, "4": 3}


def render_direct(root, raw_pattern):
    """Substitute radical digits in-place. No ف/ع/ل round-trip, no clitic stripping."""
    if not raw_pattern or raw_pattern in ("None", "na") or not root:
        return None, "no_pattern"
    rads = root.split(".")
    if "#" in rads:
        return None, "root_has_hash"
    digits = DIG.findall(raw_pattern)
    ds = set(digits)
    if ds not in ({"1", "2", "3"}, {"1", "2", "3", "4"}):
        return None, "digit_set_incomplete"
    if len(digits) != len(ds):
        return None, "repeated_digit"
    if len(rads) != len(ds):
        return None, "root_len_mismatch"
    out = []
    for ch in raw_pattern:
        if ch in SLOT:
            out.append(rads[SLOT[ch]])
        else:
            out.append(ch)
    return "".join(out), "ok"


print("=" * 78)
print("A. The diagnosis, demonstrated on one token")
print("=" * 78)
raw, root = "ال1ا2ِ3ِ", "ص.د.ر"
print(f"  raw pattern : {raw}")
print(f"  root        : {root}")
print(f"  their route : pattern -> 'الفاعِلِ' -> substitute ف,ع,ل -> 'ارصادِرِ'  (ال destroyed)")
print(f"  direct route: substitute digits in place            -> ", end="")
print(f"{render_direct(root, raw)[0]!r}")
print()
print("  -> ف/ع/ل are a HUMAN display convention. Using them as internal slot markers")
print("     is unsafe because ال, ا, و, ي, ت also appear as literal affixes.")

print()
print("=" * 78)
print("B. Coverage of the direct rule, vs the previous 63.1%")
print("=" * 78)
toks = []
with open(f"{PD}/ar_padt-ud-train.conllu", encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#") or not line.strip():
            if len(toks) >= 4000: break
            continue
        c = line.rstrip("\n").split("\t")
        if len(c) < 10 or "-" in c[0] or "." in c[0] or c[3] == "PUNCT": continue
        if not re.search(r"[\u0621-\u064a]", c[1]): continue
        toks.append(c[1])
toks = toks[:4000]
dis = [d for d in mle.disambiguate(toks) if d.analyses]

per = collections.defaultdict(lambda: [0, 0])
reasons = collections.Counter()
examples = []
for d in dis:
    a = d.analyses[0].analysis
    if a.get("source") != "lex" or not a.get("root"):
        continue
    full = a.get("diac")
    if not full or full in ("None", "na"):
        continue
    got, why = render_direct(a["root"], a.get("pattern"))
    reasons[why] += 1
    if why != "ok":
        continue
    L = a["root"].replace(".", "")
    cls = ("quadriliteral" if len(L) == 4 else
           "doubled" if L[1] == L[2] else
           "hollow" if L[1] in "وي" else
           "assimilated" if L[0] in "وي" else
           "defective" if L[2] in "وي" else "sound")
    per[cls][0] += 1
    if got == full:
        per[cls][1] += 1
    elif len(examples) < 10:
        examples.append((full, got, a["root"], a.get("pattern")))

print(f"  {'class':<14} {'rendered':>9} {'EXACT':>8} {'rate':>8}")
ta = te = 0
for cls, (a_, e_) in sorted(per.items(), key=lambda x: -x[1][0]):
    ta += a_; te += e_
    print(f"  {cls:<14} {a_:>9} {e_:>8} {100*e_/max(a_,1):7.1f}%")
print(f"  {'TOTAL':<14} {ta:>9} {te:>8} {100*te/max(ta,1):7.1f}%")
print()
print("  coverage gate reasons (why tokens were skipped):")
for k, v in reasons.most_common():
    print(f"    {v:>6}  {k}")
print()
if examples:
    print("  remaining mismatches:")
    for full, got, rt, raw in examples[:8]:
        print(f"    want {full!r:18} got {got!r:18} root={rt:11} raw={raw!r}")
