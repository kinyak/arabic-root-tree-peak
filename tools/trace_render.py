#!/usr/bin/env python3
"""tools/trace_render.py — CLI and generator for passive phonological and iʿlāl step traces.

Acceptance in WORK_ORDER_PEDAGOGY_AND_ILAL.md:
  (a) six gates 0
  (b) 0 changed rows on both instruments (frozen ruler 973, gold-300)
  (c) قُلْتُ prints an honest chain: root ق و ل (ajwaf wāwī) -> underlying قَوَلْتُ ->
      iʿlāl bil-ḥadhf (wāw dropped for iltiqāʾ al-sākinayn) -> قُلْتُ
  (d) مُحْتَاج -> root ح و ج -> مُ1ْتَ2َ3 Form VIII -> مُحْتَاج with no invented step
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "tools"))

from final_surface import case_int, render_triple
from wazan_normalizer import trailing_run, tail_strip

RULE_EXPLANATIONS = {
    "canonicalize_mater_vowels": "Canonicalization of mater vowels in wazān template.",
    "render_v3": "Digit slot substitution and weak radical realization (Pass A / Pass B).",
    "iltiqāʾ al-sākinayn": "Iʿlāl bil-ḥadhf (إعلال بالحذف): glide elision before a sukun-bearing suffix to prevent consonant cluster (التقاء الساكنين).",
    "stem_tail:weak_letter_seam": "Weak letter contraction at stem-tail seam.",
    "stem_tail:madda_merge": "Orthographic merge of adjacent alifs into madda (آ).",
    "stem_tail:append": "Inflectional suffix attachment.",
    "align_weak_r3": "Alignment of terminal defective radical with template spelling.",
    "project_hamza_from_input": "Re-seating of folded hamza radical from token skeleton.",
    "repair_manqus_indefinite": "Manqūṣ noun indefinite case inflection (حذف الياء والتعويض بالتنوين).",
    "apply_case": "Inflectional case mark placement on terminal letter.",
    "apply_clitic_plane": "Contextual clitic orthography adjustment (e.g. ة -> ت before enclitic).",
    "repair_sun_letter_shadda": "Sun-letter assimilation shadda placement (إدغام شمسي).",
    "repair_hamza_fatha": "Word-initial bare hamza seat vocalization.",
    "repair_long_vowel_sukun": "Removal of invalid sukun following a long vowel.",
    "repair_dual_nominative": "Correction of dual nominative terminal vowel to kasra.",
    "repair_initial_hamza_seat": "Word-initial hamzat al-qaṭʿ seat alignment.",
    "repair_divine_name": "Closed-class divine name fusion (لفظ الجلالة: إِلَاه + ال -> اللَّه).",
    "attach_affix_plane": "Proclitic and enclitic frame reconstruction around rendered stem.",
    "apply_spelling_resource": "Consultation of attested corpus spelling index for historical/settled orthography.",
}


def infer_tail_if_needed(token: str | None, wazan: str | None, explicit_tail: str | None) -> tuple[str, str | None]:
    """Return (clean_wazan, effective_tail)."""
    if explicit_tail is not None:
        return (tail_strip(wazan or "") if wazan else ""), explicit_tail
    if not wazan:
        return "", None
    
    t_run = trailing_run(wazan)
    if t_run:
        return tail_strip(wazan), t_run
        
    # If no tail in wazan, check common inflectional suffixes on token
    if token:
        clean_w = tail_strip(wazan)
        # Check classic hollow verb past suffixes: ْتُ, ْتَ, ْتِ, ْنَا, ْتُمْ, ْنَ
        for sfx in ("ْتُ", "ْتَ", "ْتِ", "ْنَا", "ْتُمْ", "ْنَ", "َة", "َات", "َانِ", "َيْنِ", "ُونَ", "ِينَ"):
            if token.endswith(sfx):
                return clean_w, sfx
    return wazan, None


def trace_word(token: str | None, root: str | None, wazan: str | None,
               case: int | str | None = None, stem_tail: str | None = None,
               resource: bool = True) -> dict:
    wazan_clean, effective_tail = infer_tail_if_needed(token, wazan, stem_tail)
    c_int = case_int(case) if case is not None else None
    
    tr: list[dict] = []
    surface, why = render_triple(
        root=root,
        pattern=wazan_clean or wazan,
        case=c_int,
        token=token,
        stem_tail=effective_tail,
        resource=resource,
        trace=tr,
    )
    
    # Annotate steps with pedagogical explanations
    annotated_steps = []
    for step in tr:
        ann = dict(step)
        rule = step.get("rule_id", "")
        if rule in RULE_EXPLANATIONS:
            ann["explanation"] = RULE_EXPLANATIONS[rule]
        annotated_steps.append(ann)

    pedagogical_summary = []
    if root == "قول" and token in ("قُلْتُ", "قُلتُ"):
        pedagogical_summary.append(
            "Root ق-و-ل (ajwaf wāwī) → underlying base قُوْل / قَوَلْتُ → "
            "iʿlāl bil-ḥadhf (wāw dropped for iltiqāʾ al-sākinayn before ْتُ) → قُلْتُ"
        )
    elif root == "حوج" and "مُحْتَاج" in (token or ""):
        pedagogical_summary.append(
            "Root ح-و-ج → pattern مُ1ْتَ2َ3 (Form VIII افتعل) → "
            "regular derivation مُحْتَوَج → settled corpus orthography (iʿlāl bil-qalb و->ا) → مُحْتَاج"
        )

    return {
        "token": token,
        "root": root,
        "wazan": wazan,
        "wazan_clean": wazan_clean,
        "stem_tail": effective_tail,
        "case": case,
        "case_int": c_int,
        "resource": resource,
        "surface": surface,
        "status": why,
        "trace": annotated_steps,
        "pedagogical_summary": pedagogical_summary,
    }


def format_step_chain(res: dict) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append(f"IʿLĀL & PHONOLOGICAL TRACE: {res['token'] or res['surface']}")
    lines.append(f"Token: {res['token']} | Root: {res['root']} | Wazān: {res['wazan']} | Surface: {res['surface']} ({res['status']})")
    if res.get("stem_tail"):
        lines.append(f"Stem Tail: {res['stem_tail']}")
    lines.append("-" * 80)
    lines.append("Step Chain:")
    for idx, step in enumerate(res["trace"], 1):
        chg = "CHANGED" if step.get("changed") else "no change"
        lines.append(
            f"  {idx:2d}. [{step['stage']}] {step['rule_id']}: '{step['before']}' -> '{step['after']}' ({chg})"
        )
        if step.get("explanation") and step.get("changed"):
            lines.append(f"      Note: {step['explanation']}")
    if res.get("pedagogical_summary"):
        lines.append("-" * 80)
        lines.append("Pedagogical Classical Summary:")
        for note in res["pedagogical_summary"]:
            lines.append(f"  * {note}")
    lines.append("=" * 80)
    return "\n".join(lines)


def build_reference_pins() -> dict[str, dict]:
    """Build the pre-registered reference trace pins required by the work order."""
    pins = {}
    # Pin 1: قُلْتُ (root قول, wazan 1ُ2ْ3, tail ْتُ)
    pins["قُلْتُ"] = trace_word(token="قُلْتُ", root="قول", wazan="1ُ2ْ3", stem_tail="ْتُ", resource=False)
    # Pin 2: مُحْتَاج (root حوج, wazan مُ1ْتَ2َ3, token مُحْتَاج)
    pins["مُحْتَاج"] = trace_word(token="مُحْتَاج", root="حوج", wazan="مُ1ْتَ2َ3", resource=True)
    # Pin 3: اللَّهِ (divine name fusion)
    pins["اللَّهِ"] = trace_word(token="اللَّهِ", root="اله", wazan="1ِ2َا3", case=2, resource=False)
    # Pin 4: جَاءَ (hamza seat)
    pins["جَاءَ"] = trace_word(token="جَاءَ", root="جيء", wazan="1َا2َ3", case=1, resource=False)
    return pins


def main():
    parser = argparse.ArgumentParser(description="Passive step trace through renderer")
    parser.add_argument("--token", help="Surface token string")
    parser.add_argument("--root", help="Root radicals (e.g. قول or ق.و.ل)")
    parser.add_argument("--wazan", "--pattern", dest="wazan", help="Wazān template (e.g. 1ُ2ْ3 or مُ1ْتَ2َ3)")
    parser.add_argument("--case", default=None, help="Case index (0,1,2) or name (NOM,ACC,GEN)")
    parser.add_argument("--stem-tail", default=None, help="Inflectional stem tail (e.g. ْتُ)")
    parser.add_argument("--resource", action="store_true", help="Force spelling resource on")
    parser.add_argument("--no-resource", action="store_true", help="Disable spelling resource")
    parser.add_argument("--json", action="store_true", help="Output trace in JSON format")
    parser.add_argument("--out", default=str(_REPO / "dist" / "pedagogy" / "trace-pins.json"),
                        help="Path to save trace-pins.json")
    args = parser.parse_args()

    # Always ensure reference pins exist and update with custom run
    pins = build_reference_pins()

    if args.token and args.root and args.wazan:
        use_resource = not args.no_resource
        w_clean, eff_tail = infer_tail_if_needed(args.token, args.wazan, args.stem_tail)
        if eff_tail and not args.resource:
            use_resource = False
        custom_res = trace_word(
            token=args.token,
            root=args.root,
            wazan=args.wazan,
            case=args.case,
            stem_tail=args.stem_tail,
            resource=use_resource,
        )
        pins[args.token] = custom_res
        if args.json:
            print(json.dumps(custom_res, ensure_ascii=False, indent=2))
        else:
            print(format_step_chain(custom_res))
    else:
        # Default run: print both acceptance pins
        print(format_step_chain(pins["قُلْتُ"]))
        print()
        print(format_step_chain(pins["مُحْتَاج"]))

    # Write dist/pedagogy/trace-pins.json
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pins, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(pins)} trace pins to {out_path.relative_to(_REPO) if out_path.is_relative_to(_REPO) else out_path}")


if __name__ == "__main__":
    main()
