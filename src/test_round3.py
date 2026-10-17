"""Test the proposed M6 tiers, the M1 geminate discriminator, and the T5 Buckwalter table."""
import collections
import re

from camel_tools.disambig.mle import MLEDisambiguator

from paths import RAW as PD
DIAC = re.compile(r"[\u064b-\u0652\u0670]")
DIG = re.compile(r"[1-4]")

# ================================================== their T5 Buckwalter table, verbatim
BW2AR = {
    "'": "ء", "|": "آ", ">": "أ", "&": "ؤ", "<": "إ", "}": "ئ",
    "A": "ا", "b": "ب", "p": "ة", "t": "ت", "v": "ث", "j": "ج",
    "H": "ح", "x": "خ", "d": "د", "z": "ذ", "r": "ر", "w": "و",
    "s": "س", "$": "ش", "S": "ص", "D": "ض", "T": "ط", "Z": "ظ",
    "E": "ع", "g": "غ", "_": "ـ", "f": "ف", "q": "ق", "k": "ك",
    "l": "ل", "m": "م", "n": "ن", "h": "ه", "Y": "ى", "y": "ي",
    "F": "ً", "N": "ٌ", "K": "ٍ", "a": "َ", "u": "ُ", "i": "ِ",
    "~": "ّ", "o": "ْ", "`": "ٰ", "{": "ٱ",
}

print("=" * 78)
print("TEST A — the Buckwalter table: two errors")
print("=" * 78)
print("  standard Buckwalter has  '*' = ذ   and   'z' = ز")
print(f"  their table has       '*' present? {'*' in BW2AR}   'z' -> {BW2AR.get('z')!r}")
print()
for bw, should_be in [("zrE", "زرع"), ("*kr", "ذكر"), ("*hb", "ذهب"), ("zhr", "زهر"),
                      ("*ll", "ذلل"), ("zyT", "زيط")]:
    got = "".join(BW2AR.get(c, c) for c in bw)
    flag = "OK " if got == should_be else "WRONG"
    print(f"  {bw:6} -> {got:6}  (should be {should_be:6}) {flag}")
print()
print("  -> 'z' is mapped to ذ instead of ز, and '*' (ذ) is missing entirely. Any root")
print("     containing ز or ذ mis-transliterates, so T5 would report false disagreements.")
print("  -> also: PADT uses a DIFFERENT scheme (.h=ح .s=ص ^s=ش _h=خ), so one table")
print("     cannot serve both QAC and PADT. B5 still needs two converters.")

# ================================================== sample
mle = MLEDisambiguator.pretrained("calima-msa-r13")
toks = []
with open(f"{PD}/ar_padt-ud-train.conllu", encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#") or not line.strip():
            if len(toks) >= 6000: break
            continue
        c = line.rstrip("\n").split("\t")
        if len(c) < 10 or "-" in c[0] or "." in c[0] or c[3] == "PUNCT": continue
        if not re.search(r"[\u0621-\u064a]", c[1]): continue
        toks.append((c[1], c[3]))
toks = toks[:6000]
dis = list(zip([t for t, _ in toks], mle.disambiguate([t for t, _ in toks])))

CLOSED = {"PRON", "ADP", "CONJ", "PART", "PRT", "DET", "ADV_REL", "PRON_DEM", "NEG",
          "REL", "INTG", "COND", "SUB", "CERT", "EXL", "ACC", "FUT", "PRO", "ABV",
          "INL", "LOC", "T", "ANS", "AVR", "EXP", "IMPN", "INC", "AMD", "EXH",
          "INTERJ", "RES", "SUR", "PREV", "RET", "PUNC", "DET"}

hash_tokens = []
clean_root = []
for (surface, upos), d in dis:
    if not d.analyses:
        continue
    a = d.analyses[0].analysis
    if a.get("source") != "lex":
        continue
    rt = a.get("root")
    if not rt or rt in ("None", "na"):
        continue
    pos = (a.get("pos") or "").upper()
    if "#" in rt:
        hash_tokens.append((surface, rt, pos, a.get("lemma"), a.get("diac")))
    else:
        clean_root.append((surface, rt, pos, a.get("lemma"), a.get("diac")))

print()
print("=" * 78)
print(f"TEST B — what POS are the '#'-root tokens?  (n={len(hash_tokens)})")
print("=" * 78)
posc = collections.Counter(p for _, _, p, _, _ in hash_tokens)
closed_n = 0
posmap = collections.Counter()
for _, _, p, _, _ in hash_tokens:
    posmap[p] += 1
for p, c in posmap.most_common():
    print(f"  {c:>5}  {100*c/len(hash_tokens):5.1f}%  pos={p!r}")
print()
print("  their Tier A closed-class set is defined by UD tags (PRON, ADP, CONJ, ...),")
print("  but CALIMA's `pos` uses ITS OWN tagset (pron, prep, conj, ...). Check the mapping.")

print()
print("=" * 78)
print("TEST C — Tier C rule: does the LEMMA ending predict C3?")
print("=" * 78)
print("  claim: lemma ends ى -> C3=ي ;  lemma ends ا -> C3=و")
print()
conf = collections.Counter()
lam = collections.Counter()
for surface, rt, pos, lemma, diac in clean_root:
    rads = rt.split(".")
    if len(rads) != 3:
        continue
    c3 = rads[2]
    if c3 not in ("و", "ي", "ى"):
        continue
    L = DIAC.sub("", lemma or "")
    if not L:
        continue
    end = L[-1]
    lam[(end, c3)] += 1
    conf[c3] += 1

tot = sum(lam.values())
print(f"  clean 3-radical roots with C3 weak: {tot}")
print()
print(f"  {'lemma ends':<12} {'C3=و':>8} {'C3=ي':>8}")
xs = sorted({e for e, _ in lam})
for e in xs:
    print(f"  {e!r:<12} {lam.get((e,'و'),0):>8} {lam.get((e,'ي'),0):>8}")
print()
# accuracy of their rule
pred_ok = sum(v for (e, c3), v in lam.items()
              if (e in "ىي" and c3 == "ي") or (e in "اأ" and c3 == "و"))
print(f"  their rule would be right {pred_ok}/{tot} = {100*pred_ok/max(tot,1):.1f}%")
print()
print("  -> read the table: a lemma ending in ي does NOT imply C3=ي, and vice versa.")

print()
print("=" * 78)
print("TEST D — M1 Case 2 covers only digit set {1,2}; what do the others look like?")
print("=" * 78)
ds = collections.Counter()
for surface, rt, pos, lemma, diac in clean_root:
    p = None
    for (s2, u2), d in dis:
        pass
    ds[None] += 0
# redo properly: need the pattern
dscount = collections.Counter()
for (surface, upos), d in dis:
    if not d.analyses:
        continue
    a = d.analyses[0].analysis
    if a.get("source") != "lex" or not a.get("root"):
        continue
    pat = a.get("pattern")
    if not pat or pat in ("None", "na"):
        continue
    digits = set(DIG.findall(pat))
    if digits in ({"1", "2", "3"}, {"1", "2", "3", "4"}):
        continue
    dscount["".join(sorted(digits)) or "none"] += 1
tot_bad = sum(dscount.values())
print(f"  tokens with an incomplete digit set: {tot_bad}")
for k, v in dscount.most_common(10):
    cover = "covered by their Case 2" if k == "12" else "NOT addressed"
    print(f"  {v:>5}  {100*v/tot_bad:5.1f}%  {{{k}}}  {cover}")
c12 = dscount.get("12", 0)
print()
print(f"  -> their Case 2 addresses {{{'12'}}}: {c12}/{tot_bad} = {100*c12/max(tot_bad,1):.1f}% of the failures.")
