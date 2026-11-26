"""Đồng bộ thư mục truyện (library/, stories/) lên Cloudflare R2 — thay cho commit/push truyện.

Mỗi lần lưu (library_store.write_catalog) gọi request_sync(): luồng nền so thư mục với sổ ghi
``.r2_manifest.json`` (những gì đã đẩy lên), rồi chỉ tải lên phần đổi và xoá phần đã mất.
Lần lưu lỗi (mất mạng…) sẽ tự được gửi lại ở lần đồng bộ sau, kể cả lần mở app sau.

Khoá trên R2 (trình đọc qua Worker cloudflare/worker.js):
  library/<truyện>/<chương>/data.json  → library/<truyện>/<chương>/data.json.gz (nén, chữ thường)
  stories/<truyện>/data.json           → stories/<truyện>/data.json.gz
  library/list.json, library/stories.json, library/<truyện>/chapters.json, stories/list.json → nguyên văn

Thông tin đăng nhập (khoá API R2, quyền Object Read & Write cho đúng bucket) nằm ngoài repo:
%APPDATA%\\StoryStudio\\r2.json, hoặc biến môi trường STV_R2_ACCOUNT_ID / STV_R2_ACCESS_KEY_ID /
STV_R2_SECRET_ACCESS_KEY / STV_R2_BUCKET.
"""
from __future__ import annotations

import base64
import binascii
import concurrent.futures
import datetime
import gzip
import hashlib
import hmac
import json
import os
import re
import tempfile
import threading
import time
import urllib.parse

MANIFEST = '.r2_manifest.json'
PLAIN_PREFIX = '~'
DATA_BASE = 'https://stv-data.lyralei2001.workers.dev'   # Worker đọc R2 (công khai, chỉ đọc)
WORKERS = 8
DEBOUNCE = 1.5          # giây: gom nhiều lần lưu liên tiếp thành một lần đồng bộ
MAX_AUTO_DELETE = 50    # xoá nhiều hơn mức này (và >5% số file) thì dừng, chờ người dùng xác nhận

CHAPTER_RE = re.compile(r'^library/\d{6}/\d{4}/data\.json$')
STORY_RE = re.compile(r'^stories/[A-Za-z0-9_.-]+/data\.json$')
CATALOG_RE = re.compile(r'^(library/(list|stories)\.json|library/\d{6}/chapters\.json|stories/list\.json)$')


# ───────────────────────── định dạng dữ liệu ─────────────────────────
def plain(value):
    """base64 UTF-8 → '~chữ' (rỗng hoặc không phải base64 thì giữ nguyên)."""
    if not isinstance(value, str) or not value:
        return value
    try:
        text = base64.b64decode(value, validate=True).decode('utf-8')
    except (binascii.Error, ValueError):
        return value
    return PLAIN_PREFIX + text


def unplain(value):
    """'~chữ' → base64 (ngược với plain)."""
    if isinstance(value, str) and value.startswith(PLAIN_PREFIX):
        return base64.b64encode(value[1:].encode('utf-8')).decode('ascii')
    return value


def compact_data(raw):
    """data.json (base64) → gzip của JSON chữ thường, không thụt lề (≈ 1/3 dung lượng)."""
    data = json.loads(raw)
    for item in data.get('content') or []:
        if isinstance(item, dict):
            for key in ('cn', 'vi'):
                if key in item:
                    item[key] = plain(item[key])
    text = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return gzip.compress(text, compresslevel=9, mtime=0)


def expand_data(gz_bytes):
    """Ngược với compact_data: bản trên R2 → data.json (base64) như builder ghi."""
    raw = gzip.decompress(gz_bytes) if gz_bytes[:2] == b'\x1f\x8b' else gz_bytes
    data = json.loads(raw)
    for item in data.get('content') or []:
        if isinstance(item, dict):
            for key in ('cn', 'vi'):
                if key in item:
                    item[key] = unplain(item[key])
    return data


def remote_key(rel):
    """Đường dẫn tương đối trong repo → (khoá R2, content-type), None nếu không đồng bộ file này."""
    if CHAPTER_RE.match(rel) or STORY_RE.match(rel):
        return rel + '.gz', 'application/gzip'
    if CATALOG_RE.match(rel):
        return rel, 'application/json; charset=utf-8'
    return None


def local_files(root):
    """{khoá R2: (đường dẫn tương đối, content-type)} của mọi file cần có trên R2."""
    out = {}
    for top in ('library', 'stories'):
        base = os.path.join(root, top)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            if os.path.relpath(dirpath, root).replace(os.sep, '/').count('/') >= 2:
                dirnames[:] = []   # library/<truyện>/<chương>: không còn thư mục con cần xét
            for name in filenames:
                if not name.endswith('.json'):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, '/')
                mapped = remote_key(rel)
                if mapped:
                    out[mapped[0]] = (rel, mapped[1])
    return out


def body_for(root, rel):
    with open(os.path.join(root, rel), 'rb') as fh:
        raw = fh.read()
    return compact_data(raw) if rel.endswith('/data.json') else raw


# ───────────────────────── thông tin đăng nhập ─────────────────────────
def config_path():
    base = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), '.config')
    return os.path.join(base, 'StoryStudio', 'r2.json')


def load_credentials():
    """dict(account_id, access_key_id, secret_access_key, bucket) hoặc None nếu chưa cấu hình."""
    creds = {}
    try:
        with open(config_path(), encoding='utf-8') as fh:
            creds = json.load(fh)
    except (OSError, ValueError):
        pass
    for key in ('account_id', 'access_key_id', 'secret_access_key', 'bucket'):
        env = os.environ.get('STV_R2_' + key.upper())
        if env:
            creds[key] = env
    creds = {k: str(v).strip() for k, v in creds.items() if v}
    if all(creds.get(k) for k in ('account_id', 'access_key_id', 'secret_access_key', 'bucket')):
        return creds
    return None


def save_credentials(account_id, access_key_id, secret_access_key, bucket):
    path = config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = dict(account_id=account_id.strip(), access_key_id=access_key_id.strip(),
                secret_access_key=secret_access_key.strip(), bucket=bucket.strip())
    _write_json_atomic(path, data)
    return path


# ───────────────────────── R2 (API tương thích S3, chữ ký SigV4) ─────────────────────────
def _hmac(key, msg):
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()


def sigv4_headers(method, host, path, query, headers, payload_hash, access_key, secret_key,
                  region='auto', service='s3', now=None):
    """Header Authorization theo AWS Signature V4. ``path`` đã được mã hoá URL."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime('%Y%m%dT%H%M%SZ')
    date = now.strftime('%Y%m%d')
    all_headers = {k.lower(): str(v).strip() for k, v in headers.items()}
    all_headers.update({'host': host, 'x-amz-date': amz_date, 'x-amz-content-sha256': payload_hash})
    signed = sorted(all_headers)
    canonical_headers = ''.join(f'{k}:{all_headers[k]}\n' for k in signed)
    canonical_query = '&'.join(
        f'{urllib.parse.quote(k, safe="-_.~")}={urllib.parse.quote(v, safe="-_.~")}'
        for k, v in sorted(query.items()))
    canonical = '\n'.join([method, path, canonical_query, canonical_headers, ';'.join(signed), payload_hash])
    scope = f'{date}/{region}/{service}/aws4_request'
    to_sign = '\n'.join(['AWS4-HMAC-SHA256', amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(('AWS4' + secret_key).encode(), date), region), service), 'aws4_request')
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    out = {k: v for k, v in all_headers.items() if k != 'host'}
    out['Authorization'] = (f'AWS4-HMAC-SHA256 Credential={access_key}/{scope}, '
                            f'SignedHeaders={";".join(signed)}, Signature={signature}')
    return out


class R2Error(RuntimeError):
    pass


class R2Client:
    def __init__(self, creds, session=None):
        self.creds = creds
        self.host = f"{creds['account_id']}.r2.cloudflarestorage.com"
        self._session = session          # chỉ để test; bình thường mỗi luồng một Session riêng
        self._local = threading.local()

    @property
    def http(self):
        # requests.Session không cam kết an toàn khi nhiều luồng dùng chung: mỗi luồng một Session.
        if self._session is not None:
            return self._session
        if not hasattr(self._local, 'session'):
            import requests
            self._local.session = requests.Session()
        return self._local.session

    def _request(self, method, key, body=b'', content_type=None, query=None):
        path = '/' + urllib.parse.quote(self.creds['bucket'], safe='') + ('/' + urllib.parse.quote(key, safe='/-_.~') if key else '')
        query = query or {}
        headers = {'content-type': content_type} if content_type else {}
        signed = sigv4_headers(method, self.host, path, query, headers, hashlib.sha256(body).hexdigest(),
                               self.creds['access_key_id'], self.creds['secret_access_key'])
        url = f'https://{self.host}{path}' + ('?' + urllib.parse.urlencode(sorted(query.items())) if query else '')
        for attempt in range(4):
            try:
                res = self.http.request(method, url, data=body or None, headers=signed, timeout=60)
            except Exception as exc:   # mạng chập chờn: thử lại
                if attempt == 3:
                    raise R2Error(f'{method} {key}: {exc}') from exc
            else:
                if res.status_code < 500 and res.status_code != 429:
                    break
                if attempt == 3:
                    break
            time.sleep(1.5 * (attempt + 1))
        if res.status_code >= 300 and not (method == 'DELETE' and res.status_code == 404):
            raise R2Error(f'{method} {key}: HTTP {res.status_code} {res.text[:300]}')
        return res

    def put(self, key, body, content_type):
        self._request('PUT', key, body, content_type)

    def delete(self, key):
        self._request('DELETE', key)

    def check(self):
        """Thử ghi rồi xoá một file nhỏ để kiểm tra khoá API."""
        key = '_stv_check.txt'
        self.put(key, b'ok', 'text/plain')
        self.delete(key)


# ───────────────────────── sổ ghi ─────────────────────────
def _write_json_atomic(path, data):
    folder = os.path.dirname(path) or '.'
    fd, temp = tempfile.mkstemp(prefix='.tmp-', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(temp, path)
    except BaseException:
        if os.path.exists(temp):
            os.remove(temp)
        raise


def load_manifest(root):
    try:
        with open(os.path.join(root, MANIFEST), encoding='utf-8') as fh:
            data = json.load(fh)
        return data.get('files', {}) if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_manifest(root, files):
    _write_json_atomic(os.path.join(root, MANIFEST), {'version': 1, 'files': files})


# ───────────────────────── đồng bộ ─────────────────────────
class SyncResult:
    def __init__(self):
        self.uploaded, self.deleted, self.skipped, self.errors, self.held_deletes = [], [], 0, [], []

    def summary(self):
        parts = []
        if self.uploaded:
            parts.append(f'đẩy {len(self.uploaded)} file')
        if self.deleted:
            parts.append(f'xoá {len(self.deleted)} file')
        if self.held_deletes:
            parts.append(f'giữ lại {len(self.held_deletes)} file chờ xác nhận xoá')
        if self.errors:
            parts.append(f'{len(self.errors)} lỗi')
        return ', '.join(parts) or 'không có gì thay đổi'


def _safe(callback):
    """Bọc callback báo tiến độ: nó lỗi (vd. print ra console cp1252) thì bỏ qua, không làm hỏng
    việc đang chạy — trước đây lỗi này bị tính là lỗi đẩy file và chặn luôn danh mục."""
    def call(message):
        if callback is None:
            return
        try:
            callback(message)
        except Exception:
            pass
    return call


def sync(root, client, progress=None, allow_mass_delete=False):
    """Đẩy phần chênh lệch giữa thư mục truyện và sổ ghi lên R2. Trả về SyncResult."""
    progress = _safe(progress)
    result = SyncResult()
    manifest = load_manifest(root)
    wanted = local_files(root)
    lock = threading.Lock()
    dirty = [0]

    todo = []
    for key, (rel, ctype) in wanted.items():
        try:
            st = os.stat(os.path.join(root, rel))
        except OSError:
            continue
        entry = manifest.get(key)
        if entry and entry[0] == st.st_size and entry[1] == st.st_mtime_ns:
            result.skipped += 1
            continue
        todo.append((key, rel, ctype, st))
    # Chương trước, danh mục sau: trang web không bao giờ thấy chương chưa có trên R2.
    todo.sort(key=lambda item: (item[1].endswith('data.json') is False, item[0]))

    def upload(item):
        key, rel, ctype, st = item
        body = body_for(root, rel)
        digest = hashlib.sha256(body).hexdigest()
        old = manifest.get(key)
        if not (old and old[2] == digest):
            client.put(key, body, ctype)
        with lock:
            manifest[key] = [st.st_size, st.st_mtime_ns, digest]
            if not (old and old[2] == digest):
                result.uploaded.append(key)
            else:
                result.skipped += 1
            dirty[0] += 1
            if dirty[0] % 200 == 0:
                save_manifest(root, manifest)
                progress(f'R2: đã đẩy {len(result.uploaded)}/{len(todo)} file…')

    data_items = [t for t in todo if t[1].endswith('data.json')]
    catalog_items = [t for t in todo if not t[1].endswith('data.json')]
    for batch in (data_items, catalog_items):
        if not batch:
            continue
        with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
            for item, future in [(i, pool.submit(upload, i)) for i in batch]:
                try:
                    future.result()
                except Exception as exc:
                    result.errors.append(f'{item[0]}: {exc}')
        if result.errors and batch is data_items:
            # Chương lỗi: hoãn danh mục chung và chapters.json của truyện có chương lỗi, để trang không
            # trỏ tới chương thiếu; chapters.json của truyện khác vẫn đẩy. Lần sau gửi lại phần lỗi.
            failed = {key.split('/')[1] for key in (e.split(':', 1)[0] for e in result.errors)
                      if key.startswith('library/')}
            catalog_items[:] = [t for t in catalog_items
                                if t[0].startswith('library/') and t[0].endswith('/chapters.json')
                                and t[0].split('/')[1] not in failed]

    gone = [key for key in manifest if key not in wanted]
    if gone and not result.errors:
        if len(gone) > MAX_AUTO_DELETE and len(gone) > 0.05 * max(len(manifest), 1) and not allow_mass_delete:
            result.held_deletes = gone
        else:
            for key in gone:
                try:
                    client.delete(key)
                    manifest.pop(key, None)
                    result.deleted.append(key)
                except Exception as exc:
                    result.errors.append(f'xoá {key}: {exc}')
    save_manifest(root, manifest)
    return result


def restore(root, base_url=DATA_BASE, session=None, progress=None, overwrite=False):
    """Tải toàn bộ truyện từ R2 (qua Worker) về thư mục ``root`` — dùng khi mất dữ liệu trên máy.

    Không cần khoá API. File đã có trên máy được giữ nguyên trừ khi overwrite=True.
    Một file thiếu/lỗi không làm dừng cả mẻ. Trả về (số file đã ghi, [lỗi])."""
    if session is None:
        import requests          # chỉ khi thật sự gọi mạng (test truyền session giả, CI không có requests)
        session = requests.Session()
    http = session
    progress = _safe(progress)
    errors = []
    headers = {'Origin': 'https://syndoriamiku.github.io'}

    def get(key):
        res = http.get(f'{base_url}/{key}', headers=headers, timeout=60)
        res.raise_for_status()
        return res.content

    def write(rel, data_bytes):
        path = os.path.join(root, rel)
        if os.path.exists(path) and not overwrite:
            return 0
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as fh:
            fh.write(data_bytes)
        return 1

    def attempt(label, func):
        try:
            return func()
        except Exception as exc:
            errors.append(f'{label}: {exc}')
            return None

    written = 0
    jobs = []
    library = attempt('library/list.json', lambda: json.loads(get('library/list.json'))) or []
    if library:
        written += write('library/list.json', json.dumps(library, ensure_ascii=False, indent=4).encode('utf-8'))
        written += attempt('library/stories.json', lambda: write('library/stories.json', get('library/stories.json'))) or 0
    for story in library:
        slug = story.get('slug', '')
        key = f'library/{slug}/chapters.json'
        written += attempt(key, lambda key=key: write(key, get(key))) or 0
        jobs += [f"library/{slug}/{c.get('id', '')}/data.json" for c in story.get('chapters', [])]
    shorts = attempt('stories/list.json', lambda: json.loads(get('stories/list.json'))) or []
    if shorts:
        written += write('stories/list.json', json.dumps(shorts, ensure_ascii=False, indent=4).encode('utf-8'))
    jobs += [f"stories/{s.get('slug', '')}/data.json" for s in shorts]

    def fetch(rel):
        if os.path.exists(os.path.join(root, rel)) and not overwrite:
            return 0
        def run():
            data = expand_data(get(rel + '.gz'))
            return write(rel, json.dumps(data, ensure_ascii=False).encode('utf-8'))
        return attempt(rel, run) or 0

    done = 0
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        for count in pool.map(fetch, jobs):
            written += count
            done += 1
            if done % 200 == 0:
                progress(f'R2: đã tải {done}/{len(jobs)} chương…')
    return written, errors


# ───────────────────────── chạy nền ─────────────────────────
_listeners = []
_state = {'thread': None, 'again': False, 'root': None}
_state_lock = threading.Lock()
_warned_unconfigured = [False]


def reset_unconfigured_warning():
    """Gọi sau khi lưu khoá: lần sau thiếu khoá (vd. xoá file cấu hình) sẽ được nhắc lại."""
    _warned_unconfigured[0] = False


def add_listener(callback):
    """callback(message: str, ok: bool) — gọi từ luồng nền; app tự chuyển về luồng Tk."""
    if callback not in _listeners:
        _listeners.append(callback)


def remove_listener(callback):
    if callback in _listeners:
        _listeners.remove(callback)


def _notify(message, ok):
    try:
        print(message)          # console cp1252 / stdout đã đóng: bỏ qua, vẫn báo cho app
    except Exception:
        pass
    for callback in list(_listeners):
        try:
            callback(message, ok)
        except Exception:
            pass


def project_root(path):
    """Thư mục chứa library/ và stories/ (đi ngược lên từ ``path``)."""
    path = os.path.abspath(path)
    for _ in range(4):
        if os.path.isdir(os.path.join(path, 'library')) or os.path.isdir(os.path.join(path, 'stories')):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return None


def app_root():
    """Thư mục của app (giống BASE_DIR trong builder.py): nơi duy nhất được đồng bộ lên R2."""
    import sys
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
        return os.path.dirname(base) if os.path.basename(base).lower() == 'dist' else base
    return os.path.dirname(os.path.abspath(__file__))


def _same_dir(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def request_sync(path):
    """Xin một lần đồng bộ ở luồng nền (gom các lần lưu liên tiếp). An toàn khi gọi nhiều lần.

    Chỉ đồng bộ thư mục của app: thư mục khác (test, bản sao…) không bao giờ được đẩy lên bucket thật."""
    root = project_root(path)
    if root is None or not _same_dir(root, app_root()):
        return None
    if os.environ.get('STV_R2_SYNC', '1') == '0':
        return None
    with _state_lock:
        _state['root'] = root
        if _state['thread'] and _state['thread'].is_alive():
            _state['again'] = True
            return _state['thread']
        thread = threading.Thread(target=_worker, name='r2-sync', daemon=True)
        _state['thread'] = thread
        thread.start()
        return thread


def _worker():
    try:
        _worker_loop()
    finally:
        with _state_lock:
            if _state['thread'] is threading.current_thread():
                _state['thread'] = None


def _worker_loop():
    while True:
        time.sleep(DEBOUNCE)
        with _state_lock:
            _state['again'] = False
            root = _state['root']
        try:
            _sync_once(root)
        except Exception as exc:     # không bao giờ để luồng chết im lặng
            _notify(f'⚠ R2: lỗi không mong đợi — {exc}', False)
        with _state_lock:
            if not _state['again']:
                # Bỏ đánh dấu luồng ngay trong khoá: yêu cầu đến sau đó sẽ mở luồng mới, không bị
                # gộp vào luồng sắp thoát rồi mất (review Lần 5, B2).
                if _state['thread'] is threading.current_thread():
                    _state['thread'] = None
                return


def _sync_once(root):
    creds = load_credentials()
    if not creds:
        if not _warned_unconfigured[0]:
            _warned_unconfigured[0] = bool(_listeners)   # chưa có app nghe thì lần sau nhắc lại
            _notify('⚠ R2: chưa cấu hình khoá API — truyện mới chỉ lưu trên máy, chưa lên web.', False)
    else:
        try:
            result = sync(root, R2Client(creds), lambda m: _notify(m, True))
        except Exception as exc:
            _notify(f'⚠ R2: đồng bộ lỗi — {exc}. Sẽ thử lại ở lần lưu sau.', False)
        else:
            if result.errors:
                _notify(f'⚠ R2: {result.summary()} — {result.errors[0]}', False)
            elif result.held_deletes:
                _notify(f'⚠ R2: {result.summary()}. Mở ☁ R2 → "Xoá file thừa" để xác nhận xoá.', False)
            elif result.uploaded or result.deleted:
                _notify(f'R2: đã {result.summary()} — web cập nhật sau ~1 phút.', True)


if __name__ == '__main__':
    # python r2_store.py            -> đồng bộ ngay (thư mục chứa file này)
    # python r2_store.py --restore  -> tải toàn bộ truyện từ R2 về (không ghi đè file đã có)
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    here = os.path.dirname(os.path.abspath(__file__))
    if '--restore' in sys.argv:
        count, errs = restore(here, progress=print, overwrite='--overwrite' in sys.argv)
        print('Đã ghi', count, 'file', f'· {len(errs)} lỗi' if errs else '')
        for err in errs[:10]:
            print('  ', err)
    else:
        creds = load_credentials()
        if not creds:
            sys.exit(f'Chưa cấu hình R2 ({config_path()}).')
        res = sync(here, R2Client(creds), print, allow_mass_delete='--allow-delete' in sys.argv)
        print('R2:', res.summary())
        for err in res.errors[:10]:
            print('  ', err)
