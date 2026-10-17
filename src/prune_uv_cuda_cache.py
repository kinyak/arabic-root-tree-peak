"""Remove ONLY the CUDA/triton entries this session's default camel-tools install pulled in.
Keeps the CPU torch build and every other project's cache entries.
"""
import os
import shutil

CACHE = os.path.expanduser("~/.cache/uv/archive-v0")
KILL = []
TOTAL = 0
for entry in sorted(os.listdir(CACHE)):
    path = os.path.join(CACHE, entry)
    if not os.path.isdir(path):
        continue
    names = os.listdir(path)
    junk = False
    for n in names:
        low = n.lower()
        if low.startswith("nvidia") or low == "triton":
            junk = True
        # CUDA torch build has no '+cpu' in the dist-info name
        if low.startswith("torch-") and low.endswith(".dist-info") and "+cpu" not in low:
            junk = True
    if junk:
        sz = 0
        for root, _, files in os.walk(path):
            for f in files:
                try:
                    sz += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        KILL.append((path, names[:3], sz))
        TOTAL += sz

print(f"entries to remove: {len(KILL)}")
for p, sample, sz in KILL:
    print(f"  {sz/2**30:6.2f} GB  {os.path.basename(p):22} {sample}")
print(f"TOTAL: {TOTAL/2**30:.2f} GB")
print()
for p, _, _ in KILL:
    shutil.rmtree(p, ignore_errors=True)
print("removed.")
