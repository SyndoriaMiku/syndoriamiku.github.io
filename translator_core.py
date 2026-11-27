"""Phần xử lý của trình dịch (không dính giao diện): cấu hình, nháp, gọi API dịch, name, quét tên.

Dùng chung cho builder.py (Tk) và builder_qt.py (Qt). Không import tkinter/Qt ở đây.
"""
import base64  # noqa: F401  (giữ cho code cũ import qua builder)
import datetime
import json
import os
import re
import sys
import time
import unicodedata


from name_glossary import (update_name_cfg, compile_name_source_pattern, compile_name_loose_pattern,
                           substitute_names, fix_name_spacing, normalize_entries)
import library_store as store
from library_store import read_catalog, write_catalog

try:
    import han_viet as _hv
    _HAN_VIET_OK = True
except ImportError:
    _hv = None
    _HAN_VIET_OK = False

try:
    from gpu_name_scanner import NameScanner as _NameScanner
    from gpu_name_scanner import is_installed as _ner_installed, preload_in_background as _ner_preload
    _NAME_SCANNER_OK = True
except ImportError:
    _NameScanner = _ner_installed = _ner_preload = None
    _NAME_SCANNER_OK = False

try:  # MoxhiMT-30-Tag: cùng model với trang moxhi-tag.pages.dev (quét tên + cho sẵn tên tiếng Việt)
    import moxhi_scanner as _moxhi
    _MOXHI_OK = True
except ImportError:
    _moxhi = None
    _MOXHI_OK = False


# --- XÁC ĐỊNH THƯ MỤC GỐC ---
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    if os.path.basename(BASE_DIR).lower() == 'dist':
        BASE_DIR = os.path.dirname(BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- CẤU HÌNH API ---
API_URL = "https://comic.sangtacvietcdn.xyz/tsm.php?cdn=/"
CHUNK_LIMIT = 20000
DELAY = 1.2
CONFIG_PATH = os.path.join(BASE_DIR, "editor_config.json")
STORIES_DIR = os.path.join(BASE_DIR, "stories")
LIBRARY_DIR = os.path.join(BASE_DIR, "library")
LIBRARY_CATALOG = os.path.join(LIBRARY_DIR, "list.json")
DRAFT_DIR = os.path.join(BASE_DIR, ".drafts")

# Bảng màu dùng chung
BG, PANEL, FIELD, MUTED, TEXT = "#15130f", "#1e1b17", "#29251f", "#a39887", "#e6dfd2"

# Ký tự Hán chưa dịch, ký tự lỗi Unicode � và dòng API lỗi
TRANSLATION_ERROR_RE = re.compile(r'[㐀-䶿一-鿿�]|\[Lỗi dịch\]')


def name_cfg_path():
    """name.cfg sits next to the exe when frozen, else next to this file."""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "name.cfg")
    return os.path.join(BASE_DIR, "name.cfg")


def draft_path(slug):
    return os.path.join(DRAFT_DIR, f"{slug}.json")


def write_draft(title, slug, cn_lines, vi_lines):
    store.write_json_atomic(draft_path(slug), {
        "title": title, "slug": slug, "cn": list(cn_lines), "vi": list(vi_lines),
        "time": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
    })


def remove_draft(slug):
    try:
        os.remove(draft_path(slug))
    except OSError:
        pass


def read_draft(path):
    """(title, slug, cn, vi, time) của một file nháp; ValueError nếu hỏng."""
    with open(path, "r", encoding="utf-8") as f:
        draft = json.load(f)
    cn, vi = draft["cn"], draft["vi"]
    if len(cn) != len(vi):
        raise ValueError("số đoạn Trung/Việt không khớp")
    title = draft.get("title") or os.path.splitext(os.path.basename(path))[0]
    slug = draft.get("slug") or slugify_vn(title)
    return title, slug, cn, vi, draft.get("time", "")


def estimate_chunks(lines, limit=CHUNK_LIMIT):
    """Same grouping rule as run_process (before name substitution)."""
    chunks, current = 0, 0
    for line in lines:
        added = len(line) + (1 if current else 0)
        if current and current + added > limit:
            chunks += 1
            current = len(line)
        else:
            current += added
    return chunks + (1 if current else 0)


def counter_text(content):
    """Dòng đếm ký tự/đoạn/đợt API/thời gian ước lượng cho ô nội dung ("" khi trống)."""
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    if not lines:
        return ""
    chars = sum(len(line) for line in lines)
    chunks = estimate_chunks(lines)
    # ~ 1 lần gọi API mỗi đợt + DELAY; con số chỉ để ước lượng.
    seconds = chunks * (DELAY + 4)
    eta = f"~{seconds // 60:.0f} phút" if seconds >= 90 else f"~{seconds:.0f} giây"
    return f"{chars:,} ký tự · {len(lines):,} đoạn · {chunks} đợt API · {eta}".replace(",", ".")


def split_translation(lines, limit=CHUNK_LIMIT):
    """Group (orig, replaced) lines into API chunks of <= limit characters."""
    chunks, group, length = [], [], 0
    for orig_line, rep_line in lines:
        added = len(rep_line) + (1 if group else 0)
        if not group or length + added <= limit:
            group.append((orig_line, rep_line))
            length += added
        else:
            chunks.append(group)
            group, length = [(orig_line, rep_line)], len(rep_line)
    if group:
        chunks.append(group)
    return chunks


def load_config():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_config(data):
    try:
        existing = load_config()
        existing.update(data)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def slugify_vn(text):
    """Convert a Vietnamese (or any) title into a URL-friendly slug."""
    _vn_map = str.maketrans("đĐ", "dD")
    text = text.translate(_vn_map)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text


def compile_name_pattern(vi_names):
    names = sorted(set(n.strip() for n in vi_names if n and n.strip()), key=len, reverse=True)
    return re.compile(r'(?<!\w)(?:' + '|'.join(map(re.escape, names)) + r')(?!\w)') if names else None


def fix_capitalization_after_names(text: str, vi_names: list, name_pattern=None) -> str:
    """
    Hạ chữ hoa sai sau tên riêng hoặc ký tự ẩn giữa câu do API giữ lại.
    Không hạ chữ hoa nếu chuỗi tiếp theo là khởi đầu của một Tên riêng khác trong từ điển.
    """
    if not text:
        return text

    # Khớp tên dài trước, đúng ranh giới từ để không sửa bên trong tên khác.
    matches = []
    pattern = name_pattern if name_pattern is not None else compile_name_pattern(vi_names)
    if pattern is not None:
        matches = list(pattern.finditer(text))
    name_starts = {match.start() for match in matches}
    candidates = {}
    horizontal_space = r'[^\S\r\n\v\f\x85  ]'
    invisible = r'[​-‍⁠﻿]'
    separator = rf'(?:{horizontal_space}|{invisible})'
    following_pattern = re.compile(separator + r'+(\w+)')
    for match in matches:
        # API có thể giữ ký tự ẩn từ bản gốc giữa tên và từ tiếp theo
        # (đặc biệt ZWNJ U+200C). Giữ các ký tự này, chỉ sửa chữ hoa.
        # Không đi qua dấu câu hoặc xuống dòng (đầu câu mới).
        following = following_pattern.match(text, match.end())
        if not following:
            continue
        start = following.start(1)
        word = following.group(1)
        candidates[start] = word

    # Một tên có thể được API dịch khác config ("mây thư"), hoặc không có
    # trong config. Ký tự ẩn vẫn có thể làm API viết hoa nhầm từ tiếp theo.
    # Yêu cầu trước khoảng phân cách là một ký tự từ: không vượt qua dấu
    # kết câu, dấu mở lời thoại hay xuống dòng.
    hidden_boundary = re.compile(rf'(?<=\w){horizontal_space}*{invisible}{separator}*(\w+)')
    for match in hidden_boundary.finditer(text):
        candidates[match.start(1)] = match.group(1)

    edits = []
    for start, word in sorted(candidates.items()):
        if start in name_starts:
            continue
        # Giữ nguyên từ viết tắt như VIP, FBI.
        if word.istitle() and not (word.isupper() and len(word) > 1):
            edits.append((start, start + len(word), word.lower()))

    parts = []
    cursor = 0
    for start, end, replacement in edits:
        parts.extend((text[cursor:start], replacement))
        cursor = end
    parts.append(text[cursor:])
    return ''.join(parts)


def prepare_name_updates(vi_lines, wrong, right, vi_names):
    """Compute changed lines only; safe to run without accessing Tk widgets."""
    if not wrong:
        return []
    wrong_pattern = re.compile(re.escape(wrong), re.IGNORECASE)
    name_pattern = compile_name_pattern(vi_names)
    spacing_pattern = compile_name_loose_pattern([right])
    updates = []
    for index, original in enumerate(vi_lines):
        if not wrong_pattern.search(original):
            continue
        translated = wrong_pattern.sub(lambda match: right, original)
        translated = unicodedata.normalize('NFC', translated)
        translated = fix_name_spacing(translated, spacing_pattern)
        translated = fix_capitalization_after_names(translated, vi_names, name_pattern)
        if translated != original:
            updates.append((index, translated))
    return updates


def clean_vi_line(vi_line):
    """Bỏ dấu cách kép, chuẩn hoá NFC (dùng khi ghi data.json)."""
    return unicodedata.normalize('NFC', re.sub(r'  +', ' ', unicodedata.normalize('NFC', vi_line)).strip())


def story_data(title, cn_lines, vi_lines):
    """Nội dung stories/<slug>/data.json (base64 từng đoạn)."""
    return {"title": title, "content": [
        {"cn": store.b64(unicodedata.normalize('NFC', cn)), "vi": store.b64(clean_vi_line(vi))}
        for cn, vi in zip(cn_lines, vi_lines)]}


def update_story_catalog(title, slug):
    """Thêm/cập nhật truyện ngắn trong stories/list.json (ghi qua write_catalog → tự đẩy R2)."""
    catalog_path = os.path.join(STORIES_DIR, "list.json")
    os.makedirs(STORIES_DIR, exist_ok=True)
    catalog = read_catalog(catalog_path)  # lỗi đọc -> CatalogError, không ghi đè
    existing = next((item for item in catalog if item.get('slug') == slug), None)
    now = datetime.datetime.now()
    if not existing:
        catalog.append({"title": title, "slug": slug, "date": now.strftime("%d/%m/%Y"), "timestamp": now.timestamp()})
    else:
        existing['date'] = now.strftime("%d/%m/%Y")
        existing['timestamp'] = now.timestamp()
    write_catalog(catalog_path, catalog)


def is_sure_candidate(c):
    """Nhóm "Chắc chắn" của Scan Names: lặp lại nhiều / tên ≥2 chữ điểm cao / có trong từ điển."""
    # Tên ≥2 chữ điểm rất cao là tên thật dù chỉ xuất hiện 1 lần (nhân vật phụ);
    # nhiễu thường là họ 1 chữ đứng riêng hoặc từ thường điểm thấp.
    multi = len(c['cn']) >= 2
    return (c['count'] >= 3
            or (multi and (c['confidence'] >= 0.95 or (c['count'] >= 2 and c['confidence'] >= 0.85)))
            or any('Từ điển' in s or 'cùng thấy' in s for s in c.get('signals', [])))


def candidate_rank(c):
    import math
    return c['confidence'] * (1 + math.log2(c['count']))


def parse_ranges(text):
    """'41-60', '1-5, 8' → tập số; ValueError(phần không hiểu)."""
    chosen = set()
    for part in re.split(r"[,;\s]+", text.strip()):
        if not part:
            continue
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not match:
            raise ValueError(part)
        a, b = int(match.group(1)), int(match.group(2) or match.group(1))
        chosen.update(range(min(a, b), max(a, b) + 1))
    return chosen


class TranslatorCore:
    """Trạng thái + thao tác không giao diện của trình dịch. Lớp giao diện kế thừa và
    định nghĩa ``report_status(text)`` (an toàn khi gọi từ luồng nền)."""

    def __init__(self):
        # Name tạm: chỉ dùng cho lượt dịch hiện tại, không ghi name.cfg,
        # tự xoá sau khi lưu data.json / lưu vào thư viện.
        self.temp_names = {}

    def report_status(self, text):  # luồng nền gọi; lớp giao diện đẩy về luồng chính
        pass

    # ── name ──

    def load_name_config(self):
        cfg_path = name_cfg_path()
        if not os.path.exists(cfg_path):
            try:
                with open(cfg_path, "w", encoding="utf-8") as f:
                    f.write("# Thêm tên cần dịch cố định vào đây theo định dạng Trung=Việt, ví dụ:\n")
                    f.write("# 轩辕=Hiên Viên\n")
            except Exception as e:
                print(f"Lỗi khi tạo file name.cfg: {e}")

        name_dict = {}
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8-sig") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            cn, vi = line.split("=", 1)
                            if cn.strip() and vi.strip():
                                name_dict[unicodedata.normalize('NFC', cn.strip())] = unicodedata.normalize('NFC', vi.strip())
            except Exception as e:
                print(f"Lỗi khi đọc file name.cfg: {e}")
        return name_dict

    def effective_names(self, temp_names=None):
        """name.cfg + name tạm (name tạm thắng khi trùng chữ Hán)."""
        names = self.load_name_config()
        names.update(self.temp_names if temp_names is None else temp_names)
        return names

    def merge_temp_names(self, entries):
        """Thêm name tạm; ValueError nếu không hợp lệ."""
        self.temp_names.update(normalize_entries(entries))

    def save_names_to_cfg(self, entries):
        """Ghi name.cfg (một lần thay file nguyên tử) rồi bỏ name tạm cùng chữ Hán. Ném lỗi nếu hỏng."""
        update_name_cfg(name_cfg_path(), entries)
        for cn, _vi in entries:
            self.temp_names.pop(unicodedata.normalize('NFC', cn.strip()), None)

    # ── dịch ──

    def translate_api(self, text):
        import requests   # chỉ cần khi gọi API (CI chạy test không cài requests)
        headers = {"Origin": "https://www.bilibili.com", "Referer": "https://www.bilibili.com/", "User-Agent": "Mozilla/5.0"}
        try:
            res = requests.post(API_URL, data={"sajax": "trans", "content": text}, headers=headers, timeout=45)
            if res.status_code == 200:
                # Normalize NFC ngay khi nhận response để đảm bảo ký tự tiếng Việt đúng chuẩn
                return unicodedata.normalize('NFC', res.text.strip())
            return None
        except Exception:
            return None

    def translate_lines(self, lines, cancel=None):
        """Keep each translated paragraph paired with its original input line (worker thread)."""
        if not lines:
            return []
        cancelled = (lambda: cancel is not None and cancel.is_set())
        translate = self.translate_api
        result = translate("\n".join(lines))
        if not result and not cancelled():
            time.sleep(3)
            result = translate("\n".join(lines))
        if not result:
            return ["[Lỗi dịch]"] * len(lines)

        translated = result.splitlines()
        if len(translated) == len(lines):
            return translated
        if len(lines) == 1:
            # Multiple output lines still belong to the same source paragraph.
            return [" ".join(translated)]

        # Never truncate extra lines or silently shift the CN/VI pairing.
        aligned = []
        for i, line in enumerate(lines):
            if cancelled():
                aligned.extend(["[Lỗi dịch]"] * (len(lines) - i))
                break
            self.report_status(f"API trả lệch số dòng — đang dịch riêng {i + 1}/{len(lines)}...")
            time.sleep(DELAY)
            reply = translate(line)
            if not reply:
                time.sleep(3)
                reply = translate(line)
            aligned.append(" ".join(reply.splitlines()) if reply else "[Lỗi dịch]")
        return aligned

    def translate_story(self, content, cancel, temp_names=None, on_progress=None):
        """Dịch cả bài (luồng nền). on_progress(done, total, started) trước mỗi đợt.
        Trả (cn_lines, vi_lines, tổng số đoạn); dừng sớm khi cancel được đặt."""
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        name_dict = self.effective_names(temp_names or {})
        source_pattern = compile_name_source_pattern(name_dict)
        processed_lines = [(line, substitute_names(line, name_dict, source_pattern)) for line in lines]

        chunks = split_translation(processed_lines)
        vi_names = list(name_dict.values())
        name_pattern = compile_name_pattern(vi_names)
        spacing_pattern = compile_name_loose_pattern(vi_names)
        final_cn_lines, final_vi_lines = [], []
        started = time.time()

        for i, group in enumerate(chunks):
            if cancel.is_set():
                break
            if on_progress:
                on_progress(i, len(chunks), started)
            vi_lines = self.translate_lines([rep for _, rep in group], cancel)
            for j, (orig_cn, _rep_cn) in enumerate(group):
                vi = vi_lines[j] if j < len(vi_lines) else ""
                vi = re.sub(r'  +', ' ', vi).strip()  # dấu cách kép do từ không dịch được
                vi = fix_name_spacing(vi, spacing_pattern)
                vi = fix_capitalization_after_names(vi, vi_names, name_pattern)
                final_cn_lines.append(orig_cn)
                final_vi_lines.append(vi)
            if i + 1 < len(chunks):
                cancel.wait(DELAY)
        return final_cn_lines, final_vi_lines, len(lines)

    # ── quét tên ──

    def _han_viet_table(self):
        """Bảng Hán-Việt = bảng có sẵn + âm học từ name.cfg; tính lại khi name.cfg đổi."""
        path = name_cfg_path()
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            stamp = None
        cached = getattr(self, "_han_viet_cache", None)
        if cached is None or cached[0] != stamp:
            self._han_viet_cache = (stamp, _hv.build_table(path))
        return self._han_viet_cache[1]

    def _suggest_vi(self, cn: str) -> str:
        """Gợi ý Hán-Việt cho tên; rỗng nếu còn chữ chưa biết âm."""
        if not _HAN_VIET_OK:
            return ""
        return _hv.han_viet_name(cn, self._han_viet_table())

    def scan_dictionary(self):
        """Mined name dictionary (names.json) so known phrases are snapped whole."""
        if not hasattr(self, "_scan_dictionary_cache"):
            self._scan_dictionary_cache = {}
            path = os.path.join(BASE_DIR, "names.json")
            try:
                with open(path, "r", encoding="utf-8") as stream:
                    self._scan_dictionary_cache = json.load(stream).get("entries", {})
            except (OSError, ValueError):
                self._scan_dictionary_cache = {}
        return self._scan_dictionary_cache

    def _scan_engines(self):
        """Bộ quét tên đang dùng: biến môi trường STV_SCAN_ENGINE hoặc "scan_engine" trong
        editor_config.json — "moxhi" (mặc định), "both" hoặc "bert". Đọc cấu hình một lần.

        Bộ được chọn mà không nạp được thì dùng bộ còn lại và ghi lý do vào self._scan_note
        (hiện trên thanh trạng thái sau khi quét) thay vì lặng lẽ đổi."""
        if not hasattr(self, '_scan_choice'):
            self._scan_choice = (os.environ.get('STV_SCAN_ENGINE') or load_config().get('scan_engine')
                                 or 'moxhi').strip().lower()
        wanted = {'both': ('moxhi', 'bert'), 'moxhi': ('moxhi',), 'bert': ('bert',)}.get(self._scan_choice)
        self._scan_note = ''
        if wanted is None:
            self._scan_note = f'scan_engine "{self._scan_choice}" không hợp lệ (both/moxhi/bert) — dùng both'
            wanted = ('moxhi', 'bert')
        available = {'moxhi': _MOXHI_OK, 'bert': _NAME_SCANNER_OK}
        engines = [name for name in wanted if available[name]]
        missing = [name for name in wanted if not available[name]]
        if not engines:
            engines = [name for name in ('moxhi', 'bert') if available[name]]
        if missing and engines:
            self._scan_note = (f'không nạp được bộ quét {"/".join(missing)} (thiếu file hoặc thư viện) — '
                               f'đã dùng {"/".join(engines)}')
        return engines

    def preload_name_model(self):
        """Chỉ nạp model đã có trên ổ đĩa, không tự tải khi khởi động (gọi ở luồng nền)."""
        engines = self._scan_engines()
        try:
            if 'bert' in engines and _ner_installed():
                _ner_preload()
        except Exception:
            pass
        if 'moxhi' in engines and _moxhi.is_installed():
            try:
                _moxhi.preload()
            except Exception:
                pass

    def scan_name_candidates(self, text: str, max_results: int = 2000, on_progress=None, temp_names=()) -> list:
        """Quét tên chữ Hán trên máy (CUDA/CPU): MoxhiMT-30-Tag và/hoặc BERT NER, rồi gộp kết quả."""
        engines = self._scan_engines()
        if not engines:
            raise RuntimeError("Không tải được bộ quét tên (moxhi_scanner.py / gpu_name_scanner.py). "
                               "Xem SCAN_NAMES.md để cài đặt.")
        glossary = set(self.load_name_config()) | set(temp_names)
        common = dict(existing_glossary=glossary, max_results=max_results, on_progress=on_progress,
                      dictionary=self.scan_dictionary())
        found = {}
        for engine in engines:
            if engine == 'moxhi':
                found['moxhi'] = _moxhi.MoxhiScanner().scan(text, reading=self._suggest_vi, **common)
            else:
                found['bert'] = _NameScanner().scan(text, **common)
        if len(found) == 2:
            results = _moxhi.merge_candidates(found['bert'], found['moxhi'])
        else:
            results = next(iter(found.values()))
        # suggested_vi được điền sau (Moxhi → Hán-Việt → API thường) khi đã có đủ ứng viên.
        for item in results:
            item['suggested_vi'] = ''
            item.setdefault('moxhi_vi', '')
        return results[:max_results]

    def _fill_name_suggestions_from_api(self, candidates):
        from name_suggestions import NameSuggestions
        if not hasattr(self, '_name_suggestions'):
            self._name_suggestions = NameSuggestions()

        def fetch(names):
            reply = self.translate_api('\n'.join(names))
            if not reply:
                raise RuntimeError('API dịch thường không trả kết quả.')
            return reply.splitlines()

        self._name_suggestions.fill(candidates, fetch, ('legacy', API_URL))
        return candidates

    def scan_names_with_suggestions(self, raw_text, temp_names, on_progress=None):
        """Quét + điền gợi ý (Moxhi → Hán-Việt → API). Trả (candidates, cảnh báo API hoặc None)."""
        candidates = self.scan_name_candidates(raw_text, on_progress=on_progress, temp_names=temp_names)
        api_warning = None
        try:
            candidates = self._fill_name_suggestions_from_api(candidates)
        except Exception as error:
            api_warning = str(error)
        for c in candidates:
            c['api_vi'] = c.get('suggested_vi', '')
            c['hanviet'] = self._suggest_vi(c['cn'])
            # Ưu tiên tên Moxhi dịch trong ngữ cảnh (khớp name.cfg ~90%); không có thì tên người
            # dùng Hán-Việt (đúng thói quen trong name.cfg), còn lại dùng API.
            if c.get('moxhi_vi'):
                c['suggested_vi'] = c['moxhi_vi']
            elif c['hanviet'] and (c['type'] == 'PERSON' or not c['api_vi']):
                c['suggested_vi'] = c['hanviet']
        return candidates, api_warning
