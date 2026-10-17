#!/usr/bin/env python3
"""Demo — the engine with NO corpus and NO trained weights.

This repository deliberately ships without third-party corpora (see WHATS-EXCLUDED.md),
so src/smoke_test.py and src/train.py cannot run here: they need PADT/Tashkeela. This
script demonstrates the parts that are fully deterministic and data-free:

  1. the compiler          render_triple        root + wazan -> vocalized surface
  2. the i'lal trace       trace_render_triple  every morphophonemic step, in order
  3. the mizan converter   pattern_to_mizan     1َ2َ3 -> فَعَلَ, plus the verb form
  4. the i'rab card        format_irab_card     case + governor + reason, as a student sees it
  5. the nahw sandbox      verify_sentence      valid mutation vs. grammatical violation
  6. the semantic binder   bind_semantics       diacritic flip -> AGENT/PATIENT swap

Run:  python demo.py
Expected: every section prints a result; nothing here needs a corpus, a GPU, or network.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from final_surface import render_triple          # noqa: E402
from pedagogy import pattern_to_mizan, trace_render_triple, format_irab_card  # noqa: E402
from nahw_verifier import verify_sentence        # noqa: E402
from semantic_binder import bind_semantics       # noqa: E402

RULE = "=" * 70


def section(n, title):
    print(f"\n{RULE}\n{n}. {title}\n{RULE}")


def main() -> int:
    # 1. compiler -------------------------------------------------------------
    section(1, "COMPILER — root + wazan -> vocalized surface")
    for root, wazan, note in [
        ("قدم", "تَ1ْ2ِي3", "Form II masdar"),
        ("قدم", "إِ1ْ2َا3", "Form IV masdar"),
        ("قدم", "تَ1َ2ُّ3", "Form V masdar"),
    ]:
        # render_triple returns (surface, status) — the affix plane adds case endings separately.
        surf, status = render_triple(root, wazan, None, resource=False)
        print(f"  {root} + {wazan:10s} -> {surf:10s}  [{status}]   {note}")

    # 2. i'lal trace ----------------------------------------------------------
    section(2, "I'LAL TRACE — the step-by-step that no other app shows")
    for kw in [
        dict(root="قول", wazan="1ُ2ْ3", case=None, stem_tail="ْتُ", token="قُلْتُ"),
        dict(root="حوج", wazan="مُ1ْتَ2َ3", case=None, token="مُحْتَاج"),
    ]:
        steps = trace_render_triple(**kw)          # returns a list of step dicts
        print(f"  {kw['token']}   root {'.'.join(kw['root'])}")
        final = kw["token"]
        for s in (steps or []):
            final = s.get("after_surface") or final
            if not s.get("changed"):
                continue                            # only the steps that DID something
            print(f"     {s.get('rule_id','?'):26s} {s.get('before_surface','')}  ->  "
                  f"{s.get('after_surface','')}")
            if s.get("explanation"):
                print(f"        {s['explanation'][:110]}")
        print(f"     final surface: {final}")
        if final != kw["token"]:
            print(f"     NOTE: the engine's surface differs from the cited token "
                  f"({kw['token']}) — reported as produced, not adjusted.")

    # 3. mizan ---------------------------------------------------------------
    section(3, "MIZAN SARFI — internal pattern codes -> Arabic grammar")
    for pat in ["مُ1ْتَ2َ3", "1َا2ِ3", "مُ1َ2ِّ3", "إِ1ْ2َا3"]:
        m = pattern_to_mizan(pat)
        bits = [f"{k}={v}" for k, v in (m if isinstance(m, dict) else m.__dict__).items()
                if v is not None and k in ("pattern", "mizan", "form", "type", "label", "canonical")]
        print(f"  {pat:12s} -> " + ("  ".join(bits) or m))

    # 4. i'rab card ----------------------------------------------------------
    section(4, "I'RAB CARD — what the student actually reads")
    card = format_irab_card("أُصُولِ", "GEN", deprel="obl", governor_token="بِ")
    print("  " + str(card))

    # 5. nahw sandbox --------------------------------------------------------
    section(5, "NAHW SANDBOX — valid mutation vs. violation")
    valid = verify_sentence([{"surface": "ضَرَبَ"}, {"surface": "زَيْدٌ"},
                             {"surface": "عَمْرًا"}])
    print(f"  valid V-S-O      : is_valid={getattr(valid,'is_valid',None)}  "
          f"violations={getattr(valid,'violations',None)}")
    bad = verify_sentence([{"surface": "رَأَيْتُ"},
                           {"surface": "المُعَلِّمَاتَ", "user_case": "ACC_INVALID_FATHA"}])
    print(f"  bad sound plural : is_valid={getattr(bad,'is_valid',None)}  "
          f"violations={getattr(bad,'violations',None)}")

    # 6. semantic binder -----------------------------------------------------
    section(6, "SEMANTIC BINDER — one vowel moves the agent")
    for tiles in ([{"surface": "ضَرَبَ"}, {"surface": "زَيْدٌ"}, {"surface": "عَمْرًا"}],
                  [{"surface": "ضَرَبَ"}, {"surface": "زَيْدًا"}, {"surface": "عَمْرٌ"}]):
        b = bind_semantics(tiles)
        ag = b.roles.get("AGENT")
        pt = b.roles.get("PATIENT")
        print("  " + " ".join(t.get("surface", "") for t in tiles))
        print(f"     AGENT   = {getattr(ag,'surface',None)} ({getattr(ag,'gloss_en',None)})")
        print(f"     PATIENT = {getattr(pt,'surface',None)} ({getattr(pt,'gloss_en',None)})")
        print(f"     EN: {b.translation_en}   |   ID: {b.translation_id}")

    print(f"\n{RULE}\nAll six sections are deterministic. No corpus, no weights, no network.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
