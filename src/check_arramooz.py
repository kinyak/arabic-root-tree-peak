"""Check whether arramooz supplies an independent root + wazan source (Head 2 + Head 3)."""
import arramooz, os, sqlite3, glob, collections, re

base = os.path.dirname(arramooz.__file__)
db = glob.glob(os.path.join(base, "**", "arabicdictionary.sqlite"), recursive=True)[0]
c = sqlite3.connect(db)

print("=" * 74)
print("ARRAMOOZ — independent root/wazan source?")
print("=" * 74)
for t in ("nouns", "verbs"):
    n = c.execute("select count(*) from " + t).fetchone()[0]
    nn = c.execute("select count(*) from " + t + " where root is not null and root<>''").fetchone()[0]
    print("  {:8s}: {:>8,} rows, {:>8,} with a root ({:.1f}%)".format(t, n, nn, 100.0 * nn / n))

print()
print("  --- sample rows ---")
for t, col in (("nouns", "wazn"), ("verbs", "triliteral")):
    print("  [{}]  (word, root, {})".format(t, col))
    for r in c.execute("select unvocalized, root, " + col + " from " + t +
                       " where root is not null and root<>'' limit 6"):
        print("     ", r)

print()
wz = collections.Counter()
for (w,) in c.execute("select wazn from nouns where wazn is not null and wazn<>''"):
    wz[w] += 1
print("  distinct wazn strings (nouns): {}".format(len(wz)))
for w, n in wz.most_common(15):
    print("     {:>6}  {!r}".format(n, w))

print()
allroots = set()
for t in ("nouns", "verbs"):
    for (r,) in c.execute("select root from " + t + " where root is not null and root<>''"):
        allroots.add(r.strip())
print("  distinct roots across both tables: {:,}".format(len(allroots)))
samp = sorted(allroots)[:10]
print("  sample:", samp)
AR = re.compile("[\u0621-\u064a]")
print("  root field Arabic-script?", {s: bool(AR.search(s)) for s in samp})

print()
print("  --- how many distinct wazn, normalised to digits? ---")
TR = str.maketrans({"ف": "1", "ع": "2", "ل": "3", "ل": "4"})
norm = collections.Counter()
for w in wz:
    plain = re.sub("[\u064b-\u0652\u0670]", "", w)
    norm[plain] += 1
print("  after stripping diacritics: {:,} distinct".format(len(norm)))
for w, _ in norm.most_common(12):
    print("     {!r}".format(w))
