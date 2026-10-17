"""spelling_resource.py — the corpus spelling resource (skeleton -> attested vocalisations), + the case-aware selector.

WHAT THIS IS
    The missing INPUT that `docs/REVIEW-RENDERER-ROADMAP.md` and the harness CONTEXT §11 predicted: the token's
    skeleton is a legal input, and 66.2M tokens of fully vocalised book text (tashkeela, 97 books) contain the
    spellings Arabic actually uses. This module answers two questions at render time:

        consult(token)            what spelling does the corpus attest, and how confident is it?      (§2bl)
        consult_case(token, case) the same, restricted to readings whose ending carries the case head (§2bo)

PROVENANCE AND THE LEAKAGE DUTY
    source     : data/raw/tashkeela-books.jsonl — book text, NOT the ruler
    built by   : G:/aide-harness/build_spelling_index.py (one pass, 66,190,991 tokens, 433,167 skeletons)
    leakage    : G:/aide-harness/leakage_test.py searched that corpus for the ruler rows' own source
                 sentences (which the annotator sheets preserve) and found 2 of 40 — **5%**. The resource is not
                 the answer key; a lookup in it is a frequency count over other people's text.
    key        : the token's SKELETON (letters only; combining marks erased; alef-wasla -> alef). The skeleton is
                 explicitly legal. Nothing here reads the gold token's diacritics — proven, not asserted: feeding
                 a skeletonised token leaves both measurements bit-identical (§2bo).

MEASURED ON THE FROZEN RULER (973 rows; pre-resource surface pipeline = 592)
    share >= 0.95, confidence rule only                         695 (71.4%)   fixed 103  broken   0   net +103
    share >= 0.55, confidence rule only                         756 (77.7%)   fixed 224  broken  60   net +164
    CASE-AWARE selector (this file, §2bo)              **827 (85.0%)**  fixed 213  broken  81   net +132
    SOFT STEM-BOUNDARY selector (this file, §2bv)      **838 (86.1%)**  +11 over the hard filter (§2bo),
                                                                       worst per-class delta **+0.0** — no
                                                                       class below its shipped baseline
    ...and end-to-end, with the MODEL's case (300-row contextual gold): **208/300 = 69.3%**, +49 rows over the
    hard filter's 159 = 53.0%. The hard filter was fed a 61.7%-accurate case head and given VETO power over a
    corpus that is usually right; the soft prior takes the case as evidence instead of as an order.

    The case head is what makes the selector work: a candidate whose final mark is not the case's mark (or its
    tanwīn form) is not an admissible reading. Its counterexamples are named and understood — `case=ABSTAIN`
    rows (nothing to constrain, so it degrades to frequency), the enclitic plane (the case sits on the enclitic,
    e.g. حِصَّتُهُ, not on the stem), and tanwīn-versus-construct (بِشَارِبِ vs بِشَارِبٍ), which is the
    definiteness input §7 says is still missing.

    The wazān pattern's LETTERS as a filter were measured too and REJECTED: −55 net, because the human writers
    contract maters the pattern's literals prescribe (§2bl). The case head was the half that pays.

CONTROLS
    ARABIC_SPELLING_INDEX   path to the index (default: ../data/resources/tashkeela_spelling_index.tsv.gz)
    SPELLING_MIN_SHARE      confidence floor for the share rule, default 0.95
    SPELLING_MIN_ATTEST     minimum total attestations before the confidence rule may speak, default 0
    (the whole module is inert when ARABIC_SPELLING_RESOURCE=0 — see final_surface.apply_spelling_resource)
"""
from __future__ import annotations

import gzip
import math
import os
import re
import threading
from pathlib import Path

MARKS = re.compile(r"[\u064B-\u0652\u0653-\u0655\u0670\u0640\u06D6-\u06ED]")
DEFAULT_INDEX = Path(__file__).resolve().parent.parent / "data" / "resources" / "tashkeela_spelling_index.tsv.gz"

CASE_MARKS = {0: {"\u064F", "\u064C"},          # NOM: damma / dammatān
              1: {"\u064E", "\u064B"},          # ACC: fatha / fathatān
              2: {"\u0650", "\u064D"}}          # GEN: kasra / kasratān
_MARK_CHARS = set(chr(c) for c in range(0x064B, 0x0656)) | {"\u0670", "\u0640"}

# lambda in `log10(count) + CASE_BONUS * case_ok`: ONE DECADE of corpus frequency is worth one case head.
# Measured (§2bv): lambda 1.0 is the end-to-end-best point of the Pareto frontier — 1.2/1.5 buy one more ruler
# row and give back 9-12 end-to-end rows, and 0.7-0.9 give back ruler rows for 5-10 end-to-end rows.
CASE_BONUS = 1.0

_lock = threading.Lock()
_all: dict[str, list[tuple[str, int, int]]] | None = None
_all_from: Path | None = None


def skeleton(tok: str) -> str:
    """Letters only: combining marks erased, alef-wasla normalised to alef. THIS is the index key."""
    return MARKS.sub("", tok or "").replace("\u0671", "\u0627")


def index_path() -> Path:
    return Path(os.environ.get("ARABIC_SPELLING_INDEX") or DEFAULT_INDEX)


def load_all(path: Path | None = None) -> dict[str, list[tuple[str, int, int]]]:
    """Load (once) every stored spelling: skeleton -> [(form, count, skeleton_total), ...] by descending count."""
    global _all, _all_from
    p = Path(path) if path else index_path()
    with _lock:
        if _all is not None and len(_all) > 0 and _all_from == p:
            return _all
        if not p.exists():
            return {}
        idx: dict[str, list[tuple[str, int, int]]] = {}
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#"):
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) != 4:
                    continue
                try:
                    cnt, total = int(parts[2]), int(parts[3])
                except ValueError:
                    continue
                idx.setdefault(parts[0], []).append((parts[1], cnt, total))
        for forms in idx.values():
            forms.sort(key=lambda f: -f[1])
        _all, _all_from = idx, p
        return idx


def load(path: Path | None = None) -> dict[str, tuple[str, int, int]]:
    """skeleton -> (top form, its count, skeleton total). The confidence rule's view of the index."""
    return {k: v[0] for k, v in load_all(path).items()}


def _stem_boundary(tok: str) -> str:
    """The token cut at its PRONOMINAL-ENCLITIC boundary — the surface the case head actually closes.

    A token carrying an enclitic ends on the ENCLITIC's own vowel (the ـهُ of عَبْدَهُ), not on the case, so
    "the last mark of the token" reads the wrong vowel whenever an enclitic is present. The cut reuses the
    metric's OWN affix logic (`final_surface.pronominal_enclitic` and the same `_cut_at_letter` the metric
    uses), so there is no second definition of "what counts as an enclitic" to disagree with the metric — the
    §2bd lesson. Imported lazily on purpose: `final_surface` imports THIS module from inside a function, so a
    module-level import here would make the cycle order-dependent.
    """
    try:
        from final_surface import _cut_at_letter, pronominal_enclitic, strip_diac
    except Exception:                                                     # noqa: BLE001
        return tok
    if not tok:
        return tok
    if any(c in "\u064b\u064c\u064d" for c in tok):
        return tok
    sk = strip_diac(tok) or ""
    if sk.endswith("الله") or sk == "لله" or sk.endswith("إله") or sk.endswith("إلاه"):
        return tok
    e = pronominal_enclitic(tok)
    if not e:
        return tok
    return _cut_at_letter(tok, len(sk) - len(e))


def case_marks_ok(cand: str, case: int | None) -> bool:
    """True when the case head's mark — or its tanwīn form — closes the candidate's STEM.

    Read on the CANDIDATE (a corpus spelling), never on the gold token, and read at the **stem boundary**
    rather than at the token's final character: عَبْدَهُ in the accusative ends on the enclitic's damma, so a
    token-final test is blind exactly where an enclitic sits (§2bu's diagnosis). `case=None` (ABSTAIN) imposes
    nothing, which is deliberate — with no constraint the rule degrades to plain frequency.
    """
    if case is None:
        return True
    want = CASE_MARKS.get(case)
    if not want:
        return True
    marks = [c for c in _stem_boundary(cand) if c in _MARK_CHARS]
    return bool(marks) and marks[-1] in want


def consult(token: str | None, min_share: float | None = None,
            min_attest: int | None = None) -> tuple[str | None, float, int]:
    """(form, share, total) when the corpus is CONFIDENT about this token's skeleton, else (None, share, total)."""
    if not token:
        return None, 0.0, 0
    t = float(min_share if min_share is not None else os.environ.get("SPELLING_MIN_SHARE", "0.95"))
    k = int(min_attest if min_attest is not None else os.environ.get("SPELLING_MIN_ATTEST", "0"))
    forms = load_all().get(skeleton(token))
    if not forms:
        return None, 0.0, 0
    form, cnt, total = forms[0]
    share = cnt / total if total else 0.0
    if total < max(1, k) or share < t:
        return None, share, total
    return form, share, total


def consult_case(token: str | None, case: int | None,
                 min_share: float | None = None) -> tuple[str | None, float, int]:
    """The best attested spelling under a SOFT case prior: `log10(count) + CASE_BONUS * case_ok`.

    NOT a hard filter. §2bs measured the hard version at **-15.3 points end-to-end** — a 61.7%-accurate case
    head given veto power over a corpus that is usually right, so it discarded the dominant spelling on 38.3%
    of rows by construction. §2bu showed a soft score recovers it; §2bv read the case head at the STEM boundary
    and produced the shipped number:

        FROZEN RULER (973):                          **838/973 = 86.1%**  (+11 over 827, worst class +0.0)
        300-row contextual gold (the MODEL's case):  **208/300 = 69.3%**  (+49 over 159 = 53.0%)

    `CASE_BONUS = 1.0` is one decade of frequency per case head, and it is the end-to-end-best point of the
    Pareto frontier: lambda 1.2/1.5 buy one more ruler row and give back 9-12 end-to-end rows. Reading it as an
    *addition in log space* is what makes a 61.7%-accurate head useful instead of destructive.

    The score reads the CANDIDATE strings and the case only — never the gold token's marks — so the legality
    invariance that `tools/spelling_resource_probe.py` pins still holds.
    """
    if not token:
        return None, 0.0, 0
    t = float(min_share if min_share is not None else os.environ.get("SPELLING_MIN_SHARE_CASE", "0.0"))
    forms = load_all().get(skeleton(token))
    if not forms:
        return None, 0.0, 0
    total = forms[0][2]
    best = None
    for form, cnt, tot in forms:
        if t and tot and cnt / tot < t:
            continue
        score = math.log10(max(cnt, 1)) + CASE_BONUS * (1.0 if case_marks_ok(form, case) else 0.0)
        if best is None or score > best[0]:
            best = (score, form, cnt)
    if best is None:
        return None, 0.0, total
    return best[1], (best[2] / total if total else 0.0), total


if __name__ == "__main__":
    import sys
    idx = load_all()
    tok = sys.argv[1] if len(sys.argv) > 1 else "مَهْرًا"
    ci = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    print(f"index   {index_path()}  ({len(idx):,} skeletons)")
    print(f"token   {tok}   skeleton {skeleton(tok)}   case {ci}")
    print(f"  candidates: {idx.get(skeleton(tok), [])[:5]}")
    for t in (0.95, 0.55, 0.0):
        print(f"  consult      min_share {t:.2f} -> {consult(tok, min_share=t)[0]!r}")
    print(f"  consult_case -> {consult_case(tok, ci)[0]!r}")
