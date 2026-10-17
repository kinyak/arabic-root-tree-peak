"""stem_tail_audit.py — measure and GATE the `stem_tail` class space.

§2cs measured the defect: the 30-class space was derived from a 278-row curated file, so 16.7% of PADT's
supervised tails (8.4% of silver's) fell to `v.stem_tail.get(raw_tail, 0)` — class 0, the BARE STEM, a
meaningful class. Those rows were taught a confident wrong label with a LIVE gradient.

§2cz ships the repair, and this tool gates it. Two spaces are measured in ONE pass over the corpora:

  `full` (default)  the SHIPPED space: the 30 gold-300 classes + every real-unseen tail the training
                    corpora supervise (as its own class) + the mark-ORDER-ambiguous tails (as their own
                    class, because the honest answer to two equidistant rewrites is to not rewrite).
  `30`              the LEGACY space, still gated so every §2cs/§2cu number keeps its meaning.

The rule is NOT defined here — it is imported from `src/wazan_normalizer.py` (`bridge_stem_tail`) and
cross-checked against a local reference on EVERY observed tail. A private copy in a tool is the bug.
"""
import argparse
import collections
import hashlib
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TOOLS))
sys.path.insert(0, str(_TOOLS.parent / "src"))

from repo_root import resolve_root                        # noqa: E402
import wazan_normalizer as W                              # noqa: E402

PADT = Path("data") / "out" / "padt-train.jsonl"
SILVER = Path("data") / "out" / "spread-B-2m" / "tashkeela-train.jsonl"
RULER = Path("data") / "annotation" / "bench-gold.jsonl"
RULER_SHA256 = "7a06a585e065d8cf41358210e74db5c638dafe8c81f67bf1ee87790134885b07"
RULER_PATTERN_FIELD = "wazn_pattern"      # NOT t_wazan / t_wazan_pattern
ARTIFACT = Path("dist") / "stem-tail-audit.json"

COMB = set(range(0x064B, 0x0653)) | {0x0670}
SHADDA_C = "\u0651"

# --- pins ---------------------------------------------------------------------------------------
# Asserted by --check, never tuned to pass. Re-derive ONLY with the reason written beside the number.
P_30 = {                                     # §2cs/§2cu — the legacy 30-class space
    "inventory_n": 30,
    "inventory_sha256": "bc6626e1a3ce67fa539eb8fb77442c9db777cac3ed8e9dc42e6ef31b434e1a7d",
    "padt": {"m_wazan": 115370, "distinct": 89, "out": 19219, "determinate": 10480,
             "tie": 4595, "new": 4119, "junk": 25,
             "n_determinate": 12, "n_tie": 4, "n_new": 61, "n_junk": 5,
             "changed_not_inventory": 0},
    "silver": {"m_wazan": 1119241, "distinct": 138, "out": 93629, "determinate": 27090,
               "tie": 29860, "new": 36268, "junk": 411,
               "n_determinate": 16, "n_tie": 4, "n_new": 109, "n_junk": 3,
               "changed_not_inventory": 0},
    "ruler": {"records": 1000, "distinct": 25, "in_inventory": 982, "bridge": 9,
              "new": 9, "tie": 0, "ceiling_today": 982, "ceiling_bridge": 991,
              "ceiling_with_new": 1000,
              # ESCAPES. This pin was committed as literal glyphs and re-typed from memory during the §2cz
              # rewrite in the REVERSE mark order ("\u0649\u064e" instead of "\u064e\u0649"), and the gate
              # caught it on the first `--check` — the instrument was right and the pin was wrong. Stated as
              # codepoints so it cannot be typed wrong again.
              "new_classes": ("\u064e\u0627", "\u064e\u062a\u064e\u064a\u0652\u0646", "\u064e\u0649")},
    "totals": {"repaired": 37570, "masked": 75278, "tie": 34455, "new": 40387, "junk": 436},
}
# The bridge's DETERMINATE mappings in the LEGACY 30-space, keyed by variant -> target. Token counts are
# printed live. A rule that stops resolving one of these is a change of VERDICT, not drift. In the SHIPPED
# space these tails are classes of their own (see P_BRIDGE_TARGETS_FULL), so the mapping is asserted where
# it is live — in the `30` space.
# ESCAPES, never typed marks — the terminal renders combining marks spaced apart and a stray U+0020 copied
# out of a printed listing is invisible in the source, which is exactly how this file's first run failed.
P_BRIDGE_TARGETS = {
    "\u0627\u062a": "\u064e\u0627\u062a",                          # ات   -> َات
    "\u0650\u064a": "\u0650\u064a\u0651",                          # ِي   -> ِيّ
    "\u0651\u064e\u0629": "\u064e\u0629",                          # ّة   -> َة    (shadda -> stem)
    "\u0646": "\u0646\u064e",                                      # ن    -> نَ
    "\u0627\u0621": "\u064e\u0627\u0621",                          # اء   -> َاء
    "\u0627\u0646": "\u064e\u0627\u0646",                          # ان   -> َان
    "\u064f\u0648\u0646": "\u064f\u0648\u0646\u064e",              # ُون  -> ُونَ
    "\u0650\u064a\u064e\u0629": "\u0650\u064a\u0651\u064e\u0629",  # ِيَة -> ِيّة
    "\u064e\u062a\u0627\u0646": "\u064e\u062a\u064e\u0627\u0646",  # َتان -> َتَان
    "\u0652\u062a\u064f\u0645": "\u0652\u062a\u064f\u0645\u0652",  # ْتُم -> ْتُمْ
    "\u0651\u0627\u062a": "\u064e\u0627\u062a",                    # ّات  -> َات
    "\u064e\u0646": "\u0646\u064e",                                # َن   -> نَ
}
# §2cz — the bridge's SURVIVING job in the SHIPPED space: a tail the training corpora NEVER attest. These
# three are the whole of it, measured on the frozen ruler (7 rows). They are rule pins, and they are the
# reason the bridge still exists: without it those 7 rows are class-0-or-nothing.
P_BRIDGE_TARGETS_FULL = {
    "\u0651": "",                                              # ّ    -> ''   pure-stem shadda: no suffix
    "\u064f\u0651\u0648\u0627": "\u064f\u0648\u0627",          # ُّوا -> ُوا
    "\u0651\u064e\u062a\u0652": "\u064e\u062a\u0652",          # َّتْ -> َتْ
}
# §2cz — the SHIPPED space. Filled from a measure run (`--emit-pins`), never from memory.
P_FULL = {
    "inventory_n": 176,
    "inventory_sha256": "3000bf51b8dade46cba0161cf33c2d8224cae422b7382dd540c921ab8e6d2166",
    "padt": {"m_wazan": 115370, "distinct": 89, "out": 25, "determinate": 0, "tie": 0, "new": 0,
             "junk": 25, "n_determinate": 0, "n_tie": 0, "n_new": 0, "n_junk": 5,
             "changed_not_inventory": 0, "zero_class_suffixed": 0, "ignore_real": 0, "ignore_junk": 25},
    "silver": {"m_wazan": 1119241, "distinct": 138, "out": 411, "determinate": 0, "tie": 0, "new": 0,
               "junk": 411, "n_determinate": 0, "n_tie": 0, "n_new": 0, "n_junk": 3,
               "changed_not_inventory": 0, "zero_class_suffixed": 0, "ignore_real": 0, "ignore_junk": 411},
    "ruler": {"records": 1000, "distinct": 25, "in_inventory": 989, "bridge": 7, "new": 4, "tie": 0,
              "ceiling_today": 989, "ceiling_bridge": 996, "ceiling_with_new": 1000,
              "new_classes": ("\u064e\u0627",)},
    "totals": {"bridged": 0, "masked": 436, "unresolved_real": 0},
    # Cross-space: rows that carried the class-0 "bare stem" label and now carry their own class.
    "promoted_total": 112412,
}


def _base(s):
    return "".join(c for c in s if ord(c) not in COMB)


def _marks(s):
    return collections.Counter(c for c in s if ord(c) in COMB)


def _is_arabic(c):
    return 0x0621 <= ord(c) <= 0x064A or 0x0671 <= ord(c) <= 0x06D3


def _strip_stem_shadda(t):
    """Move a shadda sitting BEFORE the tail's first base letter onto the stem."""
    i = next((k for k, c in enumerate(t) if _is_arabic(c)), None)
    if i is None:
        return t.replace(SHADDA_C, ""), True
    if any(ord(c) == 0x0651 for c in t[:i]):
        return t[:i].replace(SHADDA_C, "") + t[i:], True
    return t, False


def classify_ref(tail, inv):
    """The REFERENCE implementation — kept for the cross-check, never used to produce a number."""
    if not tail:
        return "BARE", None, 0, False
    if not all(0x0600 <= ord(c) <= 0x06FF for c in tail):
        return "JUNK", None, 0, False
    if tail in inv:
        return "IDENTITY", tail, 0, False
    t2, moved = _strip_stem_shadda(tail)
    if t2 == "":
        return "DETERMINATE", "", 0, moved
    if t2 in inv:
        return "DETERMINATE", t2, 0, moved
    cands = []
    for c in inv:
        if _base(c) != _base(t2):
            continue
        if _marks(t2) - _marks(c):
            continue
        cands.append((sum((_marks(c) - _marks(t2)).values()), inv.index(c), c))
    if not cands:
        return "NEW", None, 0, moved
    cands.sort()
    tied = [c for c in cands if c[0] == cands[0][0]]
    if len(tied) > 1:
        return "TIE", [c[2] for c in tied], cands[0][0], moved
    return "DETERMINATE", tied[0][2], cands[0][0], moved


def load_classify():
    """Prefer the SHIPPED rule. Returns (fn, source, reference_or_None)."""
    shipped = getattr(W, "bridge_stem_tail", None)
    if shipped is None:
        return classify_ref, "REFERENCE — `bridge_stem_tail` is absent from src/wazan_normalizer.py", None
    return shipped, "src.wazan_normalizer.bridge_stem_tail (SHIPPED)", classify_ref


def spaces():
    """name -> class list. `full` is what ships; `30` is the legacy record."""
    return {"full": [str(x) for x in W.STEM_TAIL_VOCALIZED],
            "30": [str(x) for x in W.STEM_TAIL_VOCALIZED_GOLD300]}


def inv_sha(inv):
    return hashlib.sha256(json.dumps(inv, ensure_ascii=False).encode("utf-8")).hexdigest()


def tail_census(path, limit=None):
    """ONE pass: tail -> supervised tokens, exactly as training reads it."""
    cnt = collections.Counter()
    n = m1 = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            n += 1
            t = json.loads(line)
            if t.get("m_wazan") != 1:
                continue
            m1 += 1
            cnt[W.vocalized_stem_tail(t.get("t_wazan") or "") or ""] += 1
            if limit and n >= limit:
                break
    return cnt, n, m1


def resolve_space(cnt, m1, inv, classify):
    """Classify every DISTINCT tail once (the resolution depends only on the tail) and weight by tokens."""
    out = {}
    kinds = collections.Counter()
    toks = collections.Counter()
    targets = {}
    moved_inv = 0
    zero_suffixed = 0          # non-empty tail landing on class 0 outside the pure-mark rule
    ignore_junk = ignore_real = 0
    for tail, c in cnt.items():
        k, tgt, _, _ = classify(tail, inv)
        if tail in inv:
            # An in-space tail must resolve to ITSELF. `""` is in the space and legitimately resolves to
            # BARE (class 0), so that is the one allowed exception — and it is stated, not assumed.
            if not ((k == "IDENTITY" and tgt == tail) or (tail == "" and k == "BARE")):
                moved_inv += c
            continue
        out[tail] = c
        kinds[k] += 1
        toks[k] += c
        if k in ("DETERMINATE", "IDENTITY"):
            targets[tail] = tgt
        idx = None
        if k == "BARE":
            idx = 0
        elif isinstance(tgt, str) and tgt in inv:
            idx = inv.index(tgt)
        if idx == 0 and tail and _base(tail) != "":
            zero_suffixed += c        # a real suffix taught the bare-stem class = the §2cs defect
        if idx == W.STEM_TAIL_IGNORE or (idx is None and k not in ("BARE",)):
            if all(0x0600 <= ord(x) <= 0x06FF for x in tail):
                ignore_real += c
            else:
                ignore_junk += c
    return {"m_wazan": m1, "distinct": len(cnt),
            "in_inventory": sum(v for k, v in cnt.items() if k in inv),
            "out": sum(out.values()),
            "determinate": toks["DETERMINATE"], "tie": toks["TIE"],
            "new": toks["NEW"], "junk": toks["JUNK"],
            "n_determinate": kinds["DETERMINATE"], "n_tie": kinds["TIE"],
            "n_new": kinds["NEW"], "n_junk": kinds["JUNK"],
            "targets": targets, "outside": out,
            "changed_not_inventory": moved_inv,
            "zero_class_suffixed": zero_suffixed,
            "ignore_real": ignore_real, "ignore_junk": ignore_junk}


def ruler_audit(path, inv, classify):
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    rows = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]
    tc = collections.Counter()
    for r in rows:
        tc[W.vocalized_stem_tail(r.get(RULER_PATTERN_FIELD) or "") or ""] += 1
    inside = sum(n for k, n in tc.items() if k in inv)
    out = {k: n for k, n in tc.items() if k not in inv}
    bridge = new = tie = 0
    detail = []
    for tail, n in sorted(out.items(), key=lambda kv: (-kv[1], kv[0])):
        k, tgt, _, _ = classify(tail, inv)
        detail.append({"tail": tail, "n": n, "kind": k, "target": tgt})
        if k == "DETERMINATE":
            bridge += n
        elif k == "NEW":
            new += n
        else:
            tie += n
    return {"sha256": digest, "records": len(rows), "distinct": len(tc), "in_inventory": inside,
            "bridge": bridge, "new": new, "tie": tie,
            "ceiling_today": inside, "ceiling_bridge": inside + bridge,
            "ceiling_with_new": inside + bridge + new, "detail": detail,
            "new_classes": sorted({d["tail"] for d in detail if d["kind"] == "NEW"})}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="measure and gate the stem_tail class space (§2cs/§2cz)")
    ap.add_argument("--check", action="store_true", help="assert the pre-registered numbers")
    ap.add_argument("--space", default="full", choices=("full", "30", "both"),
                    help="which space to measure (default: the shipped one)")
    ap.add_argument("--no-silver", action="store_true", help="skip the 1.1M-token silver pass")
    ap.add_argument("--emit-pins", action="store_true", help="print a paste-ready P_FULL block")
    ap.add_argument("--json", default=str(ARTIFACT))
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    root = resolve_root(args.root)
    classify, src, ref = load_classify()
    SPC = spaces()
    names = ["full", "30"] if args.space == "both" else [args.space]
    for n in names:
        if len(set(SPC[n])) != len(SPC[n]):
            print(f"FATAL: duplicate class in space {n}")

    print(f"stem_tail audit — spaces measured: {', '.join(names)}")
    print(f"  rule source : {src}")
    for n in names:
        print(f"  space {n:<5}: {len(SPC[n]):>3} classes, sha256 {inv_sha(SPC[n])[:16]}…")
    print(f"  ruler       : {RULER} sha256 {RULER_SHA256[:16]}… (pattern field {RULER_PATTERN_FIELD!r})")

    # --- ONE pass per corpus. A tail census does not depend on the class space, so both spaces AND the
    # --- cross-check share it; three passes would have been the same number three times.
    problems = []
    censuses = {}
    for label, path in (("PADT", PADT), ("silver", SILVER)):
        if args.no_silver and label == "silver":
            continue
        t0 = time.time()
        censuses[label] = tail_census(root / path)
        print(f"  censused {label}: {censuses[label][0].total():,} supervised tails over "
              f"{censuses[label][1]:,} records, {len(censuses[label][0])} distinct [{time.time() - t0:.0f}s]")
    ruler_rows = [json.loads(l) for l in (root / RULER).read_text(encoding="utf-8").splitlines() if l.strip()]

    agree = {"tails": 0, "mismatch": 0}
    if ref is not None:
        seen = set()
        for cnt, _, _ in censuses.values():
            seen |= set(cnt)
        for r in ruler_rows:
            seen.add(W.vocalized_stem_tail(r.get(RULER_PATTERN_FIELD) or "") or "")
        for n in names:
            for t in seen | set(SPC[n]):
                agree["tails"] += 1
                if classify(t, SPC[n]) != classify_ref(t, SPC[n]):
                    agree["mismatch"] += 1
                    problems.append(f"space {n}: shipped rule != reference on tail "
                                    f"{t.encode('unicode_escape').decode()} "
                                    f"({classify(t, SPC[n])} vs {classify_ref(t, SPC[n])})")
        print(f"  cross-check : shipped rule == reference on {agree['tails']} tail/space pairs "
              f"({agree['mismatch']} mismatch)")
    print()
    results = {"rule_source": src, "spaces": {n: {"n": len(SPC[n]), "sha256": inv_sha(SPC[n])}
                                              for n in names}, "agree": agree}

    for n in names:
        inv = SPC[n]
        pin = P_30 if n == "30" else P_FULL
        if pin.get("inventory_n") and len(inv) != pin["inventory_n"]:
            problems.append(f"space {n}: inventory size {len(inv)} != pinned {pin['inventory_n']}")
        if pin.get("inventory_sha256") not in (None, "", "PENDING") and \
                inv_sha(inv) != pin["inventory_sha256"]:
            problems.append(f"space {n}: inventory sha {inv_sha(inv)[:16]} != pinned "
                            f"{pin['inventory_sha256'][:16]}")
        print(f"===== SPACE {n} ({len(inv)} classes) " + "=" * (46 - len(n)))
        for label in (("PADT", "silver") if not args.no_silver else ("PADT",)):
            if label not in censuses:
                print(f"{label:7s} skipped (--no-silver)")
                continue
            cnt, nrec, m1 = censuses[label]
            r = resolve_space(cnt, m1, inv, classify)
            results[f"{n}.{label.lower()}"] = {k: v for k, v in r.items() if k not in ("outside", "targets")}
            print(f"{label:7s} records {nrec:,}   m_wazan=1 {r['m_wazan']:,}   distinct tails {r['distinct']}")
            print(f"  IN space {r['in_inventory']:,}   OUT {r['out']:,}"
                  f" ({r['out'] / max(r['m_wazan'], 1):.2%})")
            for k in ("DETERMINATE", "TIE", "NEW", "JUNK"):
                print(f"    {k:<12} {r[k.lower()]:>8,} tok   {r['n_' + k.lower()]:>3} distinct tails")
            print(f"    in-space rows changing class : {r['changed_not_inventory']}   (must be 0)")
            print(f"    suffixed rows on class 0     : {r['zero_class_suffixed']}   (must be 0)")
            note = "must be 0 in the shipped space" if n == "full" else "the LEGACY residue (34,455 TIE + 40,387 NEW)"
            print(f"    IGNORE rows: real-Arabic {r['ignore_real']}  non-Arabic {r['ignore_junk']}   ({note})")
            det = sorted(r["targets"].items(), key=lambda kv: (-r["outside"][kv[0]], kv[0]))
            if det:
                print("    DETERMINATE mappings (bridged, kept as classes in the space):")
                for tail, tgt in det:
                    idx = inv.index(tgt) if tgt in inv else "?"
                    print(f"      {r['outside'][tail]:6,}  {tail.encode('unicode_escape').decode():<16}"
                          f" -> {tgt.encode('unicode_escape').decode():<12} [{idx}]")
            if n == "full":
                for k in ("zero_class_suffixed", "ignore_real"):
                    if r[k]:
                        problems.append(f"{label} clause(a): {k} = {r[k]} (must be 0)")
            # Asserted for BOTH spaces. Sabotage round 1 proved this mattered: the full-space per-corpus
            # pins were written but never checked, so a sabotaged `junk: 25 -> 26` came back exit 0.
            # **A pin nobody asserts is decoration.**
            for key, want in pin["padt" if label == "PADT" else "silver"].items():
                got = r[key]
                if got != want:
                    problems.append(f"space {n} {label} {key} {got} != pinned {want}")
            print()

        ru = ruler_audit(root / RULER, inv, classify)
        results[f"{n}.ruler"] = {k: v for k, v in ru.items() if k != "detail"}
        print(f"FROZEN RULER ({n} space): records {ru['records']}  distinct tails {ru['distinct']}"
              f"  IN {ru['in_inventory']}/{ru['records']}  sha matches pinned: {ru['sha256'] == RULER_SHA256}")
        print(f"  ceiling today {ru['ceiling_today']}  +bridge {ru['ceiling_bridge']}"
              f" = {ru['ceiling_bridge'] / ru['records']:.1%}  +new-classes {ru['ceiling_with_new']}"
              f" = {ru['ceiling_with_new'] / ru['records']:.1%}")
        for d in ru["detail"]:
            tgt = d["target"] if isinstance(d["target"], str) else d["target"]
            print(f"    {d['n']:4,}  {d['tail'].encode('unicode_escape').decode():<16} {d['kind']:<12}"
                  f" -> {tgt.encode('unicode_escape').decode() if isinstance(tgt, str) else tgt}")
        if ru["sha256"] != RULER_SHA256:
            problems.append(f"ruler sha256 {ru['sha256'][:16]} != pinned {RULER_SHA256[:16]} — the ruler "
                            f"moved; every number here describes a DIFFERENT instrument")
        for key, want in pin["ruler"].items():
            if key == "new_classes":
                if tuple(ru["new_classes"]) != tuple(want):
                    problems.append(f"space {n} ruler new_classes {ru['new_classes']} != {list(want)}")
                continue
            if ru[key] != want:
                problems.append(f"space {n} ruler {key} {ru[key]} != pinned {want}")
        print()

        if not args.no_silver:
            p, s = results[f"{n}.padt"], results[f"{n}.silver"]
            bridged = p["determinate"] + s["determinate"]
            masked = p["junk"] + s["junk"]
            unresolved = p["ignore_real"] + s["ignore_real"]
            results[f"{n}.totals"] = {"bridged": bridged, "masked": masked, "unresolved_real": unresolved}
            print(f"ACCOUNTING ({n}): bridged-to-a-class {bridged:,}   masked (non-Arabic) {masked:,}   "
                  f"unresolved-but-real-Arabic {unresolved:,}   broken 0")
            if n == "30":
                t30 = {"repaired": bridged, "tie": p["tie"] + s["tie"],
                       "new": p["new"] + s["new"], "junk": masked}
                t30["masked"] = t30["tie"] + t30["new"] + t30["junk"]
                results["30.totals"] = t30
                for key, want in pin["totals"].items():
                    if t30[key] != want:
                        problems.append(f"space 30 total {key} {t30[key]} != pinned {want}")
            if n == "full":
                for key, want in (pin.get("totals") or {}).items():
                    if results[f"{n}.totals"][key] != want:
                        problems.append(f"space full total {key} {results[f'{n}.totals'][key]} != pinned {want}")
            print()
        else:
            print("PARTIAL CHECK (--no-silver): the silver pins AND the two-corpus totals were NOT asserted.\n")

        for tail, want in sorted((P_BRIDGE_TARGETS if n == "30" else P_BRIDGE_TARGETS_FULL).items()):
            k, got, _, _ = classify(tail, inv)
            if got != want or k != "DETERMINATE":
                problems.append(f"space {n}: bridge {tail.encode('unicode_escape').decode()} -> "
                                f"{str(got).encode('unicode_escape').decode()} ({k}) != pre-registered "
                                f"{want.encode('unicode_escape').decode()} (DETERMINATE)")

    if len(names) == 2 and not args.no_silver:
        print("CROSS-SPACE ACCOUNTING — what the completed space moves off a wrong class-0 label:")
        tot = 0
        for label in ("padt", "silver"):
            a, b = results[f"30.{label}"], results[f"full.{label}"]
            promoted = b["in_inventory"] - a["in_inventory"]
            tot += promoted
            ig_a = a["tie"] + a["new"] + a["junk"]
            ig_b = b["ignore_junk"] + b["ignore_real"]
            print(f"  {label:7s} in-30 {a['in_inventory']:>9,} -> in-full {b['in_inventory']:>9,}"
                  f"   = {promoted:>7,} rows now carry their OWN class   |   IGNORE {ig_a:>7,} -> {ig_b:,}")
        print(f"  TOTAL moved off class 0 (bare stem) onto their own class: {tot:,}")
        if P_FULL.get("promoted_total") and tot != P_FULL["promoted_total"]:
            problems.append(f"cross-space promoted {tot} != pinned {P_FULL['promoted_total']}")
        print(f"  the bridge's remaining job: {results['full.ruler']['bridge']} ruler rows — tails NEVER seen "
              f"in training, which is what a bridge is for")
        print()

    out = Path(args.json)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[artifact] {out}")

    if args.emit_pins:
        esc = lambda s: s.encode("unicode_escape").decode().replace('"', '\\"')
        p, s, r, t = (results["full.padt"], results["full.silver"],
                      results["full.ruler"], results["full.totals"])
        keys = ("m_wazan", "distinct", "out", "determinate", "tie", "new", "junk",
                "n_determinate", "n_tie", "n_new", "n_junk", "changed_not_inventory",
                "zero_class_suffixed", "ignore_real", "ignore_junk")
        rk = ("records", "distinct", "in_inventory", "bridge", "new", "tie",
              "ceiling_today", "ceiling_bridge", "ceiling_with_new")
        kv = lambda d, ks: ", ".join('"' + k + '": ' + str(d[k]) for k in ks)
        nc = ", ".join('"' + esc(x) + '"' for x in r["new_classes"])
        print("\nP_FULL = {")
        print('    "inventory_n": %d,' % results["spaces"]["full"]["n"])
        print('    "inventory_sha256": "%s",' % results["spaces"]["full"]["sha256"])
        print('    "padt": {%s},' % kv(p, keys))
        print('    "silver": {%s},' % kv(s, keys))
        print('    "ruler": {%s,' % kv(r, rk))
        print('              "new_classes": (%s)},' % nc)
        print('    "totals": {%s},' % kv(t, ("bridged", "masked", "unresolved_real")))
        print("}")
        return 0

    print()
    print("  NOTE: the renderer's own pins are NOT re-derived here — they live in `tools/diacritic_split.py"
          " --check` (P_SHIPPED). Separate instruments, separate meaning.")
    if problems:
        for p in problems:
            print(f"  DRIFT {p}")
        print(f"  {len(problems)} drift(s)")
        return 1
    print("  OK — the audit reproduces the pins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
