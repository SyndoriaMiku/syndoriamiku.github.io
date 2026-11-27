"""Chạy MoxhiMT-30-Tag (Marian) bằng numpy thuần, không cần torch/transformers.

Dùng cho bản exe: torch (vài GB) không đóng gói được, còn model này nhỏ (37M tham số, encoder 8 lớp,
decoder 2 lớp) nên numpy trên CPU đủ nhanh. Đọc thẳng ``model.safetensors`` và tách từ bằng
sentencepiece + ``vocab.json``, giống MarianTokenizer.

Kiến trúc theo transformers.models.marian (post-norm, swish, vị trí sin/cos không xen kẽ, nhúng
nhân sqrt(d_model), lm_head dùng chung ma trận nhúng + final_logits_bias). Kết quả được so với
bản torch trong tests/test_moxhi_numpy.py (chạy khi máy có torch + model).
"""
import json
import os
import struct

import numpy as np

_DTYPES = {'F32': np.float32, 'F16': np.float16}


def load_safetensors(path):
    """{tên: mảng numpy} từ file .safetensors (chỉ F32/F16)."""
    with open(path, 'rb') as fh:
        size = struct.unpack('<Q', fh.read(8))[0]
        header = json.loads(fh.read(size))
        data = fh.read()
    out = {}
    for name, info in header.items():
        if name == '__metadata__':
            continue
        if info['dtype'] not in _DTYPES:
            raise ValueError(f'{name}: kiểu {info["dtype"]} chưa hỗ trợ')
        start, end = info['data_offsets']
        arr = np.frombuffer(data, dtype=_DTYPES[info['dtype']], count=(end - start) // np.dtype(
            _DTYPES[info['dtype']]).itemsize, offset=start)
        out[name] = arr.reshape(info['shape']).astype(np.float32)
    return out


def _sinusoids(n, dim):
    pos = np.array([[p / np.power(10000, 2 * (j // 2) / dim) for j in range(dim)] for p in range(n)])
    out = np.zeros((n, dim), dtype=np.float32)
    half = dim // 2 if dim % 2 == 0 else dim // 2 + 1
    out[:, :half] = np.sin(pos[:, 0::2])
    out[:, half:] = np.cos(pos[:, 1::2])
    return out


def _layer_norm(x, w, b, eps=1e-5):
    mean = x.mean(-1, keepdims=True)
    var = ((x - mean) ** 2).mean(-1, keepdims=True)
    return (x - mean) / np.sqrt(var + eps) * w + b


def _swish(x):
    return x / (1.0 + np.exp(-x))


def _softmax(x):
    x = x - x.max(-1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(-1, keepdims=True)


def log_softmax(x):
    x = x - x.max(-1, keepdims=True)
    return x - np.log(np.exp(x).sum(-1, keepdims=True))


class _Linear:
    __slots__ = ('w', 'b')

    def __init__(self, weights, prefix):
        self.w = np.ascontiguousarray(weights[prefix + '.weight'].T)
        self.b = weights[prefix + '.bias']

    def __call__(self, x):
        return x @ self.w + self.b


class _Attention:
    def __init__(self, weights, prefix, heads):
        self.q, self.k, self.v, self.o = (_Linear(weights, f'{prefix}.{name}')
                                          for name in ('q_proj', 'k_proj', 'v_proj', 'out_proj'))
        self.heads = heads

    def split(self, x):                      # [B, T, D] -> [B, H, T, d]
        b, t, d = x.shape
        return x.reshape(b, t, self.heads, d // self.heads).transpose(0, 2, 1, 3)

    def attend(self, q, k, v, bias):
        d = q.shape[-1]
        scores = (q * d ** -0.5) @ k.transpose(0, 1, 3, 2)
        if bias is not None:
            scores = scores + bias
        out = _softmax(scores) @ v           # [B, H, Tq, d]
        b, h, t, dd = out.shape
        return self.o(out.transpose(0, 2, 1, 3).reshape(b, t, h * dd))


class MarianNumpy:
    def __init__(self, path):
        with open(os.path.join(path, 'config.json'), encoding='utf-8') as fh:
            cfg = json.load(fh)
        if cfg.get('model_type') != 'marian' or cfg.get('activation_function') != 'swish':
            raise ValueError('Chỉ hỗ trợ Marian dùng swish.')
        w = load_safetensors(os.path.join(path, 'model.safetensors'))
        self.cfg = cfg
        self.d = cfg['d_model']
        self.scale = np.sqrt(self.d) if cfg.get('scale_embedding') else 1.0
        self.embed = w['model.shared.weight']
        self.lm_bias = w['final_logits_bias'][0]
        self.pos = _sinusoids(cfg['max_position_embeddings'], self.d)
        self.pad, self.eos = cfg['pad_token_id'], cfg['eos_token_id']
        self.start = cfg['decoder_start_token_id']
        self.enc = []
        for i in range(cfg['encoder_layers']):
            p = f'model.encoder.layers.{i}'
            self.enc.append((_Attention(w, p + '.self_attn', cfg['encoder_attention_heads']),
                             (w[p + '.self_attn_layer_norm.weight'], w[p + '.self_attn_layer_norm.bias']),
                             _Linear(w, p + '.fc1'), _Linear(w, p + '.fc2'),
                             (w[p + '.final_layer_norm.weight'], w[p + '.final_layer_norm.bias'])))
        self.dec = []
        for i in range(cfg['decoder_layers']):
            p = f'model.decoder.layers.{i}'
            self.dec.append((_Attention(w, p + '.self_attn', cfg['decoder_attention_heads']),
                             (w[p + '.self_attn_layer_norm.weight'], w[p + '.self_attn_layer_norm.bias']),
                             _Attention(w, p + '.encoder_attn', cfg['decoder_attention_heads']),
                             (w[p + '.encoder_attn_layer_norm.weight'], w[p + '.encoder_attn_layer_norm.bias']),
                             _Linear(w, p + '.fc1'), _Linear(w, p + '.fc2'),
                             (w[p + '.final_layer_norm.weight'], w[p + '.final_layer_norm.bias'])))
        self.lm_w = np.ascontiguousarray(self.embed.T)

    # ── encoder ──
    def encode(self, ids, mask, layers=None):
        """ids, mask: [B, T] int. Trả về trạng thái sau ``layers`` lớp (mặc định: tất cả)."""
        ids = np.asarray(ids)
        mask = np.asarray(mask)
        t = ids.shape[1]
        h = self.embed[ids] * self.scale + self.pos[:t]
        bias = np.where(mask[:, None, None, :] > 0, 0.0, -1e9).astype(np.float32)
        for attn, ln1, fc1, fc2, ln2 in self.enc[:layers]:
            x = attn.attend(attn.split(attn.q(h)), attn.split(attn.k(h)), attn.split(attn.v(h)), bias)
            h = _layer_norm(h + x, *ln1)
            h = _layer_norm(h + fc2(_swish(fc1(h))), *ln2)
        return h

    # ── decoder (có cache) ──
    def _cross_cache(self, enc):
        return [(attn.split(attn.k(enc)), attn.split(attn.v(enc))) for _, _, attn, *_ in self.dec]

    def _step(self, tokens, step, self_cache, cross_cache, enc_bias):
        """tokens: [B] token vừa sinh; trả về log-xác suất [B, V] và cache mới."""
        h = self.embed[tokens][:, None, :] * self.scale + self.pos[step]
        new_cache = []
        for (sa, ln1, ca, ln2, fc1, fc2, ln3), past, (ck, cv) in zip(self.dec, self_cache, cross_cache):
            k, v = sa.split(sa.k(h)), sa.split(sa.v(h))
            if past is not None:
                k = np.concatenate([past[0], k], axis=2)
                v = np.concatenate([past[1], v], axis=2)
            new_cache.append((k, v))
            h = _layer_norm(h + sa.attend(sa.split(sa.q(h)), k, v, None), *ln1)
            h = _layer_norm(h + ca.attend(ca.split(ca.q(h)), ck, cv, enc_bias), *ln2)
            h = _layer_norm(h + fc2(_swish(fc1(h))), *ln3)
        logits = h[:, 0, :] @ self.lm_w + self.lm_bias
        logits[:, self.pad] = -np.inf          # không bao giờ sinh <pad>
        return log_softmax(logits), new_cache

    def generate(self, ids, mask, beams=2, max_length=512):
        """Dịch một lô câu bằng beam search (length_penalty=1, early_stopping=False như mặc định
        của transformers). Mọi câu × beam chạy chung một lượt để numpy nhân ma trận lớn.
        Trả về danh sách id token sinh ra cho từng câu (không gồm token bắt đầu)."""
        ids, mask = np.asarray(ids), np.asarray(mask)
        n, k = len(ids), beams
        enc = self.encode(ids, mask)
        rows = np.repeat(np.arange(n), k)                    # hàng -> câu
        cross = [(ck[rows], cv[rows]) for ck, cv in self._cross_cache(enc)]
        enc_bias = np.where(mask[rows][:, None, None, :] > 0, 0.0, -1e9).astype(np.float32)
        seqs = [[] for _ in range(n * k)]
        scores = np.tile(np.r_[0.0, np.full(k - 1, -1e9)], n)  # lúc đầu chỉ beam 0 của mỗi câu được tính
        last = np.full(n * k, self.start)
        cache = [None] * len(self.dec)
        done = [[] for _ in range(n)]                         # mỗi câu: [(điểm chuẩn hoá, chuỗi)]
        active = list(range(n))                               # câu còn đang dịch (thứ tự khớp các hàng)
        for step in range(max_length - 1):
            logp, cache = self._step(last, step, cache, cross, enc_bias)
            if step == max_length - 2:                        # forced_eos ở độ dài tối đa
                forced = np.full_like(logp, -np.inf)
                forced[:, self.eos] = logp[:, self.eos]
                logp = forced
            vocab = logp.shape[1]
            total = (scores[:, None] + logp).reshape(len(active), k * vocab)
            top = np.argpartition(-total, 2 * k, axis=1)[:, :2 * k]
            keep_rows, keep_seqs, keep_scores, keep_last, still = [], [], [], [], []
            for slot, sent in enumerate(active):
                cand = top[slot][np.argsort(-total[slot, top[slot]])]
                picked = []
                for idx in cand:
                    b, tok = divmod(int(idx), vocab)
                    row = slot * k + b
                    score = float(total[slot, idx])
                    if tok == self.eos:
                        done[sent].append((score / (len(seqs[row]) + 1), seqs[row]))
                        continue
                    picked.append((row, seqs[row] + [tok], score, tok))
                    if len(picked) == k:
                        break
                done[sent] = sorted(done[sent], key=lambda x: -x[0])[:k]
                best_open = max((p[2] for p in picked), default=-np.inf) / (step + 1)
                if len(done[sent]) >= k and best_open <= done[sent][-1][0]:
                    continue                                  # câu này xong
                if not picked:
                    continue
                while len(picked) < k:                        # hiếm: thiếu ứng viên, chép beam cuối
                    picked.append(picked[-1][:2] + (-np.inf, picked[-1][3]))
                still.append(sent)
                for row, seq, score, tok in picked:
                    keep_rows.append(row)
                    keep_seqs.append(seq)
                    keep_scores.append(score)
                    keep_last.append(tok)
            if not still:
                break
            src = np.array(keep_rows)
            if len(still) != len(active):                     # bỏ hàng của câu đã xong
                gone = np.repeat([a in still for a in active], k)
                cross = [(ck[gone], cv[gone]) for ck, cv in cross]
                enc_bias = enc_bias[gone]
            cache = [(ck[src], cv[src]) for ck, cv in cache]
            active, seqs, scores, last = still, keep_seqs, np.array(keep_scores), np.array(keep_last)
        out = []
        for sent in range(n):
            if not done[sent] and sent in active:
                slot = active.index(sent)
                done[sent] = [(scores[slot * k] / max(len(seqs[slot * k]), 1), seqs[slot * k])]
            out.append(max(done[sent], key=lambda x: x[0])[1] if done[sent] else [])
        return out


class MarianTokens:
    """Tách/ghép token như MarianTokenizer (sentencepiece nguồn/đích + vocab.json chung)."""

    def __init__(self, path):
        import sentencepiece as spm
        with open(os.path.join(path, 'vocab.json'), encoding='utf-8') as fh:
            self.vocab = json.load(fh)
        added = os.path.join(path, 'added_tokens.json')
        if os.path.exists(added):
            with open(added, encoding='utf-8') as fh:
                self.vocab.update(json.load(fh))
        self.inv = {i: t for t, i in self.vocab.items()}
        self.src = spm.SentencePieceProcessor(model_file=os.path.join(path, 'source.spm'))
        self.tgt = spm.SentencePieceProcessor(model_file=os.path.join(path, 'target.spm'))
        self.unk = self.vocab.get('<unk>', 3)
        self.eos = self.vocab.get('</s>', 2)
        self.pad = self.vocab.get('<pad>', 0)
        self.special = {'<pad>', '<s>', '</s>', '<unk>'} | {t for t in self.vocab if t.startswith('<') and
                                                           t.endswith('>') and t.strip('</>').isupper()}

    def ids(self, pieces):
        return [self.vocab.get(p, self.unk) for p in pieces]

    def encode(self, text, max_length=512):
        return self.ids(self.src.encode(text, out_type=str))[:max_length - 1] + [self.eos]

    def batch(self, texts, max_length=512):
        rows = [self.encode(t, max_length) for t in texts]
        width = max(len(r) for r in rows)
        ids = np.full((len(rows), width), self.pad, dtype=np.int64)
        mask = np.zeros((len(rows), width), dtype=np.int64)
        for i, r in enumerate(rows):
            ids[i, :len(r)] = r
            mask[i, :len(r)] = 1
        return ids, mask

    def decode(self, ids):
        """Giữ thẻ đặc biệt (như decode(skip_special_tokens=False) của MarianTokenizer)."""
        parts, sub = [], []
        for token in (self.inv.get(i, '<unk>') for i in ids):
            if token in self.special:
                if sub:
                    parts.append(self.tgt.decode_pieces(sub))
                parts.append(token)
                sub = []
            else:
                sub.append(token)
        if sub:
            parts.append(self.tgt.decode_pieces(sub))
        return ' '.join(p.replace('▁', ' ').strip() for p in parts).strip()
