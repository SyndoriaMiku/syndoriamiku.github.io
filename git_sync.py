"""Tự động commit và push nội dung truyện lên origin sau mỗi lần lưu.

library_store.write_catalog() gọi autocommit_async() sau mỗi lần lưu truyện/chương (builder và
editor đều lưu qua đó). Commit chạy ở luồng nền để git push không treo giao diện Tk.

- Push bị từ chối vì origin có commit mới (vd. sửa bằng trình sửa trên web): tự
  ``git pull --rebase --autostash`` rồi push lại một lần.
- Gặp ``index.lock`` (hai app cùng lưu, hoặc đang chạy git khác): đợi rồi thử lại.
- Kết quả và lỗi được báo cho app qua add_listener(), không chỉ in ra studio.log.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time

COMMIT_MESSAGE = "`feat` add new stories"
# Chỉ đưa nội dung truyện lên; nháp, .bak, .commandcode... không thuộc commit này.
TRACKED_PATHS = ("library", "stories", "name.cfg")
GIT_TIMEOUT = 300
# pythonw không có console: chặn cửa sổ đen của git bật lên mỗi lần lưu.
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

LOCK_RETRIES = 6          # ~ 9 giây chờ index.lock
LOCK_WAIT = 1.5

_sync_lock = threading.Lock()
_listeners = []


def add_listener(callback):
    """callback(message: str, ok: bool) — gọi từ luồng nền; app tự chuyển về luồng Tk."""
    if callback not in _listeners:
        _listeners.append(callback)


def remove_listener(callback):
    if callback in _listeners:
        _listeners.remove(callback)


def _notify(message, ok):
    print(message)
    for callback in list(_listeners):
        try:
            callback(message, ok)
        except Exception:
            pass


class GitSyncError(RuntimeError):
    pass


def _git(repo, *args, check=True):
    for attempt in range(LOCK_RETRIES + 1):
        result = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT,
                                creationflags=_CREATE_NO_WINDOW)
        # Tiến trình git khác (app thứ hai, editor của IDE…) đang giữ khoá: đợi rồi chạy lại.
        if result.returncode == 0 or "index.lock" not in (result.stderr or "") or attempt == LOCK_RETRIES:
            break
        time.sleep(LOCK_WAIT)
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
        # Không có gì mới, nhưng commit của lần push lỗi trước vẫn phải được đẩy lên.
        if not _ahead_of_origin(root):
            return None
        push(root)
        return _git(root, "rev-parse", "--short", "HEAD").stdout.strip()
    _git(root, "commit", "-m", message, "--", *paths)
    push(root)
    return _git(root, "rev-parse", "--short", "HEAD").stdout.strip()


def _ahead_of_origin(root):
    """Số commit ở máy chưa có trên origin (0 khi không xác định được nhánh trên origin)."""
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.strip()
    counted = _git(root, "rev-list", "--count", f"origin/{branch}..HEAD", check=False)
    try:
        return int(counted.stdout.strip()) if counted.returncode == 0 else 0
    except ValueError:
        return 0


def _rejected(result):
    text = (result.stderr or "") + (result.stdout or "")
    return any(key in text for key in ("[rejected]", "non-fast-forward", "fetch first", "Updates were rejected"))


def push(root):
    """Push HEAD; origin có commit mới thì rebase lên trên rồi push lại một lần.

    Commit trước đó đã nằm ở máy, nên lần lưu sau cũng đẩy luôn các commit còn tồn."""
    result = _git(root, "push", "origin", "HEAD", check=False)
    if result.returncode == 0:
        return
    if not _rejected(result):
        raise GitSyncError(f"git push thất bại: {(result.stderr or result.stdout).strip()}")
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    pulled = _git(root, "pull", "--rebase", "--autostash", "origin", branch, check=False)
    if pulled.returncode != 0:
        _git(root, "rebase", "--abort", check=False)
        raise GitSyncError("origin có thay đổi trùng chỗ, không tự gộp được — commit vẫn ở máy. "
                           f"Chạy git pull rồi git push bằng tay. ({(pulled.stderr or pulled.stdout).strip()})")
    _git(root, "push", "origin", "HEAD")


def autocommit_async(base_dir, message=COMMIT_MESSAGE):
    """Chạy commit_and_push ở luồng nền và báo kết quả qua add_listener().

    Luồng không phải daemon: đóng app ngay sau khi lưu thì Python vẫn đợi git commit/push xong
    (tối đa GIT_TIMEOUT mỗi lệnh) thay vì cắt ngang giữa chừng."""
    def work():
        with _sync_lock:
            try:
                sha = commit_and_push(base_dir, message)
            except Exception as error:
                _notify(f"⚠ Git: chưa đẩy được lên GitHub — {error}", False)
                return
            if sha:
                _notify(f"Git: đã commit & push {sha}", True)

    thread = threading.Thread(target=work, name="git-sync", daemon=False)
    thread.start()
    return thread
