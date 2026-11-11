"""Turn Chinese chapters into BIO token-classification examples.

No torch here: the tokenizer is injected so the label rules are testable. The
label order is copied from gpu_name_scanner.LABELS and checked by a test.
"""
from .labels import weak_spans

# y hệt gpu_name_scanner.LABELS (thứ tự bắt buộc)
LABELS = ['I-ORG', 'B-LOC', 'O', 'B-ORG', 'I-LOC', 'I-PER', 'B-TIME', 'I-TIME', 'B-PER']
IGNORE = -100
O = 2
B_LOC, I_LOC = 1, 4
B_ORG, I_ORG = 3, 0
B_PER, I_PER = 8, 5
B_I = {"PER": (B_PER, I_PER), "LOC": (B_LOC, I_LOC), "ORG": (B_ORG, I_ORG)}


def windows(text, size=448, overlap=64):
    """Sliding char windows; overlap keeps every name whole in some window."""
    if not text:
        return []
    step = max(1, size - overlap)
    return [(start, text[start:start + size]) for start in range(0, len(text), step)]


def _mark(labels, offsets, start, end, first, rest=None):
    rest = first if rest is None else rest
    inside = [index for index, (a, b) in enumerate(offsets) if b > a and a >= start and b <= end]
    if not inside:
        return
    labels[inside[0]] = first
    for index in inside[1:]:
        labels[index] = rest


def bio_example(window_text, tokenizer, types, ignore_types=(), max_len=512):
    """One tokenized window with BIO labels.

    Tokens inside a held-out name get IGNORE (never trained as O); special
    tokens (offset 0-0) are IGNORE too.
    """
    encoded = tokenizer(window_text, truncation=True, max_length=max_len,
                        return_offsets_mapping=True)
    input_ids = list(encoded["input_ids"])
    attention_mask = list(encoded.get("attention_mask") or [1] * len(input_ids))
    offsets = [tuple(pair) for pair in encoded["offset_mapping"]]
    labels = [O] * len(input_ids)
    for start, end, _kind in weak_spans(window_text, ignore_types or {}):
        _mark(labels, offsets, start, end, IGNORE)
    for start, end, kind in weak_spans(window_text, types):
        first, rest = B_I[kind]
        _mark(labels, offsets, start, end, first, rest)
    for index, (a, b) in enumerate(offsets):
        if b <= a:
            labels[index] = IGNORE
    return {"input_ids": input_ids, "attention_mask": attention_mask,
            "labels": labels, "offset_mapping": offsets}
