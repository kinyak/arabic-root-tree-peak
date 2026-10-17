"""Audit the renderer's GENUINE failures: dump (surface, lemma, root, pattern).

`renderer.py --measure` reports 18 content-word tokens that HAVE a usable gold root and
still do not render. This dumps their exact tuples and classifies each one as either an
UPSTREAM contradiction (CAMeL's own root and pattern disagree with each other, e.g.
أسقف -> root سقف but a 4-slot pattern أُ2ْ3ُ4ُ) or a RENDERING-RULE gap (arity is
consistent and the rule still refuses).

Read-only. No artifact is written except the console report.

Run:  .venv/Scripts/python.exe src/audit_arity_failures.py
"""
from __future__ import annotations

import collections
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(Path(__file__).resolve().parent.parent)

import reconcile as RC
from reconcile import RootDictionary, reconcile, is_gold_root, ARABIC, padt_to_arabic
from renderer import read_padt_tokens, build_table, render_rule, hybrid_render, norm_root
from build_training_jsonl import build_silver_root_dict
from paths import PADT_TEST, PADT_TRAIN

LIMIT = 4000
TABLE_LIMIT = 14000
CONTENT = {"NOUN", "VERB", "ADJ", "ADV", "PROPN", "NUM", "AUX"}
DIGITS = "1234"


def rads_of(root):
    """Radical count of a dotted (و.ز.ر) or undotted (وزر) root, '#' counted."""
    if not root:
        return 0
    return len([c for c in root if c not in ". "])


def classify(rroot, pat):
    """Why did the hybrid fail for this token?"""
    if not rroot:
        return "SUPPLY        (no root from CALIMA, dictionary or strips)"
    if not pat or "NTWS" in pat or "backoff" in pat:
        return "PATTERN       (upstream: CAMeL supplied no numeric pattern)"
    digits = {d for d in pat if d in DIGITS}
    n = rads_of(rroot)
    if len(digits) != n:
        return (f"UPSTREAM ARITY (CAMeL root has {n} radicals but the pattern implies "
                f"{len(digits)} slots)")
    return "RULE GAP      (arity is consistent and the rule still refuses)"


def main():
    # ONE reader. `renderer.read_padt_tokens` is the authority; this script used to carry
    # its own copy of the reader and the copy silently diverged (it imported
    # `reconcile.ARABIC`, which includes tatweel U+0640, while renderer defines its own
    # ARABIC that excludes it) — 3,719 of 4,000 tokens ended up misaligned, and the
    # failure count came out 13 instead of the instrument's 18. A duplicated reader is a
    # duplicated metric.
    test = read_padt_tokens(PADT_TEST, LIMIT)

    from camel_tools.disambig.mle import MLEDisambiguator
    mle = MLEDisambiguator.pretrained("calima-msa-r13")
    surf = [t["form"] for t in test]
    ana = []
    for i in range(0, len(surf), 500):
        for d in mle.disambiguate(surf[i:i + 500]):
            ana.append(d.analyses[0].analysis if (d and d.analyses) else None)

    table, tstats = build_table([PADT_TRAIN], TABLE_LIMIT)
    silver, _ = build_silver_root_dict()
    dic = RootDictionary.build_from_padt([PADT_TRAIN])
    for s, r in silver.items():
        dic.mapping.setdefault(s, r)

    failures = []
    for t, a in zip(test, ana):
        pat = a.get("pattern") if a else None
        croot = a.get("root") if a else None
        try:
            rroot, rroute = reconcile(t["form"], croot, dic)
        except ValueError:
            rroot, rroute = None, "fail"
        # hybrid: the SAME shared decision the measurement uses (renderer.hybrid_render)
        got, branch, why = hybrid_render(rroot, pat, t["case"], table)
        if got is not None:
            continue
        usable = bool(t["gold_root"]) and is_gold_root(t["gold_root"], t["upos"])
        if t["upos"] in CONTENT and usable:
            failures.append({
                "surface": t["form"], "lemma": t["lemma"], "upos": t["upos"],
                "gold_translit": t["gold_root"],
                "gold_arabic": norm_root(
                    t["gold_root"] if ARABIC.search(t["gold_root"])
                    else (padt_to_arabic(t["gold_root"]) or "")),
                "calima_root": croot, "pattern": pat, "reconciled_root": rroot,
                "route": rroute, "reason": why,
                "diagnosis": classify(rroot, pat),
            })

    print("=" * 108)
    print(f"THE ACTIONABLE RENDERING FAILURES — content words WITH a usable gold root, "
          f"none of them rendered  (n={len(failures)})")
    print("=" * 108)
    hdr = f"{'surface':<12}{'lemma':<12}{'upos':<7}{'gold(root)':<11}{'calima root':<13}{'pattern':<16}{'recon':<11}diagnosis"
    print(hdr)
    print("-" * 108)
    for f in failures:
        print(f"{f['surface']:<12}{f['lemma']:<12}{f['upos']:<7}"
              f"{f['gold_arabic']:<11}{str(f['calima_root']):<13}{str(f['pattern']):<16}"
              f"{str(f['reconciled_root']):<11}{f['diagnosis'].split('(')[0].strip()}")

    print("\n" + "-" * 108)
    tally = collections.Counter(f["diagnosis"].split("(")[0].strip() for f in failures)
    for k, v in tally.most_common():
        print(f"  {v:>3}  {k}")
    up = tally.get("UPSTREAM ARITY", 0)
    print(f"\n  upstream arity contradictions (CAMeL disagrees with itself): {up}/{len(failures)}"
          f" = {100*up/max(len(failures),1):.0f}%")
    print("  => the ones worth a renderer rule are the RULE GAP rows; the UPSTREAM rows")
    print("     are a data-quality finding about CAMeL, not a renderer defect.")
    print("\n  detail (reason codes from render_rule):")
    for f in failures:
        print(f"    {f['surface']:<12} reason={f['reason']:<22} diag={f['diagnosis']}")

    # ---- RECONCILE against the instrument that writes the report. Two hand-rolled
    # copies of the same decision drift; this repo's rule is that numbers must agree or
    # the disagreement is itself the finding. Print both, and the gap, always.
    print("\n" + "=" * 108)
    print("RECONCILIATION against data/out/renderer_report.json (the quoted instrument)")
    print("=" * 108)
    print(f"  this audit finds content+usable-gold failures : {len(failures)}")
    rp = Path("data/out/renderer_report.json")
    if rp.exists():
        rep = json.loads(rp.read_text(encoding="utf-8"))
        btc = rep.get("by_token_class", {})
        print(f"  renderer_report.json reports arity failures   : "
              f"{btc.get('failing_with_usable_gold_root')}")
        print(f"    (content tokens {btc.get('content_tokens')} · rendered "
              f"{btc.get('content_rendered')} · no-root {btc.get('failing_without_any_root')}"
              f" · floor {btc.get('closed_class_unrendered_structural_floor')})")
        if btc.get("failing_with_usable_gold_root") != len(failures):
            print("  ⚠️ MISMATCH — the two instruments disagree. One of them is wrong;")
            print("     do NOT quote either count until the gap is explained.")
        else:
            print("  ✅ agree.")


if __name__ == "__main__":
    main()
