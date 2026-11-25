"""Dựng bản deploy GitHub Pages gọn vào thư mục _site.

GitHub Pages giới hạn trang ở 1 GB. Repo chứa cả file chỉ dùng trên máy (exe, mã Python, test…) và
dữ liệu truyện dạng JSON base64 (rất tốn chỗ). Repo giữ nguyên định dạng đó — builder, editor và
trình sửa trên web không đổi gì. Chỉ bản deploy được biến đổi:

  1. chỉ chép file web (bỏ file dev, xem EXCLUDE_*);
  2. mỗi data.json → data.json.gz: chuỗi base64 đổi thành chữ thường có tiền tố "~", JSON không
     thụt lề, nén gzip (≈ 1/3 dung lượng). File data.json gốc không được deploy;
  3. chèn library/assets/chapter-data.js vào mọi trình đọc: tải .gz, giải nén trong trình duyệt,
     và shim atob để trình đọc cũ hiểu chuỗi "~chữ";
  4. trình đọc truyện ngắn cũ ($.getJSON('./data.json', ...)) được đổi sang ChapterData.jq(...).

Vượt LIMIT_MB thì dừng với thông báo rõ ràng thay vì để GitHub báo lỗi mơ hồ.

Kho dữ liệu ngoài (Cloudflare R2 + Worker, xem docs/STORAGE.md):
  --data-dir DIR   chép thêm mọi data.json.gz vào DIR (cùng đường dẫn) để workflow đồng bộ lên R2.
  --data-base URL  địa chỉ Worker. Khi có: trình duyệt đọc chương từ Worker và _site KHÔNG còn chứa
                   dữ liệu chương (bắt buộc kèm --data-dir). Không có: dữ liệu vẫn nằm trong _site.

Chạy:  python tools/build_site.py [thư_mục_ra] [--data-dir _data] [--data-base https://….workers.dev]
"""
import argparse
import base64
import binascii
import gzip
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT_MB = 1000      # giới hạn cứng của GitHub Pages
WARN_MB = 800        # cảnh báo sớm trong log Actions

EXCLUDE_DIRS = {'.github', '.claude', '.commandcode', 'cloudflare', '_data', 'dist', 'docs', 'tests', 'tools', 'models', 'build',
                '.archify', '_site'}
EXCLUDE_EXT = {'.py', '.pyc', '.spec', '.bat', '.cfg', '.md', '.txt', '.log'}
EXCLUDE_FILES = {'.gitignore', 'names.json', 'editor_config.json', 'package.json', 'package-lock.json',
                 'test-paths.html', 'debug.html'}

PLAIN_PREFIX = '~'
LOADER_SRC = '/library/assets/chapter-data.js'
LOADER_TAG = f'<script src="{LOADER_SRC}"></script>'
DATA_BASE_MARKER = "/*DATA_BASE*/''"
OLD_STORY_LOAD = "$.getJSON('./data.json', function (data) {"
NEW_STORY_LOAD = "ChapterData.jq('./data.json', function (data) {"


def tracked_files():
    # Gồm cả file mới chưa commit (không bị .gitignore) để chạy thử trên máy giống hệt CI.
    out = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                         cwd=ROOT, capture_output=True, check=True).stdout
    return [p for p in out.decode('utf-8').split('\0') if p]


def excluded(path):
    parts = path.split('/')
    if parts[0] in EXCLUDE_DIRS or '__pycache__' in parts:
        return True
    name = parts[-1]
    ext = os.path.splitext(name)[1].lower()
    if len(parts) == 1 and (name in EXCLUDE_FILES or ext in EXCLUDE_EXT):
        return True
    return ext in {'.py', '.pyc', '.exe'}


def plain(value):
    """base64 UTF-8 → '~chữ'. Chuỗi rỗng hoặc không phải base64 hợp lệ thì giữ nguyên."""
    if not isinstance(value, str) or not value:
        return value
    try:
        text = base64.b64decode(value, validate=True).decode('utf-8')
    except (binascii.Error, ValueError):
        return value
    return PLAIN_PREFIX + text


def compact_data(raw):
    """data.json (base64) → bytes gzip của JSON chữ thường."""
    data = json.loads(raw)
    for item in data.get('content') or []:
        if isinstance(item, dict):
            for key in ('cn', 'vi'):
                if key in item:
                    item[key] = plain(item[key])
    text = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return gzip.compress(text, compresslevel=9, mtime=0)


def needs_loader(raw):
    return b'data.json' in raw or b'/library/assets/reader.js' in raw


def patch_reader_html(raw):
    """Chèn bộ tải ngay sau <head> và đổi $.getJSON('./data.json') sang ChapterData.jq."""
    text = raw.decode('utf-8')
    text = text.replace(OLD_STORY_LOAD, NEW_STORY_LOAD)
    if LOADER_SRC not in text:
        i = text.lower().find('<head')
        j = text.find('>', i) + 1 if i >= 0 else 0
        text = text[:j] + LOADER_TAG + text[j:]
    return text.encode('utf-8')


def set_data_base(raw, data_base):
    """Điền địa chỉ Worker vào chapter-data.js."""
    text = raw.decode('utf-8')
    if DATA_BASE_MARKER not in text:
        raise SystemExit('chapter-data.js thiếu chỗ điền DATA_BASE')
    return text.replace(DATA_BASE_MARKER, json.dumps(data_base), 1).encode('utf-8')


def write_file(root, path, raw):
    dst = os.path.join(root, path)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'wb') as f:
        f.write(raw)


def main(out_dir, data_dir=None, data_base=''):
    data_base = (data_base or '').strip().rstrip('/')
    if data_base and not data_dir:
        raise SystemExit('--data-base cần kèm --data-dir (dữ liệu phải được đồng bộ lên kho ngoài)')
    if data_base and not data_base.startswith('https://'):
        raise SystemExit(f'--data-base phải là địa chỉ https://, nhận được: {data_base!r}')
    out_dir = os.path.abspath(out_dir)
    data_dir = os.path.abspath(data_dir) if data_dir else None
    for d in (out_dir, data_dir):
        if d and os.path.isdir(d):
            shutil.rmtree(d)
    before = after = data_after = count = data_count = 0
    for path in tracked_files():
        src = os.path.join(ROOT, path)
        if excluded(path) or not os.path.isfile(src):
            continue
        with open(src, 'rb') as f:
            raw = f.read()
        before += len(raw)
        name = os.path.basename(path)
        if name == 'data.json':
            try:
                raw = compact_data(raw)
            except ValueError as e:
                if data_base:
                    raise SystemExit(f'data.json hỏng, không đưa lên kho ngoài được: {path}: {e}')
                print(f'  ! giữ nguyên {path}: {e}', file=sys.stderr)
            else:
                path += '.gz'
                data_after += len(raw)
                data_count += 1
                if data_dir:
                    write_file(data_dir, path, raw)
                if data_base:
                    continue          # chương được phục vụ từ Worker, không đưa vào Pages
        elif name.endswith('.html') and needs_loader(raw) and path != 'library/editor.html':
            raw = patch_reader_html(raw)
        elif path == 'library/assets/chapter-data.js' and data_base:
            raw = set_data_base(raw, data_base)
        write_file(out_dir, path, raw)
        after += len(raw)
        count += 1

    mb = after / 1e6
    where = f'kho ngoài {data_base}' if data_base else 'trong Pages'
    print(f'{count} file · nguồn {before / 1e6:.1f} MB → Pages {mb:.1f} MB · giới hạn {LIMIT_MB} MB · '
          f'đã dùng {mb / LIMIT_MB:.0%}')
    print(f'Dữ liệu chương: {data_count} file, {data_after / 1e6:.1f} MB ({where})'
          + (f' · đã chép vào {data_dir}' if data_dir else ''))
    if mb > LIMIT_MB:
        print(f'::error::Bản deploy {mb:.0f} MB vượt giới hạn {LIMIT_MB} MB của GitHub Pages. '
              'Bật kho dữ liệu R2 (biến DATA_BASE) — xem docs/STORAGE.md.')
        return 1
    if mb > WARN_MB:
        print(f'::warning::Bản deploy đã {mb:.0f}/{LIMIT_MB} MB — nên bật kho dữ liệu R2 (docs/STORAGE.md).')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Dựng bản deploy GitHub Pages gọn.')
    parser.add_argument('out_dir', nargs='?', default=os.path.join(ROOT, '_site'))
    parser.add_argument('--data-dir', help='chép data.json.gz vào đây để đồng bộ lên R2')
    parser.add_argument('--data-base', default='', help='địa chỉ Worker; bỏ trống = dữ liệu nằm trong Pages')
    args = parser.parse_args()
    sys.exit(main(args.out_dir, args.data_dir, args.data_base))
