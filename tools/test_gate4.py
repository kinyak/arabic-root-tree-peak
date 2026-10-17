"""test_gate4.py — Gate 4 verification:
1. Invariance test: decode_rasm_constrained given gold_form vs. strip_diac(gold_form) produces 100% byte-identical outputs (A - B == 0).
2. Runtime benchmark on 300 gold rows: must complete in < 20 seconds on CPU.
"""
import sys
import time
from pathlib import Path
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import eval_harness as EH
from final_surface import decode_rasm_constrained, strip_diac, RootTrie
from model_arms import load_config, Vocabs, Arm, read_records

def main():
    print("=" * 70)
    print("GATE 4 VERIFICATION (Task 4)")
    print("=" * 70)

    cfg = load_config(smoke=True)
    gold = EH.load_human_gold(cfg["paths"]["human_gold"])
    print(f"Loaded {len(gold)} human gold rows.")

    recs = read_records(cfg["paths"]["dev"], limit=20)
    V = Vocabs(recs, min_freq=1, max_vocab=100)
    sizes = V.sizes()
    model = Arm(cfg, sizes, "treatment")
    model.eval()

    inv_r = {i: c for c, i in V.radical.items()}
    inv_w = {i: w for w, i in V.wazan.items()}
    inv_tail = {i: t for t, i in V.stem_tail.items()}

    # Populate a root trie with some gold roots
    roots = set()
    for g in gold:
        r = g.get("t_root_arabic")
        if r:
            roots.add(r)
    trie = RootTrie(roots)
    print(f"RootTrie populated with {len(trie)} roots.")

    # Synthetic logits
    torch.manual_seed(42)
    B = len(gold)
    root_logits = torch.randn(B, 4, sizes["radical"])
    wazan_logits = torch.randn(B, sizes["wazan"])
    case_logits = torch.randn(B, sizes["case"])
    stem_tail_logits = torch.randn(B, sizes["stem_tail"])
    def_logits = torch.randn(B, sizes["definiteness"])

    # 1. Invariance Test
    print("\n[1] Testing Invariance: gold_form vs. strip_diac(gold_form)...")
    mismatches = 0
    for i, g in enumerate(gold):
        form = g.get("form") or ""
        bare = strip_diac(form)
        out_a = decode_rasm_constrained(
            root_logits[i], wazan_logits[i], case_logits[i],
            stem_tail_logits=stem_tail_logits[i],
            def_logits=def_logits[i],
            inv_r=inv_r, inv_w=inv_w, inv_tail=inv_tail,
            token=form, engine="v3", trie=trie, resource=False
        )
        out_b = decode_rasm_constrained(
            root_logits[i], wazan_logits[i], case_logits[i],
            stem_tail_logits=stem_tail_logits[i],
            def_logits=def_logits[i],
            inv_r=inv_r, inv_w=inv_w, inv_tail=inv_tail,
            token=bare, engine="v3", trie=trie, resource=False
        )
        if out_a != out_b:
            mismatches += 1
            print(f"  Mismatch at row {i} ({form!r} vs {bare!r}):\n    A: {out_a}\n    B: {out_b}")

    assert mismatches == 0, f"Invariance test failed with {mismatches} mismatches!"
    print(f"  PASS: 100% byte-identical outputs across all {len(gold)} rows (mismatches = {mismatches}).")

    # 2. Runtime Benchmark
    print("\n[2] Benchmarking runtime on 300 gold rows on CPU...")
    t0 = time.perf_counter()
    for i, g in enumerate(gold):
        form = g.get("form") or ""
        decode_rasm_constrained(
            root_logits[i], wazan_logits[i], case_logits[i],
            stem_tail_logits=stem_tail_logits[i],
            def_logits=def_logits[i],
            inv_r=inv_r, inv_w=inv_w, inv_tail=inv_tail,
            token=form, engine="v3", trie=trie, resource=False
        )
    elapsed = time.perf_counter() - t0
    print(f"  Completed {len(gold)} rows in {elapsed:.3f} seconds ({elapsed/len(gold)*1000:.2f} ms/row).")
    assert elapsed < 20.0, f"Runtime too slow: {elapsed:.2f}s >= 20.0s bar!"
    print(f"  PASS: Runtime {elapsed:.3f}s < 20.0s bar.")

    print("\nGATE 4 ALL CHECKS PASSED (Exit 0)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
