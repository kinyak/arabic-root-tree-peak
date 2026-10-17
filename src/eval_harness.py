"""eval_harness.py — G4: the shared scoring harness (SPEC-REV6 §5.1, §5.3).

WHAT THIS FIXES
    G4 is "no evaluation that survives review". Two specific defects are addressed
    here, both named as the project's biggest validity threats:

    A3 — the two arms were scored on DIFFERENT objects. Fixed by defining ONE
    metric on the FINAL SURFACE and scoring both arms through it: the treatment
    (root+wazān+case → renderer → surface) and the BPE baseline (→ surface) are
    compared by `surface_exact_match` on the same strings. Nothing else is the
    headline.

    §5.3 — the evaluation must not be CALIMA-mediated. Eval labels come from
    human/independent treebanks only (NYUAD for syntax+case, QAC for morphology),
    never from CALIMA. And because CALIMA *is* what the treatment distils,
    `--ceiling` measures CALIMA-vs-human agreement on those same test sets: that
    number is the metric's ceiling and is a required result regardless of any
    model (SPEC-REV6 §5.3 item 3).

REPORTING RULES ENFORCED IN CODE, NOT PROSE
    · Case is reported as per-class P/R/F1 + MACRO-F1, never raw accuracy — an
      always-`Gen` predictor scores 66.9% accuracy and is worthless. The harness
      prints that majority-class baseline next to every case result so the trap is
      visible rather than remembered. §5.1 item 4.
    · Root is reported with a PER-ROOT-CLASS breakdown (sound / doubled /
      assimilated / hollow / defective / hamza / quadriliteral). §5.1 item 4.
    · Wazān is reported as COVERAGE of well-formed labels, never accuracy — no
      public gold wazān exists. §5.1 item 3.
    · Renderer accuracy and renderer coverage are separate numbers. §5.1 item 1.
    · CALIMA silver is DISTILLATION; the harness says so in its own output. §5.3 item 4.

USAGE
    python src/eval_harness.py --selftest                      # known-answer tests
    python src/eval_harness.py --ceiling --source nyuad --limit 5000
    python src/eval_harness.py --ceiling --source qac   --limit 5000
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

from paths import EQTB_CSV, GOLD_JSONL, NYUAD_TEST, PADT_TEST, QAC_TXT, require
from final_surface import (render_triple, score_final_surface, decode_root_slots,
                          decode_root_slots_beamed, decode_rasm_constrained, strip_diac)
from wazan_normalizer import (canonicalize_vocalized_wazan, canonicalize_mater_vowels,
                              tail_strip, STEM_TAIL_VOCALIZED, split_wazan_stem_and_tail)
# The Tier-1 structural abstention gate, imported from its SIBLING module exactly like
# `paths` and `final_surface` above (bare name; the script directory is on sys.path).
# The accounting built on it is ADDITIVE: it never changes a prediction, a metric, or the
# value of any already-printed number -- it only counts the gate's decisions per gold row.
from uncertainty_abstention import StructuralGate

DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
CASE_NAMES = {0: "NOM", 1: "ACC", 2: "GEN"}
CASE_MAP = {"n": 0, "a": 1, "g": 2}          # CALIMA `cas`
UD_CASE = {"nom": 0, "acc": 1, "gen": 2}     # UD `Case=`
WEAK = {"\u0648", "\u064a", "\u0627", "\u0649", "#"}   # و ي ا ى and CALIMA's '#'
HAMZA = {"\u0621", "\u0623", "\u0625", "\u0624", "\u0626"}  # ء أ إ ؤ ئ


def strip_diac(s: str) -> str:
    return DIAC.sub("", s or "")


# --------------------------------------------------------------- metrics
def confusion(gold, pred, labels):
    """gold/pred are iterables of the same length. Returns {(g,p): n}."""
    c = collections.Counter()
    for g, p in zip(gold, pred):
        if g is None:
            continue                     # masked tokens are excluded, not guessed
        c[(g, p)] += 1
    return c


def prf_per_class(gold, pred, labels=(0, 1, 2), names=None):
    """Per-class precision/recall/F1 + macro-F1 + support. No raw accuracy."""
    names = names or {i: str(i) for i in labels}
    cm = confusion(gold, pred, labels)
    out, f1s = {}, []
    for lab in labels:
        tp = cm[(lab, lab)]
        fp = sum(cm[(g, lab)] for g in labels if g != lab)
        fn = sum(cm[(lab, p)] for p in labels if p != lab)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        f1s.append(f1)
        out[names[lab]] = {"precision": prec, "recall": rec, "f1": f1,
                           "support": tp + fn}
    out["macro_f1"] = sum(f1s) / max(len(f1s), 1)
    out["n"] = sum(out[names[l]]["support"] for l in labels)
    # the trap, quantified: what a single-class predictor would score
    sup = {names[l]: out[names[l]]["support"] for l in labels}
    if out["n"]:
        maj = max(sup, key=sup.get)
        maj_f1s = []
        for l in labels:
            if names[l] == maj:
                # RECALL IS 1.0 (every true-majority token is found) BUT PRECISION IS NOT:
                # only support/n of this predictor's outputs are right. Hardcoding both to
                # 1.0 made majority_macro_f1 a constant 1/k -- 0.333 for the three case
                # classes, in EVERY run, whatever the data. A baseline that does not depend
                # on the data is not a baseline. Guarded by the self-test at the bottom.
                rec = 1.0
                prec = sup[maj] / out["n"]
                f1 = 2 * prec * rec / (prec + rec)
            else:
                prec = rec = f1 = 0.0
            maj_f1s.append(f1)
        out["majority_class"] = maj
        out["majority_accuracy"] = sup[maj] / out["n"]
        out["majority_macro_f1"] = sum(maj_f1s) / max(len(maj_f1s), 1)
    return out


def surface_exact_match(gold, pred):
    """THE SHARED FINAL-SURFACE METRIC (A3). Both arms are scored by this.

    Returns (exact, skeleton, n) where
      exact    = identical strings, diacritics included  -> the headline
      skeleton = identical once diacritics are stripped   -> reported separately,
                 never as a substitute for the headline.
    """
    ex = sk = n = 0
    for g, p in zip(gold, pred):
        if g is None:
            continue
        n += 1
        if p is not None and p == g:
            ex += 1
        if p is not None and strip_diac(p) == strip_diac(g):
            sk += 1
    return ex, sk, n


# ------------------------------------------------- human gold (278 patterns)
# The ONE reference in this project that is not CALIMA-mediated, and therefore the one
# that has to be scored IDENTICALLY for every arm and every training target. It lives
# here, with the other shared metrics, rather than inside a notebook cell — a metric
# that exists in two places is a metric that can silently diverge.
GOLD_DEFAULT = str(GOLD_JSONL)
ARABIC_LETTER = re.compile(r"[\u0621-\u064a]")
NOT_ARABIC_EDGE = re.compile(r"^[^\u0621-\u064a]+|[^\u0621-\u064a]+$")
HAMZA_FAMILY = "\u0621\u0622\u0623\u0625\u0671"          # ء آ أ إ ٱ
DIAC_CLASS = "\\u064b-\\u0652\\u0670\\u0640"
BARE_ALEF_MAP = str.maketrans({"\u0623": "\u0627", "\u0625": "\u0627",
                               "\u0622": "\u0627", "\u0621": "\u0627",
                               "\u0671": "\u0627"})
_NFC = __import__("unicodedata").normalize


def nfc(s: str | None) -> str | None:
    """Canonical composition, applied to BOTH sides of every label comparison.

    MEASURED EFFECT, so nobody later mistakes this for the explanation of the gap:
    on the 196 gold rows that have a silver label, NFC changes the exact-agreement
    count by ONE (48 -> 49 of 196). The gap is diacritic coverage and weak-radical
    spelling, which is a real difference between the two conventions — not a Unicode
    artefact. It is still applied, because the same visual string must compare equal.
    """
    return None if s is None else _NFC("NFC", s)


def bare_form(tok: str) -> str:
    """The model's INPUT convention (PADT `form_bare`): diacritics off, edges trimmed."""
    return strip_diac(NOT_ARABIC_EDGE.sub("", tok or ""))


def to_bare_root_str(s: str) -> str:
    """Rule 7 — bare alef, no separators.

    MEASURED, not cosmetic: PADT's translit table and arramooz write a hamzated radical
    as ء/أ ('ءخذ' for أخذ) while the human annotator wrote a bare alef ('ابو', 'ارض').
    Comparing raw strings scores that difference as a WRONG ROOT. Applied to BOTH sides.
    """
    if not s:
        return ""
    return "".join(c for c in s if ARABIC_LETTER.match(c)).translate(BARE_ALEF_MAP)


def lead_hamza_variant(lab: str | None) -> str | None:
    """Normalise the two spellings of a hamzated FIRST radical to the digit form.

    MEASURED on the gold itself: أُصُول is written by the annotator as '1ُ2ُو3' — the
    hamza IS radical 1, so it is written as the digit — while a CALIMA-derived label can
    carry the letter and the digit ('أُ1ُ2ُو3'). Without this the ablation reports a
    mismatch that is purely orthographic. Reported as a SEPARATE metric; the raw figure
    is never replaced by it. NFC is applied first (see nfc()).
    """
    lab = nfc(lab)
    if not lab:
        return lab
    # Form IV / Form X prefix hamza preservation:
    if re.match(r"^[\u0623\u0625\u0627][\u064e\u0650]?1\u0652", lab):
        return lab
    m = re.match(rf"^[{HAMZA_FAMILY}][{DIAC_CLASS}]*", lab)
    if not m:
        return lab
    rest = lab[m.end():]
    if "1" in re.findall(r"[1-4]", rest):
        return rest                     # the letter duplicates slot 1 -> drop it
    return "1" + rest                   # the letter IS slot 1 -> make it the digit


def load_human_gold(path: str = GOLD_DEFAULT) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def parse_gold_context(ctx: str) -> tuple[list[str], int | None]:
    """Gold context -> (bare token list, target index), or ([], None).

    The context is SELF-CONTAINED (sentence with the target in [[double brackets]]),
    which is why the same function scores a PADT-trained and a Tashkeela-trained model:
    nothing has to be located inside either corpus.
    """
    if not ctx or "[[" not in ctx or "]]" not in ctx:
        return [], None
    before, rest = ctx.split("[[", 1)
    target_and_after = rest.split("]]", 1)
    if len(target_and_after) != 2:
        return [], None
    target, after = target_and_after
    b_toks = [bare_form(t) for t in before.split() if bare_form(t)]
    tgt = bare_form(target)
    a_toks = [bare_form(t) for t in after.split() if bare_form(t)]
    toks = b_toks + [tgt] + a_toks
    idx = len(b_toks)
    if not 0 <= idx < len(toks):
        return [], None
    return toks, idx


# --------------------------------------------------- abstention-gate accounting
# The Tier-1 structural gate (`uncertainty_abstention.StructuralGate`) decides, per
# surface, whether a word is closed-class / non-templatic enough to abstain on WITHOUT
# looking at the model. This block counts those decisions on the human gold. It is strictly
# ADDITIVE: it reads the pipeline's prediction but never rewrites it, and it is evaluated
# on the SAME target token the pipeline fed the model (`toks[idx]`).
_ABSTENTION_GATE = StructuralGate()


def account_abstention_buckets(rows, gate=None):
    """Classify every ``(surface_token, pipeline_emitted)`` row into ONE bucket.

    `rows` must contain EVERY human-gold row, in gold order; the caller may not
    pre-filter (no `if not toks: continue`, no masking that could drop a row).

    Buckets, in priority order:
      structural_abstentions            the gate abstains structurally and the pipeline
                                        honoured it (emitted no prediction).
      forced_predictions_after_abstain  the gate abstains structurally but the pipeline
                                        still emitted a prediction (a forced prediction).
      confidence_abstentions            no structural reason to abstain, but the
                                        pipeline's own Tier-2/3 path declined to emit.

    A structural decision is FINAL. Once the gate abstains the row can never be
    reclassified as a confidence abstention or as accepted; if the pipeline emitted a
    prediction anyway it lands in the forced bucket -- the warning that the pipeline
    overrode a structural abstention -- never back in the confidence one, and the
    accounting never changes which prediction the pipeline reports. Rows the pipeline
    accepted with no structural hit fall in no bucket, so the three buckets sum to
    ``human_gold_rows_accounted`` (the abstention-bearing rows).
    """
    gate = _ABSTENTION_GATE if gate is None else gate
    structural = confidence = forced = 0
    for surface, emitted in rows:
        is_structural, _reason = gate.evaluate(surface)
        if is_structural:
            if emitted:
                forced += 1          # gate said abstain; pipeline emitted anyway
            else:
                structural += 1      # gate said abstain; pipeline honoured it
        elif not emitted:
            confidence += 1          # no structural reason, but the pipeline abstained
    return {
        "structural_abstentions": structural,
        "confidence_abstentions": confidence,
        "forced_predictions_after_abstain": forced,
        "human_gold_rows_accounted": structural + confidence + forced,
    }


def print_abstention_account(counts) -> None:
    """Print the additive counters with their literal metric-key labels."""
    print("  abstention gate accounting (Tier 1 structural / Tier 2-3 confidence):")
    print(f"    structural_abstentions            : {counts['structural_abstentions']}")
    print(f"    confidence_abstentions            : {counts['confidence_abstentions']}")
    print(f"    forced_predictions_after_abstain  : "
          f"{counts['forced_predictions_after_abstain']}")
    print(f"    human_gold_rows_accounted         : {counts['human_gold_rows_accounted']}")


def score_human_gold(model, v, gold: list[dict], device, max_len: int = 96,
                     surface_engines: tuple = ("v1", "v3"),
                     trie=None, beam: int = 5) -> dict:
    """Per-head accuracy against the human gold, for ONE trained model, PLUS the
    SHARED FINAL-SURFACE metric that BOTH arms are scored by (A3).

    Scoring is per HEAD and only on the rows where that head has a human label:
      wazān : strict-well-formed gold patterns (Rule 6)  -> exact label match
      root  : rows where the annotator gave a root       -> bare-alef match (Rule 7)
      case  : rows with NOM/ACC/GEN                      -> macro-F1 + accuracy
    `case_majority_macro_f1` is printed beside the case score for the same reason it
    is everywhere else in this project: always-GEN is a strong-looking, worthless baseline.

    THE FINAL-SURFACE BLOCK IS THE POINT OF THIS FUNCTION.
    The model's own (root, wazān, case) is rendered to a surface by `final_surface.
    render_triple` and compared against the human gold token at the STEM level, so the
    treatment arm (root+wazān+case -> renderer -> surface) and the BPE baseline are
    both scored on ONE metric over ONE object. It needs only the gold FORM, so unlike
    the per-head blocks it covers every annotated row, including those whose root or
    case the annotator left blank. Coverage and accuracy come back SEPARATE.
    `surface_engines` renders with both digit rules so the choice is visible, not hidden.
    """
    import torch
    inv_w = {i: w for w, i in v.wazan.items()}
    inv_r = {i: c for c, i in v.radical.items()}
    inv_tail = {i: t for t, i in v.stem_tail.items()} if hasattr(v, "stem_tail") else {0: "", **{i + 1: t for i, t in enumerate(STEM_TAIL_VOCALIZED)}}
    model.eval()
    if hasattr(torch.backends, "mha") and hasattr(torch.backends.mha, "set_fastpath_enabled"):
        torch.backends.mha.set_fastpath_enabled(False)
    oov = tot = 0
    wz = [0, 0, 0, 0, 0, 0]     # [raw, hamza-norm, +diac-free, n, radical-slot-set, canonical]
    wz_strict_raw = 0
    wz_mater_canon = 0
    st_tot = st_ok = st_suff_tot = st_suff_ok = st_bare_tot = 0
    rt = [0, 0, 0, 0]        # [argmax ok, argmax n, beamed ok, beamed n]
    cg, cp = [], []
    mismatches = []
    triples: list = []       # (gold_form, pred_root, pred_pattern, pred_case, pred_def, pred_stem_tail)
    rasm_triples: list = []  # (gold_form, rasm_surf, reason)
    # Additive abstention accounting. One entry per gold row, keyed by gold index, holding
    # the SAME target token the pipeline fed the model (`toks[idx]`) and whether this
    # pipeline reported a final surface for it. It is filled for EVERY row: rows the
    # pipeline cannot process are completed below, so no row is ever skipped.
    abstention_inputs: dict = {}
    with torch.no_grad():
        for gi, g in enumerate(gold):
            toks, idx = parse_gold_context(g.get("context") or "")
            if not toks:
                continue
            if len(toks) > max_len:                 # window around the target
                lo = max(0, min(idx - max_len // 2, len(toks) - max_len))
                toks = toks[lo:lo + max_len]
                idx -= lo
            ids = [v.encode(t) for t in toks]
            oov += sum(1 for t in toks if v.encode(t) == 1)
            tot += len(toks)
            x = torch.tensor([ids], device=device)
            # v12: build character tensor
            max_char_len = 16  # must match CharEncoder.max_char_len in model_arms.py
            x_char_list = []
            for t in toks:
                chars = [v.char.get(c, 0) for c in t[:max_char_len]]
                chars += [0] * (max_char_len - len(chars))
                x_char_list.append(chars)
            x_char = torch.tensor([x_char_list], device=device)
            out = model(x, x_char)
            pw = None
            if out["wazan"] is not None:
                pw = inv_w.get(int(out["wazan"][0, idx].argmax()), None)
            # ---- the shared final-surface input, collected for EVERY gold row (it needs
            # only the gold FORM, so rows the annotator left partly blank still count) ----
            # PRONG 1 (CHALLENGES 2x.14): slice the slots to the PREDICTED PATTERN's arity. The 4th
            # root slot is unsupervised (trained as IGNORE, never <pad>), so reading it as content gave
            # every triliteral root length 4 and produced 296/296 root_len_mismatch.
            _r = (to_bare_root_str(decode_root_slots(
                      out["root"][0, idx].argmax(-1).tolist(), pw, inv_r))
                  if out["root"] is not None else None)
            pred_def = int(out["definiteness"][0, idx].argmax()) if ("definiteness" in out and out["definiteness"] is not None) else None
            from final_surface import is_verbal_tail, is_verb_template
            pred_stem_tail = inv_tail.get(int(out["stem_tail"][0, idx].argmax()), "") if ("stem_tail" in out and out["stem_tail"] is not None) else ""
            is_verb = (pred_def in (3, "OTHER", "INVARIABLE")) or is_verbal_tail(pred_stem_tail) or is_verb_template(pw)
            _c = None if is_verb else (int(out["case"][0, idx].argmax()) if out["case"] is not None else None)
            triples.append((g.get("form"), _r, pw, _c, pred_def, pred_stem_tail))

            # Rasm-constrained decode lattice candidate
            if out["wazan"] is not None and out["root"] is not None:
                c_logits = out["case"][0, idx] if out["case"] is not None else None
                tail_logits = out["stem_tail"][0, idx] if ("stem_tail" in out and out["stem_tail"] is not None) else None
                df_logits = out["definiteness"][0, idx] if ("definiteness" in out and out["definiteness"] is not None) else None
                use_res = os.environ.get("ARABIC_SPELLING_RESOURCE", "1") != "0"
                _r_rasm, _w_rasm, _c_rasm, s_rasm, _ = decode_rasm_constrained(
                    out["root"][0, idx], out["wazan"][0, idx], c_logits,
                    stem_tail_logits=tail_logits,
                    def_logits=df_logits,
                    inv_r=inv_r, inv_w=inv_w, inv_tail=inv_tail,
                    token=strip_diac(g.get("form")),
                    engine=surface_engines[0],
                    trie=trie,
                    resource=use_res
                )
                rasm_triples.append((g.get("form"), s_rasm, "ok" if s_rasm else "abstain"))
            else:
                rasm_triples.append((g.get("form"), None, "abstain"))

            # The pipeline's OWN emitted prediction for this row is its final surface: the
            # renderer returning None is the harness's non-structural (Tier-2/3) abstention.
            # `strip_diac` (§2ci): the renderer and the resource must see the UNVOCALIZED form, the
            # same input a real inference call would have. Measured neutral — the affix plane was
            # proven invariant to input diacritics (§2ce, 0 of 1278 rows differ) and the resource
            # keys the token's skeleton — so this is DEFENSE IN DEPTH, not a number change. It closes
            # the path by which the vocalized gold reached the decoder in the first place.
            _acc_surface, _acc_why = render_triple(_r, pw, _c, engine=surface_engines[0],
                                                   token=strip_diac(g.get("form")),
                                                   definiteness=pred_def, stem_tail=pred_stem_tail)
            abstention_inputs[gi] = (toks[idx], _acc_surface is not None)
            if g.get("pattern_valid") and g.get("t_wazan_pattern"):
                gp = nfc(g["t_wazan_pattern"])
                wz[3] += 1
                pw_c = canonicalize_mater_vowels(pw)
                gp_c = canonicalize_mater_vowels(gp)
                gold_stem_raw = tail_strip(gp)
                gold_stem_c = canonicalize_mater_vowels(gold_stem_raw)

                # Strict raw: exact string match against gold tail_strip(t_wazan_pattern)
                is_strict_raw = (nfc(pw) == nfc(gold_stem_raw))
                if is_strict_raw:
                    wz_strict_raw += 1

                # Mater canon: exact string match after canonicalize_mater_vowels
                is_mater_canon = (pw_c is not None and pw_c == gold_stem_c)
                if is_mater_canon:
                    wz_mater_canon += 1

                gp_tail_stripped = canonicalize_mater_vowels(tail_strip(gp))
                is_exact = is_strict_raw or is_mater_canon or (pw_c == gp_c) or (pw_c == gp_tail_stripped)
                wz[0] += 1 if is_exact else 0
                wz[1] += 1 if lead_hamza_variant(pw) == lead_hamza_variant(gp) else 0
                wz[2] += 1 if (strip_diac(lead_hamza_variant(pw) or "")
                               == strip_diac(lead_hamza_variant(gp) or "")) else 0
                # 4th column: do the two agree about WHICH SLOTS hold radicals, ignoring
                # how the weak radical is spelled (CALIMA writes a digit, the human
                # annotator wrote the letter — e.g. '123' vs '1َا2َ3' for وَقَالَ).
                # MEASURED on 20k silver records: the exact string agrees on 28% of gold
                # rows while the radical-slot set agrees on 99%. The difference is a
                # CONVENTION, not a grammar error, so both are reported and neither
                # replaces the other.
                wz[4] += 1 if (sorted(re.findall(r"[1-4]", pw or ""))
                               == sorted(re.findall(r"[1-4]", gp or ""))) else 0
                pw_canon = canonicalize_vocalized_wazan(lead_hamza_variant(pw))
                gp_canon = canonicalize_vocalized_wazan(lead_hamza_variant(gp))
                wz[5] += 1 if (pw_canon and pw_canon == gp_canon) else 0

                # stem_tail evaluation on gold-300
                wz_split = split_wazan_stem_and_tail(gp)
                if wz_split is not None:
                    _, gold_tail = wz_split
                    st_tot += 1
                    if gold_tail == "":
                        st_bare_tot += 1
                    else:
                        st_suff_tot += 1
                    pred_tail = pred_stem_tail or ""
                    if pred_tail == gold_tail:
                        st_ok += 1
                        if gold_tail != "":
                            st_suff_ok += 1

                if not is_exact and len(mismatches) < 12:
                    mismatches.append({"form": g["form"], "gold": gp, "pred": pw,
                                       "pred_norm": lead_hamza_variant(pw),
                                       "pred_canon": pw_canon, "gold_canon": gp_canon})
            if out["root"] is not None and g.get("root_valid") and g.get("t_root_arabic"):
                slots = out["root"][0, idx].argmax(-1).tolist()
                # same ONE decoder as the surface path, so the per-head root score and the composed
                # surface score can no longer disagree about what the model predicted
                got = to_bare_root_str(decode_root_slots(slots, pw, inv_r))
                rt[1] += 1
                if got == to_bare_root_str(g["t_root_arabic"]):
                    rt[0] += 1
                if trie is not None:
                    # the same weights decoded a second time, trie-constrained (CHALLENGES 2aa)
                    rb = decode_root_slots_beamed(out["root"][0, idx].detach().cpu().tolist(),
                                                  pw, inv_r, trie, beam=beam)
                    rt[3] += 1
                    if to_bare_root_str(rb["root"]) == to_bare_root_str(g["t_root_arabic"]):
                        rt[2] += 1
            if out["case"] is not None and g.get("t_case") is not None:
                cg.append(int(g["t_case"]))
                cp.append(int(out["case"][0, idx].argmax()))
    model.train()
    # Additive accounting over EVERY gold row, in gold order. A row the pipeline could not
    # process emitted nothing; the gate is still run on its gold form, so nothing is dropped.
    abstention_rows = [abstention_inputs.get(gi, (g.get("form"), False))
                       for gi, g in enumerate(gold)]
    abstention_account = account_abstention_buckets(abstention_rows)
    print_abstention_account(abstention_account)
    # THE SHARED FINAL-SURFACE METRIC, per engine, on the SAME rows for every arm.
    # Pass the renderer's REASON through as well as its surface. `[0]` alone discarded the reason,
    # which is why 296 human-gold abstentions could only be reported as one bucket (R19b).
    # `(gf,) + render_triple(...)` == (gold_form, surface|None, why) — the order score_final_surface
    # expects, with no extra bookkeeping.
    fs = {
        "v3_resource_off_argmax": score_final_surface([
            (gf,) + tuple(render_triple(r, p, c, engine="v3", token=strip_diac(gf),
                                        definiteness=df, stem_tail=tail, resource=False))
            for gf, r, p, c, df, tail in triples
        ]),
        "v3_resource_on": score_final_surface([
            (gf,) + tuple(render_triple(r, p, c, engine="v3", token=strip_diac(gf),
                                        definiteness=df, stem_tail=tail, resource=True))
            for gf, r, p, c, df, tail in triples
        ]),
    }
    use_res = os.environ.get("ARABIC_SPELLING_RESOURCE", "1") != "0"
    if rasm_triples:
        joint_sc = score_final_surface(rasm_triples)
        if use_res:
            fs["v3_resource_on_joint"] = joint_sc
        else:
            fs["v3_resource_off_joint"] = joint_sc
        fs["v3_rasm"] = joint_sc
    for e in surface_engines:
        if e not in fs:
            fs[e] = score_final_surface([
                (gf,) + tuple(render_triple(r, p, c, engine=e, token=strip_diac(gf),
                                            definiteness=df, stem_tail=tail, resource=use_res))
                for gf, r, p, c, df, tail in triples
            ])
    res = {
        "gold_rows": len(gold),
        "contexts_scored": tot,
        "final_surface": fs,
        "oov_rate": round(oov / max(tot, 1), 4),
        "wazan": {"correct": wz[0], "n": wz[3],
                  "accuracy": round(wz[0] / max(wz[3], 1), 4)},
        "wazan_strict_raw": {"correct": wz_strict_raw, "n": wz[3],
                             "accuracy": round(wz_strict_raw / max(wz[3], 1), 4)},
        "wazan_mater_canon": {"correct": wz_mater_canon, "n": wz[3],
                              "accuracy": round(wz_mater_canon / max(wz[3], 1), 4)},
        "wazan_hamza_normalised": {"correct": wz[1], "n": wz[3],
                                   "accuracy": round(wz[1] / max(wz[3], 1), 4)},
        "wazan_hamza_normalised_diacritic_free": {
            "correct": wz[2], "n": wz[3], "accuracy": round(wz[2] / max(wz[3], 1), 4)},
        "wazan_canonical": {"correct": wz[5], "n": wz[3],
                            "accuracy": round(wz[5] / max(wz[3], 1), 4)},
        "wazan_radical_slots": {"correct": wz[4], "n": wz[3],
                                "accuracy": round(wz[4] / max(wz[3], 1), 4),
                                "constant_baseline": 0.989},
        "stem_tail": {
            "accuracy": round(st_ok / max(st_tot, 1), 4),
            "overall_accuracy": round(st_ok / max(st_tot, 1), 4),
            "suffixed_only_accuracy": round(st_suff_ok / max(st_suff_tot, 1), 4) if st_suff_tot else 0.0,
            "constant_bare_baseline": round(st_bare_tot / max(st_tot, 1), 4) if st_tot else 0.0,
            "n": st_tot,
            "n_suffixed": st_suff_tot,
        },
        "root": {"correct": rt[0], "n": rt[1],
                 "accuracy": round(rt[0] / max(rt[1], 1), 4)},
        # the SAME rows decoded a second way (trie-constrained beam) — reported BESIDE the
        # argmax figure, never blended into it (CHALLENGES 2aa). None when no trie was given.
        "root_whole_beamed": ({"correct": rt[2], "n": rt[3],
                               "accuracy": round(rt[2] / max(rt[3], 1), 4)}
                              if rt[3] else None),
        "case_majority_macro_f1": (
            prf_per_class(cg, cg, names=CASE_NAMES).get("majority_macro_f1")),
        "wazan_mismatch_examples": mismatches,
    }
    # ADDITIVE keys only: the abstention counters never replace or recompute an existing key.
    res.update(abstention_account)
    if cg:
        res["case"] = prf_per_class(cg, cp, names=CASE_NAMES)
    return res


# --------------------------------------------------- root morphology class
def root_class(root: str) -> str:
    """Classify a 3/4-radical Arabic root. Deterministic priority order:

        quadriliteral -> doubled -> hamza -> assimilated -> hollow -> defective -> sound

    A root can belong to several classes (a doubled hollow root exists); the order
    above is the convention used here and is STATED so the breakdown is
    reproducible. '#' (CALIMA's unassigned weak radical) counts as WEAK.

    Priority rationale: arity and doubling are structural facts about the written
    skeleton, so they are decided first; hamza is a property of a specific radical;
    the weak-letter classes require the weak letter to be *identified*, which for
    CALIMA output is exactly what '#' fails to do.
    """
    rads = [c for c in (root or "") if c not in "."]
    if not rads:
        return "unknown"
    if all(r == "#" for r in rads):
        return "unknown"          # fully unassigned: no morphology to name
    if len(rads) >= 4:
        return "quadriliteral"
    if len(rads) != 3:
        return "unknown"
    c1, c2, c3 = rads
    if c2 == c3 and c2 != "#":
        return "doubled"
    if any(r in HAMZA for r in rads):
        return "hamza"
    if c1 in WEAK:
        return "assimilated"
    if c2 in WEAK:
        return "hollow"
    if c3 in WEAK:
        return "defective"
    return "sound"


def root_metrics(gold_roots, pred_roots):
    """Exact-skeleton accuracy overall AND per root class.

    Masking rule: a pair is scored only when the gold root is usable; `pred` may be
    None and that counts as a miss. Per-class accuracy is what exposes the class
    bias documented in M1 (sound roots recover far better than weak ones).
    """
    tot = ok = 0
    per = collections.defaultdict(lambda: [0, 0])
    for g, p in zip(gold_roots, pred_roots):
        if not g:
            continue
        cls = root_class(g)
        tot += 1
        per[cls][1] += 1
        if p == g:
            ok += 1
            per[cls][0] += 1
    return {"accuracy": ok / max(tot, 1), "n": tot,
            "per_class": {k: {"accuracy": v[0] / max(v[1], 1), "n": v[1],
                              "correct": v[0]}
                          for k, v in sorted(per.items())}}


def deprel_metrics(gold_rel, pred_rel, gold_head=None, pred_head=None):
    out = {"n": 0, "deprel_accuracy": 0.0}
    ok = tot = 0
    for g, p in zip(gold_rel, pred_rel):
        if g is None:
            continue
        tot += 1
        ok += 1 if g == p else 0
    out["n"], out["deprel_accuracy"] = tot, ok / max(tot, 1)
    if gold_head is not None and pred_head is not None:
        ua = la = 0
        for gh, ph, gr, pr in zip(gold_head, pred_head, gold_rel, pred_rel):
            if gh is None:
                continue
            if gh == ph:
                ua += 1
                if gr == pr:
                    la += 1
        out["uas"] = ua / max(tot, 1)
        out["las"] = la / max(tot, 1)
    return out


def wazan_coverage(labels):
    """COVERAGE of well-formed labels. Never accuracy — no public gold wazān."""
    n = sum(1 for l in labels if l is not None)
    return {"wellformed_labels": n, "total": len(labels),
            "coverage": n / max(len(labels), 1)}


# ------------------------------------------------------------- reporting
def print_head(title, payload, ceiling=None):
    print(f"\n{'-'*84}\n{title}\n{'-'*84}")
    for k, v in payload.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"    {kk}: {vv}")
        else:
            print(f"  {k}: {v}")
    if ceiling is not None:
        print(f"  !! CEILING (CALIMA vs human, §5.3 item 3): {ceiling}")


def selftest() -> int:
    print("=" * 84)
    print("EVAL HARNESS — known-answer self-test")
    print("=" * 84)
    bad = []

    # 1. the majority-class trap, exactly as §5.1 item 4 warns. Gold is the PADT
    #    case distribution (GEN 50%, ACC 20%, NOM 30%) and the predictor always says
    #    GEN — the documented "always-predict-Gen scores 66.9%" trap, scaled down.
    #    NOTE the macro-F1 is 0.154, NOT 1/3: predicting one class everywhere accrues
    #    false positives on every other class, so its own precision collapses too.
    gold = [2] * 5 + [1] * 2 + [0] * 3      # GEN 50% / ACC 20% / NOM 30%
    pred = [2] * 10                          # always GEN — the majority class
    m = prf_per_class(gold, pred, names=CASE_NAMES)
    print(f"\n[1] always-GEN predictor: n={m['n']} "
          f"majority_accuracy={m['majority_accuracy']:.3f} "
          f"macro_f1={m['macro_f1']:.3f}")
    if abs(m["majority_accuracy"] - 0.500) > 1e-9:
        bad.append("majority accuracy should be 0.500")
    # THE BASELINE MUST MATCH ITS OWN DEFINITION. In this toy the prediction IS always-GEN,
    # which IS the majority class -- so `majority_macro_f1` must equal the macro-F1 that
    # prf_per_class itself scores for that same prediction (0.154, per the note above). The
    # old code hardcoded prec = rec = 1.0, so it returned exactly 1/3 here: a constant
    # that never moved with the data, and the reason "(majority 0.333)" appeared in every
    # kernel log of every round. This assertion is the guard that was missing.
    if abs(m["majority_macro_f1"] - m["macro_f1"]) > 1e-9:
        bad.append("majority_macro_f1 %.3f != the same predictor's macro_f1 %.3f"
                   % (m["majority_macro_f1"], m["macro_f1"]))
    # AND AGAINST THE CLOSED FORM, so this is not merely an identity between two functions.
    # For an always-majority predictor: recall 1.0, precision = support/n, so macro-F1 is
    # (2p/(p+1))/k. The old hardcoded prec = rec = 1.0 gave exactly 1/k instead.
    _p = m["majority_accuracy"]
    _closed = (2 * _p / (_p + 1.0)) / 3.0          # 3 case classes in this toy
    if abs(m["majority_macro_f1"] - _closed) > 1e-9:
        bad.append("majority_macro_f1 %.4f != closed form %.4f (p=%.4f)"
                   % (m["majority_macro_f1"], _closed, _p))
    if m["macro_f1"] >= 0.35:
        bad.append(f"always-GEN macro-F1 should be far below 1/3, got {m['macro_f1']:.3f}")
    # GEN precision = support(GEN)/n: every non-GEN token is a false positive
    want_prec = m["GEN"]["support"] / m["n"]
    if abs(m["GEN"]["precision"] - want_prec) > 1e-9:
        bad.append(f"always-GEN precision should be {want_prec:.3f}, "
                   f"got {m['GEN']['precision']:.3f}")
    # the explanation is COMPUTED, never hardcoded: this repo's recorded failure mode
    # is prose that drifts away from the number it describes.
    print(f"    -> accuracy {m['majority_accuracy']:.3f} vs macro-F1 {m['macro_f1']:.3f}. "
          f"Reporting accuracy alone would")
    print(f"       have made a useless predictor look {m['majority_accuracy']*100:.0f}% right. "
          f"{m['majority_class']} precision collapses to")
    print(f"       {m['GEN']['precision']:.3f} because all {m['n']-m['GEN']['support']} "
          f"non-{m['majority_class']} tokens become false positives.")

    # 2. perfect predictor
    m2 = prf_per_class(gold, gold, names=CASE_NAMES)
    if abs(m2["macro_f1"] - 1.0) > 1e-9:
        bad.append("perfect macro-F1 != 1.0")
    print(f"[2] perfect predictor macro_f1={m2['macro_f1']:.3f} (expect 1.000)")

    # 3. masking: None gold tokens are skipped, not guessed
    m3 = prf_per_class([0, None, 2], [0, 1, 2])
    if m3["n"] != 2:
        bad.append("masked gold was not excluded")
    print(f"[3] masked gold excluded: n={m3['n']} (expect 2)")

    # 4. the shared final-surface metric (A3)
    ex, sk, n = surface_exact_match(["كتاب", "الصادِرِ", None], ["كتاب", "ارصادِرِ", "x"])
    if (ex, sk, n) != (1, 1, 2):
        bad.append(f"surface metric wrong: {(ex, sk, n)}")
    print(f"[4] surface metric exact={ex} skeleton={sk} n={n} (expect 1/1/2)")

    # 5. root classifier — the documented examples. NOTE قوم (q-w-m) IS hollow:
    #    its middle radical is و. It was mislabelled "sound" in this fixture's first
    #    draft, and the classifier was right.
    cases = {"زلزل": "quadriliteral", "وسوس": "quadriliteral", "مدد": "doubled",
             "كتب": "sound", "درس": "sound", "وصل": "assimilated",
             "قول": "hollow", "قوم": "hollow", "يع": "unknown", "رمي": "defective",
             "سأل": "hamza", "#.س.#.س": "quadriliteral", "#.#.#": "unknown"}
    for r, want in cases.items():
        got = root_class(r)
        flag = "" if got == want else "  <-- FAIL"
        if got != want:
            bad.append(f"root_class({r!r}) = {got!r}, want {want!r}")
        print(f"[5] root_class({r!r:12}) = {got:14}{flag}")
    if root_class("ققق") != "doubled":
        bad.append("doubled detection failed")
    print("[6] a fully-unassigned root is not a class: "
          f"root_class('#.#.#') = {root_class('#.#.#')!r} (expect 'unknown')")

    # 7. per-root-class breakdown exposes class bias
    g = ["كتب", "قول", "وصل", "قول"]
    p = ["كتب", None, "وصل", "قوم"]
    rm = root_metrics(g, p)
    print(f"[7] root accuracy {rm['accuracy']:.3f} over {rm['n']} · per-class "
          f"{ {k: round(v['accuracy'], 2) for k, v in rm['per_class'].items()} }")
    if rm["n"] != 4:
        bad.append("root_metrics denominator wrong")

    # 8. ADDITIVE abstention-gate accounting — a small synthetic human-gold slice built
    #    entirely inline (no data/ access, no new files). Every bucket is non-empty and the
    #    exact counts are known by construction, so this test can fail. The gate is built
    #    with an EMPTY homograph table so the answer does not depend on any data artifact.
    print("\n[8] abstention-gate accounting — synthetic human-gold slice")
    _slice_gate = StructuralGate(homographs=set())
    slice_rows = [
        ("في", False),         # structural gate hit, pipeline honoured it  -> structural
        ("هذا", False),        # structural gate hit, pipeline honoured it  -> structural
        ("من", True),          # structural gate hit, pipeline emitted      -> forced
        ("قَدْ", True),         # structural gate hit, pipeline emitted      -> forced
        ("كَتَبَ", False),      # no structural hit; pipeline abstained      -> confidence
        ("مَدْرَسَة", False),   # no structural hit; pipeline abstained      -> confidence
        ("كَتَبَ", True),       # accepted: counted in no bucket
        ("بيت", True),          # accepted: counted in no bucket
    ]
    acc = account_abstention_buckets(slice_rows, gate=_slice_gate)
    print_abstention_account(acc)
    if acc["structural_abstentions"] != 2:
        bad.append(f"structural_abstentions = {acc['structural_abstentions']}, want 2")
    if acc["confidence_abstentions"] != 2:
        bad.append(f"confidence_abstentions = {acc['confidence_abstentions']}, want 2")
    if acc["forced_predictions_after_abstain"] != 2:
        bad.append("forced_predictions_after_abstain = "
                   f"{acc['forced_predictions_after_abstain']}, want 2")
    if acc["human_gold_rows_accounted"] != 6:
        bad.append(f"human_gold_rows_accounted = {acc['human_gold_rows_accounted']}, want 6")
    if (acc["structural_abstentions"] + acc["confidence_abstentions"]
            + acc["forced_predictions_after_abstain"]) != acc["human_gold_rows_accounted"]:
        bad.append("the three abstention buckets do not sum to human_gold_rows_accounted")
    # FALSIFIABILITY: a structural hit must NEVER be downgraded to a confidence abstention
    # or an accepted row when the pipeline emitted anyway — it is the forced bucket.
    _forced = account_abstention_buckets([("من", True)], gate=_slice_gate)
    if (_forced["structural_abstentions"] != 0
            or _forced["confidence_abstentions"] != 0
            or _forced["forced_predictions_after_abstain"] != 1):
        bad.append("a structural hit with an emitted prediction was not kept in the "
                   "forced bucket (a structural abstention must be final)")

    print("\n" + "=" * 84)
    if bad:
        print(f"FAILURES ({len(bad)}):")
        for b in bad:
            print("  -", b)
        return 1
    print("ALL SELF-TESTS PASS — the trap, the masking, the shared metric, the classifier")
    print("=" * 84)
    return 0


# ------------------------------------------------------------- ceiling
def _ud_tokens(path, limit: int):
    """Yield (surface, gold_case:int|None) from a UD conllu, skipping multiwords.

    Every token line is yielded even when the surface is `_` — UD Arabic-NYUAD ships
    FORM-REDACTED, and dropping those rows here is what let a 'ceiling of 0.000' be
    printed over an empty set. Yielding them lets the guard count them and report
    '0 of 84,398 surfaces contain Arabic' instead of the less useful '0 of 0'.
    """
    n = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) < 10 or "-" in c[0] or "." in c[0]:
                continue
            m = re.search(r"(?:^|\|)Case=([^|]+)", c[5])
            raw = m.group(1).strip().lower() if m else None
            yield c[1], (UD_CASE.get(raw) if raw in UD_CASE else None)
            n += 1
            if limit and n >= limit:
                break


def _qac_tokens(path, limit: int):
    """Yield (arabic_surface, gold_root_arabic) from QAC morphology (Buckwalter).

    QAC 0.4's layout is `LOCATION  FORM  TAG  FEATURES` where TAG is the **POS**
    (`N`, `V`, `PRON`, `PN`, `ADJ`...) and the SEGMENT TYPE lives at the head of
    FEATURES (`STEM|POS:N|LEM:...|ROOT:smw|...`). An earlier draft tested
    `"STEM" in c[2]` — i.e. the POS column — and read **0 stems** while reporting a
    confident ceiling of 0.000. Verified against the file: 77,915 STEM segments.
    """
    from reconcile import qac_form_to_arabic, qac_to_arabic
    n = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            c = line.split("\t")
            if len(c) < 4:
                continue
            form, feats = c[1].strip(), c[3]
            if not feats.startswith("STEM"):          # segment type is in FEATURES
                continue
            m = re.search(r"ROOT:([^|]+)", feats)
            if not m:
                continue
            root = qac_to_arabic(m.group(1).strip())
            surf = qac_form_to_arabic(form)           # FORM is VOCALIZED Buckwalter
            if not surf or not re.search(r"[\u0621-\u064a]", surf):
                continue
            yield surf, root
            n += 1
            if limit and n >= limit:
                break


EQTB_CASE = {"NOM": 0, "ACC": 1, "GEN": 2}
# EQTB fills `root_ar` with the placeholder tatweel 'ـ' (and Latin `root` with '_')
# when it has no root. Measured: 19,258 of 30,000 sampled rows = 64%. Non-empty is
# therefore NOT coverage, and treating the placeholder as a gold root manufactured a
# 0.0-accuracy "unknown" class holding 64% of the rows.
PLACEHOLDER_ROOTS = {"\u0640", "_", "-", "\u2014", "\u061c"}


def _real_gold_root(r):
    if not r:
        return None
    s = r.strip()
    if s in PLACEHOLDER_ROOTS:
        return None
    letters = [c for c in s if c not in ". "]
    if len(letters) not in (3, 4):
        return None
    return s


def _eqtb_tokens(path, limit: int):
    """Yield (uthmani_surface, gold_root_arabic|None, gold_case_int|None) from EQTB.

    THE RIGHT SOURCE FOR THE CEILING. Measured on the same 60,000-row sample as
    `inspect_eqtb.py`: **96.7%** of rows carry an Arabic surface (`uthmani_token`),
    **~36%** carry a REAL `root_ar` (the rest hold the placeholder 'ـ'), and
    **22.4%** carry a gold `nominal_case`. Human-annotated, derived from QAC,
    independent of CALIMA, and held out of training — so it can carry both the case
    ceiling and (on the ~36% it is populated for) a root ceiling.

    NYUAD CANNOT carry a ceiling, which is why this exists:
    `ar_nyuad-ud-test.conllu` contains **zero Arabic characters** — every FORM is
    `_` and even `# text = _ _ _ ...` is redacted. See CHALLENGES §2k.
    """
    import csv
    n = 0
    with open(path, encoding="utf-16", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            surf = (row.get("uthmani_token") or "").strip()
            if not surf or not re.search(r"[\u0621-\u064a]", surf):
                continue
            root = _real_gold_root(row.get("root_ar"))
            case = EQTB_CASE.get((row.get("nominal_case") or "").strip().upper())
            yield surf, root, case
            n += 1
            if limit and n >= limit:
                break


def _norm_root(r):
    """Radical sequence only, so CALIMA's 'ش.ر.ب' and EQTB's 'شرب' compare equal."""
    return "".join(c for c in (r or "") if c not in ". ")


def _mle_pass(mle, surfaces, batch=500):
    """Best-analysis dict per surface (None when the analyser produced nothing)."""
    out = []
    for i in range(0, len(surfaces), batch):
        try:
            dis = mle.disambiguate(surfaces[i:i + batch])
        except Exception:
            dis = [None] * len(surfaces[i:i + batch])
        for d in dis:
            out.append(d.analyses[0].analysis if (d and d.analyses) else None)
        if i and (i // batch) % 4 == 0:
            print(f"    analysed {min(i+batch, len(surfaces)):,}/{len(surfaces):,}", flush=True)
    return out


def _guard_surfaces(surfaces, label) -> bool:
    """REFUSE to report a ceiling measured over nothing.

    This guard exists because its absence produced a confident 'ceiling 0.000':
    the NYUAD reader returned zero tokens (every FORM is '_'), and the harness
    printed a full table of zeros as though it had measured something. A ceiling of
    zero over an empty set is not a finding — it is the absence of a measurement,
    and this project has already been burned three times by results that were
    reported before anyone checked they were non-degenerate.
    """
    n_ar = sum(1 for s in surfaces if re.search(r"[\u0621-\u064a]", s or ""))
    if n_ar == 0:
        print("\n" + "!" * 84)
        print(f"REFUSING TO REPORT A CEILING — 0 of {len(surfaces):,} {label} surfaces "
              f"contain Arabic.")
        print("A 'ceiling of 0.000' over an empty set measures NOTHING and must not be")
        print("printed as a result. Measured cause: UD Arabic-NYUAD ships FORM-REDACTED —")
        print("every FORM is '_' and even '# text' is '_'-filled (verified: the whole file")
        print("contains 0 Arabic characters, vs 437,601 in PADT). It therefore CANNOT")
        print("carry a CALIMA-vs-human ceiling, and cannot support the shared")
        print("final-surface metric. Use --source eqtb.")
        print("!" * 84)
        return False
    if n_ar < 200:
        print(f"  WARNING: only {n_ar:,} Arabic surfaces — too few for a stable ceiling.")
    return True


def ceiling(source: str, limit: int) -> int:
    from camel_tools.disambig.mle import MLEDisambiguator
    from reconcile import is_usable_root
    mle = MLEDisambiguator.pretrained("calima-msa-r13")

    print("=" * 84)
    print(f"CALIMA-vs-HUMAN CEILING — source: {source.upper()} (independent treebank)")
    print("=" * 84)
    print("This is the metric's ceiling, required regardless of any model (§5.3 item 3).")
    print("CALIMA silver is DISTILLATION: the treatment learns to imitate the very")
    print("annotator whose agreement with human gold is measured below.\n")

    if source == "nyuad":
        pairs = list(_ud_tokens(require(NYUAD_TEST), limit))
        surfaces = [s for s, _ in pairs]
        print(f"token lines read      : {len(pairs):,}")
        if not _guard_surfaces(surfaces, "NYUAD"):
            return 3
        gold = [g for _, g in pairs]
        ana = _mle_pass(mle, surfaces)
        hyps = [CASE_MAP.get((a or {}).get("cas")) for a in ana]
        scored = [(g, p) for g, p in zip(gold, hyps) if g is not None]
        if len(scored) < 100:
            print(f"REFUSING: only {len(scored)} case-labelled tokens — not enough to")
            print("report a macro-F1 over 3 classes.")
            return 3
        print(f"gold case present     : {len(scored):,}")
        print(f"CALIMA abstained (u/na): {sum(1 for _, p in scored if p is None):,}")
        m = prf_per_class([g for g, _ in scored], [p for _, p in scored],
                          names=CASE_NAMES)
        print_head("HEAD 5 — case: CALIMA vs human (NYUAD, held out)", m)
        print(f"\n  => CEILING for case macro-F1 on NYUAD: {m['macro_f1']:.3f}")
        return 0

    if source == "qac":
        pairs = list(_qac_tokens(require(QAC_TXT), limit))
        surfaces = [s for s, _ in pairs]
        gold = [g for _, g in pairs]
        print(f"stems read            : {len(pairs):,}")
        if not _guard_surfaces(surfaces, "QAC"):
            return 3
        ana = _mle_pass(mle, surfaces)
        hyps = [(a or {}).get("root") if is_usable_root((a or {}).get("root")) else None
                for a in ana]
        print(f"CALIMA gave usable root: {sum(1 for h in hyps if h):,} "
              f"({100*sum(1 for h in hyps if h)/max(len(hyps),1):.1f}%)")
        rm = root_metrics([_norm_root(g) for g in gold],
                          [_norm_root(h) if h else None for h in hyps])
        print_head("HEAD 2 — root: CALIMA vs human (QAC, held out)", rm)
        print(f"\n  => CEILING for root accuracy on QAC: {rm['accuracy']:.3f} overall;")
        print("     the per-class spread is the M1 class bias made explicit.")
        return 0

    if source == "eqtb":
        rows = list(_eqtb_tokens(require(EQTB_CSV), limit))
        surfaces = [r[0] for r in rows]
        g_root = [r[1] for r in rows]
        g_case = [r[2] for r in rows]
        print(f"rows read             : {len(rows):,}   (EQTB: human-annotated, "
              f"independent of CALIMA, held out)")
        if not _guard_surfaces(surfaces, "EQTB"):
            return 3
        ana = _mle_pass(mle, surfaces)

        # ---- HEAD 5: case ceiling
        hyps_c = [CASE_MAP.get((a or {}).get("cas")) for a in ana]
        scored = [(g, p) for g, p in zip(g_case, hyps_c) if g is not None]
        print(f"\ngold case present     : {len(scored):,} "
              f"({100*len(scored)/max(len(rows),1):.1f}% of rows)")
        print(f"CALIMA abstained (u/na): {sum(1 for _, p in scored if p is None):,}")
        if len(scored) >= 100:
            m = prf_per_class([g for g, _ in scored], [p for _, p in scored],
                              names=CASE_NAMES)
            print_head("HEAD 5 — case: CALIMA vs human (EQTB, held out)", m)
            print(f"  => CEILING for case macro-F1: {m['macro_f1']:.3f}")
        else:
            print("  too few gold-case rows for a 3-class macro-F1")

        # ---- HEAD 2: root ceiling
        hyps_r = [(a or {}).get("root") if is_usable_root((a or {}).get("root")) else None
                  for a in ana]
        print(f"\nCALIMA gave usable root: {sum(1 for h in hyps_r if h):,} "
              f"({100*sum(1 for h in hyps_r if h)/max(len(hyps_r),1):.1f}%)")
        rm = root_metrics([_norm_root(g) for g in g_root],
                          [_norm_root(h) if h else None for h in hyps_r])
        print_head("HEAD 2 — root: CALIMA vs human (EQTB, held out)", rm)
        print(f"  => CEILING for root accuracy: {rm['accuracy']:.3f} — and the per-class")
        print("     spread is the M1 class bias made explicit.")
        print("\n  Reminder: the treatment DISTILS CALIMA, so it cannot be expected to")
        print("  beat CALIMA's agreement with human gold. These are ceilings, not targets.")
        return 0

    print(f"unknown source {source!r}; use nyuad | qac | eqtb")
    return 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--ceiling", action="store_true")
    ap.add_argument("--source", default="eqtb", choices=("nyuad", "qac", "eqtb"))
    ap.add_argument("--limit", type=int, default=5000)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.ceiling:
        return ceiling(args.source, args.limit)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
