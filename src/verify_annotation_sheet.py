"""Verify a generated annotation sheet before handing it to a human annotator."""
import collections
import csv
import re
import sys

PUNCT = "\u060c\u061b\u061f\u066c\u066d\u06d4,;:!?.*\"'()[]{}_\u2014\u2013-"


def main(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    print(f"rows                : {len(rows)}")
    nomark = [r["id"] for r in rows
              if "[[" not in r["sentence_with_target_in_double_brackets"]]
    print(f"missing [[ ]] marker: {len(nomark)} {nomark[:5]}")
    punct = [(r["id"], r["target_token"]) for r in rows
             if r["target_token"] != r["target_token"].strip(PUNCT)]
    print(f"targets w/ punct    : {len(punct)} {punct[:5]}")
    # the marker must be on exactly the target token
    badmark = []
    for r in rows:
        ctx = r["sentence_with_target_in_double_brackets"]
        m = re.search(r"\[\[(.+?)\]\]", ctx)
        if m and m.group(1) != r["target_token"]:
            badmark.append((r["id"], m.group(1), r["target_token"]))
    print(f"marker/target mismatch: {len(badmark)} {badmark[:5]}")
    c = collections.Counter()
    for r in rows:
        t = r["target_token"]
        if "\u0651" in t:
            c["shadda"] += 1
        bare = "".join(ch for ch in t if not ("\u064b" <= ch <= "\u0652"))
        if re.search(r"[\u0648\u064a]", bare):
            c["weak_letter"] += 1
        if not any("\u064b" <= ch <= "\u0652" for ch in t):
            c["NOT_VOCALIZED"] += 1
        if len(re.findall(r"[\u0621-\u063a\u0641-\u064a]", t)) < 4:
            c["short(<4 letters)"] += 1
    print(f"surface mix         : {dict(c)}")
    print("\nfirst 3 rows:")
    for r in rows[:3]:
        print(f"  {r['id']}  {r['sentence_with_target_in_double_brackets'][:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1
                  else "data/annotation/full-annotation-sheet.csv"))
