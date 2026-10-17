"""tools/bench_mobile_export.py — Export neural treatment model to ONNX & INT8,
and empirically benchmark CPU latency, size, and parity against PyTorch FP32.

Zero GPU spend, local CPU execution only.
Linus Torvalds standard: Measure real numbers, never assert unmeasured claims.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Fix Windows console UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import numpy as np
import onnx
import onnxruntime as ort
from onnxruntime.quantization import quantize_dynamic, QuantType
import torch
import torch.nn as nn

# pyrefly: ignore[missing-import]
from eval_harness import (
    decode_root_slots,
    nfc,
    canonicalize_mater_vowels,
    to_bare_root_str,
)
# pyrefly: ignore[missing-import]
from final_surface import (
    case_int,
    is_verb_template,
    is_verbal_tail,
    render_triple,
    score_final_surface,
    strip_diac,
)
from diacritic_split import usable
from model_arms import Arm, Vocabs, load_config, load_for_eval
from wazan_normalizer import split_wazan_stem_and_tail, tail_strip


class ExportArm(nn.Module):
    """Clean wrapper around Arm returning a cleanly ordered, explicitly named tuple."""
    def __init__(self, m: Arm):
        super().__init__()
        self.m = m

    def forward(self, x: torch.Tensor, x_char: torch.Tensor):
        out = self.m(x, x_char)
        return (
            out["root"],
            out["wazan"],
            out["wazan_canonical"],
            out["stem_tail"],
            out["proclitic"],
            out["enclitic"],
            out["case"],
            out["definiteness"],
            out["syntax"],
        )


HEAD_NAMES = [
    "root",
    "wazan",
    "wazan_canonical",
    "stem_tail",
    "proclitic",
    "enclitic",
    "case",
    "definiteness",
    "syntax",
]


def export_onnx_models(
    ckpt_path: Path,
    out_dir: Path,
    device: torch.device = torch.device("cpu"),
) -> tuple[Path, Path]:
    """Export PyTorch treatment checkpoint to dynamic FP32 ONNX and INT8 ONNX."""
    out_dir.mkdir(parents=True, exist_ok=True)
    fp32_raw = out_dir / "model_raw.onnx"
    fp32_path = out_dir / "model_treatment_fp32.onnx"
    int8_path = out_dir / "model_treatment_int8.onnx"

    print(f"Loading checkpoint: {ckpt_path.name}...")
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    V = Vocabs.from_dict(ck["vocab"])
    sizes = {**ck.get("sizes", {}), **V.sizes()}
    cfg = ck.get("cfg") or load_config()

    model = Arm(cfg, sizes, "treatment").to(device)
    load_for_eval(model, ck["model"], verbose=False)
    model.eval()

    exp = ExportArm(model).eval()

    # Dummy inputs for tracing: batch=2, seq=8, char_len=16
    x_dummy = torch.ones((2, 8), dtype=torch.long, device=device)
    xc_dummy = torch.ones((2, 8, 16), dtype=torch.long, device=device)

    b = torch.export.Dim("batch", min=1, max=64)
    s = torch.export.Dim("seq", min=1, max=128)

    print("Exporting FP32 ONNX via Dynamo with dynamic batch & seq shapes...")
    # Suppress verbose warnings during export
    os.environ["PYTHONIOENCODING"] = "utf-8"
    torch.onnx.export(
        exp,
        (x_dummy, xc_dummy),
        str(fp32_raw),
        input_names=["x", "x_char"],
        output_names=HEAD_NAMES,
        dynamic_shapes=({0: b, 1: s}, {0: b, 1: s}),
        dynamo=True,
    )

    # Embed all weights into a single standalone self-contained ONNX file
    m = onnx.load(str(fp32_raw))
    # Clear value_info to prevent onnxruntime dimension mismatch in shape inference
    while len(m.graph.value_info) > 0:
        m.graph.value_info.pop()
    onnx.save(m, str(fp32_path))

    # Clean up raw files
    if fp32_raw.exists():
        fp32_raw.unlink()
    raw_data = out_dir / "model_raw.onnx.data"
    if raw_data.exists():
        raw_data.unlink()

    print(f"FP32 ONNX exported to {fp32_path} ({fp32_path.stat().st_size / 1e6:.2f} MB)")

    print("Quantizing FP32 ONNX -> INT8 (Dynamic Quantization)...")
    quantize_dynamic(
        str(fp32_path),
        str(int8_path),
        weight_type=QuantType.QInt8,
    )
    print(f"INT8 ONNX exported to {int8_path} ({int8_path.stat().st_size / 1e6:.2f} MB)")

    return fp32_path, int8_path


def benchmark_latency(
    model_pt: Arm,
    sess_fp32: ort.InferenceSession,
    sess_int8: ort.InferenceSession,
    device: torch.device = torch.device("cpu"),
) -> dict:
    """Benchmark CPU inference latency across sequence lengths and batch sizes."""
    benchmarks = [
        {"name": "single_word_interactive (B=1, L=1)", "B": 1, "L": 1},
        {"name": "short_phrase (B=1, L=4)", "B": 1, "L": 4},
        {"name": "typical_sentence (B=1, L=8)", "B": 1, "L": 8},
        {"name": "long_sentence (B=1, L=16)", "B": 1, "L": 16},
        {"name": "batch_throughput (B=4, L=8)", "B": 4, "L": 8},
    ]

    results = {}

    print("\n" + "=" * 78)
    print("CPU LATENCY BENCHMARK (Warmup: 10, Measured: 100 iterations)")
    print("=" * 78)
    print(f"{'Configuration':<35} | {'PyTorch FP32':<12} | {'ONNX FP32':<12} | {'ONNX INT8':<12} | {'Speedup':<8}")
    print("-" * 78)

    for b in benchmarks:
        B, L = int(b["B"]), int(b["L"])
        x_pt = torch.ones((B, L), dtype=torch.long, device=device)
        xc_pt = torch.ones((B, L, 16), dtype=torch.long, device=device)
        x_np = np.ones((B, L), dtype=np.int64)
        xc_np = np.ones((B, L, 16), dtype=np.int64)

        # Warmup
        for _ in range(10):
            with torch.no_grad():
                _ = model_pt(x_pt, xc_pt)
            _ = sess_fp32.run(None, {"x": x_np, "x_char": xc_np})
            _ = sess_int8.run(None, {"x": x_np, "x_char": xc_np})

        # PyTorch
        t_pt = []
        for _ in range(100):
            t0 = time.perf_counter()
            with torch.no_grad():
                _ = model_pt(x_pt, xc_pt)
            t_pt.append((time.perf_counter() - t0) * 1000.0)

        # ONNX FP32
        t_fp32 = []
        for _ in range(100):
            t0 = time.perf_counter()
            _ = sess_fp32.run(None, {"x": x_np, "x_char": xc_np})
            t_fp32.append((time.perf_counter() - t0) * 1000.0)

        # ONNX INT8
        t_int8 = []
        for _ in range(100):
            t0 = time.perf_counter()
            _ = sess_int8.run(None, {"x": x_np, "x_char": xc_np})
            t_int8.append((time.perf_counter() - t0) * 1000.0)

        pt_med = float(np.median(t_pt))
        fp32_med = float(np.median(t_fp32))
        int8_med = float(np.median(t_int8))
        speedup = pt_med / int8_med if int8_med > 0 else 1.0

        print(f"{b['name']:<35} | {pt_med:8.2f} ms | {fp32_med:8.2f} ms | {int8_med:8.2f} ms | {speedup:6.2f}x")

        results[b["name"]] = {
            "B": B,
            "L": L,
            "pytorch_ms": {"median": pt_med, "mean": float(np.mean(t_pt)), "p95": float(np.percentile(t_pt, 95))},
            "onnx_fp32_ms": {"median": fp32_med, "mean": float(np.mean(t_fp32)), "p95": float(np.percentile(t_fp32, 95))},
            "onnx_int8_ms": {"median": int8_med, "mean": float(np.mean(t_int8)), "p95": float(np.percentile(t_int8, 95))},
            "speedup_vs_pytorch": speedup,
        }

    return results


def run_gold_evaluation(
    model_pt: Arm,
    sess_fp32: ort.InferenceSession,
    sess_int8: ort.InferenceSession,
    V: Vocabs,
    gold_records: list[dict],
    device: torch.device = torch.device("cpu"),
) -> dict:
    """Run empirical parity and accuracy evaluation on gold-tashkeela-300."""
    inv_r = {i: c for c, i in V.radical.items()}
    inv_w = {i: w for w, i in V.wazan.items()}
    inv_tail = {i: t for t, i in V.stem_tail.items()}
    max_char_len = 16

    from eval_harness import parse_gold_context

    # Parity accumulators: count matching argmax predictions between PT and INT8
    parity_counts = {h: 0 for h in HEAD_NAMES}
    total_tokens = 0

    # Accuracy accumulators for each engine
    acc_pt = {"root": 0, "wazan_exact": 0, "stem_tail": 0, "case": 0}
    acc_fp32 = {"root": 0, "wazan_exact": 0, "stem_tail": 0, "case": 0}
    acc_int8 = {"root": 0, "wazan_exact": 0, "stem_tail": 0, "case": 0}

    root_total = 0
    wazan_total = 0
    stem_tail_total = 0
    case_total = 0

    # Compiler inputs
    triples_pt = []
    triples_fp32 = []
    triples_int8 = []

    max_len = 64

    for gi, g in enumerate(gold_records):
        toks, idx = parse_gold_context(g.get("context") or "")
        if not toks or idx is None:
            continue
        if len(toks) > max_len:
            lo = max(0, min(idx - max_len // 2, len(toks) - max_len))
            toks = toks[lo:lo + max_len]
            idx -= lo

        total_tokens += 1
        x_pt = torch.tensor([[V.encode(t) for t in toks]], device=device)
        xc_list = []
        for t in toks:
            c_ids = [V.char.get(c, 0) for c in t[:max_char_len]]
            c_ids += [0] * (max_char_len - len(c_ids))
            xc_list.append(c_ids)
        xc_pt = torch.tensor([xc_list], device=device)

        x_np = x_pt.cpu().numpy()
        xc_np = xc_pt.cpu().numpy()

        with torch.no_grad():
            out_pt = model_pt(x_pt, xc_pt)
        out_fp32 = sess_fp32.run(None, {"x": x_np, "x_char": xc_np})
        out_int8 = sess_int8.run(None, {"x": x_np, "x_char": xc_np})

        # Map ONNX lists to dicts of ndarray
        dict_fp32: dict[str, np.ndarray] = {HEAD_NAMES[i]: np.asarray(out_fp32[i]) for i in range(len(HEAD_NAMES))}
        dict_int8: dict[str, np.ndarray] = {HEAD_NAMES[i]: np.asarray(out_int8[i]) for i in range(len(HEAD_NAMES))}

        # 1. Parity checks (PT vs INT8)
        # root
        pt_root_pred = out_pt["root"][0, idx].argmax(-1).tolist()
        int8_root_pred = dict_int8["root"][0, idx].argmax(-1).tolist()
        if pt_root_pred == int8_root_pred:
            parity_counts["root"] += 1

        # Other heads
        for h in ["wazan", "wazan_canonical", "stem_tail", "proclitic", "enclitic", "case", "definiteness", "syntax"]:
            pt_p = int(out_pt[h][0, idx].argmax())
            int8_p = int(dict_int8[h][0, idx].argmax())
            if pt_p == int8_p:
                parity_counts[h] += 1

        # 2. Extract predictions for accuracy
        pw_pt = inv_w.get(int(out_pt["wazan"][0, idx].argmax()), None)
        pw_fp32 = inv_w.get(int(dict_fp32["wazan"][0, idx].argmax()), None)
        pw_int8 = inv_w.get(int(dict_int8["wazan"][0, idx].argmax()), None)

        r_pt = to_bare_root_str(decode_root_slots(pt_root_pred, pw_pt, inv_r))
        r_fp32 = to_bare_root_str(decode_root_slots(dict_fp32["root"][0, idx].argmax(-1).tolist(), pw_fp32, inv_r))
        r_int8 = to_bare_root_str(decode_root_slots(int8_root_pred, pw_int8, inv_r))

        st_pt = inv_tail.get(int(out_pt["stem_tail"][0, idx].argmax()), "")
        st_fp32 = inv_tail.get(int(dict_fp32["stem_tail"][0, idx].argmax()), "")
        st_int8 = inv_tail.get(int(dict_int8["stem_tail"][0, idx].argmax()), "")

        def_pt = int(out_pt["definiteness"][0, idx].argmax())
        def_fp32 = int(dict_fp32["definiteness"][0, idx].argmax())
        def_int8 = int(dict_int8["definiteness"][0, idx].argmax())

        c_pt = int(out_pt["case"][0, idx].argmax())
        c_fp32 = int(dict_fp32["case"][0, idx].argmax())
        c_int8 = int(dict_int8["case"][0, idx].argmax())

        is_verb_pt = (def_pt in (3, "OTHER", "INVARIABLE")) or is_verbal_tail(st_pt) or is_verb_template(pw_pt)
        case_val_pt = None if is_verb_pt else c_pt

        is_verb_fp32 = (def_fp32 in (3, "OTHER", "INVARIABLE")) or is_verbal_tail(st_fp32) or is_verb_template(pw_fp32)
        case_val_fp32 = None if is_verb_fp32 else c_fp32

        is_verb_int8 = (def_int8 in (3, "OTHER", "INVARIABLE")) or is_verbal_tail(st_int8) or is_verb_template(pw_int8)
        case_val_int8 = None if is_verb_int8 else c_int8

        triples_pt.append((g.get("form"), r_pt, pw_pt, case_val_pt, def_pt, st_pt))
        triples_fp32.append((g.get("form"), r_fp32, pw_fp32, case_val_fp32, def_fp32, st_fp32))
        triples_int8.append((g.get("form"), r_int8, pw_int8, case_val_int8, def_int8, st_int8))

        # Ground truth evaluations
        # Root
        if g.get("root_valid") and g.get("t_root_arabic"):
            root_total += 1
            gold_r = to_bare_root_str(g["t_root_arabic"])
            if r_pt == gold_r:
                acc_pt["root"] += 1
            if r_fp32 == gold_r:
                acc_fp32["root"] += 1
            if r_int8 == gold_r:
                acc_int8["root"] += 1

        # Wazān
        raw_pat = g.get("t_wazan_pattern")
        if g.get("pattern_valid") and raw_pat:
            wazan_total += 1
            gp = nfc(str(raw_pat))
            if gp is not None:
                gold_stem_raw = tail_strip(gp)
                gold_stem_c = canonicalize_mater_vowels(gold_stem_raw)
                gp_c = canonicalize_mater_vowels(gp)
                gp_tail_stripped = canonicalize_mater_vowels(tail_strip(gp))

                def is_waz_match(pw):
                    if not pw:
                        return False
                    pw_c = canonicalize_mater_vowels(pw)
                    return (nfc(pw) == nfc(gold_stem_raw) or
                            (pw_c is not None and pw_c == gold_stem_c) or
                            (pw_c == gp_c) or
                            (pw_c == gp_tail_stripped))

                if is_waz_match(pw_pt):
                    acc_pt["wazan_exact"] += 1
                if is_waz_match(pw_fp32):
                    acc_fp32["wazan_exact"] += 1
                if is_waz_match(pw_int8):
                    acc_int8["wazan_exact"] += 1

                # Stem tail
                wz_split = split_wazan_stem_and_tail(gp)
                if wz_split is not None:
                    _, gold_tail = wz_split
                    stem_tail_total += 1
                    if st_pt == gold_tail:
                        acc_pt["stem_tail"] += 1
                    if st_fp32 == gold_tail:
                        acc_fp32["stem_tail"] += 1
                    if st_int8 == gold_tail:
                        acc_int8["stem_tail"] += 1

        # Case
        if g.get("t_case") is not None:
            case_total += 1
            gold_case = int(g["t_case"])
            if c_pt == gold_case:
                acc_pt["case"] += 1
            if c_fp32 == gold_case:
                acc_fp32["case"] += 1
            if c_int8 == gold_case:
                acc_int8["case"] += 1

    # End-to-end compiler surface accuracy
    def score_triples(trips, res: bool):
        rendered = [
            (gf,) + tuple(render_triple(r, p, c, engine="v3", token=strip_diac(gf),
                                        definiteness=df, stem_tail=st, resource=res))
            for gf, r, p, c, df, st in trips
        ]
        return score_final_surface(rendered)

    surface_res_off_pt = score_triples(triples_pt, False)
    surface_res_off_fp32 = score_triples(triples_fp32, False)
    surface_res_off_int8 = score_triples(triples_int8, False)

    surface_res_on_pt = score_triples(triples_pt, True)
    surface_res_on_fp32 = score_triples(triples_fp32, True)
    surface_res_on_int8 = score_triples(triples_int8, True)

    parity_pct = {h: (parity_counts[h] / total_tokens) * 100.0 for h in HEAD_NAMES}

    return {
        "total_tokens": total_tokens,
        "parity_pct_vs_pt": parity_pct,
        "accuracies": {
            "root": {
                "total": root_total,
                "pt": acc_pt["root"],
                "fp32": acc_fp32["root"],
                "int8": acc_int8["root"],
                "pt_pct": (acc_pt["root"] / root_total) * 100.0 if root_total else 0,
                "int8_pct": (acc_int8["root"] / root_total) * 100.0 if root_total else 0,
            },
            "wazan": {
                "total": wazan_total,
                "pt": acc_pt["wazan_exact"],
                "fp32": acc_fp32["wazan_exact"],
                "int8": acc_int8["wazan_exact"],
                "pt_pct": (acc_pt["wazan_exact"] / wazan_total) * 100.0 if wazan_total else 0,
                "int8_pct": (acc_int8["wazan_exact"] / wazan_total) * 100.0 if wazan_total else 0,
            },
            "stem_tail": {
                "total": stem_tail_total,
                "pt": acc_pt["stem_tail"],
                "fp32": acc_fp32["stem_tail"],
                "int8": acc_int8["stem_tail"],
                "pt_pct": (acc_pt["stem_tail"] / stem_tail_total) * 100.0 if stem_tail_total else 0,
                "int8_pct": (acc_int8["stem_tail"] / stem_tail_total) * 100.0 if stem_tail_total else 0,
            },
            "case": {
                "total": case_total,
                "pt": acc_pt["case"],
                "fp32": acc_fp32["case"],
                "int8": acc_int8["case"],
                "pt_pct": (acc_pt["case"] / case_total) * 100.0 if case_total else 0,
                "int8_pct": (acc_int8["case"] / case_total) * 100.0 if case_total else 0,
            },
        },
        "surface_compiler": {
            "resource_off": {
                "pt": surface_res_off_pt,
                "fp32": surface_res_off_fp32,
                "int8": surface_res_off_int8,
            },
            "resource_on": {
                "pt": surface_res_on_pt,
                "fp32": surface_res_on_fp32,
                "int8": surface_res_on_int8,
            },
        },
    }


def verify_frozen_ruler(ruler_path: Path) -> dict:
    """Verify that pure compiler baseline on frozen ruler 973 rows remains 614/973 = 63.1%."""
    os.environ["ARABIC_SPELLING_RESOURCE"] = "0"
    os.environ["ARABIC_AFFIX_PLANE"] = "0"
    rows = []
    with open(ruler_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    usable_rows = [r for r in rows if usable(r)]
    triples = [
        (r["target_token"],) + tuple(render_triple(r["root"], r["wazn_pattern"], case_int(r.get("case")),
                                                   engine="v3", token=r["target_token"],
                                                   repairs=True))
        for r in usable_rows
    ]
    sc = score_final_surface(triples)
    correct = sc.get("stem_correct", 0)
    total = len(usable_rows)
    pct = (correct / total) * 100.0 if total else 0.0

    print("\n" + "=" * 78)
    print("FROZEN RULER COMPILER BASELINE VERIFICATION")
    print("=" * 78)
    print(f"Ruler rows: {len(rows)} | Usable rows: {total}")
    print(f"Correct: {correct}/{total} = {pct:.2f}% (Baseline pinned: 614/973 = 63.10%)")
    assert correct == 614, f"CRITICAL REGRESSION: expected 614, got {correct}"
    print("[PASS] 0% degradation on frozen ruler: exactly 614/973 = 63.10% preserved!")
    return {"total": total, "correct": correct, "pct": pct, "pinned": 614}


def main():
    parser = argparse.ArgumentParser(description="Export treatment model to ONNX & INT8, benchmark latency and parity.")
    parser.add_argument("--ckpt", default="checkpoints/gold-treatment-s20261009.pt", help="Path to checkpoint")
    parser.add_argument("--gold", default="data/annotation/gold-tashkeela-300.jsonl", help="Gold evaluation data")
    parser.add_argument("--ruler", default="data/annotation/bench-gold.jsonl", help="Frozen ruler benchmark")
    parser.add_argument("--out-dir", default="dist/mobile", help="Output directory")
    args = parser.parse_args()

    ckpt_path = Path(args.ckpt)
    out_dir = Path(args.out_dir)
    gold_path = Path(args.gold)
    ruler_path = Path(args.ruler)

    device = torch.device("cpu")

    # 1. Export models
    fp32_path, int8_path = export_onnx_models(ckpt_path, out_dir, device=device)

    # 2. Verify frozen ruler compiler baseline
    ruler_stats = verify_frozen_ruler(ruler_path)

    # 3. Load ONNX sessions and PyTorch model
    print("\nLoading ONNX inference sessions (CPUExecutionProvider)...")
    sess_fp32 = ort.InferenceSession(str(fp32_path), providers=["CPUExecutionProvider"])
    sess_int8 = ort.InferenceSession(str(int8_path), providers=["CPUExecutionProvider"])

    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    V = Vocabs.from_dict(ck["vocab"])
    sizes = {**ck.get("sizes", {}), **V.sizes()}
    cfg = ck.get("cfg") or load_config()
    model_pt = Arm(cfg, sizes, "treatment").to(device)
    load_for_eval(model_pt, ck["model"], verbose=False)
    model_pt.eval()

    # 4. Latency benchmark
    latency_stats = benchmark_latency(model_pt, sess_fp32, sess_int8, device=device)

    # 5. Gold evaluation & Parity
    print("\nEvaluating on gold-tashkeela-300 (300 rows)...")
    with open(gold_path, encoding="utf-8") as f:
        gold_records = [json.loads(line) for line in f if line.strip()]

    eval_stats = run_gold_evaluation(model_pt, sess_fp32, sess_int8, V, gold_records, device=device)

    # Report Summary
    print("\n" + "=" * 78)
    print("ARGMAX PARITY: PyTorch FP32 vs ONNX INT8 (300 tokens)")
    print("=" * 78)
    for h in HEAD_NAMES:
        pct = eval_stats["parity_pct_vs_pt"][h]
        print(f"  Head {h:<18}: {pct:6.2f}% argmax agreement")

    print("\n" + "=" * 78)
    print("TASK ACCURACY: PyTorch FP32 vs ONNX FP32 vs ONNX INT8 (gold-300)")
    print("=" * 78)
    for task, d in eval_stats["accuracies"].items():
        print(f"  {task:<12}: PyTorch={d['pt']}/{d['total']} ({d['pt_pct']:.1f}%) | "
              f"ONNX FP32={d['fp32']}/{d['total']} | "
              f"ONNX INT8={d['int8']}/{d['total']} ({d['int8_pct']:.1f}%) | "
              f"Delta={d['int8'] - d['pt']:+d}")

    def _fmt_surface(d: dict) -> str:
        n = d.get("n", 0)
        stem_ok = d.get("stem_correct", 0)
        stem_y = (d.get("stem_yield") or 0.0) * 100.0
        tok_ok = d.get("token_exact", 0)
        tok_y = (d.get("token_exact_yield") or 0.0) * 100.0
        return f"stem={stem_ok}/{n} ({stem_y:.2f}%) | token_exact={tok_ok}/{n} ({tok_y:.2f}%)"

    s_off = eval_stats["surface_compiler"]["resource_off"]
    print("\n" + "=" * 78)
    print("SURFACE COMPILER (Resource OFF — Pure Neural + Rules):")
    print(f"  PyTorch FP32: {_fmt_surface(s_off['pt'])}")
    print(f"  ONNX FP32:   {_fmt_surface(s_off['fp32'])}")
    print(f"  ONNX INT8:   {_fmt_surface(s_off['int8'])}")

    s_on = eval_stats["surface_compiler"]["resource_on"]
    print("\n" + "=" * 78)
    print("SURFACE COMPILER (Resource ON — Hybrid Production):")
    print(f"  PyTorch FP32: {_fmt_surface(s_on['pt'])}")
    print(f"  ONNX FP32:   {_fmt_surface(s_on['fp32'])}")
    print(f"  ONNX INT8:   {_fmt_surface(s_on['int8'])}")

    # Save full JSON report
    report = {
        "checkpoint": ckpt_path.name,
        "model_sizes": {
            "pytorch_fp32_mb": ckpt_path.stat().st_size / 1e6,
            "onnx_fp32_mb": fp32_path.stat().st_size / 1e6,
            "onnx_int8_mb": int8_path.stat().st_size / 1e6,
            "compression_ratio": fp32_path.stat().st_size / int8_path.stat().st_size,
        },
        "latency_benchmark": latency_stats,
        "frozen_ruler": ruler_stats,
        "gold_300_eval": eval_stats,
    }

    report_path = out_dir / "benchmark_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nWrote full benchmark report to: {report_path}")


if __name__ == "__main__":
    main()
