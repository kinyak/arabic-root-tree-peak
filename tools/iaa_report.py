"""iaa_report.py — inter-annotator agreement for the frozen benchmark (Lock D, freeze v2 §5).

WHY NOT ONE κ
    The backlog's earlier next-command named `src/crosscheck_annotation.py` for κ. That script
    does NOT compute inter-annotator agreement at all -- it cross-checks ONE sheet against
    EQTB/QAC gold and against CALIMA (diagnostics), so it cannot report agreement between two
    annotators. This tool is that missing piece.

    And κ alone would be the wrong instrument anyway. `case` has 4 categories and `confidence`
    has 3, so κ is informative for them. `root` and `wazn_pattern` have thousands of possible
    values: a pooled κ over high-cardinality labels is unstable and deflated, so it says almost
    nothing about how hard the task is. For those two fields the useful measurement is RAW exact
    agreement plus a DISAGREEMENT TAXONOMY -- *how* the two annotators differ (a missing radical
    slot, a different radical, a hamza-convention fold, an incomplete digit set). This report
    gives both, per field, never pooled.

    Everything is computed on the two RAW files, BEFORE adjudication (freeze v2 §5.4).

USAGE
    python tools/iaa_report.py --a <fileA.csv> --b <fileB.csv> [--key bench-KEY.csv] [--json out.json]
    python tools/iaa_report.py --selftest          # verifies this tool with known-answer fixtures
CPU only. Reads no analyser, no model output, no gold.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
TATWEEL = "\u0640"
ALEF_SEATS = {0x0622: "\u0627", 0x0623: "\u0627", 0x0625: "\u0627", 0x0671: "\u0627"}
# The same abstention vocabulary score_annotation.py accepts, so this report cannot disagree with
# the scorer about what "ABSTAIN" means -- with ONE deliberate difference: the scorer also maps an
# EMPTY cell to ABSTAIN, and we do not. In an agreement report a blank cell is an unfinished row
# (missing data), not a considered abstention; conflating the two would manufacture agreement out
# of two annotators both having skipped the same row.
ABSTAIN_WORDS = {"abstain", "abdtain", "abstain)", "?", "-", "na", "n/a", "none"}
BLANK = "(blank)"
FIELDS = ("root", "wazn_pattern", "case", "confidence")
CASE_CATS = ("NOM", "ACC", "GEN", "ABSTAIN")
CONF_CATS = ("high", "medium", "low")
DIGIT = re.compile(r"[1-9]")


def _abstained(v: str) -> bool:
    s = (v or "").strip().lower()
    return bool(s) and (s in ABSTAIN_WORDS or s.startswith("abstain"))


# --------------------------------------------------------------------------- normalisation ----
def norm_root(v: str) -> str:
    """dot-separated bare-alef radical string; '' for a blank cell or a considered abstention."""
    s = (v or "").strip()
    if _abstained(s):
        return ""
    s = "".join(ALEF_SEATS.get(ord(c), c) for c in s)
    return "".join(c for c in s if c not in ".·\u00b7 " and c != TATWEEL)


def norm_root_hamza(v: str) -> str:
    """hamza-folded form, used only to CLASSIFY a disagreement (is it convention or substance?)"""
    s = (v or "").strip()
    s = "".join(ALEF_SEATS.get(ord(c), c) for c in s)
    s = s.replace("\u0621", "\u0627").replace("\u0629", "\u0647")
    return norm_root(s)


def norm_wazn(v: str) -> str:
    s = (v or "").strip()
    if _abstained(s):
        return ""
    s = "".join(ALEF_SEATS.get(ord(c), c) for c in s)
    return s.replace(TATWEEL, "").replace(" ", "")


def norm_case(v: str) -> str:
    s = (v or "").strip().upper()
    if _abstained(s):
        return "ABSTAIN"
    return s or BLANK


def norm_conf(v: str) -> str:
    return (v or "").strip().lower() or BLANK


# ------------------------------------------------------------------- the `alternatives` column --
# Added before issue (freeze doc, Amendment 1). Why a column and not a prose tag inside `notes`:
# `notes` is human-readable and this tool cannot parse it, so alternative analyses recorded only as
# prose were unmeasurable, unadjudicable, and unusable for top-k evaluation -- which is the whole
# point of recording them.
#
# STRICT GRAMMAR
#     NONE                        no rival analysis -- a CONSIDERED statement, not a skip
#     case=NOM                    one rival candidate
#     root=ق.و.ل | case=GEN       candidates separated by " | "; field=value pairs separated by spaces
# A blank cell is NOT `NONE`: blank means the annotator has not done the row yet.
ALT_KEYS = {"root": "root", "wazn": "wazn", "wazn_pattern": "wazn", "case": "case"}
NONE_TOKEN = "NONE"
ALT_FIELDS = ("root", "wazn", "case")


def parse_alternatives(v: str):
    """(canonical, n_candidates, errors). canonical is a sorted tuple of 'field=value',
    the string NONE for a considered 'none', or '' for a blank cell."""
    s = (v or "").strip()
    if not s:
        return "", 0, []                      # blank: not filled, and NOT the same as NONE
    if s.upper() == NONE_TOKEN:
        return NONE_TOKEN, 0, []
    canon, errors = [], []
    for cand in s.split("|"):
        cand = cand.strip()
        if not cand:
            errors.append("empty candidate between separators")
            continue
        seen_in_cand = 0
        had_kv = False                          # a token WITH '=' but a bad key is one error, not two
        for tok in cand.split():
            if "=" not in tok:
                errors.append("candidate %r: token %r is not field=value" % (cand, tok))
                continue
            had_kv = True
            raw_key, _, val = tok.partition("=")
            key = raw_key.strip().lower()
            val = val.strip()
            if key not in ALT_KEYS:
                errors.append("candidate %r: unknown field %r (allowed: root, wazn, case)"
                              % (cand, raw_key))
                continue
            key = ALT_KEYS[key]
            seen_in_cand += 1
            if key == "case":
                nv = norm_case(val)
                if nv not in ("NOM", "ACC", "GEN"):
                    errors.append("candidate %r: case must be NOM/ACC/GEN -- an abstention belongs "
                                  "in the `case` column, not as a candidate" % cand)
                    continue
                canon.append("case=%s" % nv)
            elif key == "root":
                nr = norm_root(val)
                if not nr:
                    errors.append("candidate %r: root is empty or an abstention" % cand)
                    continue
                canon.append("root=%s" % ".".join(nr))
            else:
                nw = norm_wazn(val)
                if not digits(nw):
                    errors.append("candidate %r: wazn carries no digits" % cand)
                    continue
                canon.append("wazn=%s" % nw)
        if seen_in_cand == 0 and not had_kv:
            errors.append("candidate %r has no field=value pair" % cand)
    return tuple(sorted(set(canon))), len(canon), errors


def digits(v: str) -> list[str]:
    return DIGIT.findall(norm_wazn(v))


# ------------------------------------------------------------------------------- statistics ----
def cohen_kappa(pairs, cats) -> dict:
    """Cohen's κ over the observed category set. Degenerate cases are reported, not hidden."""
    n = len(pairs)
    if not n:
        return {"n": 0, "po": None, "pe": None, "kappa": None, "note": "no rows"}
    po = sum(1 for a, b in pairs if a == b) / n
    ca, cb = collections.Counter(a for a, _ in pairs), collections.Counter(b for _, b in pairs)
    pe = sum(ca[c] * cb[c] for c in cats) / (n * n)
    if pe >= 1.0:
        kappa = 1.0 if po >= 1.0 else 0.0
        note = "degenerate: one category only -- kappa is not interpretable, read raw agreement"
    else:
        kappa = (po - pe) / (1.0 - pe)
        note = ""
        if pe >= 0.90:
            # The prevalence trap: when one category dominates, po and pe are both ~1 and kappa
            # collapses toward 0 even at near-perfect agreement (measured: po=0.999 pe=0.999 ->
            # kappa=0.000). Reporting that kappa alone would advertise a disaster that is not there.
            note = ("prevalence effect: pe=%.3f dominates, so kappa is deflated toward 0 regardless "
                    "of raw agreement -- report raw agreement and the per-stratum table alongside "
                    "kappa, never kappa alone" % pe)
    return {"n": n, "po": po, "pe": pe, "kappa": kappa, "note": note}


def classify_root(a: str, b: str):
    ra, rb = norm_root(a), norm_root(b)
    if ra == rb:
        return "AGREE"
    if not ra and not rb:
        return "AGREE"
    # a BLANK cell is unfinished, not a considered abstention -- keep the two apart
    if not b.strip():
        return "B left blank"
    if not a.strip():
        return "A left blank"
    if not ra or not rb:
        return "one-abstained-other-answered"
    if norm_root_hamza(a) == norm_root_hamza(b):
        return "hamza-convention-only (Rule 7)"
    la, lb = list(ra), list(rb)
    if len(la) < len(lb):
        return "missing radical slot (A short by %d)" % (len(lb) - len(la))
    if len(la) > len(lb):
        return "missing radical slot (B short by %d)" % (len(la) - len(lb))
    if la != lb:
        diff = [i for i, (x, y) in enumerate(zip(la, lb)) if x != y]
        if len(diff) == 1:
            return "one radical differs at slot %d" % (diff[0] + 1)
        return "%d radicals differ" % len(diff)
    return "other"


def classify_wazn(a: str, b: str):
    wa, wb = norm_wazn(a), norm_wazn(b)
    if wa == wb:
        return "AGREE"
    if not b.strip():
        return "B left blank"
    if not a.strip():
        return "A left blank"
    if not wa or not wb:
        return "one-abstained-other-answered"
    da, db = digits(a), digits(b)
    if da != db:
        if len(da) < len(db):
            return "digit set incomplete in A (%d vs %d)" % (len(da), len(db))
        if len(da) > len(db):
            return "digit set incomplete in B (%d vs %d)" % (len(db), len(da))
        return "same digits, different order"
    # digits identical -> the difference is in the letters/vowels
    la = re.sub(r"[1-9]", "#", wa)
    lb = re.sub(r"[1-9]", "#", wb)
    if la == lb:
        return "vowel-only difference"
    la_nod = DIAC.sub("", la)
    lb_nod = DIAC.sub("", lb)
    if la_nod == lb_nod:
        return "vowel-only difference"
    return "template-letter difference"


def rule6_wellformed(v: str) -> bool:
    """The repo's existing gate (crosscheck_annotation CHECK): every digit distinct."""
    d = digits(v)
    return bool(d) and len(d) == len(set(d))


# ----------------------------------------------------------------------------------- report ----
def load(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def report(rows_a, rows_b, key_rows=None, label_a="A", label_b="B") -> dict:
    if [r["id"] for r in rows_a] != [r["id"] for r in rows_b]:
        raise SystemExit("row ids/order differ between the two files -- they cannot be compared")
    n = len(rows_a)
    out = {"rows": n, "fields": {}, "rule6": {}, "fill": {}, "abstain": {}}

    pairs = {f: [(r_a[f], r_b[f]) for r_a, r_b in zip(rows_a, rows_b)] for f in FIELDS}

    for f in ("root", "wazn_pattern"):
        norm = norm_root if f == "root" else norm_wazn
        classify = classify_root if f == "root" else classify_wazn
        both = [(a, b) for a, b in pairs[f] if norm(a) and norm(b)]
        agree = sum(1 for a, b in both if norm(a) == norm(b))
        tax = collections.Counter(classify(a, b) for a, b in pairs[f])
        out["fields"][f] = {
            "raw_exact_agreement_both_answered": (agree / len(both)) if both else None,
            "both_answered": len(both), "agree": agree,
            "kappa": None,
            "kappa_note": "high-cardinality label space -- a pooled kappa is unstable and deflated; "
                          "read raw agreement + the taxonomy below instead",
            "taxonomy": dict(tax.most_common()),
        }

    out["fields"]["case"] = {
        **cohen_kappa(pairs["case"], CASE_CATS),
        "raw_exact_agreement": sum(1 for a, b in pairs["case"] if norm_case(a) == norm_case(b)) / n,
        "taxonomy": dict(collections.Counter(
            "%s vs %s" % tuple(sorted((norm_case(a) or "BLANK", norm_case(b) or "BLANK")))
            for a, b in pairs["case"] if norm_case(a) != norm_case(b)).most_common()),
    }
    out["fields"]["confidence"] = {
        **cohen_kappa(pairs["confidence"], CONF_CATS),
        "raw_exact_agreement": sum(1 for a, b in pairs["confidence"]
                                   if norm_conf(a) == norm_conf(b)) / n,
        "taxonomy": dict(collections.Counter(
            "%s vs %s" % tuple(sorted((norm_conf(a) or "BLANK", norm_conf(b) or "BLANK")))
            for a, b in pairs["confidence"] if norm_conf(a) != norm_conf(b)).most_common()),
    }

    for f, norm in (("root", norm_root), ("wazn_pattern", norm_wazn),
                    ("case", norm_case), ("confidence", norm_conf)):
        def filled(v, _norm=norm):
            x = _norm(v)
            return bool(x) and x != BLANK          # a blank cell is NOT a filled cell
        out["fill"][f] = {
            label_a: sum(1 for r in rows_a if filled(r[f])) / n,
            label_b: sum(1 for r in rows_b if filled(r[f])) / n,
        }
    out["abstain"] = {"case_%s" % label_a: sum(1 for r in rows_a if norm_case(r["case"]) == "ABSTAIN"),
                      "case_%s" % label_b: sum(1 for r in rows_b if norm_case(r["case"]) == "ABSTAIN")}
    # The repo's existing gate (crosscheck_annotation CHECK): a pattern is well-formed when every
    # digit is distinct. A row that ABSTAINED is not a failure; a row that gave a pattern with no
    # digits, or with a repeated digit, is.
    def gate_fail(rows):
        return sum(1 for r in rows
                   if norm_wazn(r["wazn_pattern"]) and not rule6_wellformed(r["wazn_pattern"]))

    out["rule6"] = {"definition": "given pattern whose digit set is empty or has a repeated digit",
                    label_a: gate_fail(rows_a), label_b: gate_fail(rows_b)}

    # ---- `alternatives` (Amendment 1): measured, not just collected -------------------------
    av, bv = [r.get("alternatives", "") for r in rows_a], [r.get("alternatives", "") for r in rows_b]
    pa = [parse_alternatives(v) for v in av]
    pb = [parse_alternatives(v) for v in bv]
    alt_tax = collections.Counter()
    for (ca, na, ea), (cb, nb, eb) in zip(pa, pb):
        if ea or eb:
            alt_tax["MALFORMED entry (fix before adjudication)"] += 1
        elif not ca and not cb:
            alt_tax["both left blank (unfinished)"] += 1
        elif not ca or not cb:
            alt_tax["one blank, other filled"] += 1
        elif ca == NONE_TOKEN and cb == NONE_TOKEN:
            alt_tax["both NONE (agree: no rival analysis)"] += 1
        elif ca == NONE_TOKEN or cb == NONE_TOKEN:
            alt_tax["one NONE, other listed candidates"] += 1
        elif ca == cb:
            alt_tax["same candidate set"] += 1
        else:
            alt_tax["different candidate sets"] += 1
    filled_a = sum(1 for c, _, e in pa if c and not e)
    filled_b = sum(1 for c, _, e in pb if c and not e)
    # a malformed cell is NOT a measurement: it must not inflate "rival analysis" counts or the
    # per-field tallies, or a typo would read as an annotator finding an alternative.
    multi_a = sum(1 for c, _, e in pa if c and c != NONE_TOKEN and not e)
    multi_b = sum(1 for c, _, e in pb if c and c != NONE_TOKEN and not e)
    agree_alt = sum(1 for (ca, _, ea), (cb, _, eb) in zip(pa, pb)
                    if not ea and not eb and ca and ca == cb)
    both_filled = sum(1 for (ca, _, ea), (cb, _, eb) in zip(pa, pb) if ca and cb and not ea and not eb)
    per_field = {f: {"A": sum(1 for c, _, e in pa if c and c != NONE_TOKEN and not e
                             and any(x.startswith(f + "=") for x in c)),
                     "B": sum(1 for c, _, e in pb if c and c != NONE_TOKEN and not e
                              and any(x.startswith(f + "=") for x in c))} for f in ALT_FIELDS}
    out["alternatives"] = {
        "filled": {label_a: filled_a / n if n else None, label_b: filled_b / n if n else None},
        "rows_with_a_rival_analysis": {label_a: multi_a, label_b: multi_b},
        "raw_exact_agreement_both_filled": (agree_alt / both_filled) if both_filled else None,
        "both_filled": both_filled, "agree": agree_alt,
        "malformed": {label_a: sum(1 for _, _, e in pa if e), label_b: sum(1 for _, _, e in pb if e)},
        "by_field": per_field,
        "taxonomy": dict(alt_tax.most_common()),
    }

    if key_rows:
        kmap = {r["id"]: r for r in key_rows}
        per = collections.defaultdict(lambda: {"n": 0, "case_agree": 0})
        for r_a, r_b in zip(rows_a, rows_b):
            k = kmap.get(r_a["id"])
            if not k:
                continue
            s = k["primary_stratum"]
            per[s]["n"] += 1
            per[s]["case_agree"] += int(norm_case(r_a["case"]) == norm_case(r_b["case"]))
        out["by_stratum"] = {s: {"n": v["n"], "case_raw_agreement":
                                 v["case_agree"] / v["n"] if v["n"] else None}
                             for s, v in sorted(per.items())}
    return out


def print_report(rep: dict, label_a="A", label_b="B") -> None:
    print("=" * 82)
    print("INTER-ANNOTATOR AGREEMENT  (%s vs %s, raw files, BEFORE adjudication)" % (label_a, label_b))
    print("=" * 82)
    print("rows compared: %d" % rep["rows"])
    for f in ("root", "wazn_pattern", "case", "confidence"):
        d = rep["fields"][f]
        print("\n--- %s ---" % f)
        if "raw_exact_agreement_both_answered" in d and d["raw_exact_agreement_both_answered"] is not None:
            print("  raw exact agreement (both answered): %.4f  (%d/%d)"
                  % (d["raw_exact_agreement_both_answered"], d["agree"], d["both_answered"]))
        else:
            ra = d.get("raw_exact_agreement")
            print("  raw exact agreement               : %s" % ("%.4f" % ra if ra is not None else "n/a"))
        if d.get("kappa") is not None:
            print("  Cohen's kappa                     : %.4f   (po=%.4f pe=%.4f)"
                  % (d["kappa"], d["po"], d["pe"]))
            if d.get("note") or d.get("kappa_note"):
                print("  note                              : %s" % (d.get("note") or d.get("kappa_note")))
        else:
            print("  Cohen's kappa                     : NOT REPORTED -- %s" % d["kappa_note"])
        if d.get("taxonomy"):
            print("  disagreement taxonomy:")
            for k, v in d["taxonomy"].items():
                print("    %-46s %5d" % (k, v))
    print("\n--- fill / abstain ---")
    for f, v in rep["fill"].items():
        print("  %-14s %s=%.3f  %s=%.3f" % (f, label_a, v[label_a], label_b, v[label_b]))
    print("  %s" % rep["abstain"])
    print("  Rule 6 digit-gate failures: %s" % rep["rule6"])
    a = rep.get("alternatives")
    if a:
        print("\n--- alternatives (Amendment 1) ---")
        print("  filled                     : %s=%.3f  %s=%.3f"
              % (label_a, a["filled"][label_a] or 0, label_b, a["filled"][label_b] or 0))
        print("  rows with a rival analysis : %s=%d  %s=%d  <- this is the top-k margin"
              % (label_a, a["rows_with_a_rival_analysis"][label_a],
                 label_b, a["rows_with_a_rival_analysis"][label_b]))
        if a["raw_exact_agreement_both_filled"] is not None:
            print("  raw exact agreement (both filled): %.4f  (%d/%d)"
                  % (a["raw_exact_agreement_both_filled"], a["agree"], a["both_filled"]))
        print("  malformed entries          : %s=%d  %s=%d"
              % (label_a, a["malformed"][label_a], label_b, a["malformed"][label_b]))
        print("  alternative given per field: %s" % a["by_field"])
        print("  taxonomy:")
        for k, v in a["taxonomy"].items():
            print("    %-46s %5d" % (k, v))
    if "by_stratum" in rep:
        print("\n--- case agreement by stratum (PI only) ---")
        for s, v in rep["by_stratum"].items():
            print("  %-16s n=%4d  case raw agreement %.3f" % (s, v["n"], v["case_raw_agreement"]))


# ---------------------------------------------------------------------------------- selftest ----
def selftest() -> int:
    """Known-answer fixtures -- every number asserted below is known BY CONSTRUCTION, so a pass
    means the tool's normalisation, taxonomy and kappa are behaving. 12 synthetic rows."""
    # (root, wazn_pattern, case, confidence) for A and B
    data = [
        # 0 -- everything agrees (control)
        (("ك.ت.ب", "1َ2َ3", "NOM", "high"), ("ك.ت.ب", "1َ2َ3", "NOM", "high")),
        # 1 -- Rule 7 hamza convention: سوا vs سوء  (same root, different hamza convention)
        (("س.و.ا", "1َ2َ3", "GEN", "high"), ("س.و.ء", "1َ2َ3", "GEN", "high")),
        # 2 -- Rule 6 missing radical slot: B dropped the doubled radical AND its digit
        (("ح.ق.ق", "1َ2ّ3", "GEN", "medium"), ("ح.ق", "1َ2ّ", "GEN", "medium")),
        # 3 -- one radical differs, same length
        (("ن.ف.س", "1َ2ْ3", "ACC", "high"), ("ن.ف.ص", "1َ2ْ3", "ACC", "high")),
        # 4 -- case disagreement ONLY (confidence deliberately equal, to isolate the field)
        (("ع.ل.م", "1َ2ْ3", "NOM", "high"), ("ع.ل.م", "1َ2ْ3", "GEN", "high")),
        # 5 -- case disagreement involving an abstention (confidence equal again)
        (("ق.ت.ل", "1َ2ْ3", "GEN", "high"), ("ق.ت.ل", "1َ2ْ3", "ABSTAIN", "high")),
        # 6 -- both abstain on case: that IS agreement
        (("ه.د.ي", "1ُ2َ3ى", "ABSTAIN", "medium"), ("ه.د.ي", "1ُ2َ3ى", "ABSTAIN", "medium")),
        # 7 -- wazn vowel-only difference
        (("ك.ت.ب", "1َ2َ3", "NOM", "high"), ("ك.ت.ب", "1ُ2ُ3", "NOM", "high")),
        # 8 -- A answered, B abstained (considered abstention, tagged)
        (("م.ر.ي", "مُ1ْتَ2ِ3ِين", "GEN", "high"), ("ABSTAIN", "ABSTAIN", "GEN", "low")),
        # 9 -- confidence disagreement only
        (("ش.ف.ع", "1َا2ِ3ِيّ", "GEN", "medium"), ("ش.ف.ع", "1َا2ِ3ِيّ", "GEN", "low")),
        # 10 -- B left the WHOLE row blank: unfinished, and must NOT be read as an abstention
        (("ش.ف.ع", "1َا2ِ3ِيّ", "GEN", "medium"), ("", "", "", "")),
        # 11 -- quadriliteral, vowel-only wazn difference (four DISTINCT digits: the Rule 6 gate
        #       rejects a repeated digit, so a fixture with one would be malformed, not a test)
        (("ك.س.ف.ر", "1َ2ْ3َ4", "GEN", "high"), ("ك.س.ف.ر", "1ُ2ُ3ُ4", "GEN", "high")),
    ]

    def mk(idx):
        return [{"id": "X%03d" % i, "root": p[idx][0], "wazn_pattern": p[idx][1],
                 "case": p[idx][2], "confidence": p[idx][3]} for i, p in enumerate(data)]

    rep = report(mk(0), mk(1))
    checks = []

    r = rep["fields"]["root"]
    checks += [("root both_answered", r["both_answered"], 10),
               ("root agree", r["agree"], 7),
               ("root raw agreement", round(r["raw_exact_agreement_both_answered"], 4), 0.7),
               ("root kappa NOT reported", r["kappa"], None)]
    rt = r["taxonomy"]
    checks += [("root tax AGREE", rt.get("AGREE"), 7),
               ("root tax hamza-convention", rt.get("hamza-convention-only (Rule 7)"), 1),
               ("root tax missing-slot", rt.get("missing radical slot (B short by 1)"), 1),
               ("root tax one-radical-differs", rt.get("one radical differs at slot 3"), 1),
               ("root tax one-abstained", rt.get("one-abstained-other-answered"), 1),
               ("root tax B left blank", rt.get("B left blank"), 1)]

    w = rep["fields"]["wazn_pattern"]
    checks += [("wazn both_answered", w["both_answered"], 10),
               ("wazn agree", w["agree"], 7)]
    wt = w["taxonomy"]
    checks += [("wazn tax AGREE", wt.get("AGREE"), 7),
               ("wazn tax digit-set incomplete in B", wt.get("digit set incomplete in B (2 vs 3)"), 1),
               ("wazn tax vowel-only", wt.get("vowel-only difference"), 2),
               ("wazn tax one-abstained", wt.get("one-abstained-other-answered"), 1),
               ("wazn tax B left blank", wt.get("B left blank"), 1)]

    c = rep["fields"]["case"]
    checks += [("case raw agreement", round(c["raw_exact_agreement"], 4), 0.75),
               ("case po", round(c["po"], 4), 0.75),
               ("case kappa in range", -1.0 <= c["kappa"] <= 1.0, True)]
    ct = c["taxonomy"]
    checks += [("case tax GEN vs NOM", ct.get("GEN vs NOM"), 1),
               ("case tax ABSTAIN vs GEN", ct.get("ABSTAIN vs GEN"), 1),
               ("case tax blank vs GEN", ct.get("(blank) vs GEN"), 1),
               ("case tax total disagreements", sum(ct.values()), 3)]

    cf = rep["fields"]["confidence"]
    checks += [("conf raw agreement", round(cf["raw_exact_agreement"], 4), 0.75),
               ("conf kappa in range", -1.0 <= cf["kappa"] <= 1.0, True),
               ("conf conflicts", sum(cf["taxonomy"].values()), 3),
               ("conf tax blank vs medium", cf["taxonomy"].get("(blank) vs medium"), 1)]

    # the blank/abstention distinction, asserted directly
    checks += [("blank is NOT abstain (case)", norm_case(""), BLANK),
               ("blank is NOT abstain (conf)", norm_conf("   "), BLANK),
               ("abstain IS abstain (case)", norm_case("ABSTAIN"), "ABSTAIN"),
               ("scorer-typo 'na' still abstains", norm_case("n/a"), "ABSTAIN"),
               ("blank root is empty", norm_root(""), ""),
               ("abstain root is empty", norm_root("ABSTAIN"), "")]

    # Rule 6 gate, asserted directly
    checks += [("gate rejects repeated digit", rule6_wellformed("1َ2ْ2"), False),
               ("gate accepts distinct digits", rule6_wellformed("1َ2ْ3"), True),
               ("gate failures A", rep["rule6"]["A"], 0),
               ("gate failures B", rep["rule6"]["B"], 0)]

    # ---- the `alternatives` column: grammar + measurement (Amendment 1) ----------------------
    ok = [("NONE", NONE_TOKEN, 0),
          ("  none  ", NONE_TOKEN, 0),
          ("case=NOM", ("case=NOM",), 1),
          ("root=ق.و.ل | case=GEN", ("case=GEN", "root=ق.و.ل"), 2),
          ("case=GEN | root=ق.و.ل", ("case=GEN", "root=ق.و.ل"), 2),
          ("wazn_pattern=1َ2َ3", ("wazn=1َ2َ3",), 1),
          ("wazn=1َ2َ3", ("wazn=1َ2َ3",), 1),
          ("", "", 0)]
    for raw, want_c, want_n in ok:
        c, n, e = parse_alternatives(raw)
        checks.append(("alternatives ok %r" % raw, (c, n, len(e)), (want_c, want_n, 0)))
    # order-independence and the wazn/wazn_pattern alias must give IDENTICAL canonical forms
    checks.append(("alternatives order-independent",
                   parse_alternatives("root=ق.و.ل | case=GEN")[0],
                   parse_alternatives("case=GEN | root=ق.و.ل")[0]))
    checks.append(("wazn alias canonicalises to one form",
                   parse_alternatives("wazn_pattern=1َ2َ3")[0],
                   parse_alternatives("wazn=1َ2َ3")[0]))
    bad_alts = ["case=ABSTAIN", "mood=NOM", "case", "case=NOM nonsense", "|", "root="]
    for raw in bad_alts:
        _, _, e = parse_alternatives(raw)
        checks.append(("alternatives rejects %r" % raw, len(e) > 0, True))

    ALT_PAIRS = [("NONE", "NONE"), ("case=NOM", "case=NOM"), ("NONE", "case=GEN"),
                 ("case=NOM", "case=GEN"), ("root=ق.و.ل | case=GEN", "case=GEN | root=ق.و.ل"),
                 ("", ""), ("", "NONE"), ("case=ABSTAIN", "case=NOM"),
                 ("case=NOM nonsense", "NONE"), ("mood=NOM", "NONE")]
    ra = [{"id": "Y%03d" % i, "root": "ك.ت.ب", "wazn_pattern": "1َ2َ3", "case": "NOM",
           "confidence": "high", "alternatives": a} for i, (a, b) in enumerate(ALT_PAIRS)]
    rb = [{"id": "Y%03d" % i, "root": "ك.ت.ب", "wazn_pattern": "1َ2َ3", "case": "NOM",
           "confidence": "high", "alternatives": b} for i, (a, b) in enumerate(ALT_PAIRS)]
    altr = report(ra, rb)["alternatives"]
    at = altr["taxonomy"]
    checks += [("alt tax both NONE", at.get("both NONE (agree: no rival analysis)"), 1),
               ("alt tax same candidate set", at.get("same candidate set"), 2),
               ("alt tax one NONE other listed", at.get("one NONE, other listed candidates"), 1),
               ("alt tax different sets", at.get("different candidate sets"), 1),
               ("alt tax both blank", at.get("both left blank (unfinished)"), 1),
               ("alt tax one blank", at.get("one blank, other filled"), 1),
               ("alt tax malformed", at.get("MALFORMED entry (fix before adjudication)"), 3),
               ("alt tax total", sum(at.values()), 10),
               ("alt filled A", round(altr["filled"]["A"], 4), 0.5),
               ("alt filled B", round(altr["filled"]["B"], 4), 0.9),
               ("alt rival rows A", altr["rows_with_a_rival_analysis"]["A"], 3),
               ("alt rival rows B", altr["rows_with_a_rival_analysis"]["B"], 5),
               ("alt malformed A", altr["malformed"]["A"], 3),
               ("alt malformed B", altr["malformed"]["B"], 0),
               ("alt case candidates A", altr["by_field"]["case"]["A"], 3),
               ("alt root candidates A", altr["by_field"]["root"]["A"], 1)]

    # blank != NONE: a skipped row must never read as a considered "no rival analysis"
    checks.append(("blank alternatives != NONE", parse_alternatives("")[0] != NONE_TOKEN, True))

    bad = [(n, g, w_) for n, g, w_ in checks if g != w_]
    print("  selftest checks: %d, failures: %d" % (len(checks), len(bad)))
    for name, got, want in checks:
        print("    %s %-36s got=%r want=%r" % ("ok  " if got == want else "FAIL", name, got, want))
    if bad:
        print("\n  SELFTEST FAILED")
        return 1
    print("\n  SELFTEST PASSED -- per-field agreement, kappa and the disagreement taxonomy behave")
    print("  as intended, including the blank-cell != abstention rule.")
    return 0


def validate_file(path: Path) -> int:
    """Format-check ONE returned sheet. Run this on the practice pack the moment it comes back,
    and on the benchmark before any agreement number is believed: a malformed cell that reaches
    the agreement report makes the report wrong, not merely noisy. Exit 3 on any format error."""
    EXPECTED = ["id", "sentence_with_target_in_double_brackets", "target_token",
                "root", "wazn_pattern", "case", "alternatives", "confidence", "notes"]
    OLD8 = ["id", "sentence_with_target_in_double_brackets", "target_token",
            "root", "wazn_pattern", "case", "confidence", "notes"]
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rdr = csv.DictReader(fh)
        cols = list(rdr.fieldnames or [])
        rows = list(rdr)

    print("=" * 82)
    print("SHEET VALIDATION — %s" % path.name)
    print("=" * 82)
    print("  rows: %d" % len(rows))
    if cols != EXPECTED:
        if cols == OLD8:
            print("  !! 8-column sheet: predates Amendment 1 (no `alternatives` column).")
        else:
            print("  !! COLUMNS DIFFER from the frozen schema")
        print("     expected: %s" % EXPECTED)
        print("     found   : %s" % cols)

    errors, unfinished = [], 0
    for r in rows:
        rid = r.get("id", "?")
        ctx = r.get("sentence_with_target_in_double_brackets", "")
        tok = r.get("target_token", "")
        if "[[" not in ctx or "]]" not in ctx:
            errors.append("%s: target marker [[ ]] missing from the sentence" % rid)
        elif tok and tok not in ctx:
            errors.append("%s: target_token %r does not appear inside [[ ]]" % (rid, tok))
        ans = [c for c in ("root", "wazn_pattern", "case", "alternatives", "confidence", "notes")
               if (r.get(c) or "").strip()]
        if not ans:
            unfinished += 1
            continue
        if (r.get("root") or "").strip():
            rv = r["root"].strip()
            if not _abstained(rv) and (not norm_root(rv) or len(norm_root(rv)) < 3):
                errors.append("%s: root %r is neither a 3-4 radical root nor ABSTAIN" % (rid, rv))
        if (r.get("wazn_pattern") or "").strip():
            wv = r["wazn_pattern"].strip()
            if not _abstained(wv) and not rule6_wellformed(wv):
                errors.append("%s: wazn_pattern %r fails the Rule 6 digit gate" % (rid, wv))
        if (r.get("case") or "").strip():
            cv = r["case"].strip()
            if norm_case(cv) not in CASE_CATS:
                errors.append("%s: case %r is not NOM/ACC/GEN/ABSTAIN" % (rid, cv))
        if (r.get("confidence") or "").strip():
            v = r["confidence"].strip().lower()
            if v not in CONF_CATS:
                errors.append("%s: confidence %r is not high/medium/low" % (rid, v))
        # the new column: grammar, plus the two consistency rules that make it usable
        ca, na, ea = parse_alternatives(r.get("alternatives", ""))
        for e in ea:
            errors.append("%s: alternatives :: %s" % (rid, e))
        if (r.get("case") or "").strip() and norm_case(r["case"]) == "ABSTAIN":
            note = (r.get("notes") or "")
            if "both-readings-viable" in note:
                if ca == NONE_TOKEN:
                    errors.append("%s: case=ABSTAIN both-readings-viable but alternatives=NONE "
                                  "(a viable alternative must be listed)" % rid)
                elif isinstance(ca, tuple) and len([x for x in ca if x.startswith("case=")]) < 2:
                    errors.append("%s: both-readings-viable needs BOTH case candidates in "
                                  "alternatives" % rid)
            elif "ABSTAIN:" not in note:
                errors.append("%s: case=ABSTAIN without an ABSTAIN: reason tag in notes" % rid)

    print("  filled rows: %d / %d   (unfinished: %d)" % (len(rows) - unfinished, len(rows), unfinished))
    if not errors:
        if unfinished == len(rows):
            print("\n  -- pristine sheet: 0 rows filled, nothing to validate yet. OK.")
        else:
            print("\n  OK — no format errors.")
        return 0
    print("\n  %d FORMAT ERROR(S) — fix before scoring:" % len(errors))
    for e in errors[:40]:
        print("    - %s" % e)
    if len(errors) > 40:
        print("    ... and %d more" % (len(errors) - 40))
    return 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a"), ap.add_argument("--b"), ap.add_argument("--key"),
    ap.add_argument("--json"), ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--validate", metavar="SHEET",
                    help="format-check ONE returned sheet (practice pack or a real return)")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.validate:
        return validate_file(Path(args.validate))
    if not (args.a and args.b):
        ap.error("--a and --b are required (or use --selftest / --validate)")
    rep = report(load(Path(args.a)), load(Path(args.b)),
                 load(Path(args.key)) if args.key else None)
    print_report(rep)
    if args.json:
        Path(args.json).write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
        print("\n  wrote %s" % args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
