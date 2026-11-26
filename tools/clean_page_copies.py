"""Dọn các bản chép index.html cũ của từng truyện/chương (review Lần 5, B1).

Trước đây mỗi lần lưu, app chép khung trang vào library/<truyện>/index.html,
library/<truyện>/<chương>/index.html và stories/<truyện>/index.html. Giờ 404.html dựng mọi trang
nên các bản chép này thừa (không lên git, không lên R2).

Chỉ xoá index.html nằm đúng ở các vị trí trên; KHÔNG chạm library/index.html, stories/index.html,
khung library/story.html, library/chapter.html hay bất cứ file nào khác.

Chạy:  python tools/clean_page_copies.py           # chỉ liệt kê
       python tools/clean_page_copies.py --delete  # xoá thật
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERNS = (
    re.compile(r'^library/\d{6}/index\.html$'),
    re.compile(r'^library/\d{6}/\d{4}/index\.html$'),
    re.compile(r'^stories/[^/]+/index\.html$'),
)


def page_copies(root=ROOT):
    found = []
    for top in ('library', 'stories'):
        for dirpath, _dirs, files in os.walk(os.path.join(root, top)):
            if 'index.html' not in files:
                continue
            path = os.path.join(dirpath, 'index.html')
            rel = os.path.relpath(path, root).replace(os.sep, '/')
            if any(p.match(rel) for p in PATTERNS):
                found.append(path)
    return found


def main(delete):
    files = page_copies()
    size = sum(os.path.getsize(f) for f in files)
    print(f'{len(files)} bản chép index.html · {size / 1e6:.1f} MB')
    if not delete:
        print('Chỉ liệt kê. Thêm --delete để xoá.')
        return 0
    failed = 0
    for path in files:
        try:
            os.remove(path)
        except OSError as exc:
            failed += 1
            print('  không xoá được', path, exc)
    print(f'Đã xoá {len(files) - failed} file' + (f', {failed} lỗi' if failed else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    sys.exit(main('--delete' in sys.argv))
