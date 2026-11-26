#!/usr/bin/env python3
"""The bridge with no window: Range forms, streaming, cancel, lanes, the in-flight cap, every refusal.

  PYTHONDONTWRITEBYTECODE=1 <venv python> -B app/tests/test_bridge.py [-v]

Uses the made-up library in derived/app-build/testdata (no model) and a stub for chat. Never packaged."""
import faulthandler, hashlib, io, json, os, shutil, socket, statistics, subprocess, sys, tempfile, threading, time, types, unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from unittest.mock import patch

sys.dont_write_bytecode = True
faulthandler.dump_traceback_later(600, exit=True)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'app'), str(HERE)]
import fixture  # noqa: E402
DATA = fixture.ensure()
os.environ['LASTBOOK_DATA'] = str(DATA)
os.environ['SURVIVAL_MODEL_BASE'] = 'http://127.0.0.1:9'   # a dead address: the real model server is never contacted
os.environ['SURVIVAL_DISABLE_INDEX_WATCH'] = '1'
sys.modules['onnxruntime'] = None                          # importing it now raises ImportError: this Mac runs no AI models

import server, assistant, retrieval  # noqa: E402
import bridge as B  # noqa: E402

LISTENS = []
_real_listen = socket.socket.listen


def _no_listen(self, *a):
    LISTENS.append(self)
    return _real_listen(self, *a)


socket.socket.listen = _no_listen
server.init(no_index=True)
assert not retrieval.AVAILABLE and server.INDEX.emb is None, 'a model is available; refusing to run on this Mac'

MiB = B.MiB
OR = {'stream': B.ORIGIN_MAC, 'buffer': B.ORIGIN_WINDOWS}
TMP = DATA / 'tmp'
A = '/videos/a.mp4'
A_SIZE = 20 * MiB
pat = fixture.pattern
OBSERVED = {}   # numbers worth printing at the end


def fixture_pdf():
    """Three real pages and a script that would run on opening, were anything to open it with a script engine. Written by hand: a PDF is plain enough."""
    objs = [b'<</Type/Catalog/Pages 2 0 R/OpenAction<</S/JavaScript/JS(app.alert("ran"))>>>>', b'<</Type/Pages/Count 3/Kids[3 0 R 4 0 R 5 0 R]>>'] + [b'<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 400]>>'] * 3
    out, at = bytearray(b'%PDF-1.4\n'), []
    for i, o in enumerate(objs, 1):
        at.append(len(out))
        out += b'%d 0 obj\n' % i + o + b'\nendobj\n'
    xref = len(out)
    out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objs) + 1) + b''.join(b'%010d 00000 n \n' % a for a in at)
    out += b'trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n' % (len(objs) + 1, xref)
    return bytes(out)


class TestHandler(server.Handler):
    """The real Handler plus slow and odd routes, in the lanes they would land in. Lives only here."""
    seen = []
    slow_started = []

    def do_GET(self):
        p, _, q = self.path.partition('?')
        q = dict(x.split('=') for x in q.split('&') if '=' in x)
        if p in ('/api/t/slow', '/documents/t/slow', '/api/page/t/1.png'):
            TestHandler.slow_started.append(p)
            time.sleep(int(q.get('ms', 500)) / 1000)
            return self.send_json({'slept': True})
        if p == '/zim/t/pdf':
            return self.send_data(b'%PDF-1.4 inside an encyclopedia', 'application/pdf')
        if p == '/documents/t/slowbig':
            time.sleep(0.2)
            self.send_response(200)
            self.send_header('Content-Length', str(B.BIG_BODY + 1))
            self.end_headers()
            self.wfile.write(b'x' * (B.BIG_BODY + 1))
            return
        if p == '/documents/t/nolen':
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.end_headers()
            try:
                for _ in range(int(q.get('mb', 40))):
                    self.wfile.write(b'x' * MiB)
                    time.sleep(int(q.get('ms', 0)) / 1000)
            except server.library.CLIENT_GONE:
                pass
            return
        if p == '/documents/t/manywrites':
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(3 * MiB))
            self.end_headers()
            self.wfile.write(b'y' * (3 * MiB))   # one write bigger than a chunk
            return
        if p == '/documents/t/short':
            self.send_response(200)
            self.send_header('Content-Length', '1000')
            self.end_headers()
            self.wfile.write(b'z' * 10)
            return
        if p == '/documents/t/redirect':
            self.send_response(302)
            self.send_header('Location', '/documents/plain.txt?a="<b>')
            self.end_headers()
            return
        if p == '/api/t/echo':
            return self.send_json({'headers': {k.lower(): v for k, v in self.headers.items()}, 'path': self.path})
        if p == '/api/t/uncaught':
            raise RuntimeError('deliberate')
        if p == '/api/t/boom':
            try:
                raise RuntimeError('deliberate ' + str(ROOT))
            except RuntimeError:
                return self.internal_error()
        return super().do_GET()


MOD = types.SimpleNamespace(Handler=TestHandler, catalog=server.catalog, render_page=server.render_page, _pdf_lock=server._pdf_lock)


class Rec(B.Sink):
    def __init__(self, auto=True):
        self.auto, self.status, self.reason, self.hs = auto, None, None, {}
        self.parts, self.acks, self.times = [], [], []
        self.ok = None
        self.done = threading.Event()
        self.first = threading.Event()

    def head(self, status, reason, headers):
        self.status, self.reason, self.hs = status, reason, {k.lower(): v for k, v in headers}
        self.raw_hs = headers

    def data(self, chunk, ack):
        self.parts.append(chunk)
        self.times.append(time.time())
        self.first.set()
        if self.auto:
            ack()
        else:
            self.acks.append(ack)

    def finish(self, ok):
        self.ok = ok
        self.done.set()

    @property
    def body(self):
        return b''.join(self.parts)


class Res:
    def __init__(self, status, hs, body, ok=True, path=None):
        self.status, self.hs, self.body, self.ok, self.path = status, hs, body, ok, path


def call(b, method, path, headers=None, body=None, is_document=None, timeout=60, url=None):
    url = url if url is not None else b.origin + path
    if b.mode == 'stream':
        r = Rec()
        b.start(method, url, headers or {}, body, r, is_document)
        assert r.done.wait(timeout), f'no answer: {method} {path}'
        return Res(r.status, r.hs, r.body, r.ok)
    ev = threading.Event()
    box = []

    def done(resp):
        box.append(resp)
        ev.set()
    b.fetch(method, url, headers or {}, body, done, is_document)
    assert ev.wait(timeout), f'no answer: {method} {path}'
    resp = box[0]
    data = resp.body or b''
    if resp.path:
        with open(resp.path, 'rb') as f:
            data = f.read()
        if resp.delete:
            os.unlink(resp.path)
    resp.release()
    return Res(resp.status, {k.lower(): v for k, v in resp.headers}, data, True, resp.path)


def wait_until(fn, timeout=10):
    t = time.time() + timeout
    while time.time() < t:
        if fn():
            return True
        time.sleep(0.01)
    return False


def tmp_files():
    return sorted(p.name for p in TMP.iterdir())


class Both:
    """Every test in a subclass runs against one mode."""
    mode = None

    def setUp(self):
        self.logged = []
        self.b = B.Bridge(MOD, self.mode, OR[self.mode], tmpdir=str(TMP), log=self.logged.append)
        self.key = {'X-Lastbook-Key': self.b.key, 'Content-Type': 'application/json'}
        self.piece = B.VIDEO_PIECE[self.mode]

    def get(self, path, rng=None, **k):
        return call(self.b, 'GET', path, {'Range': rng} if rng else {}, **k)

    def language_bridge(self, module=server, file=None):
        if file is None:
            tmp = TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            file = Path(tmp.name) / B.ui_language.FILENAME
        bridge = B.Bridge(module, self.mode, OR[self.mode], language_file=file)
        headers = {B.KEY_HEADER: bridge.key, 'Content-Type': 'application/json'}
        return file, bridge, headers

    def test_language_reads_and_writes_require_the_desktop_key(self):
        file, b, key = self.language_bridge()
        route, body = B.ui_language.ROUTE, b'{"language":"es-419"}'
        self.assertEqual(call(b, 'POST', route, key, body).status, 200)
        for method in ('GET', 'HEAD', 'POST'):
            for headers in (None, {**key, B.KEY_HEADER: 'wrong'}, {**key, 'Origin': 'null'},
                            {**key, 'Origin': 'https://other.invalid'}):
                with self.subTest(method=method, headers=bool(headers)):
                    r = call(b, method, route, headers, b'{"language":"en"}')
                    self.assertEqual(r.status, 403)
                    self.assertNotIn(b'es-419', r.body)
                    if method == 'HEAD':
                        self.assertEqual(r.body, b'')
        r = call(b, 'GET', route, {**key, 'Origin': b.origin})
        self.assertEqual(r.status, 200)
        self.assertEqual(r.hs['cache-control'], 'no-store')
        self.assertEqual(json.loads(r.body), {'language': 'es-419'})
        self.assertEqual(call(b, 'HEAD', route, key).body, b'')
        self.assertEqual(json.loads(file.read_bytes()), {'language': 'es-419'})
        self.assertEqual(call(self.b, 'GET', route, self.key).status, 404)

    def test_simplified_chinese_can_be_saved(self):
        file, b, key = self.language_bridge()
        self.assertEqual(call(b, 'POST', B.ui_language.ROUTE, key, b'{"language":"zh-Hans"}').status, 200)
        self.assertEqual(json.loads(file.read_bytes()), {'language': 'zh-Hans'})
        self.assertEqual(json.loads(call(b, 'GET', B.ui_language.ROUTE, key).body), {'language': 'zh-Hans'})

    def test_german_can_be_saved(self):
        file, b, key = self.language_bridge()
        self.assertEqual(call(b, 'POST', B.ui_language.ROUTE, key, b'{"language":"de"}').status, 200)
        self.assertEqual(json.loads(file.read_bytes()), {'language': 'de'})

    def test_dutch_can_be_saved(self):
        file, b, key = self.language_bridge()
        self.assertEqual(call(b, 'POST', B.ui_language.ROUTE, key, b'{"language":"nl"}').status, 200)
        self.assertEqual(json.loads(file.read_bytes()), {'language': 'nl'})
        self.assertEqual(json.loads(call(b, 'GET', B.ui_language.ROUTE, key).body), {'language': 'nl'})

    def test_language_rejects_invalid_bodies_and_paths(self):
        file, b, key = self.language_bridge()
        route = B.ui_language.ROUTE
        bad = (b'', b'null', b'[]', b'{', b'{}', b'{"language":null}', b'{"language":true}',
               b'{"language":"en","language":"es-419"}', b'{"language":["en"]}', b'{"language":"es-ES"}',
               b'{"language":"en","path":"../settings.json"}', b'{"language":"../settings.json"}',
               b'{"language":"<img src=x>"}', b'{"language":"\xff"}', b' ' * 129)
        for body in bad:
            with self.subTest(body=body):
                self.assertEqual(call(b, 'POST', route, key, body).status, 400)
        self.assertEqual(call(b, 'POST', route, {**key, 'Content-Type': 'application/jsonp'}, b'{"language":"en"}').status, 400)
        for target in (route + '/', route + '?path=../settings.json', '/api/%75i-language', '/ui/../ui-language.json', '/ui/%2e%2e/ui-language.json'):
            with self.subTest(target=target):
                self.assertEqual(call(b, 'POST', target, key, b'{"language":"en"}').status, 404)
                self.assertEqual(call(b, 'GET', target).status, 404)
        self.assertFalse(file.exists())

    def test_language_file_survives_setup_library_and_new_bridge_keys(self):
        file, setup, key = self.language_bridge(server.setup_api.SetupServer)
        route = B.ui_language.ROUTE
        settings = file.with_name('settings.json')
        settings.write_bytes(b'{"library":"/path/to/library"}\n')
        before = settings.read_bytes()
        self.assertEqual(json.loads(call(setup, 'GET', route, key).body), {'language': None})
        self.assertEqual(call(setup, 'POST', route, key, b'{"language":"es-419"}').status, 200)
        for _ in range(2):  # a newly launched library bridge, including after a folder switch
            _, library, new_key = self.language_bridge(file=file)
            self.assertEqual(call(library, 'GET', route, key).status, 403)
            self.assertEqual(json.loads(call(library, 'GET', route, new_key).body), {'language': 'es-419'})
        self.assertEqual(settings.read_bytes(), before)

    def test_language_file_recovers_from_corruption_and_failed_replace(self):
        file, b, key = self.language_bridge()
        route = B.ui_language.ROUTE
        for data in (b'\xff', b'{"language":"es-ES"}', b'{"language":"es-419","language":"en"}', b' ' * 129):
            file.write_bytes(data)
            self.assertEqual(json.loads(call(b, 'GET', route, key).body), {'language': None})
            self.assertEqual(file.read_bytes(), data)
        self.assertEqual(call(b, 'POST', route, key, b'{"language":"es-419"}').status, 200)
        with patch.object(B.ui_language.os, 'replace', side_effect=PermissionError('cannot replace')):
            r = call(b, 'POST', route, key, b'{"language":"en"}')
        self.assertEqual(r.status, 500)
        self.assertEqual(json.loads(call(b, 'GET', route, key).body), {'language': 'es-419'})
        self.assertEqual(list(file.parent.iterdir()), [file])

    def test_language_concurrent_windows_commit_in_replacement_order(self):
        file, first, first_key = self.language_bridge()
        _, second, second_key = self.language_bridge(file=file)
        route = B.ui_language.ROUTE
        replace = os.replace
        arrived, release = threading.Event(), threading.Event()
        replies = []

        def replace_language(src, dst):
            if Path(dst) == file and json.loads(Path(src).read_bytes()) == {'language': 'es-419'}:
                arrived.set()
                if not release.wait(5):
                    raise TimeoutError('test did not release the first write')
            replace(src, dst)

        def first_save():
            replies.append(call(first, 'POST', route, first_key, b'{"language":"es-419"}').status)

        with patch.object(B.ui_language.os, 'replace', side_effect=replace_language):
            worker = threading.Thread(target=first_save)
            worker.start()
            try:
                self.assertTrue(arrived.wait(5))
                self.assertEqual(call(second, 'POST', route, second_key, b'{"language":"en"}').status, 200)
                self.assertEqual(json.loads(call(first, 'GET', route, first_key).body), {'language': 'en'})
            finally:
                release.set()
                worker.join(6)
        self.assertEqual(replies, [200])
        self.assertEqual(json.loads(call(second, 'GET', route, second_key).body), {'language': 'es-419'})
        self.assertEqual(list(file.parent.iterdir()), [file])

    def test_language_interrupted_write_and_nonregular_objects(self):
        file, b, key = self.language_bridge()
        route = B.ui_language.ROUTE
        file.mkdir()
        self.assertEqual(json.loads(call(b, 'GET', route, key).body), {'language': None})
        self.assertEqual(call(b, 'POST', route, key, b'{"language":"en"}').status, 500)
        self.assertEqual(list(file.parent.iterdir()), [file])
        file.rmdir()
        if hasattr(os, 'mkfifo'):
            os.mkfifo(file)
            self.assertEqual(json.loads(call(b, 'GET', route, key, timeout=3).body), {'language': None})
            file.unlink()
        saved = b'{"language":"es-419"}'
        file.write_bytes(saved)
        orphan = file.with_name('.ui-language-interrupted')
        orphan.write_bytes(b'{"language":')
        self.assertEqual(json.loads(call(b, 'GET', route, key).body), {'language': 'es-419'})
        with patch.object(B.ui_language.os, 'fsync', side_effect=OSError('interrupted write')):
            self.assertEqual(call(b, 'POST', route, key, b'{"language":"en"}').status, 500)
        self.assertEqual(file.read_bytes(), saved)
        self.assertEqual(set(file.parent.iterdir()), {file, orphan})

    @unittest.skipUnless(os.name == 'posix', 'symlink test uses POSIX file semantics')
    def test_language_symlink_cannot_read_or_overwrite_another_file(self):
        file, b, key = self.language_bridge()
        other = file.with_name('settings.json')
        other.write_bytes(b'{"language":"es-419"}')
        file.symlink_to(other)
        route = B.ui_language.ROUTE
        self.assertEqual(json.loads(call(b, 'GET', route, key).body), {'language': None})
        self.assertEqual(call(b, 'POST', route, key, b'{"language":"en"}').status, 200)
        self.assertFalse(file.is_symlink())
        self.assertEqual(other.read_bytes(), b'{"language":"es-419"}')
        self.assertEqual(json.loads(call(b, 'GET', route, key).body), {'language': 'en'})

    def test_language_save_retries_a_replace_another_process_is_holding(self):
        file, b, key = self.language_bridge()
        route = B.ui_language.ROUTE
        real = os.replace
        refusals = [PermissionError('in use'), PermissionError('in use')]

        def replace_when_free(src, dst):
            if refusals:
                raise refusals.pop()
            real(src, dst)

        with patch.object(B.ui_language.os, 'replace', side_effect=replace_when_free) as replace, \
                patch.object(B.ui_language, 'REPLACE_WAIT', 0):
            r = call(b, 'POST', route, key, b'{"language":"es-419"}')
        self.assertEqual(r.status, 200)
        self.assertEqual(replace.call_count, 3)
        self.assertEqual(json.loads(file.read_bytes()), {'language': 'es-419'})
        self.assertEqual(list(file.parent.iterdir()), [file])
        # A refusal that never clears still ends in a clean 500 after a bounded number of tries.
        with patch.object(B.ui_language.os, 'replace', side_effect=PermissionError('in use')) as replace, \
                patch.object(B.ui_language, 'REPLACE_WAIT', 0):
            r = call(b, 'POST', route, key, b'{"language":"en"}')
        self.assertEqual(r.status, 500)
        self.assertEqual(replace.call_count, B.ui_language.REPLACE_TRIES)
        self.assertEqual(json.loads(file.read_bytes()), {'language': 'es-419'})
        self.assertEqual(list(file.parent.iterdir()), [file])
        # Only a permission refusal is retried.
        with patch.object(B.ui_language.os, 'replace', side_effect=OSError('disk')) as replace:
            self.assertEqual(call(b, 'POST', route, key, b'{"language":"en"}').status, 500)
        self.assertEqual(replace.call_count, 1)

    @unittest.skipUnless(hasattr(os, 'O_DIRECTORY'), 'folder sync is POSIX only')
    def test_language_save_syncs_the_folder_but_never_fails_on_it(self):
        file, b, key = self.language_bridge()
        route = B.ui_language.ROUTE
        synced = []
        real = os.fsync

        def fsync(fd):
            synced.append(stat_is_dir(fd))
            return real(fd)

        def stat_is_dir(fd):
            import stat as stat_module
            return stat_module.S_ISDIR(os.fstat(fd).st_mode)

        with patch.object(B.ui_language.os, 'fsync', side_effect=fsync):
            self.assertEqual(call(b, 'POST', route, key, b'{"language":"es-419"}').status, 200)
        self.assertEqual(synced, [False, True])  # the new file's data, then the folder entry

        def fsync_folder_fails(fd):
            if stat_is_dir(fd):
                raise OSError('not supported here')
            return real(fd)

        with patch.object(B.ui_language.os, 'fsync', side_effect=fsync_folder_fails):
            self.assertEqual(call(b, 'POST', route, key, b'{"language":"en"}').status, 200)
        self.assertEqual(json.loads(file.read_bytes()), {'language': 'en'})
        real_open = os.open
        refused = []

        def open_without_folders(path, flags, *args, **kwargs):
            if flags & os.O_DIRECTORY:
                refused.append(path)
                raise OSError('no folder handle')
            return real_open(path, flags, *args, **kwargs)

        with patch.object(B.ui_language.os, 'open', side_effect=open_without_folders):
            self.assertEqual(call(b, 'POST', route, key, b'{"language":"es-419"}').status, 200)
        self.assertTrue(refused)
        self.assertEqual(json.loads(file.read_bytes()), {'language': 'es-419'})

    def test_language_symlink_swapped_in_after_the_check_reads_as_unset(self):
        import errno
        file, b, key = self.language_bridge()
        route = B.ui_language.ROUTE
        file.write_bytes(b'{"language":"es-419"}')
        # O_NOFOLLOW reports a link that replaced the file between lstat and open as ELOOP.
        real_open = os.open

        def fail_for_the_file(error):
            def opener(path, flags, *args, **kwargs):
                if Path(path) == file:
                    raise error
                return real_open(path, flags, *args, **kwargs)
            return opener

        with patch.object(B.ui_language.os, 'open', side_effect=fail_for_the_file(OSError(errno.ELOOP, 'too many links'))):
            r = call(b, 'GET', route, key)
        self.assertEqual(r.status, 200)
        self.assertEqual(json.loads(r.body), {'language': None})
        # Other open failures are still errors the person can see.
        with patch.object(B.ui_language.os, 'open', side_effect=fail_for_the_file(PermissionError(errno.EACCES, 'denied'))):
            self.assertEqual(call(b, 'GET', route, key).status, 500)

    # ---- Range forms on video
    def check_slice(self, r, start, end, size=A_SIZE):
        self.assertEqual(r.status, 206)
        self.assertEqual(r.hs['content-range'], f'bytes {start}-{end}/{size}')
        self.assertEqual(int(r.hs['content-length']), end - start + 1)
        self.assertEqual(len(r.body), end - start + 1)
        self.assertEqual(hashlib.sha256(r.body).digest(), hashlib.sha256(pat(start, end - start + 1)).digest())

    def test_video_bounded_range(self):
        self.check_slice(self.get(A, 'bytes=0-99'), 0, 99)
        self.check_slice(self.get(A, 'bytes=1000-1999'), 1000, 1999)
        self.check_slice(self.get(A, 'bytes=0-0'), 0, 0)

    def test_video_open_range_gets_one_piece(self):
        self.check_slice(self.get(A, 'bytes=0-'), 0, self.piece - 1)
        self.check_slice(self.get(A, 'bytes=12345-'), 12345, 12345 + self.piece - 1)

    def test_video_long_bounded_range_is_capped(self):
        self.check_slice(self.get(A, f'bytes=5-{A_SIZE - 1}'), 5, 5 + self.piece - 1)

    def test_video_largest_player_ask_is_answered_whole(self):
        ask = int(2.38 * 1000 * 1000)
        self.assertGreater(self.piece, ask)
        self.check_slice(self.get(A, f'bytes=0-{ask - 1}'), 0, ask - 1)

    def test_video_no_range_gets_first_piece(self):
        self.check_slice(self.get(A), 0, self.piece - 1)

    def test_video_end_past_file_and_last_byte(self):
        self.check_slice(self.get(A, f'bytes={A_SIZE - 10}-{A_SIZE + 500}'), A_SIZE - 10, A_SIZE - 1)
        self.check_slice(self.get(A, f'bytes={A_SIZE - 1}-'), A_SIZE - 1, A_SIZE - 1)

    def test_video_refused_forms(self):
        for rng in (f'bytes={A_SIZE}-', 'bytes=5-3', 'bytes=-500', 'bytes=abc', 'items=0-5', 'bytes=', 'bytes=99999999999999999999-'):
            self.assertEqual(self.get(A, rng).status, 416, rng)

    def test_video_multi_range_reads_as_first(self):
        self.check_slice(self.get(A, 'bytes=0-9,20-29'), 0, 9)
        self.check_slice(self.get(A, f'bytes=0-{A_SIZE},20-29'), 0, self.piece - 1)

    def test_video_walk_whole_file(self):
        got, off = [], 0
        n = 0
        while off < A_SIZE:
            r = self.get(A, f'bytes={off}-')
            self.assertEqual(r.status, 206)
            got.append(r.body)
            off += len(r.body)
            n += 1
        self.assertEqual(hashlib.sha256(b''.join(got)).digest(), hashlib.sha256(pat(0, A_SIZE)).digest())
        self.assertEqual(n, -(-A_SIZE // self.piece))

    def test_video_other_types_and_case(self):
        self.assertEqual(self.get('/videos/b.webm', 'bytes=0-9').status, 206)
        self.assertEqual(self.get('/videos/huge.mkv').status, 206)
        self.assertEqual(len(self.get('/videos/huge.mkv').body), self.piece)

    def test_video_head_is_not_capped(self):
        r = call(self.b, 'HEAD', A)
        self.assertEqual(r.status, 200)
        self.assertEqual(int(r.hs['content-length']), A_SIZE)
        self.assertEqual(r.body, b'')

    # ---- a PDF never reaches the web view: it becomes pictures
    def real_pdf(self):
        path = DATA / 'library-data' / 'documents' / 'real.pdf'
        if not path.exists():
            path.write_bytes(fixture_pdf())
        return '/documents/real.pdf'

    def test_pdf_file_is_never_handed_over(self):
        p = self.real_pdf()
        for rng in (None, 'bytes=0-99', 'bytes=-500', 'bytes=0-'):
            r = self.get(p, rng)
            self.assertEqual(r.status, 200, rng)
            self.assertTrue(r.hs['content-type'].startswith('text/html'), rng)
            self.assertNotIn(b'%PDF', r.body, rng)
            self.assertNotIn('accept-ranges', r.hs)
            self.assertTrue(r.hs['content-security-policy'].startswith('sandbox allow-scripts;'))
            self.assertIn("script-src 'none'", r.hs['content-security-policy'])

    def test_pdf_viewer_lists_pages_and_runs_nothing(self):
        b = self.get(self.real_pdf()).body
        self.assertEqual(b.count(b'class="p"'), 3)
        self.assertIn(b'id="page=3"', b)
        self.assertIn(b'src="?pdf-page=2"', b)
        self.assertNotIn(b'<script', b.lower())
        self.assertNotRegex(b.split(b'</style>')[1], rb'\son\w+=')
        o = self.b.origin
        self.assertTrue(self.b.is_pdf_viewer(o + '/documents/a%20b.PDF#page=3'))
        for u in (o + '/documents/a.pdf?pdf-page=3', o + '/documents/a.html', o + '/documents/a.html?x=.pdf', o + '/documents/a.html#.pdf', o + '/', o + '/api/a.pdf', 'https://e.example/a.pdf'):
            self.assertFalse(self.b.is_pdf_viewer(u), u)

    def test_pdf_page_is_a_picture(self):
        r = self.get(self.real_pdf() + '?pdf-page=2')
        self.assertEqual(r.status, 200)
        self.assertEqual(r.hs['content-type'], 'image/png')
        self.assertEqual(r.body[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(self.get(self.real_pdf() + '?pdf-page=9').status, 404)
        self.assertEqual(self.get(self.real_pdf() + '?pdf-page=0').status, 404)

    def test_pdf_pictures_have_their_own_lane(self):
        self.assertEqual(B._lane_for('GET', '/documents/real.pdf', False, '/documents/real.pdf?pdf-page=2'), 'render')
        self.assertEqual(B._lane_for('GET', '/documents/real.pdf', False, '/documents/real.pdf'), 'large')

    def test_damaged_pdf_shows_a_notice_and_not_its_bytes(self):
        for p in ('/documents/s.pdf', '/documents/big.pdf'):
            for rng in (None, 'bytes=0-99'):
                r = self.get(p, rng)
                self.assertEqual(r.status, 404)
                self.assertEqual(r.body, B.PDF_NOTICE)
                self.assertIn('sandbox', r.hs['content-security-policy'])

    def test_pdf_elsewhere_is_refused_by_its_type(self):
        r = self.get('/zim/t/pdf')
        self.assertEqual(r.status, 404)
        self.assertEqual(r.body, B.PDF_NOTICE)

    def test_pdf_head(self):
        r = call(self.b, 'HEAD', self.real_pdf())
        self.assertEqual(r.status, 200)
        self.assertEqual(r.body, b'')

    def test_other_file_ignores_range(self):
        r = self.get('/documents/mid.bin', 'bytes=0-9')
        self.assertEqual(r.status, 200)
        self.assertEqual(len(r.body), 5 * MiB)

    # ---- every refusal
    def test_refused_host(self):
        for url in ('https://evil.example/', 'lastbook://other/', self.b.origin + '.evil/', self.b.origin + '@evil/', 'file:///etc/hosts', 'about:blank', ''):
            r = call(self.b, 'GET', '', url=url)
            self.assertEqual(r.status, 400, url)
        self.assertGreaterEqual(self.b.counts['host'], 7)

    def test_refused_target(self):
        for t in ('//evil/', '/a b', '/a\nb', '/a\x00b', '/a\tb', '/\x7f'):
            self.assertEqual(self.get(t).status, 400, repr(t))
        self.assertEqual(self.b.counts['target'], 6)

    def test_refused_method(self):
        for m in ('PUT', 'DELETE', 'OPTIONS', 'TRACE', 'PATCH', 'CONNECT', 'get'):
            self.assertEqual(call(self.b, m, '/').status, 405, m)

    def test_post_needs_the_key(self):
        before = self.chat_count()
        for name, h, why in [
            ('no key', {'Content-Type': 'application/json'}, 'post-key'),
            ('wrong key', {'Content-Type': 'application/json', 'X-Lastbook-Key': 'x'}, 'post-key'),
            ('empty key', {'Content-Type': 'application/json', 'X-Lastbook-Key': ''}, 'post-key'),
            ('null origin with key', {**self.key, 'Origin': 'null'}, 'post-origin'),
            ('other origin with key', {**self.key, 'Origin': 'https://evil.example'}, 'post-origin'),
            ('text type with key', {'X-Lastbook-Key': self.b.key, 'Content-Type': 'text/plain'}, 'post-type'),
            ('no type with key', {'X-Lastbook-Key': self.b.key}, 'post-type'),
        ]:
            n = self.b.counts.get(why, 0)
            r = call(self.b, 'POST', '/api/chat', h, b'{}')
            self.assertEqual(r.status, 403, name)
            self.assertEqual(self.b.counts[why], n + 1, name)
        self.assertEqual(self.chat_count(), before)

    def test_post_too_big(self):
        self.assertEqual(call(self.b, 'POST', '/api/chat', self.key, b'x' * (B.MAX_POST + 1)).status, 413)

    def test_each_launch_has_its_own_key(self):
        other = B.Bridge(MOD, self.mode, OR[self.mode], tmpdir=str(TMP))
        self.assertNotEqual(self.b.key, other.key)
        self.assertEqual(call(other, 'POST', '/api/chat', self.key, b'{}').status, 403)

    def test_path_attacks(self):
        attacks = ['/../canary-root.txt', '/documents/../canary-root.txt', '/%2e%2e/canary-root.txt', '/documents/%2e%2e/%2e%2e/outside-canary.txt', '/canary-root.txt',
                   '/video-auth.json', '/documents/video-auth-copy.json', '/documents/x.info.json', '/documents/.hidden', '/tools/secret.txt', '/logs/x.log', '/catalog.json',
                   '/search.sqlite', '/documents/hl.txt', '/pages/hl2.txt', '/zim/../canary-root.txt', '/zim/%2e%2e%2fcanary-root.txt/x', '/ui/../server.py',
                   '/ui/%2e%2e/server.py', '/documents%2f..%2f..%2fcanary-root.txt', '/documents/..\\canary-root.txt', '/documents/plain.txt/../../canary-root.txt', '/assets/../tools/secret.txt']
        for t in attacks:
            for m in ('GET', 'HEAD'):
                r = call(self.b, m, t)
                self.assertGreaterEqual(r.status, 400, f'{m} {t}')
                self.assertNotIn(fixture.CANARY, r.body, t)
        r = self.get('/?x=../canary-root.txt')
        self.assertEqual(r.status, 200)
        self.assertNotIn(fixture.CANARY, r.body)

    def test_symlink_out_of_the_library_is_refused(self):
        """A link to a file outside the library, in its own test: on a machine with no right to make links the fixture cannot build one, and a skip says so where an address that is simply absent would have looked like a pass."""
        if not fixture.LINKED:
            self.skipTest('no right to make symbolic links (Developer Mode on Windows)')
        for method in ('GET', 'HEAD'):
            r = call(self.b, method, '/documents/out.txt')
            self.assertGreaterEqual(r.status, 400, method)
            self.assertNotIn(fixture.CANARY, r.body, method)

    def test_hard_link_refused_but_plain_files_served(self):
        self.assertEqual(os.stat(fixture.LIB / 'documents' / 'hl.txt').st_nlink, 2)
        self.assertEqual(self.get('/documents/hl.txt').status, 404)
        self.assertEqual(self.get('/pages/hl2.txt').status, 404)
        self.assertEqual(self.get('/documents/plain.txt').status, 200)

    def test_headers_a_page_cannot_smuggle(self):
        r = call(self.b, 'GET', '/api/t/echo', {'X-Lastbook-Key': 'secret', 'Cookie': 'sg_key=1', 'Host': 'evil.example', 'X-Forwarded-For': '1.2.3.4', 'Accept': 'x/y', 'Range': 'bytes=0-1', 'Bad': 'a\r\nInjected: 1', 'Accept\r\nInjected': '2'})
        seen = json.loads(r.body)['headers']
        self.assertEqual(seen['host'], 'localhost')
        self.assertEqual(seen['accept'], 'x/y')
        for h in ('x-lastbook-key', 'cookie', 'x-forwarded-for', 'bad', 'injected'):
            self.assertNotIn(h, seen)

    def test_own_origin_maps_and_null_stays(self):
        seen = json.loads(call(self.b, 'GET', '/api/t/echo', {'Origin': self.b.origin}).body)['headers']
        self.assertEqual(seen['origin'], 'http://localhost')
        seen = json.loads(call(self.b, 'GET', '/api/t/echo', {'Origin': 'null'}).body)['headers']
        self.assertEqual(seen['origin'], 'null')

    def test_non_ascii_target(self):
        r = self.get('/documents/پ.txt')
        self.assertEqual(r.status, 404)   # no such file, and no crash on the way

    def test_log_never_holds_the_key(self):
        call(self.b, 'POST', '/api/chat', self.key, b'{}')
        call(self.b, 'POST', '/api/chat', {'Content-Type': 'application/json', 'X-Lastbook-Key': 'wrong'}, b'{}')
        wait_until(lambda: len(self.logged) >= 2)
        self.assertNotIn(self.b.key, json.dumps(self.logged))

    # ---- the flood gate
    def test_gate_refuses_big_without_a_ticket(self):
        r = self.get('/documents/big.bin')
        self.assertEqual(r.status, 403)
        self.assertEqual(r.body, B.TOO_LARGE)
        self.assertEqual(self.b.counts['flood-gate'], 1)

    def test_gate_size_edge(self):
        self.assertEqual(self.get('/documents/over.bin').status, 403)
        self.assertEqual(self.get('/documents/mid.bin').status, 200)

    def test_gate_ticket_once(self):
        url = self.b.origin + '/documents/big.bin'
        self.b.give_ticket(url + '#x')
        r = self.get('/documents/big.bin', is_document=True)
        self.assertEqual(r.status, 200)
        self.assertEqual(len(r.body), 40 * MiB)
        self.assertEqual(r.body[:1000], pat(0, 1000))
        self.assertEqual(self.get('/documents/big.bin', is_document=True).status, 403)

    def test_gate_ticket_needs_a_document_when_the_shell_knows(self):
        self.b.give_ticket(self.b.origin + '/documents/big.bin')
        self.assertEqual(self.get('/documents/big.bin', is_document=False).status, 403)
        self.assertEqual(self.get('/documents/big.bin', is_document=True).status, 200)

    def test_gate_ticket_for_another_target(self):
        self.b.give_ticket(self.b.origin + '/documents/big.bin?x=1')
        self.assertEqual(self.get('/documents/big.bin').status, 403)

    def test_gate_ticket_expires(self):
        self.b.give_ticket(self.b.origin + '/documents/big.bin')
        self.b.tickets['/documents/big.bin'] -= B.TICKET_LIFE + 1
        self.assertEqual(self.get('/documents/big.bin').status, 403)

    def test_gate_catches_a_video_the_engine_does_not_recognise(self):
        r = self.get('/videos/huge.mk%76', 'bytes=0-')   # the engine's own Range path looks at the raw address, so it answers whole
        self.assertEqual(r.status, 403)

    def test_rewrite_takes_linear_time_on_tags_that_never_close(self):
        """A whole page against 1/64 of one. In step with its size the whole page takes 64 times as long; quadratic, 4096 times. A limit in seconds
        says more about the computer, and what else it is doing, than about rewrite: at 5 s this failed two runs in five on a busy Windows laptop, on
        '<a x>', which takes 2.2 s there when the laptop is idle. The eleven other pages take 0.1 to 0.5 s."""
        from engine import saved_pages as P

        def took(data):
            t0 = time.perf_counter()
            P.rewrite(data, lambda src: b'WEBVTT\n' + b'<' * P.MAX_TRANSCRIPT)
            return time.perf_counter() - t0

        for unit in (b'<button x>', b'<a x>', b'<a ', b'<head ', b'<track src="a.vtt ', b'<track ', b'<div class="image-gallery" data-base-url="x">', b'<div class="image-gallery ',
                     b'<!doctype ', b'<a href=x target=y download ', b'<div class="image-gallery" data-base-url="x"><a ', b'<tr><td><small>A1</small> </td>'):
            small = min(took(unit * (P.MAX_PAGE // 64 // len(unit))) for _ in range(5))     # the quietest of five: other work on the computer only ever adds time
            whole = took(unit * (P.MAX_PAGE // len(unit)))
            self.assertLess(whole, 16 * 64 * small, (unit, small, whole))     # measured 2 to 3 times in step when idle, 6 with every core busy; quadratic is 64

    def test_rewrite_blank_rows_only_when_too_large(self):
        from engine import saved_pages as P
        blank = b'<tr><td><small>A1</small> </td><td><small>B1</small> </td></tr>'
        real = b'<tr><td><small>A2</small> water</td><td><small>B2</small> </td></tr>'
        small = b'<table>' + blank + real + b'</table>'
        self.assertIn(blank, P.rewrite(small))
        big = P.rewrite(b'<html><head></head><table>' + blank * (P.MAX_PAGE // len(blank) + 1) + real + b'</table>')
        self.assertNotIn(blank, big)
        self.assertIn(real, big)
        self.assertIn(P.CSS, big)
        full = b'<html><head></head>' + b'x' * P.MAX_PAGE
        self.assertEqual(P.rewrite(full), full)

    def test_gate_ticket_counts_from_the_request_not_the_answer(self):
        """The engine can take longer than a ticket lasts to get its answer ready."""
        self.b.give_ticket(self.b.origin + '/documents/t/slowbig')
        r = self.get('/documents/t/slowbig', is_document=True)
        self.assertEqual(r.status, 200)

    def test_drop_waiting_answers_what_is_in_line(self):
        if self.b.mode != 'buffer':
            return
        b = B.Bridge(MOD, 'buffer', B.ORIGIN_WINDOWS, tmpdir=str(TMP), lanes={**B.LANES, 'large': (1, 100, 64 * MiB)})
        answers = []
        for i in range(5):
            b.fetch('GET', b.origin + f'/documents/t/slow?ms=400&i={i}', {}, None, answers.append)
        time.sleep(0.05)
        for ex in b.lanes['large'].waiting:
            ex.t0 -= 5
        self.assertEqual(b.drop_waiting(), 4)
        self.assertEqual(sorted(r.status for r in answers), [503] * 4)
        deadline = time.time() + 5
        while len(answers) < 5 and time.time() < deadline:
            time.sleep(0.02)
        self.assertEqual(len(answers), 5)

    def test_unknown_length_over_the_limit(self):
        r = self.get('/documents/t/nolen?mb=40')
        if self.mode == 'stream':
            self.assertEqual(r.status, 200)
            self.assertFalse(r.ok)
            self.assertLessEqual(len(r.body), B.BIG_BODY + MiB)
        else:
            self.assertEqual(r.status, 413)
        self.assertEqual(self.b.counts['unknown-length'], 1)
        self.assertEqual(self.b.lanes['large'].budget.used, 0)

    # ---- what stays the engine's
    def no_code(self, r, sandbox='sandbox;'):
        csp = r.hs['content-security-policy']
        self.assertTrue(csp.startswith(sandbox), csp)
        for word in ('allow-scripts', 'allow-popups', 'allow-forms', 'allow-downloads', 'unsafe-eval', 'blob:', 'http'):
            self.assertNotIn(word, csp)
        for rule in ("default-src 'none'", "script-src 'none'", "object-src 'none'", "connect-src 'none'", "form-action 'none'", "base-uri 'none'"):
            self.assertIn(rule, csp)

    def test_saved_page_runs_no_code(self):
        r = self.get('/pages/s.html')
        self.assertEqual(r.status, 200)
        self.no_code(r)
        self.assertNotIn('allow-same-origin', r.hs['content-security-policy'])
        self.no_code(self.get('/pages/a.svg'))

    def test_every_answer_for_library_content_runs_no_code(self):
        d = fixture.LIB / 'pages' / 'kinds'
        (d / 'folder').mkdir(parents=True, exist_ok=True)
        (d / 'folder' / 'index.html').write_bytes(b'<p>in a folder')
        (d / 'nosuffix').write_bytes(b'<script>1</script>')
        (d / 'upper.HTML').write_bytes(b'<script>1</script>')
        (d / 'x.xhtml').write_bytes(b'<html xmlns="http://www.w3.org/1999/xhtml"><script>1</script></html>')
        for t in ('/pages/kinds/nosuffix', '/pages/kinds/upper.HTML', '/pages/kinds/x.xhtml', '/pages/kinds/folder/', '/pages/kinds/folder/index.html', '/pages/kinds/none.html', '/pages/kinds/none', '/%70ages/kinds/nosuffix'):
            r = self.get(t)
            self.assertIn(r.status, (200, 404), t)
            self.no_code(r)
        r = self.get('/pages/kinds/folder')     # a folder with no slash: a redirect
        self.assertEqual(r.status, 200 if self.mode == 'stream' else 301)
        if self.mode == 'stream':               # the page that stands in for it holds no code either, and cannot be sandboxed
            self.assertEqual(r.hs['content-security-policy'], "default-src 'none'; script-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'")
            self.assertIn(b'http-equiv="refresh"', r.body)
            self.assertNotIn(b'<script', r.body)
        else:
            self.no_code(r)
        for t in ('/zim/none.zim/A/x', '/zim/none.zim/', '/zim/'):
            r = self.get(t)
            self.no_code(r, 'sandbox allow-same-origin;')
        self.assertEqual(server.Handler.ZIM_CSP, 'sandbox allow-same-origin; ' + server.Handler.NO_CODE_CSP)

    def test_a_library_page_may_be_called_tools(self):
        for rel in ('courses/c1/resources/tools/index.html', 'pages/work/index.html', 'documents/logs/index.html', 'assets/runtime/index.html', 'metadata/videos/tools/index.html', 'collections/tools/index.html'):
            p = fixture.LIB / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'<!doctype html><title>t</title><script>1</script><p>a real page')
            for t in ('/' + rel, '/' + rel[:-len('index.html')]):
                r = self.get(t)
                self.assertEqual(r.status, 200, t)
                self.assertIn(b'a real page', r.body, t)
                self.no_code(r)
        p = fixture.LIB / 'courses' / 'c1' / 'resources' / 'tools' / 'index.xml'
        p.write_bytes(b'<?xml version="1.0"?><x/>')
        self.no_code(self.get('/courses/c1/resources/tools/index.xml'))
        hidden = fixture.LIB / 'courses' / 'c1' / 'tools' / '.Data'
        hidden.mkdir(parents=True, exist_ok=True)
        (hidden / 'x.txt').write_bytes(fixture.CANARY)
        (fixture.LIB / 'courses' / 'c1' / '.git').mkdir(exist_ok=True)
        (fixture.LIB / 'courses' / 'c1' / '.git' / 'config').write_bytes(fixture.CANARY)
        for t in ('/courses/c1/tools/.Data/x.txt', '/courses/c1/.git/config', '/tools/secret.txt', '/TOOLS/secret.txt', '/logs/x.log', '/courses/../tools/secret.txt', '/courses/c1/%2e%2e/%2e%2e/tools/secret.txt'):
            r = self.get(t)
            self.assertGreaterEqual(r.status, 400, t)
            self.assertNotIn(fixture.CANARY, r.body, t)

    def test_a_link_inside_a_served_folder_is_refused(self):
        """A link from a served folder to the library's own tools folder, in its own test: it needs the right to make a link, so where that right is missing this says so instead of checking an address that is simply absent."""
        link, target = fixture.LIB / 'courses' / 'c1' / 'tools-link', fixture.LIB / 'tools'
        link.parent.mkdir(parents=True, exist_ok=True)
        usable = lambda: link.is_symlink() and os.path.isfile(link / 'secret.txt')
        why = 'the link does not resolve to the tools folder'
        if not usable():
            try:
                if link.is_symlink() or link.exists():
                    link.unlink()
                os.symlink(target, link)
            except OSError as e:
                why = f'{type(e).__name__}: {e}'     # e.g. WinError 1314, no right to make links on Windows
        if not usable():
            self.skipTest(f'could not make a usable link to the tools folder ({why})')
        r = self.get('/courses/c1/tools-link/secret.txt')
        self.assertGreaterEqual(r.status, 400)
        self.assertNotIn(fixture.CANARY, r.body)

    def test_page_with_a_connection_hint_loses_it(self):
        d = fixture.LIB / 'pages' / 'kinds'
        d.mkdir(parents=True, exist_ok=True)
        (d / 'hints.html').write_bytes(b'''<!doctype html><html><head><link rel=preconnect href="http://x.invalid"><link href="//y.invalid" rel="dns-prefetch"><LINK REL='Prefetch' href=/z>
<link rel="prerender" href=/q><link rel="stylesheet" href="keep.css"><link rel="canonical" href="/keep"></head><body><p>rel=preconnect stays as text</p></body></html>''')
        r = self.get('/pages/kinds/hints.html')
        self.assertEqual(r.status, 200)
        low = r.body.lower()
        for gone in (b'x.invalid', b'y.invalid', b'prerender', b"'prefetch'"):
            self.assertNotIn(gone, low)
        for kept in (b'keep.css', b'href="/keep"', b'rel=preconnect stays as text'):
            self.assertIn(kept, low)
        self.assertEqual(r.hs['x-dns-prefetch-control'], 'off')

    def test_saved_page_comes_with_what_its_scripts_unfolded(self):
        d = fixture.LIB / 'pages' / 'kinds'
        d.mkdir(parents=True, exist_ok=True)
        (d / 'talk.vtt').write_bytes(b'WEBVTT\n\n00:01.000 --> 00:02.000\nHello <b>there</b> & welcome\n\n00:02.000 --> 00:03.000\nHello <b>there</b> & welcome\n')
        page = (b'<!doctype html><html><head><title>t</title></head><body><a href="x.pdf" target="_blank" download>f</a><a href="https://e.example/" target="_blank">w</a>'
                b'<button data-toggle="offcanvas" data-target="#menu">m</button><video><track src="talk.vtt"></video>'
                b'<video><track src="../../../secret.vtt"></video></body></html>')
        (d / 'ocw.html').write_bytes(page)
        (d / 'index.html').write_bytes(page)
        for t in ('/pages/kinds/ocw.html', '/pages/kinds/', '/pages/kinds/index.html'):
            r = self.get(t)
            self.assertEqual(r.status, 200, t)
            self.no_code(r)
            self.assertEqual(int(r.hs['content-length']), len(r.body), t)
            b = r.body
            self.assertLess(b.lower().index(b'<head>'), b.index(b'<style>'))
            self.assertIn(b'.collapse', b)
            self.assertRegex(b, rb'<a href="x.pdf"\s*>')
            self.assertIn(b'https://e.example/" target="_blank"', b)    # still does nothing, but the page is not changed for it
            self.assertIn(b'<a href="#menu"', b)
            self.assertEqual(b.count(b'Hello there &amp; welcome'), 1)
            self.assertNotIn(b'<script', b)
        self.assertEqual(self.get('/pages/s.html').status, 200)

    def test_saved_page_transcript_stays_in_the_library(self):
        self.assertIsNone(self.part('/pages/kinds/ocw.html', '../../../canary-root.txt'))
        self.assertIsNone(self.part('/pages/kinds/ocw.html', 'https://evil.example/a.vtt'))
        self.assertIsNone(self.part('/pages/kinds/ocw.html', '//evil.example/a.vtt'))
        self.assertIsNone(self.part('/pages/kinds/ocw.html', '/api/health'))

    def part(self, page, src):
        h = server.Handler.__new__(server.Handler)
        h.path, h.directory = page, str(fixture.LIB)
        return h.saved_page_part(src)

    def test_app_page_may_not_sit_in_a_frame(self):
        r = self.get('/')
        self.assertEqual(r.status, 200)
        self.assertIn('<', r.body.decode()[:50])
        self.assertEqual(r.hs['content-security-policy'], "frame-ancestors 'none'")

    def test_no_server_or_date_header(self):
        r = self.get('/api/health')
        self.assertNotIn('server', r.hs)
        self.assertNotIn('date', r.hs)

    def test_map_info_has_no_personal_paths(self):
        r = self.get('/api/map/info')
        self.assertEqual(r.status, 200)
        info = json.loads(r.body)
        self.assertEqual(info['national'], {'state': 'complete', 'features': 7})
        self.assertNotIn(b'/Users/', r.body)

    def test_engine_error_is_an_answer(self):
        r = self.get('/api/t/boom')
        self.assertEqual(r.status, 500)
        self.assertNotIn(str(ROOT).encode(), r.body)
        self.assertEqual(self.get('/api/t/uncaught').status, 502)   # an error the Handler let out still becomes an answer

    def test_ordinary_api(self):
        self.assertEqual(json.loads(self.get('/api/health').body)['offline'], True)
        self.assertEqual(self.get('/ui/app.js').status, 200)
        self.assertEqual(self.get('/reader.css').status, 200)
        self.assertEqual(self.get('/api/nope').status, 404)
        r = json.loads(self.get('/api/find?q=boil').body)
        self.assertTrue(r)
        self.assertEqual(json.loads(self.get('/api/doc/pdfsmall').body)['id'], 'pdfsmall')

    def test_short_answer(self):
        r = self.get('/documents/t/short')
        self.assertEqual(r.status, 200)
        if self.mode == 'stream':
            self.assertFalse(r.ok)

    # ---- where things may go
    def test_frame_rule(self):
        ok = ['/documents/s.pdf', '/pages/s.html', '/videos/a.mp4', '/zim/x/y', '/assets/a', '/courses/a', '/collections/a', '/transcripts/a', '/metadata/videos/a', '/videos-external/a', '/documents/a?x=1#y']
        no = ['/', '/index.html', '/api/health', '/ui/app.js', '/sw.js', '/reader.css', '/__bridge/stream/start', '/documents/../api/health', '/documents/%2e%2e/api/health', '/zim/../api/x', '/documents', '/documentsx/a', '/metadata/x']
        for t in ok:
            self.assertTrue(self.b.frame_url_ok(self.b.origin + t), t)
        for t in no:
            self.assertFalse(self.b.frame_url_ok(self.b.origin + t), t)
        for u in ('https://evil.example/documents/a', 'file:///documents/a', 'javascript:alert(1)', 'lastbook://other/documents/a', self.b.origin + '.evil/documents/a'):
            self.assertFalse(self.b.frame_url_ok(u), u)
        for u in ('about:blank', 'about:srcdoc'):
            self.assertTrue(self.b.frame_url_ok(u), u)
        for u in ('data:text/html,<script>1</script>', 'blob:x', 'about:x', 'javascript:1', 'mailto:a@b', 'tel:1', 'macappstore://x', 'itms://x'):   # a new document in a frame does not keep the old one's policy
            self.assertFalse(self.b.frame_url_ok(u), u)

    def test_top_rule(self):
        o = self.b.origin
        for u in (o, o + '/', o + '/#/read/x?p=1', o + '/#/'):
            self.assertTrue(self.b.top_url_ok(u), u)
        for u in (o + '/pages/s.html', o + '/documents/s.pdf', o + '/api/health', o + '/ui/app.js', o + '/index.html', o + '/?x=1', 'https://evil.example/', 'about:blank', 'data:text/html,x', 'blob:x', o + '.evil/', 'javascript:1'):
            self.assertFalse(self.b.top_url_ok(u), u)

    def test_link_rule(self):
        o, nw = self.b.origin, self.b.new_window
        for gesture in (True, False, None):   # direct web addresses never leave the app
            self.assertEqual(nw('https://example.org/a', True, gesture), ('nothing', None))
            self.assertEqual(nw('http://example.org/', True, gesture), ('nothing', None))
        for gesture in (True, False, None):   # a frame opens nothing, gesture or not
            self.assertEqual(nw('https://example.org/', False, gesture), ('nothing', None))
            self.assertEqual(nw(o + '/documents/s.pdf', False, gesture), ('nothing', None))
        for u in ('file:///etc/hosts', 'javascript:alert(1)', 'data:text/html,x', 'about:blank', 'blob:x', 'ftp://x/', 'mailto:a@b', 'https://', 'https://a b/', 'lastbook://other/x', 'https://x/\ny'):
            self.assertEqual(nw(u, True, True), ('nothing', None), u)
        self.assertEqual(nw(o + '/documents/s.pdf#page=7', True, True), ('inside', o + '/#/read/pdfsmall?p=7&view=pdf'))
        self.assertEqual(nw(o + '/documents/s.pdf', True, None), ('inside', o + '/#/read/pdfsmall?p=1&view=pdf'))
        self.assertEqual(nw(o + '/pages/s.html', True, True), ('inside', o + '/#/read/saved'))
        self.assertEqual(nw(o + '/videos/a.mp4', True, True), ('inside', o + '/#/watch/vida'))
        self.assertEqual(nw(o + '/zim/wiki%20x.zim/A/B_c', True, True), ('inside', o + '/#/wiki/wiki%20x.zim/A/B_c'))
        self.assertEqual(nw(o + '/reports/gap-closure-status.html', True, True), ('nothing', None))   # the UI links there; the engine serves nothing there
        self.assertEqual(nw(o + '/documents/not-in-catalog.pdf', True, True), ('nothing', None))
        self.assertEqual(nw(o + '/pages/s.html', True, False), ('nothing', None))
        for u in (nw(o + '/pages/s.html', True, True)[1], nw(o + '/documents/s.pdf', True, True)[1], nw(o + '/zim/a/b', True, True)[1]):
            self.assertTrue(self.b.top_url_ok(u), u)

    def test_project_repository_requires_a_top_frame_popup_with_a_user_gesture(self):
        origin, new_window = self.b.origin, self.b.new_window
        action = origin + '/contribute/github'
        self.assertEqual(new_window(action, True, True, popup=True), ('contribute', None))
        for args in ((False, True), (True, False), (True, None)):
            self.assertEqual(new_window(action, *args, popup=True), ('nothing', None))
        self.assertEqual(new_window(action, True, True), ('nothing', None))
        self.assertFalse(self.b.top_url_ok(action))
        self.assertFalse(self.b.frame_url_ok(action))
        for url in (action + '?q=local', action + '#local', action + '/', 'https://github.com/Immortal-Protocols/lastbook'):
            self.assertEqual(new_window(url, True, True, popup=True), ('nothing', None), url)


class AssistantStaysHere(unittest.TestCase):
    def test_only_loopback_addresses(self):
        for good, out in (('http://127.0.0.1:19443', 'http://127.0.0.1:19443'), ('http://127.0.0.1:1/', 'http://127.0.0.1:1'), ('http://[::1]:80', 'http://[::1]:80'), ('http://localhost:9', 'http://127.0.0.1:9')):
            self.assertEqual(assistant.loopback_base(good), out)
        for bad in ('https://127.0.0.1:1', 'http://127.0.0.1', 'http://127.0.0.1:1/v1', 'http://10.0.0.5:1', 'http://example.org:80', 'http://127.0.0.1.example.org:1', 'http://127.0.0.1:1@example.org:1',
                    'http://localhost.example.org:1', 'http://0.0.0.0:1', 'http://127.0.0.1:1\n', 'ftp://127.0.0.1:1', ''):
            with self.assertRaises(ValueError, msg=bad):
                assistant.loopback_base(bad)

    def test_no_request_leaves_this_computer(self):
        import urllib.error, urllib.request
        for bad in ('http://example.org:80/v1/models', 'https://127.0.0.1:1/x', 'http://127.0.0.1:1@example.org:1/x', 'http://127.0.0.1:1\n/x'):
            with self.assertRaises(urllib.error.URLError, msg=bad):
                assistant.model_open(bad, 1)
        with self.assertRaises(urllib.error.URLError):
            assistant.model_open(urllib.request.Request('http://example.org:80/v1/chat/completions', b'{}'), 1)
        from engine import model_server     # where assistant.model_open lives
        kinds = {type(h).__name__ for h in model_server._opener.handlers}
        self.assertNotIn('ProxyHandler', {k for k in kinds if getattr(next(h for h in model_server._opener.handlers if type(h).__name__ == k), 'proxies', None)})
        self.assertIn('_NoRedirect', kinds)
        self.assertNotIn('HTTPRedirectHandler', kinds)
        self.assertIsNone(model_server._NoRedirect().redirect_request(None, None, 302, 'Found', {}, 'https://example.org/'))
        self.assertEqual(assistant.MODEL_URL, 'http://127.0.0.1:9/v1/chat/completions')



class AssistantChosenServer(unittest.TestCase):
    """#78: a model server chosen in Setup answers instead of Lastbook's own local AI, text only; choosing none goes back.
    REAL_STATUS and REAL_CHAT: the module below puts stubs in their place for the HTTP tests."""
    def setUp(self):
        self.local = mock.Mock()
        self.local.available.return_value = True
        self.local.status.return_value = {'name': 'Lastbook AI', 'state': 'stopped'}
        p = patch.object(assistant, 'LOCAL', self.local)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(assistant.use_server, None, None)

    def test_bundled_model_answers_when_nothing_is_chosen(self):
        self.assertTrue(assistant.local_on())
        st = REAL_STATUS()
        self.assertEqual((st['model'], st['online'], st['local']['name']), ('Lastbook AI', True, 'Lastbook AI'))
        self.assertNotIn('server', st)

    def test_chosen_server_answers_and_back(self):
        listed = []

        def models(url, timeout):
            listed.append(url)
            return io.BytesIO(b'{"data":[{"id":"small-9b"}]}')
        assistant.use_server('http://127.0.0.1:11434', 'small-9b')
        self.assertFalse(assistant.local_on())
        self.local.stop.assert_called_once()
        self.assertEqual((assistant.MODEL_URL, assistant.MODEL), ('http://127.0.0.1:11434/v1/chat/completions', 'small-9b'))
        with patch.object(assistant, 'model_open', side_effect=models):
            st = REAL_STATUS()
        self.assertEqual(listed, ['http://127.0.0.1:11434/v1/models'])
        self.assertEqual((st['model'], st['online'], st['local'], st['vision'], st['server']),
                         ('small-9b', True, None, False, {'address': '127.0.0.1:11434', 'model': 'small-9b'}))

        assistant.use_server(None, None)
        self.assertTrue(assistant.local_on())
        self.assertEqual((assistant.MODEL_URL, assistant.MODEL), ('http://127.0.0.1:9/v1/chat/completions', assistant.STARTED_WITH[1]))

    def test_an_unavailable_chosen_server_is_offline(self):
        assistant.use_server('http://127.0.0.1:11434', 'small-9b')
        with patch.object(assistant, 'model_open', side_effect=ConnectionRefusedError()):
            st = REAL_STATUS()
        self.assertEqual((st['online'], st['error'], st['server']['address']), (False, 'ConnectionRefusedError', '127.0.0.1:11434'))

    def test_never_off_this_computer(self):
        for bad in ('http://10.0.0.5:8080', 'http://example.org:80'):
            with self.assertRaises(ValueError):
                assistant.use_server(bad, 'm')
        self.assertFalse(assistant.CHOSEN)
        self.assertEqual(assistant.MODEL_URL, 'http://127.0.0.1:9/v1/chat/completions')

    def test_chosen_server_gets_text_tools_only(self):
        seen = []

        def one_round(msgs, tools, cancelled, wrote, set_state):
            seen.append(([t['function']['name'] for t in tools or []], msgs[0]['content']))
            return ('Answer.', {})
        assistant.use_server('http://127.0.0.1:11434', 'small-9b')
        with patch.object(assistant, '_http_round', side_effect=one_round), patch.object(assistant, 'context_for', return_value=None):
            REAL_CHAT([{'role': 'user', 'content': 'x'}], 'about', lambda ev: None, lambda: False)
        names, system = seen[0]
        self.assertIn('search_library', names)
        self.assertNotIn('view_page', names)
        self.assertEqual(system, assistant.SYSTEM_TEXT_ONLY)
        self.local.ensure_running.assert_not_called()

class AssistantHTTPMessages(unittest.TestCase):
    def round(self, messages, tools=None):
        import io
        sent, pieces = [], []
        response = io.BytesIO(b'data: {"choices":[{"delta":{"content":"Answer [S1]"}}]}\n\ndata: [DONE]\n')

        def send(req, timeout):
            body = json.loads(req.data)
            sent.append(body)
            if any(m['role'] == 'system' for m in body['messages'][1:]):
                raise ValueError('System message must be at the beginning.')
            return response

        with mock.patch.object(assistant, 'model_open', side_effect=send):
            result = assistant._http_round(messages, tools, lambda: False, pieces.append, lambda state: None)
        self.assertEqual(result, ('Answer [S1]', {}))
        self.assertEqual(pieces, ['Answer [S1]'])
        self.assertTrue(response.closed)
        return sent[0]

    def test_later_app_notes_stay_in_order_with_only_one_system_message(self):
        messages = [
            {'role': 'system', 'content': 'Use only the library.'},
            {'role': 'system', 'content': 'The person is on a guide.'},
            {'role': 'user', 'content': 'Which pages cover this?'},
            {'role': 'system', 'content': 'Initial library search results: [S1].'},
            {'role': 'assistant', 'content': '', 'tool_calls': [
                {'id': 'call_0', 'type': 'function', 'function': {'name': 'read_pages', 'arguments': '{}'}}]},
            {'role': 'tool', 'tool_call_id': 'call_0', 'content': 'Page text [S1].'},
            {'role': 'system', 'content': 'Stop searching now.'},
            {'role': 'system', 'content': 'Your reply was empty. Answer the question now.'},
        ]
        before = json.loads(json.dumps(messages))
        tools = [{'type': 'function', 'function': {'name': 'read_pages', 'parameters': {'type': 'object'}}}]
        body = self.round(messages, tools)
        self.assertEqual(body['tools'], tools)
        self.assertEqual([m['role'] for m in body['messages']],
                         ['system', 'user', 'user', 'user', 'assistant', 'tool', 'user', 'user'])
        for i, message in enumerate(before):
            expected = ({'role': 'user', 'content': '[Note from the Lastbook app, not from the person]\n' + message['content']}
                        if i > 0 and message['role'] == 'system' else message)
            self.assertEqual(body['messages'][i], expected)
        self.assertEqual(messages, before)
        self.assertEqual(self.round(messages, tools), body)  # a later round must not add a second marker
        self.assertEqual(messages, before)

    def test_without_later_system_messages_keeps_image_and_tool_messages(self):
        messages = [
            {'role': 'system', 'content': 'Use only the library.'},
            {'role': 'user', 'content': [{'type': 'text', 'text': 'Look at this page.'},
                                         {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,AA=='}}]},
            {'role': 'assistant', 'content': '', 'tool_calls': [
                {'id': 'call_1', 'type': 'function', 'function': {'name': 'view_page', 'arguments': '{}'}}]},
            {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'Page image [S1].'},
        ]
        body = self.round(messages)
        self.assertEqual(body['messages'], messages)
        self.assertNotIn('tools', body)


class ServerMode(unittest.TestCase):
    """server.py run on its own (--lan, the library server): the map asks for 20 or more tiles at once."""

    def listen_queue(self, server_class, handler):
        srv = server_class(('127.0.0.1', 0), handler, bind_and_activate=False)
        try:
            with mock.patch.object(socket.socket, 'listen') as listen:   # never really listens: WholeProcess checks that
                srv.server_bind()
                srv.server_activate()
            return listen.call_args.args[0]
        finally:
            srv.server_close()

    def test_listen_queue_holds_a_burst_of_tiles(self):
        # Python's default queue is 5: on macOS the waiting connections beyond it were reset, and those tiles stayed blank.
        self.assertGreaterEqual(self.listen_queue(server.HTTPServer, server.Handler), 64)

    def test_library_server_has_the_same_queue(self):
        # engine/library.py serve: the plain library server, without server.py on top.
        library = server.library
        self.assertGreaterEqual(self.listen_queue(library.HTTPServer, library.Handler), 64)


class CatalogWrite(unittest.TestCase):
    """engine/library.py writes catalog.json when it builds; the app recognises a library by that file (app/main.py check)."""

    def test_cut_short_keeps_the_old_catalog(self):
        library = server.library
        root = Path(tempfile.mkdtemp(prefix='lastbook-catalog-'))
        self.addCleanup(shutil.rmtree, root)
        (root / 'manifests').mkdir()
        (root / 'docs').mkdir()
        (root / 'docs' / 'a.pdf').write_bytes(b'%PDF-1.4')
        (root / 'manifests' / 'docs.json').write_text(json.dumps([{'path': 'docs/a.pdf', 'title': 'A'}]), encoding='utf-8')
        old = '[{"path": "docs/a.pdf", "title": "A"}]'
        (root / 'catalog.json').write_text(old, encoding='utf-8')
        real_write = Path.write_text

        def half_then_fail(path, text, *args, **kwargs):   # a full disk, or the build stopped mid-write
            real_write(path, text[:len(text) // 2], *args, **kwargs)
            raise OSError('No space left on device')

        with mock.patch.object(library, 'ROOT', root), mock.patch.object(Path, 'write_text', half_then_fail):
            with self.assertRaises(OSError):
                library.catalog()
        self.assertEqual((root / 'catalog.json').read_text(encoding='utf-8'), old)


class NothingGoesOut(unittest.TestCase):
    """The shells cannot run here on both systems, so what must be gone from them is checked in their source."""

    def test_no_way_to_hand_anything_to_the_system(self):
        for name in ('shell_macos.py', 'shell_windows.py', 'bridge.py', 'main.py'):
            src = (ROOT / 'app' / name).read_text(encoding='utf-8')
            for word in ('open_in_browser', 'open_external', 'startfile', 'NSWorkspace', 'openURL', "'browser'", 'webbrowser', 'Process.Start', 'ShellExecute'):
                self.assertNotIn(word, src, name)

    def test_contribution_opens_only_the_public_project_repository(self):
        from contribute import launch_project_repository
        with mock.patch('contribute.webbrowser.open') as launch:
            launch_project_repository()
        launch.assert_called_once_with('https://github.com/Immortal-Protocols/lastbook')


class StreamTests(Both, unittest.TestCase):
    mode = 'stream'

    def chat_count(self):
        return len(STUB['runs'])

    def test_cancel_mid_body_stops_the_handler(self):
        b = B.Bridge(MOD, 'stream', B.ORIGIN_MAC, per_request=4 * MiB)
        r = Rec(auto=False)
        ex = b.start('GET', b.origin + '/videos/huge.mkv', {}, None, r)
        self.assertTrue(wait_until(lambda: len(r.parts) == 4))
        lane = b.lanes['large']
        self.assertEqual(lane.budget.used, 4 * MiB)
        self.assertEqual(lane.active, 1)
        ex.cancel()
        self.assertTrue(ex.stopped)
        self.assertEqual(lane.budget.used, 0)
        self.assertTrue(wait_until(lambda: lane.active == 0))
        self.assertFalse(r.done.is_set())
        self.assertEqual(len(r.parts), 4)
        for a in r.acks:   # acks that arrive late must not count twice
            a()
        self.assertEqual(lane.budget.used, 0)

    def test_chunks_are_bounded(self):
        r = Rec()
        self.b.start('GET', self.b.origin + A, {'Range': 'bytes=0-'}, None, r)
        self.assertTrue(r.done.wait(20))
        self.assertTrue(all(len(p) <= B.CHUNK for p in r.parts))
        self.assertTrue(r.ok)
        r = Rec()
        self.b.start('GET', self.b.origin + '/documents/t/manywrites', {}, None, r)
        self.assertTrue(r.done.wait(20))
        self.assertEqual(max(len(p) for p in r.parts), B.CHUNK)
        self.assertEqual(sum(len(p) for p in r.parts), 3 * MiB)

    def test_head_comes_before_body_and_order_is_kept(self):
        events = []

        class S(Rec):
            def head(self, *a):
                events.append('head')
                super().head(*a)

            def data(self, c, ack):
                events.append('data')
                super().data(c, ack)

            def finish(self, ok):
                events.append('finish')
                super().finish(ok)
        r = S()
        self.b.start('GET', self.b.origin + '/documents/s.pdf', {}, None, r)
        self.assertTrue(r.done.wait(10))
        self.assertEqual(events[0], 'head')
        self.assertEqual(events[-1], 'finish')
        self.assertEqual(set(events[1:-1]), {'data'})

    def test_chat_arrives_piece_by_piece(self):
        r = Rec()
        STUB.update(pieces=6, delay=0.1)
        t0 = time.time()
        self.b.start('POST', self.b.origin + '/api/chat', self.key, b'{"messages":[{"role":"user","content":"hi"}]}', r)
        self.assertTrue(r.first.wait(5))
        first_at = time.time() - t0
        self.assertTrue(r.done.wait(10))
        spread = r.times[-1] - r.times[0]
        OBSERVED['stream chat'] = f'{len(r.parts)} pieces over {spread:.2f} s, first after {first_at * 1000:.0f} ms'
        self.assertEqual(r.status, 200)
        self.assertEqual(r.hs['content-type'], 'text/event-stream')
        self.assertGreaterEqual(len(r.parts), 6)
        self.assertGreater(spread, 0.4)
        self.assertLess(first_at, 0.3)
        self.assertIn(b'"done"', r.body)
        self.assertTrue(r.ok)

    def test_chat_stop_reaches_the_model_side(self):
        r = Rec()
        STUB.update(pieces=200, delay=0.05)
        before = len(STUB['stopped'])
        ex = self.b.start('POST', self.b.origin + '/api/chat', self.key, b'{}', r)
        self.assertTrue(wait_until(lambda: len(r.parts) >= 3))
        ex.cancel()
        self.assertTrue(wait_until(lambda: len(STUB['stopped']) > before, 5))
        self.assertLess(STUB['stopped'][-1], 50)
        self.assertFalse(r.done.is_set())
        self.assertTrue(wait_until(lambda: self.b.lanes['chat'].active == 0))

    def test_cancel_while_waiting_on_the_budget(self):
        tiny = {**B.LANES, 'large': (2, 10, 2 * MiB)}
        b = B.Bridge(MOD, 'stream', B.ORIGIN_MAC, lanes=tiny, per_request=8 * MiB)
        r1, r2 = Rec(auto=False), Rec(auto=False)
        e1 = b.start('GET', b.origin + '/videos/huge.mkv', {}, None, r1)
        e2 = b.start('GET', b.origin + '/videos/huge.mkv', {}, None, r2)
        lane = b.lanes['large']
        self.assertTrue(wait_until(lambda: lane.budget.used == 2 * MiB and lane.active == 2))
        time.sleep(0.2)
        t = time.time()
        e1.cancel()
        e2.cancel()
        self.assertTrue(wait_until(lambda: lane.active == 0, 2))
        OBSERVED['cancel to worker free, while blocked on the budget'] = f'{(time.time() - t) * 1000:.0f} ms'
        self.assertEqual(lane.budget.used, 0)

    def test_cancel_while_queued_never_runs(self):
        lanes = {**B.LANES, 'large': (1, 10, 64 * MiB)}
        b = B.Bridge(MOD, 'stream', B.ORIGIN_MAC, lanes=lanes)
        r1, r2 = Rec(auto=False), Rec()
        e1 = b.start('GET', b.origin + '/videos/huge.mkv', {}, None, r1)
        self.assertTrue(r1.first.wait(5))
        e2 = b.start('GET', b.origin + '/videos/a.mp4', {}, None, r2)
        e2.cancel()
        e1.cancel()
        self.assertTrue(wait_until(lambda: b.lanes['large'].done >= 2))
        self.assertIsNone(r2.status)
        self.assertFalse(r2.done.is_set())

    def test_cap_holds_and_work_resumes(self):
        cap, per = 4 * MiB, 2 * MiB
        lanes = {**B.LANES, 'large': (6, 100, cap)}
        b = B.Bridge(MOD, 'stream', B.ORIGIN_MAC, lanes=lanes, per_request=per)
        recs = [Rec(auto=False) for _ in range(12)]
        for r in recs:
            b.start('GET', b.origin + '/videos/a.mp4', {'Range': 'bytes=0-3145727'}, None, r)   # 3 MiB each
        lane = b.lanes['large']
        self.assertTrue(wait_until(lambda: lane.budget.used == cap))
        time.sleep(0.3)
        self.assertEqual(lane.budget.used, cap)
        self.assertEqual(lane.budget.peak, cap)
        self.assertEqual(lane.active, 6)
        self.assertEqual(sum(len(r.parts) for r in recs), 4)    # 4 MiB out, the rest held back at the source
        small = call(b, 'GET', '/api/health')     # the large budget is full; the small lane does not care
        self.assertEqual(small.status, 200)
        deadline = time.time() + 20
        while time.time() < deadline and not all(r.done.is_set() for r in recs):
            for r in recs:
                acks, r.acks = r.acks, []
                for a in acks:
                    a()
            time.sleep(0.005)
        self.assertTrue(all(r.done.is_set() for r in recs))
        for r in recs:
            self.assertEqual(r.body, pat(0, 3 * MiB))
            for a in r.acks:
                a()
        self.assertLessEqual(lane.budget.peak, cap)
        self.assertEqual(lane.budget.used, 0)

    def test_per_request_limit(self):
        b = B.Bridge(MOD, 'stream', B.ORIGIN_MAC)
        r = Rec(auto=False)
        ex = b.start('GET', b.origin + '/videos/huge.mkv', {}, None, r)
        self.assertTrue(wait_until(lambda: len(r.parts) == B.PER_REQUEST // MiB))
        time.sleep(0.2)
        self.assertEqual(len(r.parts), B.PER_REQUEST // MiB)
        ex.cancel()

    def test_default_cap_under_flood(self):
        b = B.Bridge(MOD, 'stream', B.ORIGIN_MAC)
        recs = [Rec(auto=False) for _ in range(300)]
        exs = [b.start('GET', b.origin + '/videos/huge.mkv', {'Range': f'bytes={i * 1000}-'}, None, r) for i, r in enumerate(recs)]
        lane = b.lanes['large']
        self.assertTrue(wait_until(lambda: lane.budget.used >= 6 * B.PER_REQUEST))
        time.sleep(0.2)
        self.assertTrue(wait_until(lambda: lane.budget.used == lane.budget.cap))   # a piece fits the per-request limit, so finished requests can hold bytes too
        time.sleep(0.2)
        self.assertEqual(lane.budget.used, lane.budget.cap)
        self.assertEqual(lane.budget.peak, lane.budget.cap)
        self.assertEqual(lane.active, 6)
        self.assertGreater(len(lane.waiting), 280)
        times = []
        for _ in range(200):
            t = time.perf_counter()
            self.assertEqual(call(b, 'GET', '/api/health').status, 200)
            times.append(time.perf_counter() - t)
        t = time.perf_counter()
        self.assertEqual(call(b, 'GET', '/ui/app.js').status, 200)
        ui = time.perf_counter() - t
        OBSERVED['stream, small during large flood (300 videos, nothing acknowledged)'] = f'/api/health median {statistics.median(times) * 1000:.2f} ms, max {max(times) * 1000:.2f} ms over 200; /ui/app.js {ui * 1000:.1f} ms; large budget used {lane.budget.used / MiB:.0f} MiB of {lane.budget.cap / MiB:.0f}'
        self.assertLess(max(times), 1.0)
        for e in exs:
            e.cancel()
        self.assertTrue(wait_until(lambda: lane.active == 0 and not lane.waiting))
        self.assertEqual(lane.budget.used, 0)

    def test_queue_full(self):
        lanes = {**B.LANES, 'large': (1, 2, 64 * MiB)}
        b = B.Bridge(MOD, 'stream', B.ORIGIN_MAC, lanes=lanes)
        recs = [Rec(auto=False) for _ in range(3)]
        exs = [b.start('GET', b.origin + '/videos/huge.mkv', {}, None, r) for r in recs]
        self.assertTrue(recs[0].first.wait(5))
        wait_until(lambda: b.lanes['large'].active == 1)
        extra = [Rec() for _ in range(3)]
        got = [b.start('GET', b.origin + '/videos/a.mp4', {}, None, r) for r in extra]
        self.assertIn(None, got)
        self.assertEqual(sum(r.status == 503 for r in extra), got.count(None))
        self.assertGreaterEqual(b.counts['queue-full'], 1)
        for e in exs + got:
            if e:
                e.cancel()

    def test_redirect_becomes_a_page_that_moves_itself(self):
        r = self.get('/documents/t/redirect')
        self.assertEqual(r.status, 200)
        self.assertIn(b'http-equiv="refresh"', r.body)
        self.assertIn(b'&quot;&lt;b&gt;', r.body)
        self.assertNotIn(b'"<b>', r.body)
        self.assertIn("default-src 'none'", r.hs['content-security-policy'])

    def test_no_poll_route(self):
        self.assertEqual(call(self.b, 'POST', '/__bridge/stream/start', {**self.key, 'Content-Type': 'application/octet-stream'}, b'{}').status, 404)
        self.assertEqual(self.get('/__bridge/stream/start').status, 404)

    def test_top_script_no_polling(self):
        s = self.b.top_script()
        self.assertIn(self.b.key, s)
        self.assertIn('POLL = false', s)
        out = run_node(s, self.b.origin, self.b.key, 0)
        self.assertTrue(out['top_patched'])
        self.assertFalse(out['frame_patched'])
        self.assertFalse(out['sandboxed_top_patched'])

    def test_real_chat_with_no_model_is_plain(self):
        assistant.model_status, assistant.chat = REAL_STATUS, REAL_CHAT
        try:
            assistant._status['at'] = 0
            r = call(self.b, 'POST', '/api/chat', self.key, b'{}', timeout=15)
        finally:
            assistant.model_status, assistant.chat = stub_status, stub_chat
        self.assertEqual(r.status, 200)
        self.assertIn(b'model_unavailable', r.body)
        OBSERVED['chat with no model'] = r.body.decode().strip()


class BufferTests(Both, unittest.TestCase):
    mode = 'buffer'

    def chat_count(self):
        return len(STUB['runs'])

    def poll(self, op, body=b'', b=None):
        b = b or self.b
        return call(b, 'POST', '/__bridge/stream' + op, {'X-Lastbook-Key': b.key, 'Content-Type': 'application/octet-stream', 'Origin': b.origin}, body)

    def test_whole_file_is_handed_over_by_name(self):
        r = self.get('/documents/mid.bin')
        self.assertEqual(r.status, 200)
        self.assertTrue(r.path.endswith('mid.bin'))
        self.assertEqual(self.b.lanes['large'].budget.peak, 0)
        self.assertEqual(self.b.lanes['large'].budget.used, 0)

    def test_big_ticketed_file_copies_nothing(self):
        self.b.give_ticket(self.b.origin + '/documents/big.bin')
        r = self.get('/documents/big.bin', is_document=True)
        self.assertTrue(r.path.endswith('big.bin'))
        self.assertEqual(self.b.lanes['large'].budget.peak, 0)

    def test_whole_max(self):
        b = B.Bridge(MOD, 'buffer', B.ORIGIN_WINDOWS, tmpdir=str(TMP), whole_max=35 * MiB)
        b.give_ticket(b.origin + '/documents/big.bin')
        self.assertEqual(call(b, 'GET', '/documents/big.bin', is_document=True).status, 413)
        self.assertEqual(B.WHOLE_MAX, 256 * MiB)
        self.assertEqual(self.b.whole_max, 256 * MiB)

    def test_big_generated_body_spills_and_is_cleaned_up(self):
        before = tmp_files()
        ev, box = threading.Event(), []
        self.b.give_ticket(self.b.origin + '/documents/t/nolen?mb=20')
        self.b.fetch('GET', self.b.origin + '/documents/t/nolen?mb=20', {}, None, lambda r: (box.append(r), ev.set()))
        self.assertTrue(ev.wait(30))
        resp = box[0]
        self.assertTrue(resp.path and resp.delete)
        self.assertEqual(os.path.getsize(resp.path), 20 * MiB)
        self.assertEqual(self.b.lanes['large'].budget.used, 0)
        os.unlink(resp.path)
        self.assertEqual(tmp_files(), before)

    def test_cancelled_spill_is_removed(self):
        before = tmp_files()
        ev = threading.Event()
        ex = self.b.fetch('GET', self.b.origin + '/documents/t/nolen?mb=30&ms=50', {}, None, lambda r: ev.set())
        self.assertTrue(wait_until(lambda: tmp_files() != before, 10))
        ex.cancel()
        self.assertTrue(wait_until(lambda: tmp_files() == before, 10))
        self.assertFalse(ev.is_set())

    def test_budget_blocks_and_never_deadlocks(self):
        cap = 6 * MiB
        lanes = {**B.LANES, 'large': (6, 100, cap)}
        b = B.Bridge(MOD, 'buffer', B.ORIGIN_WINDOWS, tmpdir=str(TMP), lanes=lanes)
        before = tmp_files()
        results, lock = [], threading.Lock()
        n = 24
        ev = threading.Event()

        def done(resp):
            data = resp.body
            if resp.path:
                with open(resp.path, 'rb') as f:
                    data = f.read()
                os.unlink(resp.path)
            time.sleep(0.02)
            resp.release()
            with lock:
                results.append((resp.status, hashlib.sha256(data).digest()))
                if len(results) == n:
                    ev.set()
        for _ in range(n):
            b.fetch('GET', b.origin + A, {'Range': 'bytes=0-'}, None, done)
        self.assertTrue(ev.wait(60), b.stats())
        want = hashlib.sha256(pat(0, 4 * MiB)).digest()
        self.assertTrue(all(s == 206 and d == want for s, d in results))
        lane = b.lanes['large']
        OBSERVED['buffer, 24 pieces through a 6 MiB budget'] = f"peak {lane.budget.peak / MiB:.0f} MiB, {b.counts.get('spilled', 0)} spilled to disk, all bytes right"
        self.assertLessEqual(lane.budget.peak, cap)
        self.assertEqual(lane.budget.used, 0)
        self.assertEqual(tmp_files(), before)

    def test_small_during_large_flood(self):
        TestHandler.slow_started.clear()
        ev = threading.Event()
        count = [0]

        def done(resp):
            resp.release()
            count[0] += 1
            if count[0] == 106:
                ev.set()
        for _ in range(106):
            self.b.fetch('GET', self.b.origin + '/documents/t/slow?ms=400', {}, None, done)
        lane = self.b.lanes['large']
        self.assertTrue(wait_until(lambda: lane.active == 6))
        times = []
        for _ in range(100):
            t = time.perf_counter()
            self.assertEqual(call(self.b, 'GET', '/api/health').status, 200)
            times.append(time.perf_counter() - t)
        OBSERVED['buffer, small during large flood (106 slow requests)'] = f'/api/health median {statistics.median(times) * 1000:.2f} ms, max {max(times) * 1000:.2f} ms over 100; large lane active {lane.active}, waiting {len(lane.waiting)}'
        self.assertLess(max(times), 0.3)
        self.assertEqual(lane.peak_active, 6)
        self.assertTrue(ev.wait(30))

    def test_renders_do_not_take_small_workers(self):
        for _ in range(20):
            self.b.fetch('GET', self.b.origin + '/api/page/t/1.png?ms=400', {}, None, lambda r: r.release())
        lane = self.b.lanes['render']
        self.assertTrue(wait_until(lambda: lane.active == 2))
        t = time.perf_counter()
        self.assertEqual(call(self.b, 'GET', '/api/health').status, 200)
        self.assertLess(time.perf_counter() - t, 0.2)
        self.assertEqual(lane.peak_active, 2)
        self.assertEqual(self.b.lanes['small'].active, 0)

    def keyed_health_ms(self):
        t = time.perf_counter()
        self.assertEqual(call(self.b, 'GET', '/api/health', headers={B.KEY_HEADER: self.b.key}).status, 200)
        return (time.perf_counter() - t) * 1000

    def test_slow_api_with_no_key_never_holds_up_the_top_frame(self):
        """No key: a saved page. It has its own lane, however much of it it fills."""
        for _ in range(64):
            self.b.fetch('GET', self.b.origin + '/api/t/slow?ms=1000', {}, None, lambda r: r.release())
        guest = self.b.lanes['guest']
        self.assertTrue(wait_until(lambda: guest.active >= 8))
        self.assertEqual(self.b.lanes['small'].active, 0)
        ms = self.keyed_health_ms()
        OBSERVED['/api/health with the key, behind 64 slow requests with none'] = f'{ms:.0f} ms'
        self.assertLess(ms, 200)

    def test_slow_api_with_the_key_makes_the_lane_grow(self):
        """The top frame's own slow requests add workers instead of holding up its quick ones."""
        for i in range(20):
            self.b.fetch('GET', self.b.origin + '/api/t/slow?ms=3000', {B.KEY_HEADER: self.b.key}, None, lambda r: r.release())
        small = self.b.lanes['small']
        self.assertTrue(wait_until(lambda: small.active >= 8))
        ms = self.keyed_health_ms()
        OBSERVED['/api/health behind 20 slow requests of 3 s in the same lane'] = f'{ms:.0f} ms'
        self.assertLess(ms, 500)
        self.assertLessEqual(small.peak_threads, B.GROW_TO['small'])

    def test_a_wrong_key_is_no_key(self):
        before = self.b.lanes['guest'].done
        self.assertEqual(call(self.b, 'GET', '/api/health', headers={B.KEY_HEADER: 'x' * 43}).status, 200)
        self.assertTrue(wait_until(lambda: self.b.lanes['guest'].done == before + 1))

    def test_added_workers_go_away(self):
        for i in range(20):
            self.b.fetch('GET', self.b.origin + '/api/t/slow?ms=100', {}, None, lambda r: r.release())
        guest = self.b.lanes['guest']
        self.assertTrue(wait_until(lambda: guest.threads > 8))
        real = B.SHRINK_AFTER
        self.assertTrue(wait_until(lambda: guest.threads == 8, real + 3))

    def test_redirect_passes_through(self):
        r = self.get('/documents/t/redirect')
        self.assertEqual(r.status, 302)
        self.assertEqual(r.hs['location'], '/documents/plain.txt?a="<b>')

    # ---- chat by polling
    def run_poll_to_end(self, sid):
        got, polls = b'', 0
        while True:
            r = self.poll(f'/{sid}/next')
            polls += 1
            self.assertEqual(r.status, 200)
            got += r.body
            if r.hs.get('x-bridge-end'):
                return got, polls

    def test_poll_chat(self):
        STUB.update(pieces=6, delay=0.1)
        s = self.poll('/start', b'{"messages":[{"role":"user","content":"hi"}]}')
        self.assertEqual(s.status, 200)
        self.assertEqual(s.hs['x-bridge-status'], '200')
        self.assertEqual(dict(json.loads(s.hs['x-bridge-headers']))['Content-Type'], 'text/event-stream')
        got, polls = self.run_poll_to_end(s.hs['x-bridge-stream'])
        OBSERVED['poll chat'] = f'{polls} polls'
        self.assertIn(b'"done"', got)
        self.assertGreater(polls, 2)
        self.assertEqual(self.poll(f"/{s.hs['x-bridge-stream']}/next").status, 404)

    def test_poll_cancel_reaches_the_model_side(self):
        STUB.update(pieces=200, delay=0.05)
        before = len(STUB['stopped'])
        s = self.poll('/start', b'{}')
        sid = s.hs['x-bridge-stream']
        self.poll(f'/{sid}/next')
        self.assertEqual(self.poll(f'/{sid}/cancel').status, 200)
        self.assertTrue(wait_until(lambda: len(STUB['stopped']) > before, 5))
        self.assertEqual(self.poll(f'/{sid}/next').status, 404)

    def test_poll_refusals(self):
        before = self.chat_count()
        oct_ = {'Content-Type': 'application/octet-stream'}
        self.assertEqual(call(self.b, 'POST', '/__bridge/stream/start', {**oct_, 'Origin': self.b.origin}, b'{}').status, 403)
        self.assertEqual(call(self.b, 'POST', '/__bridge/stream/start', {**oct_, 'Origin': 'null', 'X-Lastbook-Key': self.b.key}, b'{}').status, 403)
        self.assertEqual(call(self.b, 'POST', '/__bridge/stream/start', {'Content-Type': 'application/json', 'X-Lastbook-Key': self.b.key}, b'{}').status, 403)
        self.assertEqual(self.get('/__bridge/stream/start').status, 403)
        self.assertEqual(self.poll('/' + 'a' * 32 + '/next').status, 404)
        self.assertEqual(self.poll('/nonsense').status, 404)
        self.assertEqual(call(self.b, 'POST', '/__bridge/other', {'X-Lastbook-Key': self.b.key, 'Content-Type': 'application/octet-stream'}, b'').status, 404)
        self.assertEqual(self.chat_count(), before)

    def test_poll_cap_and_idle_reap(self):
        STUB.update(pieces=2000, delay=0.05)
        ids = []
        for _ in range(B.MAX_STREAMS):
            s = self.poll('/start', b'{}')
            self.assertEqual(s.status, 200)
            ids.append(s.hs['x-bridge-stream'])
        self.assertEqual(self.poll('/start', b'{}').status, 429)
        before = len(STUB['stopped'])
        for s in self.b.streams.values():
            s['seen'] -= B.STREAM_IDLE + 1
        s = self.poll('/start', b'{}')
        self.assertEqual(s.status, 200)
        self.assertTrue(wait_until(lambda: len(STUB['stopped']) >= before + B.MAX_STREAMS, 5))
        self.poll(f"/{s.hs['x-bridge-stream']}/cancel")

    def test_poll_empty_next_keeps_waiting(self):
        b = B.Bridge(MOD, 'buffer', B.ORIGIN_WINDOWS, tmpdir=str(TMP), poll_wait=0.05)
        STUB.update(pieces=2, delay=0.3)
        s = self.poll('/start', b'{}', b)
        sid = s.hs['x-bridge-stream']
        empties = 0
        while True:
            r = self.poll(f'/{sid}/next', b=b)
            empties += not r.body
            if r.hs.get('x-bridge-end'):
                break
        self.assertGreater(empties, 0)

    def test_top_script_polling(self):
        s = self.b.top_script()
        self.assertIn('POLL = true', s)
        out = run_node(s, self.b.origin, self.b.key, 1)
        self.assertTrue(out['top_patched'])
        self.assertFalse(out['frame_patched'])
        self.assertFalse(out['sandboxed_top_patched'])
        by = {(c['method'], c['url'].replace(self.b.origin, '')): c for c in out['calls']}
        self.assertEqual(by[('GET', '/api/health')]['key'], self.b.key)       # the top frame's own /api/ reads: see LANES
        self.assertIsNone(by[('GET', '/ui/app.css')]['key'])
        self.assertIsNone(by[('GET', 'https://elsewhere.example/y')]['key'])
        self.assertEqual(by[('POST', '/api/tool/x')]['key'], self.b.key)
        self.assertIsNone(by[('POST', 'https://elsewhere.example/x')]['key'])
        self.assertEqual(by[('POST', '/__bridge/stream/start')]['key'], self.b.key)
        self.assertEqual(out['chat_status'], 200)
        self.assertIn('data: hi', out['chat_text'])
        self.assertNotIn(('POST', '/api/chat'), by)


def _windows_sockets(pid):
    """This process's rows in `netstat -ano` (TCP and UDP, listening or connected). netstat ships with Windows."""
    r = subprocess.run(['netstat', '-ano'], capture_output=True, encoding='oem', errors='replace')   # netstat writes the OEM code page
    if r.returncode or 'TCP' not in r.stdout:
        raise RuntimeError(f'netstat gave no usable output: {r.returncode} {r.stderr}')
    return '\n'.join(line for line in r.stdout.splitlines()
                     if line.split()[:1] in (['TCP'], ['UDP']) and line.split()[-1] == pid)


def _windows_modules():
    """Every DLL and the exe loaded into this process, as lower-case paths, from EnumProcessModulesEx (psapi)."""
    import ctypes
    from ctypes import wintypes
    psapi, kernel32 = ctypes.WinDLL('psapi'), ctypes.WinDLL('kernel32')
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD,
                                           ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    proc = kernel32.GetCurrentProcess()
    needed, size = wintypes.DWORD(), 1024
    while True:   # grow the array until every module fits: a module past the end would be dropped without a word
        mods = (wintypes.HMODULE * size)()
        if not psapi.EnumProcessModulesEx(proc, mods, ctypes.sizeof(mods), ctypes.byref(needed), 3):   # 3 = LIST_MODULES_ALL
            raise ctypes.WinError()
        if needed.value <= ctypes.sizeof(mods):
            break
        size = needed.value // ctypes.sizeof(wintypes.HMODULE)
    name, paths = ctypes.create_unicode_buffer(1024), []
    for m in mods[:needed.value // ctypes.sizeof(wintypes.HMODULE)]:
        if psapi.GetModuleFileNameExW(proc, wintypes.HMODULE(m), name, len(name)):
            paths.append(name.value)
    return '\n'.join(paths).lower().replace('\\', '/')


class WholeProcess(unittest.TestCase):
    def test_no_listening_socket_and_no_model(self):
        self.assertEqual(LISTENS, [])
        pid = str(os.getpid())
        lsof = '/usr/sbin/lsof' if os.path.exists('/usr/sbin/lsof') else shutil.which('lsof')   # the system lsof first on a Mac
        if lsof:
            out = subprocess.run([lsof, '-nP', '-a', '-p', pid, '-i'], capture_output=True, text=True).stdout
            files = subprocess.run([lsof, '-nP', '-p', pid], capture_output=True, text=True).stdout.lower()
            how = 'lsof -i'
        elif sys.platform == 'win32':
            # No lsof on Windows. netstat covers the sockets; the loaded-module list covers the model runtime (onnxruntime.dll).
            # A model file opened as plain data is not checked here; without the runtime loaded, nothing can use it.
            out, files, how = _windows_sockets(pid), _windows_modules(), 'netstat -ano'
        else:
            self.skipTest('no lsof on this system, and not Windows: the process-level socket and file check cannot run here')
        self.assertIn('python', files, 'the process file/module listing came back empty, so this check proved nothing')
        self.assertEqual(out.strip(), '', out)
        for word in ('onnx', 'bge-small', 'derived/models'):
            self.assertNotIn(word, files)
        self.assertNotIn('onnxruntime.', ' '.join(k for k, v in sys.modules.items() if v is not None))
        OBSERVED[f'{how} for this process'] = 'no rows' if not out.strip() else out

    def test_map_info_still_gives_what_the_ui_reads(self):
        info = server.map_info()
        for k in ('national', 'version', 'aerial_detail', 'aerial_rev', 'terrain_circle', 'datasets'):
            self.assertIn(k, info)
        self.assertEqual(info['national']['state'], 'complete')
        self.assertEqual(server.national_status()['source'], '/Users/someone/library-data/x.pbf')   # the engine itself still sees it

    def test_nothing_written_to_the_real_library(self):
        self.assertTrue(str(server.LIB).startswith(str(DATA)))

    def test_budgets_add_up(self):
        self.assertEqual(B.TOTAL_INFLIGHT, 128 * MiB)
        for mode in ('stream', 'buffer'):
            self.assertGreater(B.VIDEO_PIECE[mode], 2.38e6)
            self.assertGreaterEqual(B.VIDEO_PIECE[mode], 4 * MiB)
            self.assertLessEqual(B.VIDEO_PIECE[mode], 8 * MiB)


def run_node(script, origin, key, poll):
    node = shutil.which('node') or '/Users/you/.local/bin/node'
    p = DATA / 'tmp-top-script.js'
    p.write_text(script)
    try:
        r = subprocess.run([node, str(HERE / 'top_script_test.mjs'), str(p), origin, key, str(poll)], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(p)
    if r.returncode:
        raise AssertionError(r.stderr[-1500:])
    return json.loads(r.stdout)


# ---- the stub: stands in for the model. handle_post, emit and wfile are the real ones.
STUB = {'pieces': 4, 'delay': 0.05, 'runs': [], 'sent': [], 'stopped': []}
REAL_STATUS, REAL_CHAT = assistant.model_status, assistant.chat


def stub_status():
    return {'online': True, 'model': 'TEST-STUB-NOT-A-MODEL', 'error': None}


def stub_chat(messages, about, emit, cancelled):
    STUB['runs'].append(time.time())
    emit({'type': 'state', 'state': 'thinking'})
    for i in range(STUB['pieces']):
        if cancelled():
            STUB['stopped'].append(i)
            return
        time.sleep(STUB['delay'])
        emit({'type': 'delta', 'text': f'p{i} '})
        STUB['sent'].append(i)
    emit({'type': 'done', 'answer': 'x', 'sources': [], 'consulted': [], 'invalid': [], 'latency': {}})


assistant.model_status, assistant.chat = stub_status, stub_chat

if __name__ == '__main__':
    prog = unittest.main(exit=False, verbosity=2 if '-v' in sys.argv else 1)
    print('\nObserved:')
    for k, v in OBSERVED.items():
        print(f'  {k}: {v}')
    sys.stdout.flush()
    os._exit(0 if prog.result.wasSuccessful() else 1)
