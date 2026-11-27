"""Bản chạy Moxhi bằng numpy (cho exe). Phần so với torch chỉ chạy khi máy có torch + model."""
import importlib.util
import json
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HAS_NUMPY = importlib.util.find_spec('numpy') is not None
HAS_TORCH = all(importlib.util.find_spec(m) for m in ('torch', 'transformers', 'sentencepiece'))


@unittest.skipUnless(HAS_NUMPY, 'cần numpy')
class LoaderTest(unittest.TestCase):
    def test_safetensors_roundtrip(self):
        import numpy as np
        import moxhi_numpy as mn
        a = np.arange(6, dtype=np.float32).reshape(2, 3)
        b = np.array([1.5, -2.0], dtype=np.float16)
        header = {'a': {'dtype': 'F32', 'shape': [2, 3], 'data_offsets': [0, 24]},
                  'b': {'dtype': 'F16', 'shape': [2], 'data_offsets': [24, 28]},
                  '__metadata__': {'format': 'pt'}}
        raw = json.dumps(header).encode()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'm.safetensors')
            with open(path, 'wb') as fh:
                fh.write(struct.pack('<Q', len(raw)) + raw + a.tobytes() + b.tobytes())
            got = mn.load_safetensors(path)
        np.testing.assert_array_equal(got['a'], a)
        np.testing.assert_array_equal(got['b'], b.astype(np.float32))
        self.assertNotIn('__metadata__', got)

    def test_sinusoids_not_interleaved(self):
        import numpy as np
        import moxhi_numpy as mn
        pos = mn._sinusoids(4, 6)
        np.testing.assert_allclose(pos[0], [0, 0, 0, 1, 1, 1], atol=1e-7)   # sin trước, cos sau
        self.assertAlmostEqual(float(pos[1][0]), float(np.sin(1.0)), places=6)


class BackendChoiceTest(unittest.TestCase):
    def test_env_forces_backend(self):
        import moxhi_scanner as ms
        old = os.environ.get('STV_MOXHI_BACKEND')
        try:
            os.environ['STV_MOXHI_BACKEND'] = 'numpy'
            self.assertEqual(ms.backend(), 'numpy')
            os.environ['STV_MOXHI_BACKEND'] = 'torch'
            self.assertEqual(ms.backend(), 'torch')
        finally:
            if old is None:
                os.environ.pop('STV_MOXHI_BACKEND', None)
            else:
                os.environ['STV_MOXHI_BACKEND'] = old


class DownloadWithoutHubTest(unittest.TestCase):
    """Bản exe không có huggingface_hub: tải thẳng từng file của revision đã ghim."""

    def test_downloads_every_file_at_pinned_revision(self):
        import types
        import moxhi_scanner as ms
        urls = []

        class Res:
            def __init__(self, url):
                self.url, self.status_code = url, 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def raise_for_status(self):
                pass

            def iter_content(self, size):
                yield self.url.encode()

        class Session:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def get(self, url, stream=False, timeout=None):
                urls.append(url)
                return Res(url)

        fake = types.SimpleNamespace(Session=Session)
        old = sys.modules.get('requests')
        sys.modules['requests'] = fake
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ms._download_files(tmp, lambda message: None)
                with open(os.path.join(tmp, 'ner_head', 'ner_head_l6_linear.json'), 'rb') as fh:
                    self.assertIn(ms.REVISION.encode(), fh.read())
        finally:
            if old is None:
                sys.modules.pop('requests', None)
            else:
                sys.modules['requests'] = old
        self.assertEqual(len(urls), len(ms.ALLOW))
        self.assertTrue(all(f'/resolve/{ms.REVISION}/' in u for u in urls))


@unittest.skipUnless(HAS_NUMPY and HAS_TORCH, 'cần torch + transformers để so')
class MatchesTorchTest(unittest.TestCase):
    """Bản numpy phải cho đúng trạng thái encoder và đúng chuỗi token như transformers."""

    @classmethod
    def setUpClass(cls):
        import moxhi_scanner as ms
        if not ms.is_installed():
            raise unittest.SkipTest('chưa có model MoxhiMT-30-Tag trên máy')
        import moxhi_numpy as mn
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        path = ms.model_dir()
        cls.tok = AutoTokenizer.from_pretrained(path, local_files_only=True)
        cls.ref = AutoModelForSeq2SeqLM.from_pretrained(path, local_files_only=True).eval()
        cls.np_model, cls.np_tok = mn.MarianNumpy(path), mn.MarianTokens(path)
        cls.sentences = ['慕云烟是落云宗的长老，她来自天南城。', '韩立呈上青冥剑。',
                         '慕云烟点了点头，韩立退下，向着太浩宗内走去。']

    def test_encoder_and_generation(self):
        import numpy as np
        import torch
        enc = self.tok(self.sentences, return_tensors='pt', padding=True)
        ids, mask = self.np_tok.batch(self.sentences)
        np.testing.assert_array_equal(ids, enc['input_ids'].numpy())
        with torch.inference_mode():
            hidden = self.ref.get_encoder()(**enc, output_hidden_states=True).hidden_states
            ref_out = self.ref.generate(**enc, num_beams=2, max_length=512)
        valid = mask.astype(bool)
        for layer in (6, 8):
            diff = np.abs(hidden[layer].numpy() - self.np_model.encode(ids, mask, layer))[valid].max()
            self.assertLess(float(diff), 1e-4, f'lớp {layer}')
        drop = {0, 1, 2, 3}
        ref_ids = [[i for i in row if i not in drop] for row in ref_out.tolist()]
        got_ids = [[i for i in row if i not in drop] for row in self.np_model.generate(ids, mask, beams=2)]
        self.assertEqual(got_ids, ref_ids)
        self.assertEqual([self.np_tok.decode(r) for r in got_ids],
                         [self.tok.decode(r, skip_special_tokens=False).strip() for r in ref_ids])


if __name__ == '__main__':
    unittest.main()
