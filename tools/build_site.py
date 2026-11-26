"""Dựng bản deploy GitHub Pages vào thư mục _site: chỉ code và giao diện của trang.

Truyện (library/<truyện>/…, stories/<truyện>/…, các danh mục) không nằm trong git nữa: app trên
máy đẩy thẳng lên Cloudflare R2 (r2_store.py) và trang đọc qua Worker (cloudflare/worker.js).
Mọi trang truyện/chương do 404.html dựng từ khung library/story.html, library/chapter.html, reader.html.

Script chỉ chép các file web đang được git theo dõi, bỏ file dev (exe, mã Python, test…), và dừng
với thông báo rõ ràng nếu bản deploy vượt giới hạn 1 GB của GitHub Pages.

Chạy:  python tools/build_site.py [thư_mục_ra]   (mặc định _site)
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT_MB = 1000      # giới hạn cứng của GitHub Pages
WARN_MB = 800

EXCLUDE_DIRS = {'.github', '.claude', '.commandcode', 'cloudflare', 'dist', 'docs', 'tests', 'tools', 'models',
                'build', '.archify', '_site', '_data'}
EXCLUDE_EXT = {'.py', '.pyc', '.spec', '.bat', '.cfg', '.md', '.txt', '.log'}
EXCLUDE_FILES = {'.gitignore', 'names.json', 'editor_config.json', 'package.json', 'package-lock.json',
                 'test-paths.html', 'debug.html'}


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


def main(out_dir):
    out_dir = os.path.abspath(out_dir)
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    total = count = 0
    for path in tracked_files():
        src = os.path.join(ROOT, path)
        if excluded(path) or not os.path.isfile(src):
            continue
        dst = os.path.join(out_dir, path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        total += os.path.getsize(dst)
        count += 1
    mb = total / 1e6
    print(f'{count} file · Pages {mb:.1f} MB · giới hạn {LIMIT_MB} MB · đã dùng {mb / LIMIT_MB:.0%}')
    if mb > LIMIT_MB:
        print(f'::error::Bản deploy {mb:.0f} MB vượt giới hạn {LIMIT_MB} MB của GitHub Pages.')
        return 1
    if mb > WARN_MB:
        print(f'::warning::Bản deploy đã {mb:.0f}/{LIMIT_MB} MB.')
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')   # console Windows cp1252
    except Exception:
        pass
    parser = argparse.ArgumentParser(description='Dựng bản deploy GitHub Pages.')
    parser.add_argument('out_dir', nargs='?', default=os.path.join(ROOT, '_site'))
    sys.exit(main(parser.parse_args().out_dir))
