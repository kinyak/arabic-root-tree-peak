"""Round-4 verification: corrected Buckwalter, the LEMMA_TO_ROOT dictionary, the
geminate label normalizer, and a data-derived alternative to the hand-written dict.

CORRECTED 2026-10-09 — this script used to read `a.get("lemma")`, a field CALIMA does
NOT have (the analyser exposes `lex`).  With `or ""` that silently keyed every row on
the empty string, so TEST 2 reported 0.0% and TEST 3 "resolved" 2,114 of 2,114 tokens
from a ONE-entry table — and those degenerate figures were then cited (with different
numbers, 96.4%/99.8%) as the provenance for "the root blocker is solved" in
CHALLENGES.md §2d and docs/SPEC-REV6.md §8.  Fixed to read `lex`, with a guard, and
the results re-derived below.  The real reconciler is now src/reconcile.py.
"""
import collections
import re

from camel_tools.disambig.mle import MLEDisambiguator

from paths import RAW as PD
DIAC = re.compile(r"[\u064b-\u0652\u0670]")

# ============================================ their corrected table, verbatim
BW2AR = {
    "'": "ء", "|": "آ", ">": "أ", "&": "ؤ", "<": "إ", "}": "ئ",
    "A": "ا", "b": "ب", "p": "ة", "t": "ت", "v": "ث", "j": "ج",
    "H": "ح", "x": "خ", "d": "د", "*": "ذ", "r": "ر", "z": "ز",
    "s": "س", "$": "ش", "S": "ص", "D": "ض", "T": "ط", "Z": "ظ",
    "E": "ع", "g": "غ", "_": "ـ", "f": "ف", "q": "ق", "k": "ك",
    "l": "ل", "m": "م", "n": "ن", "h": "ه", "w": "و", "Y": "ى",
    "y": "ي", "F": "ً", "N": "ٌ", "K": "ٍ", "a": "َ", "u": "ُ",
    "i": "ِ", "~": "ّ", "o": "ْ", "`": "ٰ", "{": "ٱ",
}
AR2BW = {v: k for k, v in BW2AR.items()}

print("=" * 78)
print("TEST 1 — corrected Buckwalter table")
print("=" * 78)
for bw, want in [("zrE", "زرع"), ("*kr", "ذكر"), ("*hb", "ذهب"), ("zhr", "زهر"),
                 ("ktb", "كتب"), ("Elm", "علم"), ("qwl", "قول"), ("Smw", "سمو"),
                 ("Alh", "اله"), ("Hmd", "حمد")]:
    got = "".join(BW2AR.get(c, c) for c in bw)
    print(f"  {bw:5} -> {got:6} want {want:6} {'OK' if got == want else 'CHECK'}")
dupes = collections.Counter(BW2AR.values())
bad = [k for k, v in dupes.items() if v > 1]
print(f"\n  BW2AR size: {len(BW2AR)}   AR2BW size: {len(AR2BW)}")
print(f"  non-injective (breaks AR2BW inversion): {bad if bad else 'none'}")
missing = [c for c in "M,;:!?." if c not in BW2AR]
print(f"  standard chars absent (harmless for roots): {missing}")

# ============================================ their dictionary, verbatim
LEMMA_TO_ROOT = {
    "يوم": "ي.و.م", "دولة": "د.و.ل", "بين": "ب.ي.ن", "عام": "ع.و.م",
    "سوق": "س.و.ق", "قوة": "ق.و.ي", "صوت": "ص.و.ت", "نار": "ن.و.ر",
    "بيت": "ب.ي.ت", "زيت": "ز.ي.ت", "خير": "خ.ي.ر", "سير": "س.ي.ر",
    "وزير": "و.ز.ر", "متحد": "و.ح.د", "متحدة": "و.ح.د", "وقت": "و.ق.ت",
    "وجود": "و.ج.د", "وضع": "و.ض.ع", "وصول": "و.ص.ل", "وفاة": "و.ف.ي",
    "ماضي": "م.ض.ي", "نادي": "ن.د.ي", "محامي": "ح.م.ي", "قاضي": "ق.ض.ي",
    "رئيس": "ر.أ.س", "مسؤول": "س.أ.ل", "قراءة": "ق.ر.ء",
    "مليون": "NON_ROOT", "مليار": "NON_ROOT", "دولار": "NON_ROOT", "بنك": "NON_ROOT",
}
print(f"\n  their dictionary: {len(LEMMA_TO_ROOT)} entries")

# ============================================ sample
mle = MLEDisambiguator.pretrained("calima-msa-r13")
pairs = []
with open(f"{PD}/ar_padt-ud-train.conllu", encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#") or not line.strip():
            if len(pairs) >= 8000: break
            continue
        c = line.rstrip("\n").split("\t")
        if len(c) < 10 or "-" in c[0] or "." in c[0] or c[3] == "PUNCT": continue
        if not re.search(r"[\u0621-\u064a]", c[1]): continue
        pairs.append((c[1], c[3]))
pairs = pairs[:8000]
dis = mle.disambiguate([p[0] for p in pairs])
rows = []
for (s, up), d in zip(pairs, dis):
    if not d.analyses: continue
    a = d.analyses[0].analysis
    if a.get("source") != "lex" or not a.get("root"): continue
    rows.append({"s": s, "root": a["root"], "pos": a.get("pos") or "",
                 "lex": a.get("lex") or "", "pat": a.get("pattern") or "",
                 "diac": a.get("diac") or ""})


def clean_lemma(t):
    assert t and isinstance(t, str), "empty lex: the field name is wrong (use `lex`)"
    t = DIAC.sub("", t)
    if t.startswith("ال"): t = t[2:]
    return t


hash_rows = [r for r in rows if "#" in r["root"]]
clean_rows = [r for r in rows if "#" not in r["root"]]

print()
print("=" * 78)
print("TEST 2 — coverage of the hand-written 30-entry dictionary")
print("=" * 78)
hit = sum(1 for r in hash_rows if clean_lemma(r["lex"]) in LEMMA_TO_ROOT)
print(f"  tokens with a '#' root           : {len(hash_rows)}")
print(f"  ...covered by LEMMA_TO_ROOT      : {hit}  ({100*hit/max(len(hash_rows),1):.1f}%)")
distinct = {clean_lemma(r["lex"]) for r in hash_rows}
print(f"  distinct '#'-lexemes needed      : {len(distinct)}")
print(f"  dictionary entries provided      : {len(LEMMA_TO_ROOT)}")
print(f"  -> a 30-entry dict cannot scale to {len(distinct)} lexemes.")

print()
print("=" * 78)
print("TEST 3 — the DATA-DERIVED alternative (self-join within PADT gold)")
print("=" * 78)
print("  Idea: don't hand-write the dict. Build lemma -> root from tokens that ALREADY")
print("  have a clean root, then apply it to the '#' tokens.")
print()
lut = collections.defaultdict(collections.Counter)
for r in clean_rows:
    lut[clean_lemma(r["lex"])][r["root"]] += 1
resolved = {k: c.most_common(1)[0][0] for k, c in lut.items()}
hit2 = sum(1 for r in hash_rows if clean_lemma(r["lex"]) in resolved)
print(f"  lexeme->root entries derived from CLEAN CALIMA rows : {len(resolved)}")
print(f"  '#' tokens resolved by the derived table            : {hit2} "
      f"({100*hit2/max(len(hash_rows),1):.1f}%)")
agree = 0
for r in hash_rows:
    k = clean_lemma(r["lex"])
    if k in resolved and resolved[k] == r["root"]:
        agree += 1
print()
print(f"  distinct clean CALIMA lexemes    : {len({clean_lemma(r['lex']) for r in clean_rows})}")
print(f"  lexemes present in BOTH the clean and '#' buckets: "
      f"{len({clean_lemma(r['lex']) for r in clean_rows} & {clean_lemma(r['lex']) for r in hash_rows})}")
print(f"  -> a CALIMA-derived table cannot repair a CALIMA failure: the overlap is ~0.")
print()
print(f"  vs the hand-written dict: {hit} ({100*hit/max(len(hash_rows),1):.1f}%)")
print()
print("  NOTE: some '#' tokens are ambiguous by lemma (waqf vs wuquf etc.), so the")
print("  top-1 lemma->root map is itself noisy. A confidence threshold is needed.")

print()
print("=" * 78)
print("TEST 4 — the geminate label normalizer: pattern.replace('2ّ', '2َ3')")
print("=" * 78)
REAL = [("مَدَّ", "1َ2ُّ"), ("رَدَّ", "1َ2ٍّ"), ("شَدَّ", "1َ2َّ"),
        ("جَلَّ", "1َ2ّ"), ("حَبَّ", "1ُ2ٍّ"), ("عَلَّمَ", "1ُ2ِ3َ")]
for word, pat in REAL:
    out = pat.replace("2ّ", "2َ3")
    fired = "FIRED" if out != pat else "did NOT fire"
    print(f"  {word:9} {pat:8} -> {out:10} {fired}")
print()
print("  -> it only fires when digit-2 is IMMEDIATELY followed by the shadda.")
print("     For مَدَّ (1َ2ُّ) a vowel sits between, so the branch is skipped and the")
print("     label stays a 2-slot pattern. The fix must be a regex that allows")
print("     intervening vowels, e.g.  r'(2)([َُِْ]*)(ّ)'  ->  r'\\1\\2\\3'")
print()
print("  NOTE also: analyses[0] is the top-ranked reading, not necessarily the token's")
print("  actual form, so some of these patterns disagree with the surface vocalization.")
