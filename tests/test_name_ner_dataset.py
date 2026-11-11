"""BIO example builder for NER fine-tuning (no torch needed).

Run from the repository root:

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gpu_name_scanner
from tools.name_ner import dataset


class CharTokenizer:
    """One token per character, offsets in characters (like a Chinese BERT)."""
    def __call__(self, text, truncation=True, max_length=512, return_offsets_mapping=True):
        text = text[:max_length]
        return {"input_ids": [1] * len(text), "attention_mask": [1] * len(text),
                "offset_mapping": [(i, i + 1) for i in range(len(text))]}


class ClsTokenizer(CharTokenizer):
    def __call__(self, text, **kwargs):
        out = super().__call__(text, **kwargs)
        out["input_ids"] = [101] + out["input_ids"] + [102]
        out["attention_mask"] = [1] + out["attention_mask"] + [1]
        out["offset_mapping"] = [(0, 0)] + out["offset_mapping"] + [(0, 0)]
        return out


class LabelsTest(unittest.TestCase):

    def test_label_order_matches_production(self):
        self.assertEqual(dataset.LABELS, gpu_name_scanner.LABELS)


class WindowsTest(unittest.TestCase):

    def test_windows_overlap(self):
        self.assertEqual(dataset.windows("abcdef", size=4, overlap=1), [(0, "abcd"), (3, "def")])

    def test_short_text_is_one_window(self):
        self.assertEqual(dataset.windows("ab", size=4, overlap=1), [(0, "ab")])

    def test_empty_text(self):
        self.assertEqual(dataset.windows("", size=4, overlap=1), [])


class BioExampleTest(unittest.TestCase):

    def test_positive_span_gets_bio_labels(self):
        example = dataset.bio_example("慕容雪说道", CharTokenizer(), {"慕容雪": "PER"})
        self.assertEqual(example["labels"], [dataset.B_PER, dataset.I_PER, dataset.I_PER,
                                             dataset.O, dataset.O])

    def test_place_and_org_types(self):
        example = dataset.bio_example("青云宗", CharTokenizer(), {"青云宗": "ORG"})
        self.assertEqual(example["labels"], [dataset.B_ORG, dataset.I_ORG, dataset.I_ORG])

    def test_held_out_span_is_ignored_not_negative(self):
        example = dataset.bio_example("慕容雪说道", CharTokenizer(), {}, {"慕容雪": "PER"})
        self.assertEqual(example["labels"], [dataset.IGNORE, dataset.IGNORE, dataset.IGNORE,
                                             dataset.O, dataset.O])

    def test_special_tokens_are_ignored(self):
        example = dataset.bio_example("慕容雪", ClsTokenizer(), {"慕容雪": "PER"})
        self.assertEqual(example["labels"][0], dataset.IGNORE)
        self.assertEqual(example["labels"][-1], dataset.IGNORE)
        self.assertEqual(example["labels"][1:4], [dataset.B_PER, dataset.I_PER, dataset.I_PER])

    def test_offsets_are_reported_for_scoring(self):
        example = dataset.bio_example("慕容雪", CharTokenizer(), {"慕容雪": "PER"})
        self.assertEqual(example["offset_mapping"], [(0, 1), (1, 2), (2, 3)])


if __name__ == "__main__":
    unittest.main()
