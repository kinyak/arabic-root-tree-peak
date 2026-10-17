"""Empirically verify the CAMeL Tools CALIMA `pattern` feature.

Claim under test (asserted by the user):
  - CALIMA emits a `pattern` key in each analysis dict
  - radicals are encoded as the DIGITS 1, 2, 3 (and 4 for quadriliteral roots)
  - 1 = fa' al-kalima, 2 = 'ayn al-kalima, 3 = lam al-kalima, 4 = second lam

Test words deliberately chosen to exercise every case:
  triliteral sound, derived forms, quadriliteral, hollow, defective, geminate, and a noun.
"""
from camel_tools.morphology.database import MorphologyDB
from camel_tools.morphology.analyzer import Analyzer

CASES = [
    ("كَتَبَ",  "k-t-b", "Form I verb, sound triliteral"),
    ("اسْتَغْفَرَ", "gh-f-r", "Form X verb (must not produce a 4th placeholder)"),
    ("عَلَّمَ",  "ʿ-l-m", "Form II, geminate-looking (shadda)"),
    ("زَلْزَلَ", "z-l-z-l", "QUADRILITERAL — the decisive test for digit 4"),
    ("وَسْوَسَ", "w-s-w-s", "quadriliteral"),
    ("قَالَ",   "q-w-l", "hollow (ajwaf) — radical 2 elides"),
    ("دَعَا",   "d-ʿ-w", "defective (naqis) — radical 3 elides"),
    ("مَكْتَب",  "k-t-b", "noun, maf'al"),
    ("مَدِينَة", "m-d-n", "noun, fa'ila"),
    ("طَالِب",  "ṭ-l-b", "active participle, fa'il"),
]

print(f"{'word':<14} {'root':<8} {'pattern':<18} {'pos':<6} {'lex'}")
print("-" * 78)

db = MorphologyDB.builtin_db()
an = Analyzer(db)

all_keys = set()
seen_patterns = {}
quad_seen = []

for surface, root, why in CASES:
    analyses = an.analyze(surface)
    if not analyses:
        print(f"{surface:<14} {root:<8} !! NO ANALYSES RETURNED")
        continue
    for a in analyses:
        all_keys.update(a.keys())
        pat = a.get("pattern", "<NO pattern KEY>")
        seen_patterns.setdefault(pat, []).append(surface)
        if "4" in str(pat):
            quad_seen.append((surface, root, pat))
        print(f"{surface:<14} {a.get('root',''):<8} {str(pat):<18} "
              f"{str(a.get('pos','')):<6} {a.get('lex','')}")
    print(f"{'':<14} ({why})")
    print()

print("=" * 78)
print("VERDICT")
print("=" * 78)
print(f"'pattern' key present in analysis dict : "
      f"{'YES' if 'pattern' in all_keys else 'NO'}")
print(f"total distinct pattern strings observed: {len(seen_patterns)}")
print(f"words whose pattern contains a '4'   : {len(quad_seen)}")
for s, r, p in quad_seen:
    print(f"    {s} ({r}) -> {p}")
print()
print("all analysis-dict keys:")
print(sorted(all_keys))
