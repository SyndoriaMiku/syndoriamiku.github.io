"""Read the translated corpus and split it by story for NER fine-tuning.

Pure Python (no torch, no Tk) so the data rules are testable on their own.
"""
import base64
import hashlib
import json
import os
import random
import unicodedata
from collections import namedtuple

Chapter = namedtuple("Chapter", "story slug path cn")


def _decode(value):
    try:
        return unicodedata.normalize("NFC", base64.b64decode(value).decode("utf-8"))
    except Exception:
        return ""


def _read_chapter(path, story, slug):
    try:
        with open(path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return None
    lines = [_decode(item.get("cn", "")).strip() for item in data.get("content", [])]
    text = "\n".join(line for line in lines if line)
    if not text:
        return None
    return Chapter(story, slug, path, text)


def iter_chapters(library_dir, stories_dir):
    """Every non-empty chapter.

    ``library/<story>/<chapter>/data.json`` keeps its story and chapter ids;
    ``stories/<slug>/data.json`` (a short one-file story) uses ``""`` as slug.
    """
    chapters = []
    for root, _dirs, files in os.walk(library_dir):
        if "data.json" not in files:
            continue
        parts = os.path.relpath(root, library_dir).split(os.sep)
        if len(parts) != 2:  # only library/<story>/<chapter>/data.json
            continue
        chapter = _read_chapter(os.path.join(root, "data.json"), parts[0], parts[1])
        if chapter:
            chapters.append(chapter)
    if os.path.isdir(stories_dir):
        for entry in sorted(os.listdir(stories_dir)):
            root = os.path.join(stories_dir, entry)
            path = os.path.join(root, "data.json")
            if os.path.isdir(root) and os.path.isfile(path):
                chapter = _read_chapter(path, entry, "")
                if chapter:
                    chapters.append(chapter)
    chapters.sort(key=lambda chapter: (chapter.story, chapter.slug))
    return chapters


def dedupe(chapters):
    """Drop any later chapter whose text is byte-identical to an earlier one."""
    seen = set()
    unique = []
    for chapter in chapters:
        digest = hashlib.md5(chapter.cn.encode("utf-8")).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        unique.append(chapter)
    return unique


def split_stories(story_ids, ratios=(0.8, 0.1, 0.1), seed=0):
    """Story-disjoint train/val/test split; deterministic for a given seed."""
    ids = sorted(set(story_ids))
    random.Random(seed).shuffle(ids)
    train_end = int(len(ids) * ratios[0])
    val_end = train_end + int(len(ids) * ratios[1])
    return {"train": ids[:train_end], "val": ids[train_end:val_end], "test": ids[val_end:]}
