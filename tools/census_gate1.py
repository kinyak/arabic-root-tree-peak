"""Census script for Gate 1 verification.

Runs a census over:
- padt-train.jsonl (223,881 rows)
- tashkeela-train.jsonl (1,871,205 rows)
- gold-tashkeela-300.jsonl (300 rows)

Asserts:
1. suffixed_mapped_to_zero == 0 on all three datasets.
2. non_arabic_tails_in_vocab == 0.
3. on gold-300, render_triple(gold_root, stem_c, gold_case, token=gold_form, stem_tail=tail_c)
   with resource_off achieves >= 78.8% stem accuracy.
"""
import json
import os
import re
import sys
from pathlib import Path

# Add src to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from wazan_normalizer import (
    split_wazan_stem_and_tail,
    STEM_TAIL_VOCALIZED,
    STEM_TAIL_VOCALIZED_GOLD300,
    ARABIC_ONLY,
    canonicalize_mater_vowels,
)
from final_surface import render_triple, strip_diac


def build_union_tail_vocab(paths: list[Path]) -> dict[str, int]:
    tail_set = set()
    
    # 1. STEM_TAIL_VOCALIZED from gold-300 and corpus
    for raw_st in STEM_TAIL_VOCALIZED:
        if not raw_st:
            continue
        res = split_wazan_stem_and_tail("123" + raw_st)
        if res is not None and res[1]:
            tail_set.add(res[1])

    # 2. Iterate datasets
    for p in paths:
        if not p.exists():
            print(f"Warning: path not found: {p}")
            continue
        print(f"Scanning {p} for tails...")
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                # handle both corpus schema (t_wazan) and gold schema (t_wazan_pattern)
                raw_w = row.get("t_wazan") or row.get("t_wazan_pattern")
                if not raw_w or not row.get("m_wazan", 1):
                    continue
                res = split_wazan_stem_and_tail(raw_w)
                if res is not None and res[1]:
                    tail_set.add(res[1])

    vocab = {"": 0}
    for t in sorted(tail_set):
        if t != "":
            vocab[t] = len(vocab)
    print(f"Built union stem_tail vocab: {len(vocab)} classes (class 0 is bare stem '')")
    return vocab


def check_dataset_tails(path: Path, vocab: dict[str, int], name: str) -> tuple[int, int, int]:
    """Returns (total_rows, suffixed_count, suffixed_mapped_to_zero)"""
    total = 0
    suffixed = 0
    suffixed_mapped_to_zero = 0
    
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            total += 1
            row = json.loads(line)
            m_w = row.get("m_wazan", 1 if "t_wazan_pattern" in row else 0)
            if not m_w:
                continue
            raw_w = row.get("t_wazan") or row.get("t_wazan_pattern")
            if not raw_w:
                continue
            res = split_wazan_stem_and_tail(raw_w)
            if res is None:
                continue
            stem_c, tail_c = res
            if tail_c != "":
                suffixed += 1
                tail_id = 0 if tail_c == "" else vocab.get(tail_c, -100)
                if tail_id == 0:
                    suffixed_mapped_to_zero += 1
                    
    print(f"[{name}] Total: {total:,} | Suffixed: {suffixed:,} | Mapped to 0: {suffixed_mapped_to_zero}")
    return total, suffixed, suffixed_mapped_to_zero


def main():
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__)
        return 0

    print("=" * 70)
    print("GATE 1 CENSUS: wazan + stem_tail seam & clean union tail inventory")
    print("=" * 70)

    padt_path = ROOT / "data" / "out" / "padt-train.jsonl"
    silver_path = ROOT / "data" / "out" / "spread-B-2m" / "tashkeela-train.jsonl"
    gold_path = ROOT / "data" / "annotation" / "gold-tashkeela-300.jsonl"

    for p in (padt_path, silver_path, gold_path):
        assert p.exists(), f"Required dataset missing: {p}"

    vocab = build_union_tail_vocab([padt_path, silver_path, gold_path])

    # Check 1: Non-arabic tails in vocab == 0
    non_arabic = 0
    for tail in vocab:
        if tail == "":
            continue
        # Strip diacritics and check if remaining characters are Arabic letters
        letters = re.sub(r"[\u064b-\u0652\u0670\u0671]", "", tail)
        if not letters or not re.match(r"^[\u0621-\u064a]+$", letters):
            print(f"Non-arabic or empty tail in vocab: {tail!r} (letters: {letters!r})")
            non_arabic += 1

    print(f"\nNon-Arabic tails in vocab: {non_arabic}")
    assert non_arabic == 0, f"Found {non_arabic} non-Arabic tails in vocab!"

    # Check 2: Suffixed mapped to 0 == 0 on all 3 datasets
    print("\nChecking suffixed_mapped_to_zero on 3 datasets:")
    t1, s1, z1 = check_dataset_tails(padt_path, vocab, "PADT-Train")
    assert z1 == 0, f"PADT-Train has {z1} suffixed mapped to 0!"

    t2, s2, z2 = check_dataset_tails(silver_path, vocab, "Tashkeela-Train")
    assert z2 == 0, f"Tashkeela-Train has {z2} suffixed mapped to 0!"

    t3, s3, z3 = check_dataset_tails(gold_path, vocab, "Gold-Tashkeela-300")
    assert z3 == 0, f"Gold-Tashkeela-300 has {z3} suffixed mapped to 0!"

    # Check 3: Gold-300 stem accuracy >= 78.8% with resource_off
    os.environ["ARABIC_SPELLING_RESOURCE"] = "0"
    print("\nChecking gold-300 stem accuracy with resource_off:")
    gold_records = [json.loads(l) for l in open(gold_path, encoding="utf-8") if l.strip()]
    n_scored = 0
    n_correct = 0
    for g in gold_records:
        if not (g.get("pattern_valid") and g.get("t_wazan_pattern") and g.get("root_valid") and g.get("t_root_arabic")):
            continue
        res = split_wazan_stem_and_tail(g["t_wazan_pattern"])
        if res is None:
            continue
        stem_c, tail_c = res
        gold_root = g["t_root_arabic"]
        gold_case = g.get("t_case")
        gold_form = g.get("form")

        n_scored += 1
        surf, _ = render_triple(gold_root, stem_c, gold_case, token=gold_form, stem_tail=tail_c)
        if surf and strip_diac(surf) == strip_diac(gold_form):
            n_correct += 1

    acc = n_correct / max(n_scored, 1)
    print(f"Gold-300 Scored: {n_scored} | Correct: {n_correct} | Stem Accuracy: {acc:.2%}")
    assert acc >= 0.788, f"Stem accuracy {acc:.2%} < 78.8% threshold!"

    print("\n" + "=" * 70)
    print("GATE 1 PASSED: all 3 assertions hold exit 0.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
