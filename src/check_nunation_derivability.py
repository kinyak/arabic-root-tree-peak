"""Is the surface DERIVABLE from (root, wazān pattern, case) alone?

THE QUESTION
    B003 gold مَالِكٍ (kasratan, GEN) vs B002 gold رَسُولِ (plain kasra, GEN). Same
    case, same slot, different nunation. If rows sharing an IDENTICAL
    (root, pattern, case) triple carry DIFFERENT surfaces, then the triple is
    UNDER-SPECIFIED and no renderer — however good — can reach 100% exact vocalized
    match on it. That would make the plan's "Fully Vocalized Match (accounting for
    the case slot)" target unreachable by construction, and the fix would be an extra
    INPUT (definiteness), not a better rule.

    This is measured, not argued: group the human gold by its own triple and look for
    a group whose members differ only in nunation.
"""
from __future__ import annotations

import collections
import json
import sys

from paths import GOLD_JSONL

TAN = set("\u064b\u064c\u064d")


def main() -> int:
    rows = [json.loads(l) for l in open(GOLD_JSONL, encoding="utf-8") if l.strip()]
    usable = [r for r in rows
              if r.get("t_root_arabic") and r.get("t_wazan_pattern")
              and r.get("t_case") is not None]
    print(f"rows with a full triple: {len(usable)}")

    g = collections.defaultdict(list)
    for r in usable:
        g[(r["t_root_arabic"], r["t_wazan_pattern"], r["t_case"])].append(r["form"])

    multi = {k: v for k, v in g.items() if len(set(v)) > 1}
    print(f"distinct triples       : {len(g)}")
    print(f"triples with >1 surface: {len(multi)}  "
          f"({100*len(multi)/max(len(g),1):.1f}% of triples)")

    def tan(f):
        return bool(TAN & set(f))

    nun = {k: v for k, v in multi.items() if len({tan(f) for f in v}) > 1}
    print()
    print(f"OF THOSE, triples whose surfaces DISAGREE ON NUNATION: {len(nun)}")
    print("  -> for these, (root, pattern, case) does NOT determine the surface.")
    shown = 0
    for k, v in sorted(nun.items(), key=lambda x: -len(x[1])):
        print(f"    root={k[0]:<6} pat={k[1]:<12} case={k[2]}  ->  "
              + " | ".join(sorted(set(v))))
        shown += 1
        if shown >= 12:
            break

    other = {k: v for k, v in multi.items() if k not in nun}
    print()
    print(f"triples with >1 surface but SAME nunation: {len(other)} "
          "(a different under-specification)")
    for k, v in list(other.items())[:8]:
        print(f"    root={k[0]:<6} pat={k[1]:<12} case={k[2]}  ->  "
              + " | ".join(sorted(set(v))))

    if nun:
        print()
        print("VERDICT: the triple is under-specified. A definiteness / nunation")
        print("         signal must be added to the renderer's input before any")
        print("         'fully vocalized match' target is meaningful.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
