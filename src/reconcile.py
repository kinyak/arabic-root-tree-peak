"""reconcile.py — weak-root reconciler, production module.

WHAT IT IS FOR
    CALIMA (CAMeL Tools' MSA analyser) supplies a usable root for well under half
    of running-text tokens: `#` marks a weak radical (~31%), `NTWS` is a raw-surface
    fallback (~27%), and incomplete digit sets in `pattern` mirror the same failure.
    This module recovers those roots from a dictionary built on GOLD annotation.

WHY THE DICTIONARY MUST BE GOLD, NOT CALIMA
    CALIMA's failure is per-lexeme and deterministic: of the surfaces it analyses
    cleanly and those it breaks, the intersection is EMPTY. A dictionary derived
    from CALIMA output therefore can never repair a CALIMA failure. Established
    in CHALLENGES.md §2d; re-verified by src/test_round4.py (see NOTE below).

WHY THE DICTIONARY MUST NOT BE BUILT FROM THE EVAL SPLIT
    A surface-keyed dictionary built from the corpus you evaluate on hands the
    model its answers. Build from PADT *train* (+ QAC/EQTB where applicable) and
    evaluate on a disjoint split or corpus. `build_from_padt()` takes explicit
    paths for exactly this reason.

CALIMA FIELD TRAP (the bug this module exists to not repeat)
    The analysis dict exposes `lex`, NOT `lemma`. Reading analysis["lemma"] yields
    None; `x.get("lemma") or ""` silently turns that into the empty string, so every
    row keys on '' and a one-entry table "resolves" 100% of tokens. `_key()` below
    raises on an empty key instead of producing one.

USAGE
    # build (gold, train split only)
    dic = RootDictionary.build_from_padt(["data/raw/ar_padt-ud-train.conllu"])
    # recover a root for one token (returns Arabic radicals + which route fired)
    root, how = reconcile("اليوم", calima_root="#.#.م", dic=dic)
    # acceptance test (held-out coverage + accuracy)
    python src/reconcile.py --limit 6000
"""
from __future__ import annotations

import argparse
import collections
import re
from dataclasses import dataclass, field
from paths import RAW

DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
ARABIC = re.compile(r"[\u0621-\u064a]")
ROOT_FIELD = re.compile(r"(?:^|\|)Root=([^|]+)")

# CALIMA markers that mean "no usable root" rather than "this token has no root"
UNUSABLE_MARKERS = ("#", "NTWS", "backoff")

# ---------------------------------------------------------------- root schemes
QAC_BW = {
    "A": "ا", "b": "ب", "t": "ت", "v": "ث", "j": "ج", "H": "ح", "x": "خ",
    "d": "د", "*": "ذ", "r": "ر", "z": "ز", "s": "س", "$": "ش", "S": "ص",
    "D": "ض", "T": "ط", "Z": "ظ", "E": "ع", "g": "غ", "f": "ف", "q": "ق",
    "k": "ك", "l": "ل", "m": "م", "n": "ن", "h": "ه", "w": "و", "Y": "ى",
    "y": "ي", "'": "ء", "|": "آ", ">": "أ", "&": "ؤ", "<": "إ", "}": "ئ",
}

# PADT uses a MODIFIED translit: ح/ص/ض/ش/خ are digraphs (.h .s .d ^s _h), not the
# plain-Buckwalter uppercase H S D $ x. Units below agreed with CALIMA's Arabic root
# at 100% over 2,046 aligned token pairs (src/derive_padt_translit.py); `O`/`V` occur
# ONLY inside the literal sentinel "OOV" and are deliberately absent.
PADT_TRANSLIT = {
    "b": "ب", "t": "ت", "v": "ث", "_t": "ث", "j": "ج", ".h": "ح", "d": "د", "*": "ذ",
    "r": "ر", "z": "ز", "s": "س", "^s": "ش", ".s": "ص", ".d": "ض", "T": "ط",
    "Z": "ظ", "`": "ع", "^g": "ج", "g": "غ", "_h": "خ", "f": "ف", "q": "ق",
    "k": "ك", "l": "ل", "m": "م", "n": "ن", "h": "ه", "w": "و", "Y": "ى",
    "y": "ي", "'": "ء", "A": "ا", "a": "ا", "i": "ي", "I": "ي", "u": "و",
    "U": "و",
}
PADT_DIGRAPHS = tuple(sorted((k for k in PADT_TRANSLIT if len(k) > 1),
                             key=len, reverse=True))

CONTENT_POS = {"NOUN", "VERB", "ADJ", "PROPN", "NUM", "AUX"}

# gold-column sentinels that are NOT roots (measured: they are frequent)
NON_ROOT_SENTINELS = {"OOV", "NON_ROOT"}

PREFIXES = (
    # Compound proclitics (longest first for greedy matching)
    "وال", "بال", "فال", "كال", "لل", "ال",
    # Verb prefixes (present tense, imperatives, participles)
    "يست", "تست", "نست", "أست", "مست",
    "يت", "تت", "نت", "أت", "مت",
    "ي", "ت", "ن", "أ", "ا", "م",
    # Simple proclitics
    "و", "ف", "ب", "ك", "ل",
    # Definite article with hamza
    "الأ", "الا",
)

SUFFIXES = (
    # Noun/adjective suffixes (longest first)
    "يين", "يات", "ية", "يات", "يتين",
    "ات", "تين", "ون", "ين", "ان",
    "ياتي", "يتين",
    # Pronoun suffixes
    "هما", "كم", "كن", "نا", "ها", "هم", "هن", "كا", "كي",
    "ه", "ي", "ك", "نا",
    # Verb suffixes (past tense)
    "تم", "تن", "وا", "ت", "ا", "و", "ن",
    # Nisba and other common suffixes
    "ي", "ة", "ه", "ان",
)

# MINIMUM STEM LENGTH AFTER A STRIP. Measured, not a preference: with a `>= 2` gate the
# strip routes returned the WRONG root 15% (prefix), 12% (suffix) and 30-43%
# (prefix+suffix) of the time on PADT test — because a 2-letter remainder is usually a
# root radical being stripped off, not an affix. Concrete false positives, all passing
# the old gate: بدو -> بدد (gold بدو), الأمد -> مدد (gold امد), الأمس -> مسس (gold امس),
# امل -> ملل (gold امل), امر -> مرر.
#
# MEASURED TRADE at 3 (PADT test, 12,454 gold-root tokens): coverage 12,420 -> 12,405
# (-15) and correct 12,254 -> 12,249 (-5), while every strip route got MORE precise
# (prefix 84.8->87.2, suffix 92.2->95.0, prefix+suffix 70.0->75.0): 10 of the 15 blocked
# strips were wrong and 5 were right, so a 2-letter remainder is wrong 2 times in 3.
# Precision is the right bet here — a wrong root renders a wrong word silently.
MIN_STEM = 3


def strip_diacritics(text: str) -> str:
    return DIAC.sub("", text or "")


def padt_units(root: str) -> list[str]:
    """Split a PADT root into translit units; drop spaces and hyphens."""
    out, i = [], 0
    s = (root or "").strip().replace("-", "")
    while i < len(s):
        for d in PADT_DIGRAPHS:
            if s.startswith(d, i):
                out.append(d)
                i += len(d)
                break
        else:
            if s[i] != " ":
                out.append(s[i])
            i += 1
    return out


def padt_to_arabic(root: str) -> str | None:
    """PADT translit -> Arabic radicals. None if any unit is unmappable."""
    out = []
    for u in padt_units(root):
        a = PADT_TRANSLIT.get(u)
        if a is None:
            return None
        out.append(a)
    return "".join(out)


def qac_to_arabic(root: str) -> str:
    return "".join(QAC_BW.get(c, "?") for c in root)


# QAC 0.4's FORM column is FULLY VOCALIZED Buckwalter: short vowels, shadda and
# sukun are written as their own ASCII characters (`{ll~ahi` = ٱللَّهِ), unlike the
# ROOT column which is consonants only. Running the consonants-only table over a
# FORM therefore yields '?لل??ه?' — and CALIMA cannot analyse that, which produced a
# root ceiling of 0.000 over 3,298 stems before this existed.
QAC_BW_DIACRITIC = {
    "a": "\u064e",   # fatha
    "i": "\u0650",   # kasra
    "u": "\u064f",   # damma
    "F": "\u064b",   # fathatan
    "N": "\u064d",   # kasratan
    "K": "\u064c",   # dammatan
    "o": "\u0652",   # sukun
    "~": "\u0651",   # shadda
    "`": "\u0670",   # superscript alef
    "_": "\u0640",   # tatweel
}
# Buckwalter letters absent from QAC_BW above that DO occur in FORM
QAC_BW_FORM_EXTRA = {
    "{": "\u0627",   # ا  (alef, the '{' spelling used in Quranic Buckwalter)
    "p": "\u0629",   # ة  (ta marbuta)
    "Y": "\u0649",   # ى
    "'": "\u0621",   # ء
    "|": "\u0622",   # آ
    ">": "\u0623",   # أ
    "<": "\u0625",   # إ
    "&": "\u0624",   # ؤ
    "}": "\u0626",   # ئ
    "#": "\u0671",   # ٱ  (alef wasla)
}


def qac_form_to_arabic(form: str) -> str:
    """QAC 0.4 FORM (vocalized Buckwalter) -> vocalized Arabic, for analysis.

    Order matters: diacritics must FOLLOW their carrier consonant, so this is a
    character-by-character emit, not a sort. Returns '' if any character is
    unknown, rather than silently emitting '?' into a surface CALIMA will then
    fail on (that silent failure is what produced a 0.000 ceiling).
    """
    out = []
    for c in form or "":
        if c in QAC_BW_DIACRITIC:
            out.append(QAC_BW_DIACRITIC[c])
        elif c in QAC_BW:
            out.append(QAC_BW[c])
        elif c in QAC_BW_FORM_EXTRA:
            out.append(QAC_BW_FORM_EXTRA[c])
        else:
            return ""
    return "".join(out)


def load_weak_radical_dict():
    """Load weak radical dictionary from data/weak_radical_dict.json.
    
    Returns dict mapping surface forms to their Arabic roots for weak radical cases.
    """
    import json
    from pathlib import Path
    
    dict_path = Path(__file__).parent.parent / "data" / "weak_radical_dict.json"
    if not dict_path.exists():
        return {}
    
    with open(dict_path, encoding='utf-8') as f:
        data = json.load(f)
    
    # Extract just the Arabic roots
    return {form: info['root_arabic'] for form, info in data.items()}


def is_usable_root(root: str | None) -> bool:
    """True only for a CALIMA-style dot-separated 3- or 4-radical Arabic root."""
    if not root or any(m in root for m in UNUSABLE_MARKERS):
        return False
    parts = root.split(".")
    if len(parts) not in (3, 4):
        return False
    return all(len(p) == 1 and ARABIC.match(p) for p in parts)


def gold_root_reason(root: str | None, upos: str | None = None) -> str:
    """Why `is_gold_root` accepts or rejects a PADT `Root=` value."""
    if not root or not root.strip():
        return "empty"
    if root.strip() in NON_ROOT_SENTINELS:
        return "sentinel"
    if upos is not None and upos not in CONTENT_POS:
        return "closed_class_pos"
    units = list(root.strip()) if ARABIC.search(root) else padt_units(root)
    if len(units) not in (3, 4):
        return "radical_count"
    if not ARABIC.search(root):
        return "ok" if all(u in PADT_TRANSLIT for u in units) else "unmappable_unit"
    return "ok" if all(len(u) == 1 and ARABIC.match(u) for u in units) else "not_radicals"


def is_gold_root(root: str | None, upos: str | None = None) -> bool:
    """Is this PADT/QAC `Root=` value a real root rather than a column artefact?

    Measured on PADT train, the column also carries `OOV`, function words (`wa`,
    `bi`, `fI`, `min`), bare letters (`l`, `'`), multiword proper names
    (`\\`abd-al-l_ah`, 1,842 distinct space-containing values) and >4-radical loanword
    stems (`barlIn`, `'amIrik`). All of those poison a root dictionary.

    NOTE: spaces in PADT roots are a RADICAL SEPARATOR (`r f .d`), not a sign of a
    multiword value — do not reject on whitespace.
    """
    return gold_root_reason(root, upos) == "ok"


# ---------------------------------------------------------------- dictionary
@dataclass
class RootDictionary:
    """surface -> root. Keys are diacritic-stripped surfaces; values are roots."""
    mapping: dict[str, str]
    source: str = "unknown"
    scheme: str = "padt"
    stats: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.mapping:
            raise ValueError("refusing to build an empty root dictionary")
        if any(not k for k in self.mapping):
            raise ValueError("empty-string key: the dict is keyed on the wrong field "
                             "(CALIMA exposes `lex`, not `lemma`)")
        if len(self.mapping) < 2:
            raise ValueError(f"degenerate dictionary: {len(self.mapping)} entries")

    def __len__(self):
        return len(self.mapping)

    def lookup(self, surface: str, allow_prefix_strip: bool = True) -> tuple[str | None, str]:
        """Return (root, route). route in {exact, prefix, suffix, prefix+suffix, miss}.

        A strip is only accepted when the REMAINDER is at least `MIN_STEM` letters —
        see that constant for the measured reason (a 2-letter remainder is a stripped
        root radical far more often than it is an affix).
        """
        key = _key(surface)
        if key in self.mapping:
            return self.mapping[key], "exact"
        if allow_prefix_strip:
            # Try prefix stripping only
            for p in PREFIXES:
                if key.startswith(p) and len(key) - len(p) >= MIN_STEM:
                    k2 = key[len(p):]
                    if k2 in self.mapping:
                        return self.mapping[k2], "prefix"
            # Try suffix stripping only
            for s in SUFFIXES:
                if key.endswith(s) and len(key) - len(s) >= MIN_STEM:
                    k2 = key[:-len(s)]
                    if k2 in self.mapping:
                        return self.mapping[k2], "suffix"
            # Try both prefix and suffix stripping
            for p in PREFIXES:
                if key.startswith(p) and len(key) - len(p) >= MIN_STEM:
                    k2 = key[len(p):]
                    for s in SUFFIXES:
                        if k2.endswith(s) and len(k2) - len(s) >= MIN_STEM:
                            k3 = k2[:-len(s)]
                            if k3 in self.mapping:
                                return self.mapping[k3], "prefix+suffix"
        return None, "miss"

    def lookup_arabic(self, surface: str,
                      allow_prefix_strip: bool = True) -> tuple[str | None, str]:
        """Same, but return Arabic radicals (for the CALIMA-side pipeline)."""
        root, how = self.lookup(surface, allow_prefix_strip=allow_prefix_strip)
        if root is None:
            return None, how
        return (root if ARABIC.search(root) else padt_to_arabic(root)), how

    @classmethod
    def build_from_padt(cls, paths, keep_only_gold_roots: bool = True) -> "RootDictionary":
        """Build from PADT `Root=` gold annotation. Pass TRAIN paths only."""
        raw = collections.Counter()
        reasons = collections.Counter()
        kept = 0
        for path in paths:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("#"):
                        continue
                    cols = line.rstrip("\n").split("\t")
                    if len(cols) < 10 or "-" in cols[0] or "." in cols[0]:
                        continue
                    if not ARABIC.search(cols[1]):
                        continue
                    m = ROOT_FIELD.search(cols[9])
                    if not m:
                        continue
                    root = m.group(1).strip()
                    reason = gold_root_reason(root, cols[3])
                    reasons[reason] += 1
                    if keep_only_gold_roots and reason != "ok":
                        continue
                    kept += 1
                    raw[(_key(cols[1]), root)] += 1
        by_key = collections.defaultdict(collections.Counter)
        for (key, root), n in raw.items():
            _key(key)  # raises on empty
            by_key[key][root] += n
        mapping = {k: c.most_common(1)[0][0] for k, c in by_key.items()}
        ambiguous = sum(1 for c in by_key.values() if len(c) > 1)
        return cls(mapping=mapping, source=";".join(str(p) for p in paths),
                   scheme="padt",
                   stats={"tokens_kept": kept,
                          "reasons": dict(reasons),
                          "tokens_considered": sum(reasons.values()),
                          "distinct_surfaces": len(mapping), "ambiguous_keys": ambiguous})


def _key(surface: str) -> str:
    k = strip_diacritics(surface)
    if not k:
        raise ValueError(f"empty dictionary key from surface {surface!r} — the field "
                         f"you read is not the surface (or you read a missing key)")
    return k


def reconcile(surface: str, calima_root: str | None, dic: RootDictionary,
              allow_prefix_strip: bool = True) -> tuple[str | None, str]:
    """Root for one token. Returns (root, route).

    route: 'calima'          — CALIMA's root was already usable, returned unchanged
           'exact'           — recovered from the gold dictionary
           'prefix'          — recovered after stripping a proclitic
           'suffix'          — recovered after stripping a suffix
           'prefix+suffix'   — recovered after stripping both prefix and suffix
           'weak'            — recovered from weak radical dictionary
           'fail'            — CALIMA unusable and the dictionary has no entry
    """
    if is_usable_root(calima_root):
        return calima_root, "calima"
    # Use lookup_arabic to ensure returned roots are in Arabic radicals,
    # not PADT translit (e.g. 'w s `' instead of 'وس ع'). The renderer
    # requires Arabic radicals; PADT translit causes silent no_root failures.
    root, how = dic.lookup_arabic(surface)
    if root:
        return (root, how)
    
    # Try weak radical dictionary as fallback
    weak_dict = load_weak_radical_dict()
    key = _key(surface)
    if key in weak_dict:
        return weak_dict[key], "weak"
    if surface in weak_dict:
        return weak_dict[surface], "weak"
    
    return (None, "fail")


# ---------------------------------------------------------------- acceptance test
def _probe_pairs(path, limit):
    """(surface, calima_analysis) for real tokens, plus PADT gold root if present."""
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 10 or "-" in cols[0] or "." in cols[0]:
                continue
            if not ARABIC.search(cols[1]):
                continue
            m = ROOT_FIELD.search(cols[9])
            rows.append((cols[1], cols[3], m.group(1).strip() if m else None))
            if len(rows) >= limit:
                break
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=6000)
    ap.add_argument("--raw", default=str(RAW))
    args = ap.parse_args()

    from camel_tools.disambig.mle import MLEDisambiguator

    print("=" * 78)
    print("ACCEPTANCE TEST — reconciler, dictionary from PADT train, probe dev+test")
    print("=" * 78)
    dic = RootDictionary.build_from_padt([f"{args.raw}/ar_padt-ud-train.conllu"])
    s = dic.stats
    total = s["tokens_considered"]
    print(f"  dict: {len(dic):,} surfaces from {s['tokens_kept']:,} usable gold-rooted tokens")
    print(f"  PADT train `Root=`-bearing tokens: {total:,}  "
          f"-> usable: {100*s['tokens_kept']/max(total,1):.1f}%")
    for reason, n in sorted(s["reasons"].items(), key=lambda x: -x[1]):
        if reason != "ok":
            print(f"       dropped — {reason:16} {n:>7,}  ({100*n/max(total,1):5.1f}%)")
    print(f"        surfaces with >1 competing root (top-1 wins): {s['ambiguous_keys']:,}")
    print(f"  degeneracy check: {len(dic):,} entries, "
          f"{len(set(dic.mapping.values())):,} distinct roots  "
          f"(a 1-entry table means the key field is wrong)")

    probe = (_probe_pairs(f"{args.raw}/ar_padt-ud-dev.conllu", args.limit // 2)
             + _probe_pairs(f"{args.raw}/ar_padt-ud-test.conllu", args.limit // 2))
    mle = MLEDisambiguator.pretrained("calima-msa-r13")
    dis = mle.disambiguate([p[0] for p in probe])

    OPEN = {"noun", "verb", "adj", "noun_prop", "noun_num", "adj_comp", "adj_num"}
    checked = collections.Counter()
    for allow_prefix in (False, True):
        cov = acc = unres = 0
        oc_n = ocov = oacc = 0
        per_route = collections.Counter()
        for (surf, upos, gold), d in zip(probe, dis):
            if not d.analyses:
                continue
            a = d.analyses[0].analysis
            if a.get("source") != "lex":
                continue
            cro = a.get("root") or ""
            if is_usable_root(cro):
                continue  # CALIMA already fine, nothing to reconcile
            if not gold or not is_gold_root(gold, upos):
                continue  # no held-out gold to score against
            got, how = dic.lookup(surf, allow_prefix_strip=allow_prefix)
            open_class = (a.get("pos") or upos) in OPEN
            per_route[how if got is None else "recovered"] += 1
            if open_class:
                oc_n += 1
            if got is None:
                unres += 1
                continue
            cov += 1
            hit = padt_units(got) == padt_units(gold)  # scheme-robust comparison
            acc += hit
            if open_class:
                ocov += 1
                oacc += hit
        checked[allow_prefix] = (cov, acc, unres, oc_n, ocov, oacc, dict(per_route))
        label = "exact match only" if not allow_prefix else "exact + proclitic-stripped fallback"
        print()
        print(f"  --- {label} ---")
        print(f"    tokens scored (CALIMA-unusable + held-out gold): {cov+unres:,}")
        print(f"    recovered by dictionary : {cov:,}  ({100*cov/max(cov+unres,1):.1f}% coverage)")
        print(f"    root CORRECT vs gold    : {acc:,}  ({100*acc/max(cov,1):.1f}% of recovered"
              f", {100*acc/max(cov+unres,1):.1f}% of all)")
        print(f"    open-class recovered    : {ocov:,} / {oc_n:,}")
        print(f"    open-class CORRECT      : {oacc:,} / {oc_n:,} "
              f"({100*oacc/max(oc_n,1):.1f}%)")
        print(f"    routes: {checked[allow_prefix][6]}")

    cov_e, acc_e, unres_e, *_ = checked[False]
    cov_p, acc_p, unres_p, *_ = checked[True]
    print()
    print("  VERDICT")
    print(f"    proclitic fallback changes coverage {100*cov_e/(cov_e+unres_e):.1f}% -> "
          f"{100*cov_p/(cov_p+unres_p):.1f}%, accuracy "
          f"{100*acc_e/max(cov_e,1):.1f}% -> {100*acc_p/max(cov_p,1):.1f}%")
    print("    Report BOTH coverage and accuracy: a dictionary that answers is not a")
    print("    dictionary that answers correctly.")


if __name__ == "__main__":
    main()
