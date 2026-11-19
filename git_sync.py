"""Tự động commit và push nội dung truyện lên origin sau mỗi lần lưu.

builder.py và editor.py gọi autocommit_async() sau khi ghi xong truyện/chương.
Commit chạy ở luồng nền để git push không treo giao diện Tk.
"""
from __future__ import annotations

import os
import subprocess
import threading

COMMIT_MESSAGE = "`feat` add new stories"
# Chỉ đưa nội dung truyện lên; nháp, .bak, .commandcode... không thuộc commit này.
TRACKED_PATHS = ("library", "stories", "name.cfg")
GIT_TIMEOUT = 300
# pythonw không có console: chặn cửa sổ đen của git bật lên mỗi lần lưu.
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_sync_lock = threading.Lock()


class GitSyncError(RuntimeError):
    pass


def _git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT,
                            creationflags=_CREATE_NO_WINDOW)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise GitSyncError(f"git {args[0]} thất bại: {detail or result.returncode}")
    return result


def repo_root(path):
    """Thư mục gốc git chứa ``path``; None khi không phải repo (vd. thư mục test)."""
    if not path or not os.path.isdir(path):
        return None
    try:
        result = _git(path, "rev-parse", "--show-toplevel", check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def commit_and_push(base_dir, message=COMMIT_MESSAGE):
    """Stage, commit và push các đường dẫn truyện.

    Trả về short sha vừa commit, hoặc None khi không phải repo / không có gì đổi.
    """
    root = repo_root(base_dir)
    if root is None:
        return None
    paths = [name for name in TRACKED_PATHS if os.path.exists(os.path.join(root, name))]
    if not paths:
        return None
    # Chỉ stage và commit các đường dẫn truyện: thay đổi khác người dùng đã stage
    # (nếu có) không bị cuốn vào commit này.
    _git(root, "add", "-A", "--", *paths)
    if not _git(root, "status", "--porcelain", "--", *paths).stdout.strip():
        return None
    _git(root, "commit", "-m", message, "--", *paths)
    _git(root, "push", "origin", "HEAD")
    return _git(root, "rev-parse", "--short", "HEAD").stdout.strip()


def autocommit_async(base_dir, message=COMMIT_MESSAGE):
    """Chạy commit_and_push ở luồng nền; lỗi chỉ ghi ra console/studio.log."""
    def work():
        with _sync_lock:
            try:
                sha = commit_and_push(base_dir, message)
            except Exception as error:
                print(f"Git: không commit/push được — {error}")
                return
            if sha:
                print(f"Git: đã commit & push {sha} ({message})")

    threading.Thread(target=work, name="git-sync", daemon=True).start()
