import base64
import datetime
import gzip
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import r2_store  # noqa: E402


def b64(text):
    return base64.b64encode(text.encode('utf-8')).decode('ascii')


class FakeClient:
    def __init__(self, fail=()):
        self.objects, self.calls, self.fail = {}, [], set(fail)

    def put(self, key, body, content_type):
        if key in self.fail:
            raise r2_store.R2Error(f'PUT {key}: HTTP 500')
        self.calls.append(('PUT', key))
        self.objects[key] = (body, content_type)

    def delete(self, key):
        self.calls.append(('DELETE', key))
        self.objects.pop(key, None)


class SigV4Test(unittest.TestCase):
    def test_aws_documented_example(self):
        # Ví dụ "GET Object" trong tài liệu AWS Signature V4 cho S3.
        headers = r2_store.sigv4_headers(
            'GET', 'examplebucket.s3.amazonaws.com', '/test.txt', {}, {'Range': 'bytes=0-9'},
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
            'AKIAIOSFODNN7EXAMPLE', 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
            region='us-east-1', now=datetime.datetime(2013, 5, 24, tzinfo=datetime.timezone.utc))
        self.assertEqual(
            headers['Authorization'],
            'AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, '
            'SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, '
            'Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41')


class CodecTest(unittest.TestCase):
    def test_compact_and_expand_roundtrip(self):
        src = {'title': 'T', 'chapter_title': 'C', 'content': [{'cn': b64('你好'), 'vi': b64('Xin chào')},
                                                                {'cn': '', 'vi': b64('~ dấu ngã')}]}
        gz = r2_store.compact_data(json.dumps(src).encode())
        shown = json.loads(gzip.decompress(gz))
        self.assertEqual(shown['content'][0], {'cn': '~你好', 'vi': '~Xin chào'})
        self.assertEqual(r2_store.expand_data(gz), src)

    def test_remote_keys(self):
        self.assertEqual(r2_store.remote_key('library/000006/0012/data.json')[0], 'library/000006/0012/data.json.gz')
        self.assertEqual(r2_store.remote_key('stories/abc-def/data.json')[0], 'stories/abc-def/data.json.gz')
        for rel in ('library/list.json', 'library/stories.json', 'library/000006/chapters.json', 'stories/list.json'):
            self.assertEqual(r2_store.remote_key(rel)[0], rel)
        for rel in ('library/list.json.bak', 'library/assets/core.js', 'library/000006/index.html', 'name.cfg'):
            self.assertIsNone(r2_store.remote_key(rel))


class SyncTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        for sid, cid in (('000001', '0001'), ('000001', '0002'), ('000002', '0001')):
            self.write(f'library/{sid}/{cid}/data.json', {'title': sid, 'content': [{'cn': '', 'vi': b64(cid)}]})
        for sid in ('000001', '000002'):
            self.write(f'library/{sid}/chapters.json', {'slug': sid})
            self.write(f'library/{sid}/index.html', '<html>')
        self.write('library/list.json', [])
        self.write('library/stories.json', [])
        self.write('library/list.json.bak', [])
        self.write('stories/truyen-a/data.json', {'title': 'A', 'content': []})
        self.write('stories/list.json', [])

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, data):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(data if isinstance(data, str) else json.dumps(data))

    def test_first_sync_uploads_chapters_before_catalogs(self):
        client = FakeClient()
        res = r2_store.sync(self.root, client)
        self.assertEqual(len(res.uploaded), 9)
        keys = [k for _, k in client.calls]
        last_chapter = max(i for i, k in enumerate(keys) if k.endswith('.gz'))
        first_catalog = min(i for i, k in enumerate(keys) if not k.endswith('.gz'))
        self.assertLess(last_chapter, first_catalog)
        body, ctype = client.objects['library/000001/0002/data.json.gz']
        self.assertEqual(ctype, 'application/gzip')
        self.assertEqual(r2_store.expand_data(body)['content'][0]['vi'], b64('0002'))
        self.assertNotIn('library/list.json.bak', client.objects)

    def test_second_sync_only_sends_changes(self):
        client = FakeClient()
        r2_store.sync(self.root, client)
        client.calls.clear()
        self.assertEqual(r2_store.sync(self.root, client).uploaded, [])
        time.sleep(0.01)
        self.write('library/000002/0001/data.json', {'title': 'x', 'content': [{'cn': '', 'vi': b64('mới')}]})
        os.utime(os.path.join(self.root, 'library/list.json'))   # chạm file nhưng nội dung y nguyên
        res = r2_store.sync(self.root, client)
        self.assertEqual(res.uploaded, ['library/000002/0001/data.json.gz'])

    def test_deleted_chapter_is_removed(self):
        client = FakeClient()
        r2_store.sync(self.root, client)
        os.remove(os.path.join(self.root, 'library/000001/0002/data.json'))
        res = r2_store.sync(self.root, client)
        self.assertEqual(res.deleted, ['library/000001/0002/data.json.gz'])
        self.assertNotIn('library/000001/0002/data.json.gz', client.objects)

    def test_mass_delete_is_held(self):
        client = FakeClient()
        old = r2_store.MAX_AUTO_DELETE
        r2_store.MAX_AUTO_DELETE = 2
        try:
            r2_store.sync(self.root, client)
            import shutil
            shutil.rmtree(os.path.join(self.root, 'library'))     # vd. thư mục bị đổi tên nhầm
            res = r2_store.sync(self.root, client)
            self.assertEqual(res.deleted, [])
            self.assertEqual(len(res.held_deletes), 7)
            self.assertIn('library/list.json', client.objects)
            res = r2_store.sync(self.root, client, allow_mass_delete=True)
            self.assertEqual(len(res.deleted), 7)
        finally:
            r2_store.MAX_AUTO_DELETE = old

    def test_failed_chapter_blocks_catalog_and_is_retried(self):
        client = FakeClient(fail={'library/000002/0001/data.json.gz'})
        res = r2_store.sync(self.root, client)
        self.assertEqual(len(res.errors), 1)
        sent = {k for _, k in client.calls}
        # chưa đẩy danh mục chung lẫn chapters.json của truyện có chương lỗi
        self.assertFalse(sent & {'library/list.json', 'library/stories.json', 'stories/list.json',
                                 'library/000002/chapters.json'})
        client.fail.clear()
        res = r2_store.sync(self.root, client)
        self.assertIn('library/000002/0001/data.json.gz', res.uploaded)
        self.assertIn('library/list.json', res.uploaded)
        self.assertNotIn('library/000001/0001/data.json.gz', res.uploaded)   # đã lên từ lần trước

    def test_broken_progress_callback_is_not_a_file_error(self):
        # Review C3: print() ra console cp1252 ném lỗi trong callback tiến độ → trước đây bị tính là
        # lỗi đẩy file và chặn luôn danh mục ở lần đồng bộ đầu (≥ 200 file).
        old = r2_store.MAX_AUTO_DELETE
        for i in range(3, 205):
            self.write(f'library/000003/{i:04d}/data.json', {'title': 'x', 'content': []})

        def broken(message):
            raise UnicodeEncodeError('charmap', message, 0, 1, 'character maps to <undefined>')
        client = FakeClient()
        res = r2_store.sync(self.root, client, broken)
        self.assertEqual(res.errors, [])
        self.assertIn('library/list.json', client.objects)
        r2_store.MAX_AUTO_DELETE = old

    def test_chapter_error_still_sends_unrelated_chapter_lists(self):
        client = FakeClient(fail={'library/000002/0001/data.json.gz'})
        r2_store.sync(self.root, client)
        self.assertIn('library/000001/chapters.json', client.objects)      # truyện khác vẫn lên
        self.assertNotIn('library/000002/chapters.json', client.objects)   # truyện có chương lỗi: hoãn
        self.assertNotIn('library/list.json', client.objects)              # danh mục chung: hoãn

    def test_project_root(self):
        self.assertEqual(r2_store.project_root(os.path.join(self.root, 'library')), self.root)

    def test_other_folders_never_sync(self):
        # Thư mục test/bản sao không bao giờ được đẩy lên bucket thật, kể cả khi máy đã có khoá R2.
        self.assertIsNone(r2_store.request_sync(os.path.join(self.root, 'library')))


class NotifyAndRestoreTest(unittest.TestCase):
    def test_notify_survives_unprintable_console(self):
        import builtins
        got, real_print = [], builtins.print
        listener = lambda message, ok: got.append(message)
        r2_store.add_listener(listener)

        def cp1252_print(*args, **kw):
            raise UnicodeEncodeError('charmap', 'đ', 0, 1, 'character maps to <undefined>')
        builtins.print = cp1252_print
        try:
            r2_store._notify('R2: đã đẩy 3 file', True)
        finally:
            builtins.print = real_print
            r2_store.remove_listener(listener)
        self.assertEqual(got, ['R2: đã đẩy 3 file'])   # app vẫn nhận được thông báo

    def test_restore_continues_past_missing_objects(self):
        store = {
            'library/list.json': json.dumps([{'slug': '000001', 'chapters': [{'id': '0001'}, {'id': '0002'}]}]),
            'library/stories.json': '[]',
            'library/000001/chapters.json': '{}',
            'library/000001/0001/data.json.gz': r2_store.compact_data(json.dumps(
                {'title': 'T', 'content': [{'cn': '', 'vi': b64('một')}]}).encode()),
            # 0002 thiếu trên R2; stories/list.json cũng thiếu
        }

        class Res:
            def __init__(self, key):
                self.key = key
                self.content = store[key].encode() if isinstance(store.get(key), str) else store.get(key)

            def raise_for_status(self):
                if self.key not in store:
                    raise RuntimeError(f'404 {self.key}')

        class Session:
            def get(self, url, headers=None, timeout=None):
                return Res(url.split('workers.dev/', 1)[1])

        with tempfile.TemporaryDirectory() as root:
            count, errors = r2_store.restore(root, base_url='https://x.workers.dev', session=Session())
            with open(os.path.join(root, 'library/000001/0001/data.json'), encoding='utf-8') as fh:
                self.assertEqual(json.load(fh)['content'][0]['vi'], b64('một'))
        self.assertEqual(count, 4)   # list.json, stories.json, chapters.json, chương 0001
        self.assertEqual(sorted(e.split(':')[0] for e in errors),
                         ['library/000001/0002/data.json', 'stories/list.json'])


class WorkerExitRaceTest(unittest.TestCase):
    """Review Lần 5, B2: yêu cầu đến lúc luồng nền vừa quyết định thoát không được mất."""

    def test_request_during_worker_exit_starts_new_thread(self):
        import threading
        root = os.path.abspath(os.path.dirname(__file__))
        runs, exiting = [], threading.Event()
        saved = {name: getattr(r2_store, name)
                 for name in ('_sync_once', '_worker_loop', 'DEBOUNCE', 'app_root', 'project_root')}
        saved_state = dict(r2_store._state)
        real_loop = r2_store._worker_loop

        def slow_exit_loop():
            real_loop()
            exiting.set()       # đã quyết định thoát nhưng luồng còn sống: đúng cửa sổ của lỗi cũ
            time.sleep(0.2)

        r2_store._sync_once = runs.append
        r2_store._worker_loop = slow_exit_loop
        r2_store.DEBOUNCE = 0.01
        r2_store.app_root = lambda: root
        r2_store.project_root = lambda path: root
        try:
            t1 = r2_store.request_sync(root)
            self.assertTrue(exiting.wait(2))
            t2 = r2_store.request_sync(root)
            t1.join(2)
            t2.join(2)
            self.assertIsNot(t1, t2)
            self.assertEqual(len(runs), 2)
        finally:
            for name, value in saved.items():
                setattr(r2_store, name, value)
            with r2_store._state_lock:      # không để trạng thái luồng nền rò sang test khác
                r2_store._state.clear()
                r2_store._state.update(saved_state)


class ConcurrentSyncTest(unittest.TestCase):
    """Review Lần 6, B4: nút "Đồng bộ ngay" và luồng nền không được chạy sync() chồng nhau."""

    def test_concurrent_syncs_are_serialised(self):
        import threading
        with tempfile.TemporaryDirectory() as root:
            for cid in ('0001', '0002', '0003'):
                path = os.path.join(root, 'library', '000001', cid, 'data.json')
                os.makedirs(os.path.dirname(path))
                with open(path, 'w', encoding='utf-8') as fh:
                    json.dump({'title': 'T', 'content': []}, fh)
            class SlowClient(FakeClient):
                def put(self, key, body, content_type):
                    time.sleep(0.05)         # đủ lâu để hai lần sync chồng nhau nếu không có khoá
                    super().put(key, body, content_type)

            client = SlowClient()
            workers = [threading.Thread(target=r2_store.sync, args=(root, client)) for _ in range(2)]
            for t in workers:
                t.start()
            for t in workers:
                t.join(10)
            # Lần thứ hai chờ lần đầu xong và thấy sổ ghi đã cập nhật: không gửi lại gì.
            self.assertEqual(len([c for c in client.calls if c[0] == 'PUT']), 3)


class EnsureStoryDirTest(unittest.TestCase):
    """Review Lần 5, B1: lưu chương không còn sinh index.html thừa (404.html dựng trang)."""

    def test_save_writes_data_only(self):
        import library_store as store
        with tempfile.TemporaryDirectory() as base:
            library = os.path.join(base, 'library')
            os.makedirs(library)
            for name in ('story.html', 'chapter.html'):
                with open(os.path.join(library, name), 'w') as fh:
                    fh.write('<html>')
            store.save_chapters(library, base, os.path.join(library, 'list.json'), '', 'T',
                                [('0001', 'C1', [('你', 'bạn')])])
            made = sorted(os.path.relpath(os.path.join(d, f), library).replace(os.sep, '/')
                          for d, _, files in os.walk(library) for f in files)
        self.assertNotIn('index.html', ' '.join(made))
        self.assertTrue(any(m.endswith('/0001/data.json') for m in made), made)


class WriteCatalogHookTest(unittest.TestCase):
    """Mọi lần lưu đi qua write_catalog, nơi phải xin một lần đồng bộ R2."""

    def test_write_catalog_requests_sync_of_the_project_root(self):
        import library_store as store
        with tempfile.TemporaryDirectory() as base:
            library = os.path.join(base, 'library')
            os.makedirs(library)
            calls = []
            original = r2_store.request_sync
            r2_store.request_sync = lambda path, **kw: calls.append(path)
            try:
                store.write_catalog(os.path.join(library, 'list.json'), [])
            finally:
                r2_store.request_sync = original
            self.assertEqual(calls, [base])


if __name__ == '__main__':
    unittest.main()
