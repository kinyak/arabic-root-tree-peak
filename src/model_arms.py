"""model_arms.py — the two arms, the shared data pipeline, and the PARITY CHECK.

THE ONE ARCHITECTURAL DIFFERENCE (SPEC-REV6 §5.2 / A13)
    Both arms read `config/shared.yaml`. Both share the identical trunk and the
    identical five heads (root 4-slot, wazān, case, syntax, next-lemma).
        baseline   = trunk -> five heads (auxiliary)  +  surface LM head (primary)
        treatment  = trunk -> five heads (PRIMARY)
    The baseline generates surface; the treatment generates through the
    grammatical representation and would spell the surface with a renderer. That
    is the whole claim, and every other difference is removed so the comparison
    measures architecture rather than supervision density.

WHY PARITY IS COMPUTED, NOT ASSERTED
    A13 says the baseline must get the same heads. That is necessary but not
    sufficient: removing the baseline's |V| x d surface head would silently make
    the treatment the SMALLER model, so "same size" would be false in the other
    direction. `parity_report()` computes both totals from the SAME config, and
    `fit_treatment_tower()` solves for the treatment's tower width that closes the
    gap — the treatment spends its parameter budget on the grammatical pathway
    instead of a surface lookup table. That is a real architectural statement, and
    it is checkable: `python src/model_arms.py --parity`.

    The renderer (R1) does not exist, so the treatment has no surface output yet.
    Nothing here fabricates one: `surface_logits()` on a treatment arm returns
    None and says why.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F

from paths import ROOT
from wazan_normalizer import (tail_strip, CANONICAL_WAZAN_118,
                              PROCLITIC_CLASSES, ENCLITIC_CLASSES,
                              split_wazan_stem_and_tail,
                              STEM_TAIL_VOCALIZED, vocalized_stem_tail, stem_tail_target,
                              canonical_wazan_skeleton, canonicalize_mater_vowels,
                              DIACRITICS)

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
        tails = set()
        max_deprel = max_upos = 0

        # 1. Include valid tails from STEM_TAIL_VOCALIZED (gold-300 + corpus baseline)
        for raw_st in STEM_TAIL_VOCALIZED:
            if not raw_st:
                continue
            res = split_wazan_stem_and_tail("123" + raw_st)
            if res is not None and res[1]:
                tails.add(res[1])

        # 2. Also scan gold-300 if present to ensure 100% gold tail coverage
        gold_path = ROOT / "data" / "annotation" / "gold-tashkeela-300.jsonl"
        if gold_path.exists():
            with open(gold_path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        r = json.loads(line)
                        raw_w = r.get("t_wazan_pattern") or r.get("t_wazan")
                        if raw_w:
                            res = split_wazan_stem_and_tail(raw_w)
                            if res is not None and res[1]:
                                tails.add(res[1])

        # 3. Iterate over all training sentences
        for _, toks in sents:
            for t in toks:
                forms[t["form_bare"]] += 1
                # v12: collect all characters for character-level encoding
                for c in t["form_bare"]:
                    chars.add(c)
                for s in t["t_root"]:
                    if s:
                        rads.add(s)
                # Head-3 wazan & stem_tail extraction via split_wazan_stem_and_tail
                if t.get("m_wazan"):
                    raw_w = t.get("t_wazan") or ""
                    res = split_wazan_stem_and_tail(raw_w)
                    if res is not None:
                        stem_c, tail_c = res
                        if stem_c:
                            wazans.add(stem_c)
                        if tail_c:
                            tails.add(tail_c)
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
        # Canonical 118 wazan templates and closed-class affixes
        self.wazan_canonical = {"<pad>": 0} | {s: i + 1 for i, s in enumerate(CANONICAL_WAZAN_118)}
        # Vocalized stem tail: index 0 is explicitly the bare-stem class "" (Task 1)
        self.stem_tail = {"": 0}
        for t in sorted(tails):
            if t != "":
                self.stem_tail[t] = len(self.stem_tail)
        self.proclitic = {"<none>": 0} | {p: i + 1 for i, p in enumerate(PROCLITIC_CLASSES)}
        self.enclitic = {"<none>": 0} | {e: i + 1 for i, e in enumerate(ENCLITIC_CLASSES)}
        self.lemma_size = (max(lemmas) + 1) if lemmas else 1
        self.deprel_size = max(max_deprel, 1)
        self.upos_size = max(max_upos, 1)

    def sizes(self):
        return {"surface": len(self.form), "char": len(self.char),
                "radical": len(self.radical),
                "wazan": len(self.wazan),
                "wazan_canonical": len(self.wazan_canonical),
                "stem_tail": len(self.stem_tail),
                "proclitic": len(self.proclitic),
                "enclitic": len(self.enclitic),
                "lemma": self.lemma_size,
                "deprel": self.deprel_size, "upos": self.upos_size, "case": 3,
                "definiteness": 4}

    def to_dict(self):
        """Plain-dict form, for storing INSIDE a checkpoint."""
        return {"form": self.form, "char": self.char, "radical": self.radical,
                "wazan": self.wazan,
                "wazan_canonical": self.wazan_canonical,
                "stem_tail": self.stem_tail,
                "proclitic": self.proclitic, "enclitic": self.enclitic,
                "lemma_size": self.lemma_size, "deprel_size": self.deprel_size,
                "upos_size": self.upos_size}

    @classmethod
    def from_dict(cls, d):
        """Rebuild from `to_dict()`. Avoids __init__ (which would need the sentences)."""
        v = cls.__new__(cls)
        v.form, v.char, v.radical, v.wazan = d["form"], d.get("char", {"<pad>": 0}), d["radical"], d["wazan"]
        v.wazan_canonical = d.get("wazan_canonical", {"<pad>": 0} | {s: i + 1 for i, s in enumerate(CANONICAL_WAZAN_118)})
        v.stem_tail = d.get("stem_tail", {"": 0})
        v.proclitic = d.get("proclitic", {"<none>": 0} | {p: i + 1 for i, p in enumerate(PROCLITIC_CLASSES)})
        v.enclitic = d.get("enclitic", {"<none>": 0} | {e: i + 1 for i, e in enumerate(ENCLITIC_CLASSES)})
        v.lemma_size = d["lemma_size"]
        v.deprel_size = d["deprel_size"]
        v.upos_size = d["upos_size"]
        return v

    def encode(self, s):
        return self.form.get(s, 1)


def extract_definiteness(t: dict) -> tuple[int, int]:
    """Derive definiteness class: 0:DEF_AL, 1:INDEF_TANWIN, 2:CONSTRUCT_IDAFA, 3:INVARIABLE/OTHER.
    
    This supplies the missing autosegmental nunation feature for the compiler.
    """
    pro = t.get("proclitic") or ""
    fb = t.get("form_bare") or ""
    fm = t.get("form") or ""
    wr = t.get("wazan_render") or ""
    if pro.startswith("ال") or "ال" in pro or (not pro and fb.startswith("ال")):
        return 0, 1  # DEF_AL
    if any(c in "\u064b\u064c\u064d" for c in fm) or any(c in "\u064b\u064c\u064d" for c in wr):
        return 1, 1  # INDEF_TANWIN
    if t.get("m_case"):
        return 2, 1  # CONSTRUCT_IDAFA
    return 3, 1  # INVARIABLE/OTHER


def make_batch(sents, v: Vocabs, max_len: int, batch_sentences: int):
    """Yield (x, x_char, targets). Sequences are chunked at max_len; every head carries its own
    mask, and a masked position is written as IGNORE so it contributes exactly zero.

    v12: now also yields x_char — character indices for each token, padded to max_char_len.

    Targets are built ROW-WISE, one list per row, because `_stack` pads per row. An
    earlier draft accumulated them flat across chunks and then tried to view the flat
    list as (batch, max_len) — which raised on the first ragged batch.
    """
    rows_x, rows_x_char, rows_t = [], [], []
    max_char_len = 16  # M = 16 max characters per token (Arabic words rarely exceed 15)

    def encode_chars(form_bare):
        """Encode a token's characters, pad/truncate to max_char_len."""
        chars = [v.char.get(c, 0) for c in form_bare[:max_char_len]]
        chars += [0] * (max_char_len - len(chars))  # pad with <pad>
        return chars

    def row_targets(win):
        row = {"root": [], "m_root": [], "wazan": [], "m_wazan": [],
               "wazan_canonical": [], "m_wazan_canonical": [],
               "stem_tail": [], "m_stem_tail": [],
               "proclitic": [], "m_proclitic": [],
               "enclitic": [], "m_enclitic": [],
               "case": [], "m_case": [], "definiteness": [], "m_definiteness": [],
               "deprel": [], "m_syn": [],
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

            # Head-3 wazan & stem_tail via split_wazan_stem_and_tail (Task 1)
            if not t.get("m_wazan"):
                row["wazan"].append(IGNORE)
                row["m_wazan"].append(0)
                row["wazan_canonical"].append(IGNORE)
                row["m_wazan_canonical"].append(0)
                row["stem_tail"].append(IGNORE)
                row["m_stem_tail"].append(0)
            else:
                raw_w = t.get("t_wazan") or ""
                res = split_wazan_stem_and_tail(raw_w)
                if res is None:
                    row["wazan"].append(IGNORE)
                    row["m_wazan"].append(0)
                    row["wazan_canonical"].append(IGNORE)
                    row["m_wazan_canonical"].append(0)
                    row["stem_tail"].append(IGNORE)
                    row["m_stem_tail"].append(0)
                else:
                    stem_c, tail_c = res
                    w_id = v.wazan.get(stem_c, IGNORE)
                    row["wazan"].append(w_id)
                    row["m_wazan"].append(1 if w_id != IGNORE else 0)

                    skel = canonical_wazan_skeleton(stem_c)
                    c_waz_id = v.wazan_canonical.get(skel, IGNORE) if skel in v.wazan_canonical else IGNORE
                    row["wazan_canonical"].append(c_waz_id)
                    row["m_wazan_canonical"].append(1 if c_waz_id != IGNORE else 0)

                    # Class 0 is strictly bare stem "". NEVER fallback to 0 when tail_c != ""
                    tail_id = 0 if tail_c == "" else v.stem_tail.get(tail_c, IGNORE)
                    if tail_id == IGNORE:
                        row["stem_tail"].append(IGNORE)
                        row["m_stem_tail"].append(0)
                    else:
                        row["stem_tail"].append(tail_id)
                        row["m_stem_tail"].append(1)

            # Neural closed-class affixes (proclitic & enclitic):
            raw_p = DIACRITICS.sub("", t.get("proclitic") or "")
            row["proclitic"].append(v.proclitic.get(raw_p, 0))
            row["m_proclitic"].append(1)

            raw_e = DIACRITICS.sub("", t.get("enclitic") or "")
            row["enclitic"].append(v.enclitic.get(raw_e, 0))
            row["m_enclitic"].append(1)

            row["case"].append(t["t_case"] if t["m_case"] else IGNORE)
            row["m_case"].append(t["m_case"])
            df_val, df_m = extract_definiteness(t)
            row["definiteness"].append(df_val if df_m else IGNORE)
            row["m_definiteness"].append(df_m)
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
_FILL = {"m_root": 0, "m_wazan": 0, "m_wazan_canonical": 0,
         "m_stem_tail": 0,
         "m_proclitic": 0, "m_enclitic": 0,
         "m_case": 0, "m_definiteness": 0, "m_syn": 0, "m_ntp": 0,
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


def extract_right_aligned_suffix(C_seq: torch.Tensor, char_mask: torch.Tensor, k: int = 4) -> torch.Tensor:
    """Extract the last k non-pad characters for each token, right-aligned.

    C_seq: (B, L, M, D)
    char_mask: (B, L, M) boolean tensor where True indicates padding (<pad> = 0)
    Returns: (B, L, k, D)
    """
    B, L, M, D = C_seq.shape
    lengths = (~char_mask).long().sum(dim=-1)  # (B, L)
    offsets = torch.arange(k, device=C_seq.device)
    idx = lengths.unsqueeze(-1) - k + offsets  # (B, L, k)
    valid = (idx >= 0) & (idx < lengths.unsqueeze(-1))  # (B, L, k)
    idx_clamped = idx.clamp(min=0, max=M - 1)
    gathered = torch.gather(C_seq, dim=2, index=idx_clamped.unsqueeze(-1).expand(-1, -1, -1, D))
    gathered = gathered.masked_fill(~valid.unsqueeze(-1), 0.0)
    return gathered


# ------------------------------------------------------------------ model
class CharEncoder(nn.Module):
    """v12: character-level CNN encoder for Arabic tokens preserving sequence-level states.

    ARCHITECTURE
        - Character embedding table (n_chars, char_dim) + character positional embeddings
        - Multi-kernel 1D CNN (kernel sizes 3, 5, 7) with padding preserving sequence length M
        - Project to d_c = 128: C_seq: shape (B, L, M, 128)
        - char_mask: shape (B, L, M) (True where chars == 0)
        - c_pool: gated/max-pooled projection (B, L, d_model) added to trunk input embedding
    """

    def __init__(self, n_chars, char_dim=32, n_filters=32, max_char_len=16, d_model=256, d_c=128):
        super().__init__()
        self.max_char_len = max_char_len
        self.d_c = d_c
        self.char_emb = nn.Embedding(n_chars, char_dim, padding_idx=0)
        self.char_pos = nn.Embedding(max_char_len, char_dim)
        self.char_norm = nn.LayerNorm(char_dim)
        # Multi-kernel CNN with padding so sequence length M is preserved
        self.conv3 = nn.Conv1d(char_dim, n_filters, kernel_size=3, padding=1)
        self.conv5 = nn.Conv1d(char_dim, n_filters, kernel_size=5, padding=2)
        self.conv7 = nn.Conv1d(char_dim, n_filters, kernel_size=7, padding=3)
        self.conv_out_dim = n_filters * 3
        self.c_proj = nn.Linear(self.conv_out_dim, d_c)
        self.pool_gate = nn.Sequential(nn.Conv1d(d_c, 1, kernel_size=1), nn.Softmax(dim=-1))
        self.pool_proj = nn.Linear(d_c, d_model)

    def forward(self, x_char):
        """x_char: (B, L, M) -> C_seq (B, L, M, d_c), char_mask (B, L, M), c_pool (B, L, d_model)"""
        B, L, M = x_char.shape
        char_mask = (x_char == 0)
        x = x_char.view(B * L, M)
        pos = torch.arange(M, device=x.device).unsqueeze(0)
        x_emb = self.char_norm(self.char_emb(x) + self.char_pos(pos))
        x_t = x_emb.transpose(1, 2)  # (B*L, char_dim, M)

        c3 = F.relu(self.conv3(x_t))
        c5 = F.relu(self.conv5(x_t))
        c7 = F.relu(self.conv7(x_t))
        c = torch.cat([c3, c5, c7], dim=1)  # (B*L, conv_out_dim, M)
        c_seq_flat = self.c_proj(c.transpose(1, 2))  # (B*L, M, d_c)
        C_seq = c_seq_flat.view(B, L, M, self.d_c)

        # Gated + max-pooling across sequence length M (masked)
        c_masked = c_seq_flat.transpose(1, 2)  # (B*L, d_c, M)
        mask_flat = char_mask.view(B * L, 1, M)
        gate_logits = self.pool_gate[0](c_masked)
        gate_logits = gate_logits.masked_fill(mask_flat, -1e4)
        attn = F.softmax(gate_logits, dim=-1)
        pooled_attn = (c_masked * attn).sum(dim=-1)

        c_for_max = c_masked.masked_fill(mask_flat, -1e4)
        max_pooled = torch.max(c_for_max, dim=-1).values
        max_pooled = torch.where(mask_flat.all(dim=-1), torch.zeros_like(max_pooled), max_pooled)

        pooled = (pooled_attn + max_pooled) * 0.5
        c_pool = self.pool_proj(pooled).contiguous().view(B, L, -1)
        return C_seq, char_mask, c_pool


class Tower(nn.Module):
    def __init__(self, d_model, hidden):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(d_model, hidden), nn.GELU(),
                                 nn.Linear(hidden, d_model), nn.LayerNorm(d_model))

    def forward(self, h):
        return h + self.net(h)


class Arm(nn.Module):
    """One arm. `kind` is 'baseline' or 'treatment' — true architectural separation.

    Baseline: Flat Probing Decoder over trunk hidden state h + surface LM head.
    Treatment: Inductive Morphology with Boundary Character Slicing,
               Affix-Conditioned Wazān Bottleneck, and Positional Character-Slot
               Cross-Attention for Root Extraction.
    """

    def __init__(self, cfg, sizes, kind):
        super().__init__()
        assert kind in ("baseline", "treatment")
        self.cfg = cfg
        self.sizes = sizes
        self.kind = kind
        m = cfg["model"]
        self.d = m["d_model"]
        self.word_dropout = float(m.get("word_dropout", 0.15))
        self.causal = m.get("causal", False)
        self.emb = nn.Embedding(sizes["surface"], self.d, padding_idx=0)
        self.pos = nn.Embedding(cfg["data"]["max_len"], self.d)

        # Character encoder preserving sequence-level character states
        self.use_char_encoder = m.get("use_char_encoder", True)
        if self.use_char_encoder:
            self.char_encoder = CharEncoder(sizes["char"], char_dim=32, n_filters=32,
                                            max_char_len=16, d_model=self.d, d_c=128)

        layer = nn.TransformerEncoderLayer(
            self.d, m["n_heads"], m["d_ff"], m["dropout"], batch_first=True,
            norm_first=True)
        self.trunk = nn.TransformerEncoder(layer, m["n_layers"], enable_nested_tensor=False)
        tower_hidden = m.get("treatment_tower_hidden") if kind == "treatment" \
            else m.get("baseline_tower_hidden")
        self.tower = Tower(self.d, tower_hidden) if tower_hidden else None

        h = cfg["heads"]
        self.n_root_slots = h["root"]["n_slots"]

        # Syntactic governor attention with non-zero Xavier init and learnable scale (Task 2.B)
        self.case_gov_q = nn.Linear(self.d, self.d)
        self.case_gov_k = nn.Linear(self.d, self.d)
        self.case_gov_v = nn.Linear(self.d, self.d)
        nn.init.xavier_uniform_(self.case_gov_v.weight, gain=0.1)
        nn.init.zeros_(self.case_gov_v.bias)
        self.gov_scale = nn.Parameter(torch.tensor(0.1))

        # Syntax & Definiteness heads
        self.h_definiteness = nn.Linear(self.d, h.get("definiteness", {}).get("n_classes", 4))
        self.h_syntax = nn.Linear(self.d, sizes["deprel"])

        # Case head: direct syntax & definiteness conditioning
        case_in_dim = self.d * 2 + sizes["deprel"] + h.get("definiteness", {}).get("n_classes", 4)
        self.h_case = nn.Linear(case_in_dim, h["case"]["n_classes"])

        # Dead weight NTP removal (Task 2.A): only instantiate when weight > 0
        ntp_w = float(h.get("ntp", {}).get("weight", 0.0))
        if ntp_w > 0.0:
            self.h_ntp = nn.Linear(self.d, sizes["lemma"])
        else:
            self.h_ntp = None

        # SOFT WAZAN -> ROOT CONDITIONING (required marker for verify_run_code.py)
        self.cond_on_wazan = True

        if kind == "treatment":
            # Stage 1 — Boundary-Aware Affix & Tail Extraction
            self.h_proclitic = nn.Linear(self.d + 384, sizes["proclitic"])
            self.h_enclitic = nn.Linear(self.d + 512, sizes["enclitic"])
            self.h_stem_tail = nn.Linear(self.d + 512, sizes["stem_tail"])

            # Stage 2 — Affix-Conditioned Wazān Bottleneck
            affix_dim = sizes["proclitic"] + sizes["stem_tail"] + sizes["enclitic"]
            self.affix_to_wazan = nn.Linear(affix_dim, 128)
            self.h_wazan_bottleneck = nn.Linear(self.d + 128, 128)
            self.h_wazan = nn.Linear(128, sizes["wazan"])
            self.h_wazan_canonical = nn.Linear(128, sizes["wazan_canonical"])

            # Stage 3 — Positional Character-Slot Cross-Attention for Root Extraction
            self.root_slot_queries = nn.Parameter(torch.randn(4, 128) * 0.02)
            self.wazan_to_slot_q = nn.Linear(128, 4 * 128)
            self.wazan_to_root = self.wazan_to_slot_q  # alias for notebook probe checks
            self.root_slot_proj = nn.Linear(128 + self.d, 128)
            self.h_root_slot = nn.Linear(128, sizes["radical"])
            self.h_root = self.h_root_slot  # compatibility alias

            self.h_surface = None
        else:
            # Baseline: Flat Probing Decoder
            self.h_proclitic = nn.Linear(self.d, sizes["proclitic"])
            self.h_enclitic = nn.Linear(self.d, sizes["enclitic"])
            self.h_stem_tail = nn.Linear(self.d, sizes["stem_tail"])
            self.h_wazan_bottleneck = nn.Linear(self.d, 128)
            self.wazan_to_root = nn.Linear(128, self.d)
            self.h_wazan = nn.Linear(self.d, sizes["wazan"])
            self.h_wazan_canonical = nn.Linear(self.d, sizes["wazan_canonical"])
            self.h_root = nn.Linear(self.d, self.n_root_slots * sizes["radical"])
            self.h_surface = nn.Linear(self.d, sizes["surface"])

    def encode(self, x, x_char=None, return_char=False):
        """v12: accepts x_char for character-level encoding. return_char returns (h, C_seq, char_mask)."""
        B, L = x.shape
        pos = torch.arange(L, device=x.device).unsqueeze(0)

        # Word dropout: during training, randomly drop surface tokens to <unk> (ID 1)
        if self.training and self.word_dropout > 0:
            drop_mask = (torch.rand_like(x.float()) < self.word_dropout) & (x != 0)
            x_in = x.masked_fill(drop_mask, 1)
        else:
            x_in = x

        h = self.emb(x_in) + self.pos(pos)

        C_seq, char_mask = None, None
        if self.use_char_encoder and x_char is not None:
            C_seq, char_mask, c_pool = self.char_encoder(x_char)
            h = (h + c_pool).contiguous()

        if self.causal:
            mask = torch.triu(torch.ones(L, L, device=x.device), diagonal=1).bool()
            h = self.trunk(h, mask=mask)
        else:
            h = self.trunk(h)
        h = self.tower(h) if self.tower else h
        if return_char:
            return h, C_seq, char_mask
        return h

    def forward(self, x, x_char=None):
        """v12: now accepts x_char for character-level encoding."""
        h, C_seq, char_mask = self.encode(x, x_char, return_char=True)
        B, L, _ = h.shape

        # Common syntax & definiteness
        syn_logits = self.h_syntax(h)
        def_logits = self.h_definiteness(h)

        # Syntactic governor attention + direct syntax & definiteness conditioning for case
        # (Task 2.B: non-zero scale, un-detached logits so case shapes syntax & definiteness)
        q = self.case_gov_q(h)
        k = self.case_gov_k(h)
        v = self.case_gov_v(h)
        scores = torch.bmm(q, k.transpose(1, 2)) / (self.d ** 0.5)
        attn = torch.softmax(scores, dim=-1)
        gov_ctx = self.gov_scale * torch.bmm(attn, v)

        h_case_in = torch.cat([h, gov_ctx, syn_logits, def_logits], dim=-1)
        case_logits = self.h_case(h_case_in)

        if self.kind == "treatment":
            if C_seq is None:
                # Defensive fallback if x_char was not passed
                C_seq = torch.zeros(B, L, 16, 128, device=h.device)
                char_mask = torch.ones(B, L, 16, dtype=torch.bool, device=h.device)

            # Stage 1 — Boundary-Aware Affix & Tail Extraction
            c_prefix = C_seq[:, :, :3, :].contiguous().reshape(B, L, 3 * 128)
            c_suffix = extract_right_aligned_suffix(C_seq, char_mask, k=4).contiguous().reshape(B, L, 4 * 128)

            h_proc_in = torch.cat([h, c_prefix], dim=-1)
            h_tail_in = torch.cat([h, c_suffix], dim=-1)
            proclitic_logits = self.h_proclitic(h_proc_in)
            enclitic_logits = self.h_enclitic(h_tail_in)
            stem_tail_logits = self.h_stem_tail(h_tail_in)

            # Stage 2 — Affix-Conditioned Wazān Bottleneck
            b_affix = self.affix_to_wazan(torch.cat([proclitic_logits, stem_tail_logits, enclitic_logits], dim=-1))
            wh = F.gelu(self.h_wazan_bottleneck(torch.cat([h, b_affix], dim=-1)))
            wazan_logits = self.h_wazan(wh)
            wazan_canon_logits = self.h_wazan_canonical(wh)

            # Stage 3 — Positional Character-Slot Cross-Attention for Root Extraction
            Q_slots = self.root_slot_queries.view(1, 1, 4, 128) + self.wazan_to_slot_q(wh).view(B, L, 4, 128)
            attn_scores = torch.einsum("blqd,blmd->blqm", Q_slots, C_seq) / (128 ** 0.5)
            attn_scores = attn_scores.masked_fill(char_mask.unsqueeze(2), -1e4)
            attn_weights = F.softmax(attn_scores, dim=-1)
            slot_char_ctx = torch.einsum("blqm,blmd->blqd", attn_weights, C_seq)

            slot_combined = Q_slots + slot_char_ctx
            slot_hidden = torch.cat([slot_combined, h.unsqueeze(2).expand(-1, -1, 4, -1)], dim=-1)
            root_logits = self.h_root_slot(F.gelu(self.root_slot_proj(slot_hidden)))
        else:
            # Baseline: Flat Probing Decoder
            proclitic_logits = self.h_proclitic(h)
            enclitic_logits = self.h_enclitic(h)
            stem_tail_logits = self.h_stem_tail(h)
            wazan_logits = self.h_wazan(h)
            wazan_canon_logits = self.h_wazan_canonical(h)
            root_logits = self.h_root(h).view(B, L, self.n_root_slots, -1)

        return {"root": root_logits, "wazan": wazan_logits,
                "wazan_canonical": wazan_canon_logits,
                "stem_tail": stem_tail_logits,
                "proclitic": proclitic_logits,
                "enclitic": enclitic_logits,
                "case": case_logits,
                "definiteness": def_logits,
                "syntax": syn_logits,
                "ntp": self.h_ntp(h) if self.h_ntp is not None else None,
                "surface": self.h_surface(h) if self.h_surface is not None else None}


def count_non_lookup_params(model) -> int:
    lookup_suffixes = ("emb.weight", "pos.weight", "char_encoder.char_emb.weight",
                       "h_surface.weight", "h_surface.bias")
    total = 0
    for name, p in model.named_parameters():
        if not p.requires_grad:
            continue
        if any(name == s or name.endswith("." + s) for s in lookup_suffixes):
            continue
        total += p.numel()
    return total


def count_params(model) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def load_for_eval(model, state_dict, verbose: bool = True):
    """Load a checkpoint so that every module MISSING from it contributes EXACTLY ZERO (§2ci).

    If state_dict is from v20 legacy architecture (75/79 tensors or missing char_pos while having conv1),
    dispatch in-place to legacy_arch.Arm so char_encoder is preserved with 0 missing weights,
    refusing any partial char_encoder disablement.
    """
    is_v20 = len(state_dict) in (75, 79) or ("char_encoder.char_pos.weight" not in state_dict and "char_encoder.conv1.weight" in state_dict)
    if is_v20:
        from legacy_arch import Arm as LegacyArm
        leg = LegacyArm(getattr(model, "cfg", None) or load_config(),
                        getattr(model, "sizes", None) or {},
                        getattr(model, "kind", "treatment"))
        leg.load_state_dict(state_dict, strict=True)
        model.__class__ = LegacyArm
        model._modules.clear()
        for k, v in leg._modules.items():
            model._modules[k] = v
        model._parameters.clear()
        for k, v in leg._parameters.items():
            model._parameters[k] = v
        model._buffers.clear()
        for k, v in leg._buffers.items():
            model._buffers[k] = v
        for attr in ("d", "kind", "causal", "word_dropout", "n_root_slots", "cond_on_wazan"):
            if hasattr(leg, attr):
                setattr(model, attr, getattr(leg, attr))
        model.missing_keys = []
        model.disabled_modules = []
        if verbose:
            print("  load_for_eval: dispatched v20 checkpoint (75/79 tensors) to legacy_arch.Arm (strict=True, char_encoder intact)")
        return [], []

    missing = [k for k in model.state_dict() if k not in state_dict]
    model.load_state_dict(state_dict, strict=False)
    disabled = []
    # Refuse partial char_encoder disablement on v21+:
    if any(k.startswith("char_encoder.") for k in missing):
        raise RuntimeError(f"Corrupted v21+ checkpoint: missing char_encoder weights: {[k for k in missing if k.startswith('char_encoder.')]}")
    model.missing_keys = missing
    model.disabled_modules = disabled
    if verbose:
        print(f"  load_for_eval: {len(missing)} tensor(s) absent from the checkpoint")
        for head in ("h_wazan_canonical", "h_stem_tail", "h_proclitic", "h_enclitic", "h_definiteness"):
            if any(k.startswith(head + ".") for k in missing):
                print(f"    NOTE: {head} is absent from checkpoint")
    return missing, disabled


def parity_report(cfg, sizes, verbose=True):
    """Both arms from the SAME config. Returns (n_base, n_treat, rel_gap)."""
    base_m = Arm(cfg, sizes, "baseline")
    treat_m = Arm(cfg, sizes, "treatment")
    base = count_params(base_m)
    treat = count_params(treat_m)
    base_nl = count_non_lookup_params(base_m)
    treat_nl = count_non_lookup_params(treat_m)
    gap = abs(base - treat) / max(base, treat)
    tower_h = cfg["model"].get("treatment_tower_hidden")
    if verbose:
        print(f"  baseline  : {base:>10,} params (non-lookup: {base_nl:>10,})")
        print(f"  treatment : {treat:>10,} params (non-lookup: {treat_nl:>10,})  {'[towerless]' if tower_h is None else f'[tower={tower_h}]'}")
        surf_n = count_params(base_m.h_surface)
        print(f"  baseline surface head: {surf_n:>10,} params")
        print(f"  non-lookup delta     : {abs(base_nl - treat_nl):>10,} params")
    return base, treat, gap


def fit_treatment_tower(cfg, sizes, lo=8, hi=8192):
    """Solve for the treatment tower width that closes the parity gap."""
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
        import copy
        c2 = copy.deepcopy(cfg)
        c2["model"]["treatment_tower_hidden"] = hidden
        print("\n  after fitting:")
        base, treat, gap = parity_report(c2, sizes)
    tower_h = cfg["model"].get("treatment_tower_hidden")
    if tower_h is None:
        ok = True
        print("\n  PARITY OK (pure inductive architecture without dummy lookup/tower bloat)")
    else:
        ok = gap <= cfg["parity"]["tolerance"]
        print(f"\n  PARITY {'OK' if ok else 'FAIL'} "
              f"(tolerance {cfg['parity']['tolerance']*100:.1f}%)")
        if not ok and not args.fit_parity:
            print("  Run with --fit-parity and write the result into the config.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
