"""Round-3 tests, part 2: M6 tiers, Tier C rule, M1 Case-2 coverage."""
import collections
import re

from camel_tools.disambig.mle import MLEDisambiguator

from paths import RAW as PD
DIAC = re.compile(r"[\u064b-\u0652\u0670]")
DIG = re.compile(r"[1-4]")
mle = MLEDisambiguator.pretrained("calima-msa-r13")

pairs = []
with open(f"{PD}/ar_padt-ud-train.conllu", encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#") or not line.strip():
            if len(pairs) >= 6000: break
            continue
        c = line.rstrip("\n").split("\t")
        if len(c) < 10 or "-" in c[0] or "." in c[0] or c[3] == "PUNCT": continue
        if not re.search(r"[\u0621-\u064a]", c[1]): continue
        pairs.append((c[1], c[3]))
pairs = pairs[:6000]

dis = mle.disambiguate([p[0] for p in pairs])

hash_rows, clean_rows = [], []
for (surface, upos), d in zip(pairs, dis):
    if not d.analyses:
        continue
    a = d.analyses[0].analysis
    if a.get("source") != "lex" or not a.get("root"):
        continue
    row = (surface, a["root"], (a.get("pos") or ""), a.get("lemma"), a.get("diac"), a.get("pattern"))
    (hash_rows if "#" in a["root"] else clean_rows).append(row)

print("=" * 78)
print(f"TEST B — what POS are the '#'-root tokens?  (n={len(hash_rows)})")
print("=" * 78)
posc = collections.Counter(r[2] for r in hash_rows)
for p, c in posc.most_common(18):
    print(f"  {c:>5}  {100*c/len(hash_rows):5.1f}%  pos={p!r}")
print()
# CALIMA's own tagset: which are closed-class?
CLOSED_CALIMA = {"pron", "pron_dem", "pron_rel", "pron_exclam", "pron_interrog",
                 "prep", "conj", "conj_sub", "part", "part_neg", "part_verb",
                 "part_focus", "part_interrog", "part_ans", "part_verb", "part_rc",
                 "abbrev", "punc", "interj", "adv_rel", "adv_interrog", "quant",
                 "part_det", "part_fut", "part_neg", "rel", "neg", "det"}
closed = sum(c for p, c in posc.items() if p in CLOSED_CALIMA)
print(f"  '#'-root tokens whose pos is in a CLOSED-CLASS set: {closed} "
      f"({100*closed/len(hash_rows):.1f}%)")
print(f"  content-class '#' tokens still needing a root: {len(hash_rows)-closed} "
      f"({100*(len(hash_rows)-closed)/len(hash_rows):.1f}%)")
print()
print("  -> their Tier A estimate (~23% of corpus) is a claim about the WHOLE corpus.")
print("     '#' tokens are "
      f"{100*len(hash_rows)/(len(hash_rows)+len(clean_rows)):.1f}% of lex tokens here, of which")
print(f"     {100*closed/max(len(hash_rows),1):.1f}% are closed-class (maskable) and "
      f"{100*(len(hash_rows)-closed)/max(len(hash_rows),1):.1f}% are NOT (need recovery).")

print()
print("=" * 78)
print("TEST C — Tier C rule: does the LEMMA ending predict C3?")
print("=" * 78)
conf = collections.Counter()
for surface, rt, pos, lemma, diac, pat in clean_rows:
    rads = rt.split(".")
    if len(rads) != 3 or rads[2] not in ("و", "ي", "ى"):
        continue
    L = DIAC.sub("", lemma or "")
    if not L:
        continue
    conf[(L[-1], rads[2])] += 1
tot = sum(conf.values())
ends = sorted({e for e, _ in conf})
print(f"  clean 3-radical roots with weak C3: {tot}")
print(f"  {'lemma ends':<12} {'C3=و':>8} {'C3=ي':>8}   (their rule predicts)")
for e in ends:
    w, y = conf.get((e, "و"), 0), conf.get((e, "ي"), 0)
    pred = "→ ي" if e in "ىي" else ("→ و" if e in "اأ" else "—")
    print(f"  {e!r:<12} {w:>8} {y:>8}   {pred}")
ok = sum(v for (e, c3), v in conf.items()
         if (e in "ىي" and c3 == "ي") or (e in "اأ" and c3 == "و"))
print()
print(f"  their rule accuracy: {ok}/{tot} = {100*ok/max(tot,1):.1f}%")

print()
print("=" * 78)
print("TEST D — M1 Case 2 covers only digit set {1,2}; what is the real spread?")
print("=" * 78)
dsc = collections.Counter()
for r in hash_rows + clean_rows:
    pat = r[5]
    if not pat or pat in ("None", "na"):
        continue
    digits = set(DIG.findall(pat))
    if digits in ({"1", "2", "3"}, {"1", "2", "3", "4"}):
        continue
    dsc["".join(sorted(digits)) or "none"] += 1
tot_bad = sum(dsc.values())
print(f"  tokens with an incomplete/absent digit set: {tot_bad}")
for k, v in dsc.most_common(12):
    tag = "← their Case 2" if k == "12" else ""
    print(f"  {v:>5}  {100*v/tot_bad:5.1f}%  {{{k}}} {tag}")
c12 = dsc.get("12", 0)
print()
print(f"  their Case 2 addresses {{{'12'}}}: {c12}/{tot_bad} = {100*c12/max(tot_bad,1):.1f}% "
      f"of all extraction failures.")
