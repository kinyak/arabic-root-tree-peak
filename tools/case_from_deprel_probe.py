"""case_from_deprel_probe.py — is CASE derivable from SYNTAX? Measured, not assumed.

WHY THIS EXISTS
    A proposal to reach the accuracy target rests on one load-bearing claim: that once the
    dependency relation and POS are known, Arabic case is a near-deterministic rule (">97%
    consistency"), so a biaxial dependency parser would lift case macro-F1 from 47.1% to 92-94%.

    That claim is testable RIGHT NOW, offline, on CPU, against the treebanks already in
    data/raw/ — no parser needs to be trained and no GPU is required. The measurement is the
    ORACLE ceiling for the proposal's own rule: it uses GOLD deprel and GOLD upos, so a trained
    parser can only do worse. If the oracle ceiling is below the claimed target, the target is
    unreachable by that route regardless of how good the parser is.

WHAT IT REPORTS
    1. consistency of P(Case | upos, deprel) learned on TRAIN, evaluated on DEV
    2. the deterministic-mapping accuracy and macro-F1 over {Nom, Acc, Gen}  (oracle ceiling)
    3. the same for P(Case | upos) ALONE -- i.e. how much syntax adds over POS
    4. the selective subset where the (upos, deprel) mapping is unambiguous in train (>= tau),
       with its coverage: the realistic deployable rule
    5. sensitivity to parser error: gold deprel corrupted at rate p (a predicted parser is not
       gold, so the oracle number is an upper bound that this bounds from below)
    6. cross-treebank transfer (fit PADT -> evaluate NYUAD, and the reverse)

CPU only, zero GPU. Reads the CoNLL-U files the project already ships in data/raw/.

USAGE
    python tools/case_from_deprel_probe.py [--root PATH] [--tau 0.95]
"""
from __future__ import annotations

import argparse
import collections
import random
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_root import resolve_root  # noqa: E402

CASES = ("Nom", "Acc", "Gen")


def read_conllu(path: Path):
    """-> list of (upos, deprel, case) for tokens carrying a Case feature."""
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip() or line.startswith("#"):
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) < 8:
                continue
            upos, feats, deprel = c[3], c[5], c[7]
            case = "None"
            for f in feats.split("|"):
                if f.startswith("Case="):
                    case = f.split("=", 1)[1]
                    break
            if case in CASES:
                out.append((upos, deprel, case))
    return out


def fit(rows, keyfn):
    """-> {key: {case: count}}"""
    m = collections.defaultdict(collections.Counter)
    for upos, deprel, case in rows:
        m[keyfn(upos, deprel)][case] += 1
    return m


def predict(m, upos, deprel, keyfn, backoff=None, global_default="Acc"):
    key = keyfn(upos, deprel)
    if key in m:
        return m[key].most_common(1)[0][0], m[key]
    if backoff is not None:
        return predict(backoff, upos, deprel, lambda u, d: u, None, global_default)
    return global_default, None


def macro_f1(gold, pred):
    f1s = []
    for c in CASES:
        tp = sum(1 for g, p in zip(gold, pred) if g == c and p == c)
        fp = sum(1 for g, p in zip(gold, pred) if g != c and p == c)
        fn = sum(1 for g, p in zip(gold, pred) if g == c and p != c)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return sum(f1s) / len(f1s)


def evaluate(train, dev, label, tau=None, keyfn=None):
    keyfn = keyfn or (lambda u, d: (u, d))
    m = fit(train, keyfn)
    back = fit(train, lambda u, d: u)
    gold = [c for _, _, c in dev]
    pred = [predict(m, u, d, keyfn, back)[0] for u, d, _ in dev]
    acc = sum(1 for g, p in zip(gold, pred) if g == p) / len(gold)
    line = "  %-34s acc=%.4f  macroF1=%.4f" % (label, acc, macro_f1(gold, pred))
    if tau is not None:
        keep = [i for i, (u, d, _) in enumerate(dev)
                if (u, d) in m and m[(u, d)].most_common(1)[0][1] / sum(m[(u, d)].values()) >= tau]
        if keep:
            a = sum(1 for i in keep if gold[i] == pred[i]) / len(keep)
            line += "   | unambiguous-subset (tau=%.2f): coverage=%.3f acc=%.4f" % (
                tau, len(keep) / len(dev), a)
    print(line)
    return acc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--tau", type=float, default=0.95)
    args = ap.parse_args()
    ROOT = resolve_root(args.root)
    raw = ROOT / "data/raw"

    sets = {}
    for tag, f in (("PADT-train", "ar_padt-ud-train.conllu"), ("PADT-dev", "ar_padt-ud-dev.conllu"),
                   ("NYUAD-train", "ar_nyuad-ud-train.conllu"), ("NYUAD-dev", "ar_nyuad-ud-dev.conllu")):
        sets[tag] = read_conllu(raw / f)

    print("=" * 96)
    print("IS CASE A FUNCTION OF SYNTAX?  (gold upos + gold deprel -> oracle ceiling)")
    print("=" * 96)
    for t in ("PADT-train", "PADT-dev", "NYUAD-train", "NYUAD-dev"):
        d = collections.Counter(c for _, _, c in sets[t])
        print("  %-14s Case-bearing tokens=%6d   %s" % (t, len(sets[t]),
              {k: round(v / len(sets[t]), 3) for k, v in d.most_common()}))

    print("\n--- the proposal's rule: P(Case | upos, deprel), fitted on train, tested on dev ---")
    evaluate(sets["PADT-train"], sets["PADT-dev"], "PADT: (upos,deprel)", args.tau)
    evaluate(sets["NYUAD-train"], sets["NYUAD-dev"], "NYUAD: (upos,deprel)", args.tau)

    print("\n--- how much does SYNTAX add over POS alone? ---")
    evaluate(sets["PADT-train"], sets["PADT-dev"], "PADT: upos only", None,
             keyfn=lambda u, d: u)
    evaluate(sets["NYUAD-train"], sets["NYUAD-dev"], "NYUAD: upos only", None,
             keyfn=lambda u, d: u)

    print("\n--- cross-treebank transfer (does the rule generalise?) ---")
    evaluate(sets["PADT-train"], sets["NYUAD-dev"], "PADT -> NYUAD")
    evaluate(sets["NYUAD-train"], sets["PADT-dev"], "NYUAD -> PADT")

    print("\n--- sensitivity: a PREDICTED deprel is not gold. Corrupt gold deprel at rate p ---")
    rng = random.Random(20261012)
    inv = sorted({d for _, d, _ in sets["PADT-train"]})
    m = fit(sets["PADT-train"], lambda u, d: (u, d))
    back = fit(sets["PADT-train"], lambda u, d: u)
    for p in (0.0, 0.05, 0.10, 0.15, 0.20):
        gold, pred = [], []
        for u, d, c in sets["PADT-dev"]:
            dd = rng.choice(inv) if rng.random() < p else d
            gold.append(c)
            pred.append(predict(m, u, dd, lambda u, d: (u, d), back)[0])
        print("  deprel noise p=%.2f   acc=%.4f   macroF1=%.4f" % (
            p, sum(1 for g, q in zip(gold, pred) if g == q) / len(gold), macro_f1(gold, pred)))

    print("\n--- most ambiguous (upos, deprel) pairs in PADT train, by token count ---")
    for (u, d), cnt in sorted(m.items(), key=lambda kv: -sum(kv[1].values()))[:8]:
        tot = sum(cnt.values())
        top, topn = cnt.most_common(1)[0]
        print("  (%-6s, %-12s) n=%6d  majority=%-4s %.3f   %s" % (
            u, d, tot, top, topn / tot, dict(cnt.most_common())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
