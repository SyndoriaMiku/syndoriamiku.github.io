"""Automatic held-out evaluation set for name recall.

A random share of name.cfg is kept out of the training labels; every occurrence
of a held-out name is *ignored* when training (not labelled O, so it never
becomes a hard negative) and later used as gold. Pure Python.
"""
import random

from .labels import IGNORE, weak_spans


def split_names(types, holdout=0.1, seed=0):
    """Split name.cfg types into (train_types, eval_types).

    ``eval_types`` holds the held-out names (never IGNORE); ``train_types``
    keeps every other entry, including IGNORE ones.
    """
    names = sorted(name for name, kind in types.items() if kind != IGNORE)
    random.Random(seed).shuffle(names)
    held = names[:int(len(names) * holdout)]
    eval_types = {name: types[name] for name in held}
    train_types = {name: kind for name, kind in types.items() if name not in eval_types}
    return train_types, eval_types


def gold_spans(chapters, types):
    """All held-out name occurrences as (story, slug, start, end, type) tuples."""
    gold = set()
    for chapter in chapters:
        for start, end, kind in weak_spans(chapter.cn, types):
            gold.add((chapter.story, chapter.slug, start, end, kind))
    return gold
