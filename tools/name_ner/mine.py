"""Mine a name dictionary from NER output over the local corpus.

The dictionary is what fixes name *phrases*: a name the model finds somewhere
gets snapped to the whole phrase everywhere. `aggregate`/`select` are pure and
tested; the CLI runs the model (use the p310 environment):

    python tools/name_ner/mine.py --out names.json
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import gpu_name_scanner as scanner
from tools.name_ner.corpus import dedupe, iter_chapters
from tools.name_ner.labels import load_name_types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TYPE_BACK = {"PERSON": "PER", "PLACE": "LOC", "ORG": "ORG", "PER": "PER", "LOC": "LOC"}


def plausible(name):
    """A mined phrase worth keeping: multi-character and name-shaped.

    Two-character mining is dominated by common words (阳光, 于是, 刚刚, 王朝)
    that NER mislabelled somewhere, so the dictionary only supplements with
    three-or-more-character phrases; NER still reports real two-character names
    directly.
    """
    return 3 <= len(name) <= 6 and scanner.is_name_shape(name)


def aggregate(observations):
    """Fold (name, scanner_type, score) rows into count/max-confidence/type."""
    entries = {}
    for name, kind, score in observations:
        name = (name or "").strip()
        if not name:
            continue
        score = float(score)
        mapped = TYPE_BACK.get(kind, "PER")
        entry = entries.get(name)
        if entry is None:
            entries[name] = {"count": 1, "confidence": score, "type": mapped}
            continue
        entry["count"] += 1
        if score > entry["confidence"]:
            entry["confidence"] = score
            entry["type"] = mapped
    return entries


def select(entries, known=(), min_count=3, min_confidence=0.8):
    """Keep frequent, confident, plausible phrases that name.cfg does not have."""
    known = set(known)
    return {name: entry["type"] for name, entry in entries.items()
            if name not in known
            and entry["count"] >= min_count
            and entry["confidence"] >= min_confidence
            and plausible(name)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(ROOT, "names.json"))
    parser.add_argument("--min-count", type=int, default=3)
    parser.add_argument("--min-confidence", type=float, default=0.85)
    parser.add_argument("--max-chapters", type=int, default=0, help="0 = all")
    args = parser.parse_args()

    types = load_name_types(os.path.join(ROOT, "name.cfg"))
    chapters = dedupe(iter_chapters(os.path.join(ROOT, "library"), os.path.join(ROOT, "stories")))
    if args.max_chapters:
        chapters = chapters[:args.max_chapters]
    ner = scanner.NameScanner()
    observations = []
    for index, chapter in enumerate(chapters, 1):
        for candidate in ner.scan(chapter.cn):
            observations.append((candidate["cn"], candidate["type"], candidate["confidence"]))
        if index % 25 == 0 or index == len(chapters):
            print(f"\r{index}/{len(chapters)} chapters, {len(observations)} observations", end="", flush=True)
    print()

    entries = select(aggregate(observations), known=set(types),
                     min_count=args.min_count, min_confidence=args.min_confidence)
    payload = {"version": 1, "generated": datetime.date.today().isoformat(),
               "min_count": args.min_count, "min_confidence": args.min_confidence,
               "chapters": len(chapters), "names": len(entries), "entries": entries}
    with open(args.out, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=0, sort_keys=True)
    print(f"wrote {len(entries)} names to {args.out}")


if __name__ == "__main__":
    main()
