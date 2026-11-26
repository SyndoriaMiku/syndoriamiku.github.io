"""Quét tên bằng MoxhiMT-30-Tag (DanVP): cùng model với trang moxhi-tag.pages.dev.

Model dịch Trung→Việt 37M tham số, đánh dấu tên riêng ngay trong bản dịch
(<PER>, <LOC>, <ORG>, <ITEM>), kèm một đầu phân loại tuyến tính đọc trạng thái encoder
(lớp 6) để tìm tên trong câu chữ Hán. Mỗi lần quét:

  1. Đầu NER nguồn tìm tên trong mọi câu chữ Hán (chỉ chạy encoder → rất nhanh).
  2. Với mỗi tên, dịch vài câu chứa nó; tên tiếng Việt lấy từ thẻ trong bản dịch, ghép với
     tên chữ Hán theo âm Hán-Việt trước, theo thứ tự sau (giống trang web của tác giả).

Model nằm ở ``models/MoxhiMT-30-Tag`` (≈150 MB), chỉ tải từ Hugging Face khi thiếu, sau đó
chạy hoàn toàn offline. Giấy phép: CC-BY-NC-4.0 (phi thương mại).

Phần hậu xử lý thẻ và đầu NER được viết lại theo mô tả trong model card; không chạy file
``moxhi_tag.py`` tải về từ repo của model.
"""
import json
import os
import re
import shutil
import sys
import threading
import unicodedata
from collections import Counter, defaultdict

from gpu_name_scanner import keep_candidate, resolve_spans, saved_spans, snap_spans

MODEL = 'DanVP/MoxhiMT-30-Tag'
REVISION = 'c761ea549aa78a7819bd7ba1ace85b3d35b7ee16'
HEAD_FILE = 'ner_head/ner_head_l6_linear.json'
MANIFEST = 'stv_model.json'
ALLOW = ['config.json', 'generation_config.json', 'model.safetensors', 'source.spm', 'target.spm',
         'vocab.json', 'tokenizer_config.json', 'added_tokens.json', 'special_tokens_map.json', HEAD_FILE]
REQUIRED = ('config.json', 'model.safetensors', 'source.spm', 'vocab.json', HEAD_FILE, MANIFEST)

TAG_TYPES = ('PER', 'LOC', 'ORG', 'ITEM')
TYPES = {'PER': 'PERSON', 'LOC': 'PLACE', 'ORG': 'ORG', 'ITEM': 'ITEM'}
_TAG_RE = re.compile(r'</?(PER|LOC|ORG|ITEM)>')

# Câu dài hơn thế bị cắt thêm ở dấu phẩy: encoder Marian tối đa 512 token, và câu ngắn dịch ổn định hơn.
MAX_SENTENCE = 160
SENTENCE_RE = re.compile(r'[^。！？!?…\n]*(?:[。！？!?…]+[”’」』"]?|\n|$)')
TRANSLATE_PER_NAME = 2       # số câu dịch để lấy tên tiếng Việt cho mỗi tên
MAX_TRANSLATIONS = 600       # trần số câu dịch mỗi lần quét (GPU)
# CPU chậm hơn GPU nhiều lần: ít câu hơn, beam nhỏ hơn (tên trong thẻ gần như không đổi theo beam).
CPU_MAX_TRANSLATIONS = 200
CPU_BEAMS = 2

_LOCK = threading.Lock()
_SESSION = None


# ───────────────────────── cài đặt model ─────────────────────────
def _app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def model_dir():
    """Thư mục model; đổi bằng biến môi trường STV_MOXHI_MODEL_DIR."""
    custom = os.environ.get('STV_MOXHI_MODEL_DIR', '').strip()
    return os.path.abspath(custom) if custom else os.path.join(_app_dir(), 'models', MODEL.split('/')[-1])


def is_installed(path=None):
    path = path or model_dir()
    if not all(os.path.isfile(os.path.join(path, name)) for name in REQUIRED):
        return False
    try:
        with open(os.path.join(path, MANIFEST), encoding='utf-8') as fh:
            info = json.load(fh)
    except (OSError, ValueError):
        return False
    return info.get('model') == MODEL and info.get('revision') == REVISION


def install_model(progress=None, force=False):
    """Bảo đảm model có trong model_dir(); chỉ tải (≈150 MB) khi thiếu."""
    progress = progress or (lambda message: None)
    target = model_dir()
    if not force and is_installed(target):
        return target
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError('Thiếu huggingface_hub. Xem SCAN_NAMES.md để cài đặt.') from exc
    progress('Đang tải model MoxhiMT-30-Tag (≈150 MB, chỉ lần đầu)…')
    staging = target + '.download'
    shutil.rmtree(staging, ignore_errors=True)
    snapshot_download(MODEL, revision=REVISION, allow_patterns=ALLOW, local_dir=staging)
    with open(os.path.join(staging, MANIFEST), 'w', encoding='utf-8') as fh:
        json.dump({'model': MODEL, 'revision': REVISION, 'license': 'cc-by-nc-4.0'}, fh, indent=2)
    shutil.rmtree(os.path.join(staging, '.cache'), ignore_errors=True)
    if os.path.isdir(target):
        shutil.rmtree(target)
    os.replace(staging, target)
    return target


def _load(progress):
    global _SESSION
    if _SESSION is not None:
        return _SESSION
    path = install_model(progress)
    progress('Đang nạp MoxhiMT-30-Tag…')
    # from_pretrained(local_files_only=True) đủ để không gọi mạng. Không bật HF_HUB_OFFLINE toàn cục:
    # nó sẽ chặn gpu_name_scanner tải model của nó sau này trong cùng tiến trình.
    try:
        import sentencepiece as spm
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError('Thiếu thư viện (torch, transformers, sentencepiece). Xem SCAN_NAMES.md.') from exc
    requested = os.environ.get('STV_NER_DEVICE', 'auto').lower()
    device = 'cuda' if requested != 'cpu' and torch.cuda.is_available() else 'cpu'
    try:
        tok = AutoTokenizer.from_pretrained(path, local_files_only=True)
        model = AutoModelForSeq2SeqLM.from_pretrained(path, local_files_only=True, use_safetensors=True,
                                                      trust_remote_code=False)
        with open(os.path.join(path, HEAD_FILE), encoding='utf-8') as fh:
            head = json.load(fh)
        sp = spm.SentencePieceProcessor(model_file=os.path.join(path, 'source.spm'))
    except Exception as exc:
        raise RuntimeError(f'Không nạp được MoxhiMT-30-Tag từ {path}. Xoá thư mục đó để tải lại. '
                           f'Chi tiết: {exc}') from exc
    model.eval().to(device)
    _SESSION = Session(torch, tok, model, head, sp, device)
    return _SESSION


# ───────────────────────── thẻ tên trong bản dịch ─────────────────────────
def tagged_entities(raw):
    """[(type, tên Việt)] từ bản dịch có thẻ; chịu được thẻ hỏng (đóng sai loại, lồng, thiếu)."""
    out, open_type, start = [], None, 0
    for m in _TAG_RE.finditer(raw):
        if m.group(0).startswith('</'):
            if open_type:
                name = re.sub(r'\s+', ' ', raw[start:m.start()]).strip(' "“”\'‘’,.')
                if name:
                    out.append((open_type, name))
            open_type = None
        else:
            open_type, start = m.group(1), m.end()   # mở lồng: bỏ thẻ mở trước, giữ thẻ sau
    return out


def fold(text):
    """So khớp không dấu, không hoa/thường."""
    text = unicodedata.normalize('NFD', text.lower()).replace('đ', 'd')
    return re.sub(r'[̀-ͯ\s\-·]', '', text)


def align_names(cn_names, vi_names, reading=None):
    """Ghép tên chữ Hán (theo thứ tự trong câu) với tên Việt trong bản dịch.

    cn_names: [(type, cn)], vi_names: [(type, vi)]. Ưu tiên khớp âm Hán-Việt; còn lại ghép theo
    thứ tự khi số tên cùng loại bằng nhau. Trả về {cn: vi}.
    """
    result, used = {}, set()
    if reading:
        for _, cn in cn_names:
            hv = fold(reading(cn) or '')
            if not hv:
                continue
            for j, (_, vi) in enumerate(vi_names):
                if j not in used and fold(vi) == hv:
                    result[cn] = vi
                    used.add(j)
                    break
    for kind in TAG_TYPES:
        left = [cn for t, cn in cn_names if t == kind and cn not in result]
        right = [j for j, (t, _) in enumerate(vi_names) if t == kind and j not in used]
        if left and len(left) == len(right):
            for cn, j in zip(left, right):
                result[cn] = vi_names[j][1]
                used.add(j)
    return result


# ───────────────────────── câu ─────────────────────────
def split_sentences(text, limit=MAX_SENTENCE):
    """[(start, end)] các câu (bỏ câu trống); câu quá dài cắt thêm ở dấu phẩy/chấm phẩy."""
    spans = []
    for m in SENTENCE_RE.finditer(text):
        a, b = m.span()
        while b - a > limit:
            cut = max(text.rfind(ch, a, a + limit) for ch in '，,；;、')
            cut = cut + 1 if cut > a else a + limit
            spans.append((a, cut))
            a = cut
        if text[a:b].strip():
            spans.append((a, b))
    return spans


class Session:
    def __init__(self, torch, tok, model, head, sp, device):
        import numpy as np
        self.np, self.torch, self.tok, self.model, self.sp, self.device = np, torch, tok, model, sp, device
        self.labels = head['labels']
        self.layer = head['layers'][0]
        self.W = torch.tensor(head['W'], dtype=torch.float32, device=device) * head['mix'][0]
        self.b = torch.tensor(head['b'], dtype=torch.float32, device=device)
        k = len(self.labels)
        allow = np.ones((k, k), dtype=bool)     # I-X chỉ sau B-X hoặc I-X
        start = np.ones(k, dtype=bool)
        for t in TAG_TYPES:
            i, b = self.labels.index('I-' + t), self.labels.index('B-' + t)
            start[i] = False
            allow[:, i] = False
            allow[b, i] = allow[i, i] = True
        self.start, self.trans = start, np.where(allow, 0.0, -1e9)
        self.drop = {tok.pad_token_id, tok.bos_token_id, tok.eos_token_id, tok.unk_token_id}

    def _viterbi(self, logp):
        np = self.np
        score = np.where(self.start, logp[0], -1e9)
        back = np.zeros(logp.shape, dtype=np.int64)
        for t in range(1, len(logp)):
            cand = score[:, None] + self.trans
            back[t] = cand.argmax(0)
            score = cand.max(0) + logp[t]
        path = [int(score.argmax())]
        for t in range(len(logp) - 1, 0, -1):
            path.append(int(back[t][path[-1]]))
        return path[::-1]

    def source_names(self, sentences, batch=32):
        """Mỗi câu → [(start, end, type, điểm)] (vị trí trong câu)."""
        torch, results = self.torch, []
        for first in range(0, len(sentences), batch):
            chunk = sentences[first:first + batch]
            pieces = [self._pieces(s) for s in chunk]
            ids = [self.tok.convert_tokens_to_ids([p[0] for p in ps]) + [self.tok.eos_token_id] for ps in pieces]
            width = max(len(x) for x in ids)
            input_ids = torch.full((len(ids), width), self.tok.pad_token_id, dtype=torch.long)
            mask = torch.zeros((len(ids), width), dtype=torch.long)
            for i, x in enumerate(ids):
                input_ids[i, :len(x)] = torch.tensor(x)
                mask[i, :len(x)] = 1
            with torch.inference_mode():
                hs = self.model.get_encoder()(input_ids=input_ids.to(self.device), attention_mask=mask.to(self.device),
                                              output_hidden_states=True).hidden_states[self.layer]
                logp = torch.log_softmax(hs.float() @ self.W.T + self.b, -1).cpu().numpy()
            for text, ps, lp in zip(chunk, pieces, logp):
                results.append(self._decode(text, ps, lp[:len(ps)]))
        return results

    def _pieces(self, text):
        """[(mảnh, đầu, cuối)] với vị trí theo ký tự. Chép ra tuple ngay: mảnh immutable_proto
        trỏ vào đối tượng cha, dùng sau khi cha bị thu hồi sẽ lỗi bộ nhớ."""
        proto = self.sp.encode(text, out_type='immutable_proto')
        return [(p.piece, p.begin, p.end) for p in proto.pieces][:510]

    def _decode(self, text, pieces, logp):
        keep = [i for i, p in enumerate(pieces) if p[1] != p[2]]
        if not keep:
            return []
        path = self._viterbi(logp[keep])
        spans, cur = [], None
        for i, lab in zip(keep, path):
            name, prob = self.labels[lab], float(self.np.exp(logp[i][lab]))
            if name == 'O':
                if cur:
                    spans.append(cur)
                cur = None
                continue
            bi, t = name.split('-')
            if bi == 'B' or cur is None or cur[2] != t:
                if cur:
                    spans.append(cur)
                cur = [pieces[i][1], pieces[i][2], t, [prob]]
            else:
                cur[1] = pieces[i][2]
                cur[3].append(prob)
        if cur:
            spans.append(cur)
        out = []
        for a, b, t, probs in spans:
            # Đầu NER gán nhãn cả mảnh BPE: bỏ một 的/在 ở đầu và một 的 ở cuối (theo model card).
            if b - a > 1 and text[a] in '的在':
                a += 1
            if b - a > 1 and text[b - 1] == '的':
                b -= 1
            out.append((a, b, t, sum(probs) / len(probs)))
        return out

    def translate(self, sentences, batch=16, beams=4):
        """Dịch có thẻ → [[(type, tên Việt)]] cho từng câu."""
        torch, out = self.torch, []
        for first in range(0, len(sentences), batch):
            chunk = sentences[first:first + batch]
            enc = self.tok(chunk, return_tensors='pt', padding=True, truncation=True, max_length=512).to(self.device)
            with torch.inference_mode():
                gen = self.model.generate(**enc, num_beams=beams, max_length=512)
            for row in gen.tolist():
                raw = self.tok.decode([i for i in row if i not in self.drop], skip_special_tokens=False)
                out.append(tagged_entities(raw))
        return out


# ───────────────────────── quét ─────────────────────────
class MoxhiScanner:
    """Cùng giao diện với gpu_name_scanner.NameScanner.scan()."""

    def scan(self, text, existing_glossary=None, max_results=250, on_progress=None, dictionary=None,
             reading=None):
        progress = on_progress or (lambda message: None)
        if not text.strip() or max_results <= 0:
            return []
        with _LOCK:
            return self._scan(text, existing_glossary or (), max_results, progress, dictionary or {}, reading)

    def _scan(self, text, glossary, limit, progress, dictionary, reading):
        session = _load(progress)
        device = session.device.upper()
        sentences = split_sentences(text)
        progress(f'Moxhi {device}: tìm tên trong {len(sentences)} câu…')
        found = {}
        per_sentence = session.source_names([text[a:b] for a, b in sentences])
        for (a, _), spans in zip(sentences, per_sentence):
            for s, e, kind, score in spans:
                name = text[a + s:a + e]
                if keep_candidate(name, score):
                    key = (a + s, a + e, kind)
                    found[key] = max(score, found.get(key, 0))
        resolved = resolve_spans(found, text, saved_spans(text, glossary))
        scores = {(s, e, k): sc for s, e, k, sc in resolved}
        from_dictionary = set()
        if dictionary:
            snapped = snap_spans(text, dictionary, set(scores))
            from_dictionary = {span for span in snapped if span not in scores}
            resolved = [(s, e, k, scores.get((s, e, k), 0.95)) for s, e, k in sorted(snapped)]

        entities, sentence_names = {}, defaultdict(list)
        starts = [a for a, _ in sentences]
        import bisect
        for s, e, kind, score in resolved:
            name = text[s:e]
            entry = entities.setdefault(name, dict(
                cn=name, type=TYPES.get(kind, 'PERSON'), confidence=0, count=0, contexts=[],
                signals=[f'Moxhi NER / {device}'], suggested_vi='', moxhi_vi='', _kinds=Counter()))
            entry['count'] += 1
            entry['confidence'] = max(entry['confidence'], score)
            entry['_kinds'][kind] += 1
            if (s, e, kind) in from_dictionary and 'Từ điển tên' not in entry['signals']:
                entry['signals'].append('Từ điển tên')
            if len(entry['contexts']) < 3:
                entry['contexts'].append(text[max(0, s - 45):min(len(text), e + 45)])
            sentence_names[bisect.bisect_right(starts, s) - 1].append((s, kind, name))

        ranked = sorted(entities.values(), key=lambda v: (-v['count'], -v['confidence'], v['cn']))[:limit]
        self._fill_vietnamese(session, text, sentences, sentence_names, ranked, reading, progress, device)
        for entry in ranked:
            kinds = entry.pop('_kinds')
            entry['type'] = TYPES.get(kinds.most_common(1)[0][0], entry['type'])
        ranked = trim_edges(ranked, reading, text)
        progress(f'Moxhi {device} hoàn tất.')
        return ranked

    def _fill_vietnamese(self, session, text, sentences, sentence_names, ranked, reading, progress, device):
        """Dịch vài câu chứa mỗi tên, lấy tên Việt từ thẻ trong bản dịch."""
        wanted = {e['cn'] for e in ranked}
        picked, need = [], Counter()
        # Ưu tiên câu ngắn: dịch nhanh và ghép tên ít nhầm.
        order = sorted(sentence_names, key=lambda i: sentences[i][1] - sentences[i][0])
        for i in order:
            names = {n for _, _, n in sentence_names[i] if n in wanted}
            if any(need[n] < TRANSLATE_PER_NAME for n in names):
                picked.append(i)
                need.update(names)
            if len(picked) >= (MAX_TRANSLATIONS if session.device == 'cuda' else CPU_MAX_TRANSLATIONS):
                break
        if not picked:
            return
        votes = defaultdict(Counter)
        done = 0
        for first in range(0, len(picked), 64):
            group = picked[first:first + 64]
            outputs = session.translate([text[sentences[i][0]:sentences[i][1]] for i in group],
                                        beams=4 if session.device == 'cuda' else CPU_BEAMS)
            for i, vi_names in zip(group, outputs):
                cn_names = [(k, n) for _, k, n in sorted(sentence_names[i])]
                for cn, vi in align_names(cn_names, vi_names, reading).items():
                    votes[cn][vi] += 1
            done += len(group)
            progress(f'Moxhi {device}: dịch tên {done}/{len(picked)} câu…')
        for entry in ranked:
            if votes[entry['cn']]:
                entry['moxhi_vi'] = votes[entry['cn']].most_common(1)[0][0]
                entry['suggested_vi'] = entry['moxhi_vi']


# ───────────────────────── làm sạch và gộp ─────────────────────────
# Chữ hư hay dính vào mép tên khi model gán nhãn cả mảnh BPE (和小龙, 太浩宗内, 韩立在).
EDGE_CHARS = set('和与跟同对向在从被把给让叫将及或的了着过是也都就还又才便却内外里上下中前后旁边')


def _merge_into(target, other):
    target['count'] += other['count']
    target['confidence'] = max(target['confidence'], other['confidence'])
    for signal in other.get('signals', []):
        if signal not in target['signals']:
            target['signals'].append(signal)
    for ctx in other.get('contexts', []):
        if len(target['contexts']) < 3 and ctx not in target['contexts']:
            target['contexts'].append(ctx)
    for key in ('moxhi_vi', 'suggested_vi'):
        if not target.get(key) and other.get(key):
            target[key] = other[key]


def trim_edges(candidates, reading=None, text=''):
    """Cắt chữ dính mép tên.

    - Theo bản dịch: âm Hán-Việt của tên bỏ 1 chữ đầu/cuối khớp đúng tên Việt Moxhi đã dịch.
    - Theo chữ hư: bỏ 1 chữ hư ở mép khi phần còn lại cũng là ứng viên (xuất hiện riêng ở chỗ khác).
    Ứng viên trùng tên sau khi cắt được gộp lại (cộng số lần, giữ điểm cao nhất).
    """
    by_cn = {c['cn']: c for c in candidates}
    renamed = {}
    for c in candidates:
        cn = c['cn']
        if len(cn) < 3:
            continue
        options = [cn[1:], cn[:-1]]
        new = None
        vi = fold(c.get('moxhi_vi') or '')
        if reading and vi and fold(reading(cn) or '') != vi:
            new = next((o for o in options if fold(reading(o) or '') == vi), None)
        if new is None:
            if cn[0] in EDGE_CHARS and cn[1:] in by_cn:
                new = cn[1:]
            elif cn[-1] in EDGE_CHARS and cn[:-1] in by_cn:
                new = cn[:-1]
        if new:
            renamed[cn] = new
    if not renamed:
        return candidates
    out = {}
    for c in candidates:
        cn = renamed.get(c['cn'], c['cn'])
        if cn != c['cn']:
            # Các lần "和小龙" và các lần "小龙" đứng riêng là những vị trí khác nhau → cộng dồn được.
            c = dict(c, cn=cn, contexts=list(c.get('contexts', [])), signals=list(c.get('signals', [])))
        if cn in out:
            _merge_into(out[cn], c)
        else:
            out[cn] = c
    return sorted(out.values(), key=lambda v: (-v['count'], -v['confidence'], v['cn']))


AGREE = 'BERT + Moxhi cùng thấy'


def merge_candidates(bert, moxhi):
    """Gộp kết quả hai bộ quét theo chữ Hán. Tên cả hai cùng thấy được gắn tín hiệu AGREE;
    loại tên lấy theo Moxhi (có thêm ITEM); số lần lấy lớn nhất (cùng một văn bản)."""
    out = {}
    for c in bert or []:
        out[c['cn']] = dict(c, signals=list(c.get('signals', [])), contexts=list(c.get('contexts', [])))
    for c in moxhi or []:
        if c['cn'] not in out:
            out[c['cn']] = dict(c, signals=list(c.get('signals', [])), contexts=list(c.get('contexts', [])))
            continue
        entry = out[c['cn']]
        entry['count'] = max(entry['count'], c['count'])
        entry['confidence'] = max(entry['confidence'], c['confidence'])
        entry['type'] = c['type']
        entry['moxhi_vi'] = c.get('moxhi_vi', '')
        for ctx in c.get('contexts', []):     # giữ cả ngữ cảnh mẫu của Moxhi (tối đa 3)
            if len(entry['contexts']) < 3 and ctx not in entry['contexts']:
                entry['contexts'].append(ctx)
        for signal in c.get('signals', []) + [AGREE]:
            if signal not in entry['signals']:
                entry['signals'].append(signal)
    merged = trim_edges(list(out.values()))
    return sorted(merged, key=lambda v: (-(AGREE in v['signals']), -v['count'], -v['confidence'], v['cn']))


def preload(on_progress=None):
    with _LOCK:
        _load(on_progress or (lambda message: None))


if __name__ == '__main__':
    # python moxhi_scanner.py          -> tải/kiểm tra model
    # python moxhi_scanner.py --test   -> quét thử một đoạn
    sys.stdout.reconfigure(encoding='utf-8')
    print('Model:', install_model(print, force='--force' in sys.argv))
    if '--test' in sys.argv:
        sample = '慕云烟是落云宗的长老，她来自天南城。韩立呈上青冥剑。慕云烟点了点头，韩立退下。'
        for item in MoxhiScanner().scan(sample, on_progress=print):
            print(item['cn'], item['type'], round(item['confidence'], 3), item['count'], item['moxhi_vi'])
