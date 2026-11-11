"""Entity-level precision/recall/F1 for name spans.

A span is a ``(start, end, type)`` tuple; a match needs the exact span and the
exact type. Pure Python.
"""


def prf(gold, pred):
    """Return tp/fp/fn and precision/recall/f1 (0.0 when a denominator is 0)."""
    gold = set(gold)
    pred = set(pred)
    tp = len(gold & pred)
    fp = len(pred - gold)
    fn = len(gold - pred)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": precision, "recall": recall, "f1": f1}
