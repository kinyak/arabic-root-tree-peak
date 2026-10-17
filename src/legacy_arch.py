"""legacy_arch.py — the VENDORED training-era arm. Do not edit; regenerate if ever needed.

PROVENANCE (see EVIDENCE_LOG.md §2cq)
    source : dist/_overwrite_proof/src/model_arms.py
    sha256 : 98b140d8bb7404dc2a1ca0982f0a839ac3d98409fff73d92c356416533a55e9e
    bytes  : 25978
    dated  : 2026-10-13 13:03 (the snapshot taken immediately before the v20 run finished 15:54)

WHY THIS FILE EXISTS
    The v20 checkpoints were trained with the code the cloud copies from the Kaggle DATASET mount
    (`dist/runs/v20/kernel.txt` line 51), NOT from the repo. The repo's `model_arms.py` has since
    grown modules that code never had, so `src/model_arms.py` CANNOT construct a v20 checkpoint at
    all (`KeyError: 'wazan_canonical'`; 19 tensors absent: `char_pos`, `pool_gate`,
    `case_gov_q/k/v`, and the four autosegmental heads). Loading one through it and calling the
    result a measurement produced the "root 13%" family of numbers — which described a FABRICATED
    model, because a randomly-initialised module in the INPUT PATHWAY feeds noise into the trunk.

    Measured: THIS file loads every v20 checkpoint with **0 missing / 0 unexpected** tensors, and
    reproduces the 2026-10-13 recorded figures to the row (root 67/136/159 of 278; TRIPLE 5/18/16
    of 300; resource-OFF 5/14/11 of 300). `src/model_arms.py` is the CURRENT architecture and is
    the right file for anything trained from now on; this one is the right file for reading v20.

    Verified by `src/diagnose_architecture.py --verify-legacy`, which asserts the key diff and
    re-derives the recorded numbers. A vendored-architecture claim that is not re-checked is a
    comment, not a guarantee.
    Regenerate with: python src/build_legacy_arch.py
"""

# ----------------------------------------------------------------------------
# VENDORED SOURCE DOCSTRING (kept as comments so `__future__` stays first)
# ----------------------------------------------------------------------------
# model_arms.py — the two arms, the shared data pipeline, and the PARITY CHECK.
# 
# THE ONE ARCHITECTURAL DIFFERENCE (SPEC-REV6 §5.2 / A13)
#     Both arms read `config/shared.yaml`. Both share the identical trunk and the
#     identical five heads (root 4-slot, wazān, case, syntax, next-lemma).
#         baseline   = trunk -> five heads (auxiliary)  +  surface LM head (primary)
#         treatment  = trunk -> five heads (PRIMARY)
#     The baseline generates surface; the treatment generates through the
#     grammatical representation and would spell the surface with a renderer. That
#     is the whole claim, and every other difference is removed so the comparison
#     measures architecture rather than supervision density.
# 
# WHY PARITY IS COMPUTED, NOT ASSERTED
#     A13 says the baseline must get the same heads. That is necessary but not
#     sufficient: removing the baseline's |V| x d surface head would silently make
#     the treatment the SMALLER model, so "same size" would be false in the other
#     direction. `parity_report()` computes both totals from the SAME config, and
#     `fit_treatment_tower()` solves for the treatment's tower width that closes the
#     gap — the treatment spends its parameter budget on the grammatical pathway
#     instead of a surface lookup table. That is a real architectural statement, and
#     it is checkable: `python src/model_arms.py --parity`.
# 
#     The renderer (R1) does not exist, so the treatment has no surface output yet.
#     Nothing here fabricates one: `surface_logits()` on a treatment arm returns
#     None and says why.
# ----------------------------------------------------------------------------
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import torch
import torch.nn as nn

from paths import ROOT
from wazan_normalizer import tail_strip

IGNORE = -100


# ------------------------------------------------------------------ config
def load_config(smoke: bool = False, path: str | None = None) -> dict:
    import yaml
    p = Path(path) if path else ROOT / "config" / "shared.yaml"
    with open(p, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if smoke:
        cfg["model"].update({k: v for k, v in cfg["smoke"].items()
                             if k in ("d_model", "n_layers", "n_heads", "d_ff")})
        cfg["data"]["max_len"] = cfg["smoke"]["max_len"]
        cfg["training"]["batch_size"] = cfg["smoke"]["batch_size"]
        cfg["training"]["steps"] = cfg["smoke"]["steps"]
        cfg["training"]["eval_every"] = cfg["smoke"]["eval_every"]
        cfg["data"]["limit_train"] = cfg["smoke"]["limit_train"]
        cfg["data"]["limit_dev"] = cfg["smoke"]["limit_dev"]
        cfg["seeds"] = cfg["seeds"][:1]
    return cfg


def resolve_device(cfg) -> torch.device:
    """Never hardcode the device, and never silently train on CPU (COLAB.md §6)."""
    want = cfg["training"].get("device", "auto")
    if want == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dev = torch.device(want)
    if dev.type == "cuda" and not torch.cuda.is_available():
        raise SystemExit("config asks for cuda but torch.cuda.is_available() is False — "
                         "refusing to silently train on CPU")
    return dev


# ------------------------------------------------------------------- data
def read_records(path, limit=None):
    """Group the JSONL into sentences: {si: [record, ...]}, in order."""
    sents = {}
    n = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            sents.setdefault(r["si"], []).append(r)
            n += 1
            if limit and n >= limit:
                break
    return [(si, sents[si]) for si in sorted(sents)]


class Vocabs:
    """Every vocabulary, built from the DATA — never assumed."""

    def __init__(self, sents, min_freq=2, max_vocab=20000):
        from collections import Counter
        forms = Counter()
        chars = set()
        rads, wazans, lemmas = set(), set(), set()
        max_deprel = max_upos = 0
        for _, toks in sents:
            for t in toks:
                forms[t["form_bare"]] += 1
                # v12: collect all characters for character-level encoding
                for c in t["form_bare"]:
                    chars.add(c)
                for s in t["t_root"]:
                    if s:
                        rads.add(s)
                # HEAD-3 TARGET SPACE (§2bw/§2bx): SUPERVISED labels only, tail-stripped. Adding every label in
                # the field is what seated 511 never-supervised classes (24.8% of it) in the softmax as dead
                # rows — 46% of the old 6,633-class head received no gradient at all — and the raw label carried
                # the inflectional tail (`123َة`, `1ا2َ3ْت`) that smeared probability across affix chunks. The
                # class is `tail_strip(...)`, defined ONCE in wazan_normalizer and used by the data build, the
                # vocabulary and the target builder alike, so the three cannot disagree about what a class is.
                if t["m_wazan"]:
                    cls = tail_strip(t["t_wazan"])
                    if cls:
                        wazans.add(cls)
                if t["t_ntp"] is not None:
                    lemmas.add(t["t_ntp"])
                max_deprel = max(max_deprel, t["deprel"] + 1)
                max_upos = max(max_upos, t["upos"] + 1)

        self.form = {"<pad>": 0, "<unk>": 1}
        for f, c in forms.most_common():
            if len(self.form) >= max_vocab:
                break
            if c >= min_freq:
                self.form[f] = len(self.form)
        # v12: character vocabulary (no frequency cutoff — all chars matter)
        self.char = {"<pad>": 0} | {c: i + 1 for i, c in enumerate(sorted(chars))}
        self.radical = {"<pad>": 0} | {r: i + 1 for i, r in enumerate(sorted(rads))}
        self.wazan = {"<pad>": 0} | {w: i + 1 for i, w in enumerate(sorted(wazans))}
        self.lemma_size = (max(lemmas) + 1) if lemmas else 1
        self.deprel_size = max(max_deprel, 1)
        self.upos_size = max(max_upos, 1)

    def sizes(self):
        return {"surface": len(self.form), "char": len(self.char),
                "radical": len(self.radical),
                "wazan": len(self.wazan), "lemma": self.lemma_size,
                "deprel": self.deprel_size, "upos": self.upos_size, "case": 3}

    def to_dict(self):
        """Plain-dict form, for storing INSIDE a checkpoint.

        A checkpoint whose vocabulary is not stored with it cannot be scored later.
        That is not hypothetical: the round-17 ablation checkpoint had to be abandoned
        because the cloud's records were not the local ones, so its un-stored vocab
        could not be rebuilt (measured size gap: surface 13,143 vs 16,503). Row 300 of
        the ablation is un-reproducible for exactly this reason.
        """
        return {"form": self.form, "char": self.char, "radical": self.radical,
                "wazan": self.wazan,
                "lemma_size": self.lemma_size, "deprel_size": self.deprel_size,
                "upos_size": self.upos_size}

    @classmethod
    def from_dict(cls, d):
        """Rebuild from `to_dict()`. Avoids __init__ (which would need the sentences)."""
        v = cls.__new__(cls)
        v.form, v.char, v.radical, v.wazan = d["form"], d.get("char", {"<pad>": 0}), d["radical"], d["wazan"]
        v.lemma_size = d["lemma_size"]
        v.deprel_size = d["deprel_size"]
        v.upos_size = d["upos_size"]
        return v

    def encode(self, s):
        return self.form.get(s, 1)


def make_batch(sents, v: Vocabs, max_len: int, batch_sentences: int):
    """Yield (x, x_char, targets). Sequences are chunked at max_len; every head carries its own
    mask, and a masked position is written as IGNORE so it contributes exactly zero.

    v12: now also yields x_char — character indices for each token, padded to max_char_len.

    Targets are built ROW-WISE, one list per row, because `_stack` pads per row. An
    earlier draft accumulated them flat across chunks and then tried to view the flat
    list as (batch, max_len) — which raised on the first ragged batch.
    """
    rows_x, rows_x_char, rows_t = [], [], []
    max_char_len = 20  # v12: max characters per token (Arabic words rarely exceed 15)

    def encode_chars(form_bare):
        """Encode a token's characters, pad/truncate to max_char_len."""
        chars = [v.char.get(c, 0) for c in form_bare[:max_char_len]]
        chars += [0] * (max_char_len - len(chars))  # pad with <pad>
        return chars

    def row_targets(win):
        row = {"root": [], "m_root": [], "wazan": [], "m_wazan": [],
               "case": [], "m_case": [], "deprel": [], "m_syn": [],
               "ntp": [], "m_ntp": [], "next_surface": [], "m_surface": []}
        for j, t in enumerate(win):
            if t["m_root"]:
                # PRONG 2 (CHALLENGES.md 2x.14). An EMPTY slot in a root-supervised token is
                # <pad> = 0, NOT ignore_index. Trained as IGNORE, slot 4 received no gradient on
                # 97,294 of the 99,869 lettered PADT roots (97.4%), so its argmax was unconstrained
                # noise; every triliteral root then decoded to length 4, and the renderer rejected all
                # of them (296/296 root_len_mismatch, root accuracy 0/278). Supervising the empty slot
                # as <pad> teaches the model root ARITY end-to-end, which makes the inference-time arity
                # slice in final_surface.decode_root_slots belt-and-braces instead of load-bearing.
                # A fully UNSUPERVISED token still takes the [IGNORE] * 4 branch below.
                row["root"].append([v.radical.get(s, IGNORE) if s else v.radical["<pad>"]
                                    for s in t["t_root"]])
            else:
                row["root"].append([IGNORE] * 4)
            row["m_root"].append(t["m_root"])
            # The target must be the SAME class the vocabulary was built from, or a SUPERVISED token silently
            # turns into IGNORE — an UNK by another name, and the exact failure this change exists to remove.
            # `tools/wazan_target_probe.py --check` asserts there is no such token.
            row["wazan"].append(v.wazan.get(tail_strip(t["t_wazan"]), IGNORE)
                                if t["m_wazan"] else IGNORE)
            row["m_wazan"].append(t["m_wazan"])
            row["case"].append(t["t_case"] if t["m_case"] else IGNORE)
            row["m_case"].append(t["m_case"])
            # THE SYNTAX HEAD MUST HONOUR ITS MASK. It used to be appended raw with
            # the comment "100% supervised" — true for PADT, FALSE for Tashkeela, which
            # has no dependency annotation at all. Unmasked, a silver-trained model
            # would have been taught to predict dependency class 0 for every token and
            # scored as if supervised. Tashkeela records carry m_syn = 0.
            row["deprel"].append(t["deprel"] if t.get("m_syn", 1) else IGNORE)
            row["m_syn"].append(t["m_syn"])
            row["ntp"].append(t["t_ntp"] if t["t_ntp"] is not None else IGNORE)
            row["m_ntp"].append(t["m_ntp"])
            has_next = j + 1 < len(win)
            row["next_surface"].append(v.encode(win[j + 1]["form_bare"])
                                       if has_next else IGNORE)
            row["m_surface"].append(1 if has_next else 0)
        return row

    for _, toks in sents:
        for i in range(0, len(toks), max_len):
            win = toks[i:i + max_len]
            if len(win) < 2:
                continue
            rows_x.append([v.encode(t["form_bare"]) for t in win])
            rows_x_char.append([encode_chars(t["form_bare"]) for t in win])
            rows_t.append(row_targets(win))
            if len(rows_x) >= batch_sentences:
                yield _stack(rows_x, rows_x_char, rows_t, max_char_len)
                rows_x, rows_x_char, rows_t = [], [], []
    if rows_x:
        yield _stack(rows_x, rows_x_char, rows_t, max_char_len)


# per-key padding: targets pad with IGNORE (so padding is never a target), masks with 0
_FILL = {"m_root": 0, "m_wazan": 0, "m_case": 0, "m_syn": 0, "m_ntp": 0,
         "m_surface": 0}


def _stack(rows_x, rows_x_char, rows_t, max_char_len):
    """v12: now stacks x_char (B, L, max_char_len) alongside x and targets."""
    L = max(len(r) for r in rows_x)
    x = torch.tensor([r + [0] * (L - len(r)) for r in rows_x])
    # v12: character tensor (B, L, max_char_len)
    x_char = torch.tensor([r + [[0] * max_char_len] * (L - len(r)) for r in rows_x_char])
    out = {}
    for k in rows_t[0]:                      # k is a TARGET KEY, not a row
        fill = _FILL.get(k, IGNORE)
        padded = []
        for row in rows_t:
            if k == "root":
                # slot axis FIRST (each token -> exactly 4 slots), then sequence axis
                vals = [s + [IGNORE] * (4 - len(s)) for s in row[k]]
                vals = vals + [[IGNORE] * 4] * (L - len(vals))
            else:
                vals = list(row[k])
                vals = vals + [fill] * (L - len(vals))
            padded.append(vals)
        out[k] = torch.tensor(padded)
    return x, x_char, out


# ------------------------------------------------------------------ model
class CharEncoder(nn.Module):
    """v12: character-level CNN encoder for Arabic tokens.

    WHY THIS EXISTS
        Word-level embeddings map OOV tokens to <unk>, so the model has no morphological
        signal for unseen words. Arabic morphology is compositional — the surface form
        contains the literal consonants of the root interspersed with augmentative letters
        (hurūf al-ziyādah). A character-level representation allows the model to see the
        consonantal skeleton directly, preventing OOV tokens from mapping to an
        uninformative unigram vector.

    ARCHITECTURE
        - Character embedding table (n_chars, char_dim)
        - Multi-kernel 1D CNN (kernel sizes 3, 5, 7) to capture n-gram patterns
        - Max-pool over sequence length to get fixed-size vector per token
        - Output: (B, L, char_out_dim) where char_out_dim = n_kernels * n_filters
    """

    def __init__(self, n_chars, char_dim=32, n_filters=32, max_char_len=20):
        super().__init__()
        self.char_emb = nn.Embedding(n_chars, char_dim, padding_idx=0)
        # Multi-kernel CNN: captures 3-gram, 5-gram, 7-gram character patterns
        self.conv3 = nn.Conv1d(char_dim, n_filters, kernel_size=3, padding=1)
        self.conv5 = nn.Conv1d(char_dim, n_filters, kernel_size=5, padding=2)
        self.conv7 = nn.Conv1d(char_dim, n_filters, kernel_size=7, padding=3)
        self.out_dim = n_filters * 3  # concatenated across kernels
        self.max_char_len = max_char_len

    def forward(self, x_char):
        """x_char: (B, L, max_char_len) -> (B, L, out_dim)"""
        B, L, C = x_char.shape
        # Flatten batch and sequence dimensions for CNN
        x = x_char.view(B * L, C)  # (B*L, C)
        x = self.char_emb(x)  # (B*L, C, char_dim)
        x = x.transpose(1, 2)  # (B*L, char_dim, C) for Conv1d

        # Apply multi-kernel CNNs
        c3 = torch.relu(self.conv3(x))  # (B*L, n_filters, C)
        c5 = torch.relu(self.conv5(x))
        c7 = torch.relu(self.conv7(x))

        # Max-pool over character dimension
        c3 = c3.max(dim=2)[0]  # (B*L, n_filters)
        c5 = c5.max(dim=2)[0]
        c7 = c7.max(dim=2)[0]

        # Concatenate and reshape back to (B, L, out_dim)
        out = torch.cat([c3, c5, c7], dim=1)  # (B*L, out_dim)
        return out.view(B, L, self.out_dim)


class Tower(nn.Module):
    def __init__(self, d_model, hidden):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(d_model, hidden), nn.GELU(),
                                 nn.Linear(hidden, d_model), nn.LayerNorm(d_model))

    def forward(self, h):
        return h + self.net(h)


class Arm(nn.Module):
    """One arm. `kind` is 'baseline' or 'treatment' — the ONLY difference.
    
    v12: now includes character-level encoding to handle OOV tokens.
    """

    def __init__(self, cfg, sizes, kind):
        super().__init__()
        assert kind in ("baseline", "treatment")
        self.kind = kind
        m = cfg["model"]
        self.d = m["d_model"]
        self.emb = nn.Embedding(sizes["surface"], self.d, padding_idx=0)
        self.pos = nn.Embedding(cfg["data"]["max_len"], self.d)
        
        # v12: character encoder for OOV handling
        self.use_char_encoder = m.get("use_char_encoder", True)
        if self.use_char_encoder:
            char_out_dim = 96  # 3 kernels * 32 filters
            self.char_encoder = CharEncoder(sizes["char"], char_dim=32, n_filters=32)
            # Project character features to d_model
            self.char_proj = nn.Linear(char_out_dim, self.d)
        
        layer = nn.TransformerEncoderLayer(
            self.d, m["n_heads"], m["d_ff"], m["dropout"], batch_first=True,
            norm_first=True)
        self.trunk = nn.TransformerEncoder(layer, m["n_layers"])
        tower_hidden = m["treatment_tower_hidden"] if kind == "treatment" \
            else m["baseline_tower_hidden"]
        self.tower = Tower(self.d, tower_hidden) if tower_hidden else None
        # ---- the SAME five heads for both arms (A13) --------------------------
        h = cfg["heads"]
        # Root is a 4-SLOT head (SPEC-REV6 §4: quadriliterals need a 4th radical),
        # so this emits 4 x |radicals| and is reshaped to (B, L, 4, V). A single
        # Linear(d, V) would silently collapse it to one distribution per position —
        # which is what the shape error in the smoke test caught.
        self.n_root_slots = h["root"]["n_slots"]
        self.h_root = nn.Linear(self.d, self.n_root_slots * sizes["radical"])
        # ---- SOFT WAZAN -> ROOT CONDITIONING (v12 Phase 2) --------------------
        # TRAP 1 IT AVOIDS — the error cascade. The conditioned arm must NEVER see a discrete
        # argmax wazan: the head is only ~55% in-domain and ~27% OOD, so a hard template injects
        # a FALSE structural prior on every misclassification, and the root decoder then slices
        # radicals from the wrong positions. Teacher forcing makes it worse (the root head learns
        # to rely on a gold wazan it will never have at inference). So the conditioning is the
        # DENSE PRE-CLASSIFIER BOTTLENECK: continuous, carries the head's own uncertainty, and
        # IDENTICAL in training and inference — there is nothing to force, so nothing to mismatch.
        #
        # TRAP 2 IT AVOIDS — parity. The conditioning lives in BOTH arms, exactly as the character
        # encoder does, so the parameter delta between arms is unchanged BY CONSTRUCTION and no
        # compensating capacity has to be bolted onto the baseline. The arm difference stays the
        # one thing the ablation is about (surface head vs grammatical pathway), and
        # parity_report asserts it before training.
        self.cond_on_wazan = bool(m.get("use_soft_wazan_conditioning", False))
        if self.cond_on_wazan:
            w_h = int(m.get("wazan_bottleneck", 128))
            self.h_wazan_bottleneck = nn.Linear(self.d, w_h)
            self.h_wazan = nn.Linear(w_h, sizes["wazan"])
            self.wazan_to_root = nn.Linear(w_h, self.d)      # dense prior, no argmax
        else:
            self.h_wazan = nn.Linear(self.d, sizes["wazan"])
        self.h_case = nn.Linear(self.d, h["case"]["n_classes"])
        self.h_syntax = nn.Linear(self.d, sizes["deprel"])
        self.h_ntp = nn.Linear(self.d, sizes["lemma"])
        # ---- the decoder difference ------------------------------------------
        self.h_surface = nn.Linear(self.d, sizes["surface"]) if kind == "baseline" else None

    def encode(self, x, x_char=None):
        """v12: now accepts x_char for character-level encoding."""
        B, L = x.shape
        pos = torch.arange(L, device=x.device).unsqueeze(0)
        h = self.emb(x) + self.pos(pos)
        
        # v12: add character features if available
        if self.use_char_encoder and x_char is not None:
            char_feat = self.char_encoder(x_char)  # (B, L, char_out_dim)
            char_feat = self.char_proj(char_feat)  # (B, L, d_model)
            h = h + char_feat
        
        mask = torch.triu(torch.ones(L, L, device=x.device), diagonal=1).bool()
        h = self.trunk(h, mask=mask)
        return self.tower(h) if self.tower else h

    def forward(self, x, x_char=None):
        """v12: now accepts x_char for character-level encoding."""
        h = self.encode(x, x_char)
        B, L, _ = h.shape
        if self.cond_on_wazan:
            # dense bottleneck -> wazan logits; the SAME dense vector conditions the root head.
            # No argmax, no teacher forcing: the prior is the model's own soft structural belief,
            # so a high-entropy wazan (Form I vs IV) reaches the root head as ambiguity rather
            # than as a confident wrong template.
            wh = torch.relu(self.h_wazan_bottleneck(h))
            wazan = self.h_wazan(wh)
            h_root_in = h + self.wazan_to_root(wh)     # residual: h is biased, never replaced
        else:
            wazan = self.h_wazan(h)
            h_root_in = h
        root = self.h_root(h_root_in).view(B, L, self.n_root_slots, -1)
        # Head 4 is named `syntax` everywhere (config, loss, reports) — its TARGET
        # comes from the data field `deprel`. Two names for one head is how a weight
        # silently fails to apply, so the mapping lives in one place (train.HEAD_SPEC).
        return {"root": root, "wazan": wazan,
                "case": self.h_case(h), "syntax": self.h_syntax(h),
                "ntp": self.h_ntp(h),
                "surface": self.h_surface(h) if self.h_surface is not None else None}


def count_params(model) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def parity_report(cfg, sizes, verbose=True):
    """Both arms from the SAME config. Returns (n_base, n_treat, rel_gap)."""
    base = count_params(Arm(cfg, sizes, "baseline"))
    treat = count_params(Arm(cfg, sizes, "treatment"))
    gap = abs(base - treat) / max(base, treat)
    if verbose:
        print(f"  baseline  : {base:>10,} params")
        print(f"  treatment : {treat:>10,} params")
        print(f"  gap       : {gap*100:6.2f}%   (tolerance "
              f"{cfg['parity']['tolerance']*100:.1f}%)")
    return base, treat, gap


def fit_treatment_tower(cfg, sizes, lo=8, hi=8192):
    """Solve for the treatment tower width that closes the parity gap.

    Two passes: a coarse stride, then a unit-step refinement around the best coarse
    width. The single coarse pass stalled at a 3.34% gap on the smoke-scale model —
    a stride of ~20 cannot land on an exact match when the per-unit parameter cost is
    small — and that showed up as a smoke-test failure rather than as a silently
    unmatched pair of arms.

    Reports the result rather than hiding it: whatever width is chosen becomes a
    number in the config, so a reader can check that the two arms really match.
    """
    import copy
    base, _, _ = parity_report(cfg, sizes, verbose=False)
    step = max(1, (hi - lo) // 200)
    best, best_gap = None, 1e9
    for hidden in range(lo, hi + 1, step):
        c = copy.deepcopy(cfg)
        c["model"]["treatment_tower_hidden"] = hidden
        _, treat, _ = parity_report(c, sizes, verbose=False)
        gap = abs(base - treat) / base
        if gap < best_gap:
            best, best_gap = hidden, gap
    # refinement: unit steps around the coarse winner
    for hidden in range(max(lo, best - step), min(hi, best + step) + 1):
        c = copy.deepcopy(cfg)
        c["model"]["treatment_tower_hidden"] = hidden
        _, treat, _ = parity_report(c, sizes, verbose=False)
        gap = abs(base - treat) / base
        if gap < best_gap:
            best, best_gap = hidden, gap
    return best, best_gap


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parity", action="store_true", help="compare both arms")
    ap.add_argument("--fit-parity", action="store_true", help="solve the tower width")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    cfg = load_config(smoke=args.smoke)
    sents = read_records(ROOT / cfg["paths"]["train"], cfg["data"]["limit_train"])
    v = Vocabs(sents, cfg["data"]["min_freq"], cfg["data"]["max_vocab"])
    sizes = v.sizes()
    print("=" * 78)
    print("PARITY — both arms built from config/shared.yaml")
    print("=" * 78)
    print(f"  vocab sizes: {sizes}")
    print(f"  records: {sum(len(t) for _, t in sents):,} in {len(sents):,} sentences")
    print()
    base, treat, gap = parity_report(cfg, sizes)
    if args.fit_parity:
        hidden, g = fit_treatment_tower(cfg, sizes)
        print(f"\n  fitted treatment_tower_hidden = {hidden}  (gap {g*100:.3f}%)")
        print("  -> put that number in config/shared.yaml; both arms then read the")
        print("     same file and match, which is what §5.2 requires.")
        # Re-report WITH the fitted width, so the verdict below is about the config
        # that will actually be used — not the pre-fit one.
        import copy
        c2 = copy.deepcopy(cfg)
        c2["model"]["treatment_tower_hidden"] = hidden
        print("\n  after fitting:")
        base, treat, gap = parity_report(c2, sizes)
    ok = gap <= cfg["parity"]["tolerance"]
    print(f"\n  PARITY {'OK' if ok else 'FAIL'} "
          f"(tolerance {cfg['parity']['tolerance']*100:.1f}%)")
    if not ok and not args.fit_parity:
        print("  Run with --fit-parity and write the result into the config.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
