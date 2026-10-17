"""repo_root.py — locate the repository from the script's own location, never from a hardcoded path.

WHY THIS EXISTS
    Three tools hardcoded `G:/arabic-root-tree`. They therefore failed — or worse, would have
    read the wrong tree — anywhere else: a copy, a CI checkout, a second machine, or a path with
    a different casing or drive root. A benchmark tool that only runs in one directory on one
    Windows box is not reproducible, and reproducibility is the whole point of a frozen artifact.

RESOLUTION ORDER
    1. an explicit `--root`, in any form the OS understands: native (`G:\\arabic-root-tree`),
       forward-slash (`G:/arabic-root-tree`), or relative to the current directory. (A POSIX
       `/g/aric-root-tree` style path is translated by a POSIX shell *before* the program sees it,
       so it is not a separate case here.) **If an explicit root is given and is NOT a repository,
       this refuses — it never falls back to the script's own tree**, because silently verifying a
       different repository is the failure this module exists to prevent;
    2. otherwise, the directory containing this file's parent — the repo the script is sitting in,
       which is the right answer when the tool is invoked from a copy or a checkout.

    A candidate is accepted only if it has the marker entries below. If nothing matches this
    REFUSES loudly rather than silently falling back to a guess: reading the wrong tree is far
    worse than failing, because every hash downstream would then describe the wrong bytes.

USAGE
    from repo_root import resolve_root
    ROOT = resolve_root(args.root)      # or resolve_root() with no argument
"""
from __future__ import annotations

from pathlib import Path

# Enough to identify a repo-root-shaped directory without requiring the whole tree (a portable
# copy used for verification may legitimately omit the corpora and the logs).
MARKERS = ("tools", "docs")


def resolve_root(explicit=None) -> Path:
    # An explicit root is an INSTRUCTION, not a hint: if it is not a repository we refuse, rather
    # than quietly verifying whatever tree the script happens to live in.
    if explicit:
        cand = Path(str(explicit)).expanduser()
        try:
            cand = cand.resolve()
        except OSError:
            cand = None
        if cand is not None and all((cand / m).exists() for m in MARKERS):
            return cand
        raise SystemExit(
            "--root %r is not a repository root (expected to find %s there). Refusing to fall back "
            "to the script's own tree (%s) -- verifying the wrong repository would make every hash "
            "downstream describe the wrong bytes."
            % (explicit, ", ".join(MARKERS), Path(__file__).resolve().parent.parent)
        )

    candidates: list[Path] = []
    here = Path(__file__).resolve().parent          # .../<repo>/tools
    candidates.append(here.parent)
    candidates.extend(here.parents)

    seen = set()
    for cand in candidates:
        try:
            cand = cand.resolve()
        except OSError:
            continue
        if cand in seen:
            continue
        seen.add(cand)
        if all((cand / m).exists() for m in MARKERS):
            return cand

    raise SystemExit(
        "could not locate the repository root (looked for %s in %s); pass --root <path>"
        % (", ".join(MARKERS), ", ".join(str(c) for c in candidates[:4]))
    )
