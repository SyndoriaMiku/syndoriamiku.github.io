"""Fine-tune the baseline NER on weak labels from name.cfg + the local corpus.

Runs only in the GPU environment (p310). Example:

    python tools/name_ner/train.py --epochs 1 --max-windows 20000 \
        --out models/bert4ner-name-vi

Held-out names (eval_types) are marked IGNORE while training, so they stay a
fair recall test. This is a bounded experiment; evaluate afterwards with
tools/name_ner/evaluate.py --model <out>.
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.name_ner.corpus import dedupe, iter_chapters, split_stories
from tools.name_ner.dataset import LABELS, O, bio_example, windows
from tools.name_ner.eval_set import split_names
from tools.name_ner.labels import load_name_types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build_examples(tokenizer, chapters, types, ignore_types, max_windows, seed=1234):
    order = list(chapters)
    random.Random(seed).shuffle(order)
    examples = []
    for chapter in order:
        for _start, text in windows(chapter.cn):
            examples.append(bio_example(text, tokenizer, types, ignore_types))
            if len(examples) >= max_windows:
                return examples
    return examples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default=os.path.join(ROOT, "models", "bert4ner-base-chinese"))
    parser.add_argument("--out", default=os.path.join(ROOT, "models", "bert4ner-name-vi"))
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--max-windows", type=int, default=20000)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--holdout", type=float, default=0.1)
    parser.add_argument("--name-seed", type=int, default=0)
    parser.add_argument("--split-seed", type=int, default=0)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    import torch
    from torch.utils.data import DataLoader, TensorDataset
    from transformers import BertForTokenClassification, BertTokenizerFast

    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    types = load_name_types(os.path.join(ROOT, "name.cfg"))
    train_types, eval_types = split_names(types, holdout=args.holdout, seed=args.name_seed)
    chapters = dedupe(iter_chapters(os.path.join(ROOT, "library"), os.path.join(ROOT, "stories")))
    train_stories = set(split_stories({c.story for c in chapters}, seed=args.split_seed)["train"])
    train_chapters = [c for c in chapters if c.story in train_stories]

    tokenizer = BertTokenizerFast.from_pretrained(args.base_model, local_files_only=True)
    print(f"building up to {args.max_windows} windows from {len(train_chapters)} chapters...", flush=True)
    examples = build_examples(tokenizer, train_chapters, train_types, eval_types, args.max_windows)
    if not examples:
        raise SystemExit("no training examples")
    max_len = min(512, max(len(e["input_ids"]) for e in examples))
    pad = lambda rows, value: torch.tensor([row[:max_len] + [value] * (max_len - len(row[:max_len])) for row in rows])
    ids = pad([e["input_ids"] for e in examples], 0)
    mask = pad([e["attention_mask"] for e in examples], 0)
    labels = pad([e["labels"] for e in examples], -100)
    loader = DataLoader(TensorDataset(ids, mask, labels), batch_size=args.batch_size, shuffle=True)

    model = BertForTokenClassification.from_pretrained(args.base_model, local_files_only=True)
    model.config.id2label = {i: LABELS[i] for i in range(len(LABELS))}
    model.config.label2id = {name: i for i, name in enumerate(LABELS)}
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    scaler = torch.amp.GradScaler("cuda", enabled=device == "cuda")
    weights = torch.ones(len(LABELS), device=device)
    weights[O] = 0.1  # O dominates; down-weight it so real names matter
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights, ignore_index=-100)

    model.train()
    print(f"training {len(examples)} windows, max_len {max_len}, device {device}", flush=True)
    for epoch in range(args.epochs):
        total, steps = 0.0, 0
        for batch_ids, batch_mask, batch_labels in loader:
            batch_ids, batch_mask, batch_labels = batch_ids.to(device), batch_mask.to(device), batch_labels.to(device)
            optimizer.zero_grad()
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=device == "cuda"):
                logits = model(input_ids=batch_ids, attention_mask=batch_mask).logits
                loss = loss_fn(logits.view(-1, len(LABELS)), batch_labels.view(-1))
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            total += loss.item()
            steps += 1
            if steps % 50 == 0:
                print(f"epoch {epoch + 1} step {steps}/{len(loader)} loss {total / steps:.4f}", flush=True)
        print(f"epoch {epoch + 1} done, mean loss {total / max(steps, 1):.4f}", flush=True)

    os.makedirs(args.out, exist_ok=True)
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    with open(os.path.join(args.out, "stv_model.json"), "w", encoding="utf-8") as stream:
        json.dump({"custom": True, "base_model": os.path.basename(args.base_model),
                   "labels": LABELS,
                   "trained": {"windows": len(examples), "epochs": args.epochs,
                               "holdout": args.holdout, "name_seed": args.name_seed,
                               "split_seed": args.split_seed}}, stream, ensure_ascii=False, indent=2)
    print("saved", args.out)


if __name__ == "__main__":
    main()
