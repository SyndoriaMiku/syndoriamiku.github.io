"""Lazy, batched Chinese NER shared by both builders (CUDA or CPU)."""
import os
import re
import threading

MODEL = 'shibing624/bert4ner-base-chinese'
REVISION = '5d660ed2aa9da482bf2d99c6bc8cf2ce66758f6a'
LABELS = ['I-ORG', 'B-LOC', 'O', 'B-ORG', 'I-LOC', 'I-PER',
          'B-TIME', 'I-TIME', 'B-PER']
TYPES = {'PER': 'PERSON', 'LOC': 'PLACE', 'ORG': 'ORG'}
_LOCK = threading.Lock()
_SESSION = None


def _load(progress):
    global _SESSION
    if _SESSION is not None:
        return _SESSION
    progress('Đang nạp mô hình NER (lần đầu cần tải khoảng 400 MB)…')
    try:
        import torch
        from transformers import BertTokenizerFast, BertForTokenClassification
    except ImportError as exc:
        raise RuntimeError('Thiếu thư viện GPU NER. Xem SCAN_NAMES.md để cài đặt.') from exc
    requested = os.environ.get('STV_NER_DEVICE', 'auto').lower()
    if requested not in ('auto', 'cuda', 'cpu'):
        raise RuntimeError('STV_NER_DEVICE chỉ nhận auto, cuda hoặc cpu.')
    if requested == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA không khả dụng. Kiểm tra PyTorch CUDA và driver NVIDIA.')
    device = 'cuda' if requested != 'cpu' and torch.cuda.is_available() else 'cpu'
    kwargs = dict(revision=REVISION, trust_remote_code=False)
    try:
        # Cached scans also work offline; network is used only on first download.
        try:
            tokenizer = BertTokenizerFast.from_pretrained(MODEL, local_files_only=True, **kwargs)
            model = BertForTokenClassification.from_pretrained(
                MODEL, local_files_only=True, use_safetensors=True, **kwargs)
        except OSError:
            tokenizer = BertTokenizerFast.from_pretrained(MODEL, **kwargs)
            model = BertForTokenClassification.from_pretrained(MODEL, use_safetensors=True, **kwargs)
    except Exception as exc:
        raise RuntimeError('Không nạp được mô hình NER. Kiểm tra kết nối Hugging Face; '
                           'xem SCAN_NAMES.md để tải trước.') from exc
    if [model.config.id2label.get(i) for i in range(len(LABELS))] != LABELS:
        raise RuntimeError('Mô hình NER có bộ nhãn không đúng phiên bản.')
    model.eval()
    if device == 'cuda':
        try:
            model.half().to(device)
        except torch.cuda.OutOfMemoryError:
            model.to('cpu').float()
            torch.cuda.empty_cache()
            device = 'cpu'
    _SESSION = torch, tokenizer, model, device
    return _SESSION


def _decode(offsets, ids, scores):
    """Decode complete BIO spans; never accept a leading I fragment."""
    active = None
    for (start, end), label_id, score in zip(offsets, ids, scores):
        label = LABELS[label_id]
        prefix, _, kind = label.partition('-')
        continues = (active and prefix == 'I' and kind == active[2]
                     and start == active[1] and end > start)
        if continues:
            active[1] = end
            active[3].append(score)
            continue
        if active:
            yield active[0], active[1], active[2], sum(active[3]) / len(active[3])
            active = None
        if end > start and prefix == 'B' and kind in TYPES:
            active = [start, end, kind, [score]]
    if active:
        yield active[0], active[1], active[2], sum(active[3]) / len(active[3])


class NameScanner:
    def scan(self, text, existing_glossary=None, max_results=250, on_progress=None):
        progress = on_progress or (lambda message: None)
        if not text.strip() or max_results <= 0:
            return []
        # Serialize access to the cached model, including device fallback.
        with _LOCK:
            return self._scan(text, existing_glossary or (), max_results, progress)

    def _scan(self, text, glossary, limit, progress):
        global _SESSION
        torch, tokenizer, model, device = _load(progress)
        saved = set(glossary)
        found = {}
        batch_size = 4 if device == 'cuda' else 2
        # Bound tokenizer memory for large novels; overlap gives edge context.
        step, window = 768, 896
        starts = range(0, len(text), step)
        cursor = 0
        while cursor < len(starts):
            batch_starts = starts[cursor:cursor + batch_size]
            pieces = [text[s:s + window] for s in batch_starts]
            encoded = tokenizer(pieces, return_tensors='pt', padding=True,
                                truncation=True, max_length=256, stride=48,
                                return_overflowing_tokens=True, return_offsets_mapping=True)
            offsets = encoded.pop('offset_mapping').tolist()
            mapping = encoded.pop('overflow_to_sample_mapping').tolist()
            try:
                rows = []
                # Overflow sequences also respect the GPU batch limit.
                for first in range(0, len(offsets), batch_size):
                    inputs = {k: v[first:first + batch_size].to(device) for k, v in encoded.items()}
                    with torch.inference_mode():
                        probs = model(**inputs).logits.float().softmax(-1)
                        scores, ids = probs.max(-1)
                    rows.extend(zip(ids.cpu().tolist(), scores.cpu().tolist()))
                    del inputs, probs, scores, ids
            except torch.cuda.OutOfMemoryError:
                # Discard partial inference and retry the same source batch.
                inputs = probs = scores = ids = None
                if batch_size > 1:
                    batch_size = max(1, batch_size // 2)
                else:
                    model.to('cpu').float()
                    device = 'cpu'
                    _SESSION = torch, tokenizer, model, device
                torch.cuda.empty_cache()
                progress(f'Thiếu VRAM: thử lại bằng {device.upper()}, lô {batch_size}.')
                continue
            for row, ((ids, scores), token_offsets) in enumerate(zip(rows, offsets)):
                source = batch_starts[mapping[row]]
                valid = [(a, b) for a, b in token_offsets if b > a]
                if not valid:
                    continue
                left, right = valid[0][0], valid[-1][1]
                for a, b, kind, score in _decode(token_offsets, ids, scores):
                    # An overlapping window will supply complete edge entities.
                    if (a == left and source + a > 0) or (b == right and source + b < len(text)):
                        continue
                    name = text[source + a:source + b]
                    if score < .80 or not re.fullmatch(r'[\u3400-\u9fff·]{2,40}', name):
                        continue
                    if name in saved or any(name in full for full in saved):
                        continue
                    key = (source + a, source + b, kind)
                    found[key] = max(score, found.get(key, 0))
            cursor += len(batch_starts)
            progress(f'NER {device.upper()} — {min(100, cursor * 100 // len(starts))}%')
        # Prefer the complete span where overlapping passes disagree.
        spans = sorted(found, key=lambda k: (k[0], -(k[1] - k[0])))
        entities = {}
        previous_end = -1
        for start, end, kind in spans:
            if start < previous_end:
                continue
            previous_end = end
            name = text[start:end]
            entry = entities.setdefault((name, kind), dict(
                cn=name, type=TYPES[kind], confidence=0, count=0, contexts=[],
                signals=[f'BERT NER / {device.upper()}'], suggested_vi=''))
            entry['count'] += 1
            entry['confidence'] = max(entry['confidence'], found[start, end, kind])
            if len(entry['contexts']) < 3:
                entry['contexts'].append(text[max(0, start-45):min(len(text), end+45)])
        progress(f'NER {device.upper()} hoàn tất — đang lấy gợi ý tên từ API…')
        return sorted(entities.values(), key=lambda v: (-v['count'], -v['confidence'], v['cn']))[:limit]
