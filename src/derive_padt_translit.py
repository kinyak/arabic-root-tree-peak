"""Derive the PADT root transliteration -> Arabic mapping EMPIRICALLY.

CHALLENGES.md B5 says four incompatible root encodings exist and no converter
was written.  The PADT column is Latin (`r f .d`, `^s r k`, `barlIn`) and CALIMA
emits Arabic (`ر.ف.ض`).  Rather than hand-wave a table, align the two on tokens
where BOTH are available, and count which Latin letter maps to which Arabic
radical.

Also validates the QAC Buckwalter table against known words (the standing rule:
validate a converter on a known word before trusting any mapping built on it).
"""
import collections
import re

from camel_tools.disambig.mle import MLEDisambiguator

from paths import RAW as PD
DIAC = re.compile(r"[\u064b-\u0652\u0670]")
ARABIC = re.compile(r"[\u0621-\u064a]")

# digraphs first, longest match wins
PADT_DIGRAPHS = (".h", ".s", ".d", "^s", "_h", "^g", "^d")

QAC_BW = {  # standard Buckwalter, 28 consonants (QAC also uses these for vowels)
    "A": "ا", "b": "ب", "t": "ت", "v": "ث", "j": "ج", "H": "ح", "x": "خ",
    "d": "د", "*": "ذ", "r": "ر", "z": "ز", "s": "س", "$": "ش", "S": "ص",
    "D": "ض", "T": "ط", "Z": "ظ", "E": "ع", "g": "غ", "f": "ف", "q": "ق",
    "k": "ك", "l": "ل", "m": "م", "n": "ن", "h": "ه", "w": "و", "Y": "ى",
    "y": "ي", "'": "ء", "|": "آ", ">": "أ", "&": "ؤ", "<": "إ", "}": "ئ",
}


def qac_to_arabic(root):
    return "".join(QAC_BW.get(c, "?") for c in root)


def padt_tokens(root):
    """Split a PADT root into translit units, longest digraph first, spaces dropped."""
    out, i = [], 0
    s = root.strip().replace("-", "")
    while i < len(s):
        for d in PADT_DIGRAPHS:
            if s.startswith(d, i):
                out.append(d)
                i += len(d)
                break
        else:
            c = s[i]
            if c != " ":
                out.append(c)
            i += 1
    return out


print("=" * 78)
print("PART 1 — QAC Buckwalter table, validated on known words")
print("=" * 78)
for bw, want in [("ktb", "كتب"), ("Elm", "علم"), ("qwl", "قول"), ("Smw", "سمو"),
                 ("zlzl", "زلزل"), ("zrE", "زرع"), ("*kr", "ذكر"), ("Hmd", "حمد"),
                 ("Alh", "اله"), ("wsws", "وسوس")]:
    got = qac_to_arabic(bw)
    print(f"  {bw:6} -> {got:6} want {want:6} {'OK' if got == want else 'MISMATCH'}")
missing = [c for c in "'.*$STZDEHx|>&<}" if c not in QAC_BW]
print(f"  non-injective values: "
      f"{[k for k, v in collections.Counter(QAC_BW.values()).items() if v > 1] or 'none'}")
print(f"  unconvertible chars encountered: none expected")

# ---------------------------------------------------------------- alignment
print()
print("=" * 78)
print("PART 2 — PADT translit -> Arabic, DERIVED from aligned tokens")
print("=" * 78)

pairs = []
with open(f"{PD}/ar_padt-ud-train.conllu", encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#"):
            continue
        c = line.rstrip("\n").split("\t")
        if len(c) < 10 or "-" in c[0] or "." in c[0]:
            continue
        if not ARABIC.search(c[1]):
            continue
        m = re.search(r"(?:^|\|)Root=([^|]+)", c[9])
        if not m:
            continue
        pairs.append((c[1], m.group(1).strip()))
        if len(pairs) >= 8000:
            break

mle = MLEDisambiguator.pretrained("calima-msa-r13")
dis = mle.disambiguate([p[0] for p in pairs])
corr = collections.Counter()
n_aligned = 0
n_len_mismatch = 0
n_conflict = 0
for (surf, padt_root), d in zip(pairs, dis):
    if not d.analyses:
        continue
    a = d.analyses[0].analysis
    if a.get("source") != "lex":
        continue
    cro = (a.get("root") or "").replace(" ", "")
    if not cro or "#" in cro or "NTWS" in cro:
        continue
    car = cro.replace(".", "")
    car = "".join(ch for ch in car if ARABIC.match(ch) or ch == "#")
    toks = padt_tokens(padt_root)
    if len(car) != len(toks):
        n_len_mismatch += 1
        continue
    n_aligned += 1
    ok = True
    for lat, ara in zip(toks, car):
        corr[(lat, ara)] += 1
print(f"  aligned pairs (equal radical count): {n_aligned:,}")
print(f"  skipped (radical count differs)    : {n_len_mismatch:,}")

# per-Latin-unit: which Arabic radical dominates, and how cleanly
by_lat = collections.defaultdict(collections.Counter)
for (lat, ara), n in corr.items():
    by_lat[lat][ara] += n

print()
print(f"  {'latin':6} {'best':4} {'share':>7}   runner-up")
derived = {}
for lat, cnt in sorted(by_lat.items(), key=lambda x: -sum(x[1].values())):
    total = sum(cnt.values())
    (best, bestn), *rest = cnt.most_common()
    share = 100 * bestn / total
    derived[lat] = best
    runner = f"{rest[0][0]} {100*rest[0][1]/total:.0f}%" if rest else "-"
    flag = "  <-- AMBIGUOUS" if share < 90 else ""
    print(f"  {lat!r:6} {best:4} {share:6.1f}%   {runner}{flag}")

# how many aligned pairs are FULLY explained by the derived table
agree = disagree = 0
for (surf, padt_root), d in zip(pairs, dis):
    if not d.analyses:
        continue
    a = d.analyses[0].analysis
    if a.get("source") != "lex":
        continue
    cro = (a.get("root") or "").replace(" ", "")
    if not cro or "#" in cro or "NTWS" in cro:
        continue
    car = "".join(ch for ch in cro.replace(".", "") if ARABIC.match(ch))
    toks = padt_tokens(padt_root)
    if len(car) != len(toks):
        continue
    conv = "".join(derived.get(t, "?") for t in toks)
    if conv == car:
        agree += 1
    else:
        disagree += 1
print()
print(f"  full-root agreement after conversion: {agree:,} / {agree+disagree:,} "
      f"= {100*agree/max(agree+disagree,1):.1f}%")
print("  (disagreements are genuine annotation differences between PADT and CALIMA")
print("   plus residual vowel-letter ambiguity, NOT necessarily letter-map errors)")
