/*
 * Bộ tải dữ liệu chương, dùng chung cho Thư viện (library/) và truyện ngắn (stories/).
 *
 * Dữ liệu có thể nằm ở ba chỗ, thử lần lượt:
 *   1. Kho dữ liệu ngoài (Cloudflare Worker + R2) — khi tools/build_site.py điền DATA_BASE;
 *   2. data.json.gz cạnh trang (bản deploy GitHub Pages nén gzip);
 *   3. data.json gốc (chạy thẳng từ repo trên máy).
 * Bản .gz chứa chữ thường có tiền tố "~" (ký tự không có trong base64); data.json gốc là base64.
 *
 * Các trình đọc giải mã bằng atob(...) + TextDecoder; shim atob bên dưới trả về đúng byte
 * UTF-8 cho chuỗi "~chữ", nên không phải sửa từng trình đọc.
 */
(function () {
    'use strict';
    if (window.ChapterData) return;

    // build_site.py thay giá trị này bằng địa chỉ Worker (vd. "https://stv-data.abc.workers.dev").
    // Rỗng = không dùng kho ngoài. Đặt window.CHAPTER_DATA_BASE trước khi nạp file để thử trên máy.
    var DATA_BASE = String(window.CHAPTER_DATA_BASE || /*DATA_BASE*/'').replace(/\/+$/, '');

    var nativeAtob = window.atob.bind(window);
    window.atob = function (s) {
        s = String(s);
        if (s.charAt(0) !== '~') return nativeAtob(s);
        var bytes = new TextEncoder().encode(s.slice(1)), out = '';
        for (var i = 0; i < bytes.length; i += 8192) {
            out += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192));
        }
        return out;
    };

    // Trình duyệt cũ (Safari < 16.4) chưa có DecompressionStream: nạp pako để giải nén.
    var PAKO = 'https://cdnjs.cloudflare.com/ajax/libs/pako/2.1.0/pako_inflate.min.js';
    var pakoReady = null;
    function loadPako() {
        if (window.pako) return Promise.resolve();
        if (!pakoReady) {
            pakoReady = new Promise(function (resolve, reject) {
                var s = document.createElement('script');
                s.src = PAKO;
                s.onload = resolve;
                s.onerror = function () { pakoReady = null; reject(new Error('Không tải được pako')); };
                document.head.appendChild(s);
            });
        }
        return pakoReady;
    }

    function gunzip(buf) {
        if (window.DecompressionStream) {
            var stream = new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'));
            return new Response(stream).arrayBuffer();
        }
        return loadPako().then(function () { return window.pako.inflate(new Uint8Array(buf)).buffer; });
    }

    function parse(buf) {
        var head = new Uint8Array(buf, 0, Math.min(2, buf.byteLength));
        // Máy chủ có thể đã tự giải nén (Content-Encoding) — kiểm tra byte đầu thay vì tin đuôi file.
        var raw = head[0] === 0x1f && head[1] === 0x8b ? gunzip(buf) : Promise.resolve(buf);
        return raw.then(function (b) { return JSON.parse(new TextDecoder('utf-8').decode(b)); });
    }

    function get(url) {
        return fetch(url).then(function (res) {
            if (!res.ok) throw new Error(res.status + ' ' + url);
            return res.arrayBuffer();
        });
    }

    /** Các địa chỉ thử lần lượt cho một data.json (tương đối theo trang hiện tại). */
    function candidates(url) {
        var abs = new URL(url, location.href), list = [];
        if (DATA_BASE && abs.origin === location.origin) list.push(DATA_BASE + abs.pathname + '.gz');
        list.push(abs.href + '.gz', abs.href);
        return list;
    }

    var cache = {};
    /** Promise → object data.json của chương. `url` là đường dẫn data.json (không có .gz). */
    function load(url) {
        var key = new URL(url, location.href).href;
        if (cache[key]) return cache[key];
        var urls = candidates(url), p = get(urls[0]);
        urls.slice(1).forEach(function (next) { p = p.catch(function () { return get(next); }); });
        var result = p.then(parse);
        cache[key] = result;
        result.catch(function () { delete cache[key]; });
        return result;
    }

    /** Tải sẵn (vd. chương sau) để trình duyệt lưu vào bộ nhớ đệm HTTP; lỗi thì bỏ qua. */
    function prefetch(url) {
        var run = function () { load(url).catch(function () {}); };
        if (window.requestIdleCallback) requestIdleCallback(run, { timeout: 3000 }); else setTimeout(run, 1500);
    }

    /** Thay cho $.getJSON(url, cb) trong trình đọc truyện ngắn cũ; vẫn hỗ trợ .fail()/.done(). */
    function jq(url, cb) {
        var p = load(url).then(function (data) { cb(data); return data; });
        var api = {
            done: function (fn) { p.then(fn); return api; },
            fail: function (fn) { p.catch(fn); return api; },
            always: function (fn) { p.then(fn, fn); return api; },
        };
        return api;
    }

    window.ChapterData = { load: load, prefetch: prefetch, jq: jq, candidates: candidates, base: DATA_BASE };
})();
