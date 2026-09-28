"""Lazy, batched Chinese NER shared by both builders (CUDA or CPU).

The model lives in a folder next to the app (``models/bert4ner-base-chinese``)
so every launch loads it straight from disk, fully offline. It is fetched from
Hugging Face only when that folder is missing or incomplete, and an existing
Hugging Face cache copy is migrated into it without re-downloading.
"""
import json
import os
import re
import shutil
import sys
import threading

MODEL = 'shibing624/bert4ner-base-chinese'
REVISION = '5d660ed2aa9da482bf2d99c6bc8cf2ce66758f6a'
LABELS = ['I-ORG', 'B-LOC', 'O', 'B-ORG', 'I-LOC', 'I-PER',
          'B-TIME', 'I-TIME', 'B-PER']
TYPES = {'PER': 'PERSON', 'LOC': 'PLACE', 'ORG': 'ORG'}
_LOCK = threading.Lock()
_SESSION = None

MANIFEST = 'stv_model.json'
WEIGHTS = 'model.safetensors'
REQUIRED = ('config.json', WEIGHTS, MANIFEST)
ALLOW = ['config.json', 'vocab.txt', 'tokenizer.json', 'tokenizer_config.json',
         'special_tokens_map.json', WEIGHTS]


def _app_dir():
    """Same root rule as the builders: exe folder (minus dist) or source folder."""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
        if os.path.basename(base).lower() == 'dist':
            base = os.path.dirname(base)
        return base
    return os.path.dirname(os.path.abspath(__file__))


def model_dir():
    """Local model folder; override with STV_NER_MODEL_DIR."""
    custom = os.environ.get('STV_NER_MODEL_DIR', '').strip()
    return os.path.abspath(custom) if custom else os.path.join(
        _app_dir(), 'models', MODEL.split('/')[-1])


def is_installed(path=None):
    """True when the local folder holds the pinned revision and its files."""
    path = path or model_dir()
    if not all(os.path.isfile(os.path.join(path, name)) for name in REQUIRED):
        return False
    if not any(os.path.isfile(os.path.join(path, name)) for name in ('vocab.txt', 'tokenizer.json')):
        return False
    try:
        with open(os.path.join(path, MANIFEST), encoding='utf-8') as fh:
            info = json.load(fh)
    except (OSError, ValueError):
        return False
    return info.get('model') == MODEL and info.get('revision') == REVISION


def _write_manifest(path, source):
    with open(os.path.join(path, MANIFEST), 'w', encoding='utf-8') as fh:
        json.dump({'model': MODEL, 'revision': REVISION, 'source': source}, fh, indent=2)


def _replace_dir(staging, target):
    """Swap a finished staging folder into place so a crash never leaves half a model."""
    old = target + '.old'
    shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(target):
        os.replace(target, old)
    os.replace(staging, target)
    shutil.rmtree(old, ignore_errors=True)


def _migrate_from_hf_cache(target, progress):
    """Copy an already-downloaded HF cache snapshot into the app folder (no network)."""
    try:
        from huggingface_hub import snapshot_download
        cached = snapshot_download(MODEL, revision=REVISION, allow_patterns=ALLOW,
                                   local_files_only=True)
    except Exception:
        return False
    if not os.path.isfile(os.path.join(cached, WEIGHTS)):
        return False
    progress('Đang chép mô hình NER từ bộ nhớ đệm Hugging Face vào thư mục models…')
    staging = target + '.partial'
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging)
    for name in os.listdir(cached):
        source = os.path.join(cached, name)
        if os.path.isfile(source):
            shutil.copyfile(source, os.path.join(staging, name))  # follows cache symlinks
    _write_manifest(staging, 'huggingface-cache')
    _replace_dir(staging, target)
    return True


def install_model(progress=None, force=False):
    """Make sure the model is in model_dir(); download (~400 MB) only if needed."""
    progress = progress or (lambda message: None)
    target = model_dir()
    if is_installed(target) and not force:
        return target
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if not force and _migrate_from_hf_cache(target, progress) and is_installed(target):
        return target
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError('Thiếu huggingface_hub (đi kèm transformers). Xem SCAN_NAMES.md.') from exc
    progress(f'Đang tải mô hình NER (~400 MB, chỉ một lần) vào {target}…')
    staging = target + '.partial'
    # Keep an interrupted download so the next attempt resumes instead of restarting.
    try:
        snapshot_download(MODEL, revision=REVISION, allow_patterns=ALLOW, local_dir=staging)
    except Exception as exc:
        raise RuntimeError('Không tải được mô hình NER. Kiểm tra kết nối Hugging Face '
                           f'hoặc chép sẵn thư mục mô hình vào {target}. Chi tiết: {exc}') from exc
    shutil.rmtree(os.path.join(staging, '.cache'), ignore_errors=True)
    _write_manifest(staging, 'download')
    if not is_installed(staging):
        raise RuntimeError(f'Tải mô hình NER chưa đủ file. Xoá {staging} rồi thử lại.')
    _replace_dir(staging, target)
    return target


def _load(progress):
    global _SESSION
    if _SESSION is not None:
        return _SESSION
    path = install_model(progress)
    progress('Đang nạp mô hình NER từ máy…')
    # Model is on disk: forbid any Hugging Face network call. PyTorch backend only.
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['USE_TF'] = '0'
    os.environ['USE_TORCH'] = '1'
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
    try:
        tokenizer = BertTokenizerFast.from_pretrained(path, local_files_only=True)
        model = BertForTokenClassification.from_pretrained(
            path, local_files_only=True, use_safetensors=True, trust_remote_code=False)
    except Exception as exc:
        raise RuntimeError(f'Không nạp được mô hình NER từ {path}. Thư mục có thể hỏng: '
                           f'xoá nó để tải lại (xem SCAN_NAMES.md). Chi tiết: {exc}') from exc
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


def preload(on_progress=None):
    """Load the model into memory ahead of the first scan (safe to call twice)."""
    with _LOCK:
        _load(on_progress or (lambda message: None))


def preload_in_background(on_progress=None, on_error=None):
    """Warm the model on a daemon thread so the first Scan Names is instant."""
    def run():
        try:
            preload(on_progress)
        except Exception as exc:  # the next real scan reports it again
            if on_error:
                on_error(exc)
    thread = threading.Thread(target=run, name='ner-preload', daemon=True)
    thread.start()
    return thread


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


if __name__ == '__main__':
    # python gpu_name_scanner.py            -> download/verify the local model
    # python gpu_name_scanner.py --force    -> re-download it
    # python gpu_name_scanner.py --test     -> also run a small scan
    target = install_model(print, force='--force' in sys.argv)
    print('Mô hình NER sẵn sàng tại:', target)
    if '--test' in sys.argv:
        print(NameScanner().scan('王宏伟来自北京。', on_progress=print))
