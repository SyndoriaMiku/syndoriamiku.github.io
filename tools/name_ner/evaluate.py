"""Measure name-NER recall on the held-out name set (baseline or fine-tuned).

    python tools/name_ner/evaluate.py [--model STV_NER_MODEL_DIR] [--out FILE]

Test chapters come from the story-disjoint test split; gold is every held-out
name.cfg occurrence (see eval_set.py). Runs the current gpu_name_scanner model
unless STV_NER_MODEL_DIR / --model points elsewhere.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.name_ner.corpus import dedupe, iter_chapters, split_stories
from tools.name_ner.eval_set import gold_spans, split_names
from tools.name_ner.labels import load_name_types
from tools.name_ner.metrics import prf

TYPE_BACK = {"PERSON": "PER", "PLACE": "LOC", "ORG": "ORG"}
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def predicted_spans(chapter, candidates):
    """Turn scanner candidates (name, type) into (story, slug, start, end, type)."""
    spans = set()
    for candidate in candidates:
        kind = TYPE_BACK.get(candidate.get("type"), "PER")
        for match in re.finditer(re.escape(candidate["cn"]), chapter.cn):
            spans.add((chapter.story, chapter.slug, match.start(), match.end(), kind))
    return spans


def run(max_chapters, holdout, name_seed, split_seed, model_dir, out_path):
    if model_dir:
        os.environ["STV_NER_MODEL_DIR"] = model_dir
    from gpu_name_scanner import NameScanner

    types = load_name_types(os.path.join(ROOT, "name.cfg"))
    _train_types, eval_types = split_names(types, holdout=holdout, seed=name_seed)
    chapters = dedupe(iter_chapters(os.path.join(ROOT, "library"), os.path.join(ROOT, "stories")))
    test_stories = set(split_stories({c.story for c in chapters}, seed=split_seed)["test"])
    test_chapters = [c for c in chapters if c.story in test_stories][:max_chapters]

    gold = gold_spans(test_chapters, eval_types)
    scanner = NameScanner()
    predictions = set()
    for index, chapter in enumerate(test_chapters, 1):
        predictions |= predicted_spans(chapter, scanner.scan(chapter.cn))
        print(f"\r{index}/{len(test_chapters)} chapters", end="", flush=True)
    print()

    result = prf(gold, predictions)
    result.update({
        "eval_names": len(eval_types), "test_chapters": len(test_chapters),
        "gold": len(gold), "predicted": len(predictions),
        "model_dir": model_dir or "base",
        "settings": {"holdout": holdout, "name_seed": name_seed, "split_seed": split_seed,
                     "max_chapters": max_chapters},
    })
    with open(out_path, "w", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in
                      ("precision", "recall", "f1", "tp", "fp", "fn", "gold", "predicted")},
                     ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="", help="STV_NER_MODEL_DIR for a fine-tuned model")
    parser.add_argument("--out", default=os.path.join(ROOT, "docs", "superpowers", "specs", "name-ner-baseline.json"))
    parser.add_argument("--max-chapters", type=int, default=200)
    parser.add_argument("--holdout", type=float, default=0.1)
    parser.add_argument("--name-seed", type=int, default=0)
    parser.add_argument("--split-seed", type=int, default=0)
    args = parser.parse_args()
    run(args.max_chapters, args.holdout, args.name_seed, args.split_seed, args.model, args.out)


if __name__ == "__main__":
    main()
