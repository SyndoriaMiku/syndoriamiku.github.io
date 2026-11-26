/*
 * Bộ tải dữ liệu truyện, dùng chung cho Thư viện (library/) và truyện ngắn (stories/).
 *
 * Truyện không nằm trên GitHub Pages: app trên máy đẩy thẳng lên Cloudflare R2 (r2_store.py),
 * trang đọc qua Worker (cloudflare/worker.js). Mỗi file thử lần lượt:
 *   1. Worker (DATA_BASE) — chương: data.json.gz; danh mục: list.json, stories.json, chapters.json;
 *   2. cùng đường dẫn trên trang hiện tại (chạy repo trên máy: data.json gốc, danh mục gốc).
 * Bản .gz chứa chữ thường có tiền tố "~" (ký tự không có trong base64); data.json gốc là base64.
 *
 * Các trình đọc giải mã bằng atob(...) + TextDecoder; shim atob bên dưới trả về đúng byte
 * UTF-8 cho chuỗi "~chữ", nên không phải sửa từng trình đọc.
 */
(function () {
    'use strict';
    if (window.ChapterData) return;

    // Worker đọc R2 (công khai, chỉ đọc). Đặt window.CHAPTER_DATA_BASE = '' trước khi nạp file
    // để chỉ đọc dữ liệu trên máy (xem thử truyện chưa đồng bộ).
    var DATA_BASE = String(window.CHAPTER_DATA_BASE !== undefined ? window.CHAPTER_DATA_BASE
        : 'https://stv-data.lyralei2001.workers.dev').replace(/\/+$/, '');
    var DATA_PATH = /^\/(library|stories)\//;

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
        if (DATA_BASE && abs.origin === location.origin && DATA_PATH.test(abs.pathname)) {
            list.push(DATA_BASE + abs.pathname + '.gz');
        }
        list.push(abs.href);
        return list;
    }

    function firstOk(urls, read) {
        var p = get(urls[0]);
        urls.slice(1).forEach(function (next) { p = p.catch(function () { return get(next); }); });
        return p.then(read);
    }

    /** Danh mục (list.json, stories.json, chapters.json…): Worker trước, rồi cùng đường dẫn. */
    function json(url) {
        var abs = new URL(url, location.href), urls = [];
        if (DATA_BASE && abs.origin === location.origin && DATA_PATH.test(abs.pathname)) {
            urls.push(DATA_BASE + abs.pathname);
        }
        urls.push(abs.href);
        return firstOk(urls, function (buf) { return JSON.parse(new TextDecoder('utf-8').decode(buf)); });
    }

    var cache = {};
    /** Promise → object data.json của chương. `url` là đường dẫn data.json (không có .gz). */
    function load(url) {
        var key = new URL(url, location.href).href;
        if (cache[key]) return cache[key];
        var result = firstOk(candidates(url), parse);
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

    /** Thay cho $.getJSON(url, cb) với danh mục (vd. stories/list.json). */
    function jqJson(url, cb) {
        var p = json(url).then(function (data) { cb(data); return data; });
        var api = {
            done: function (fn) { p.then(fn); return api; },
            fail: function (fn) { p.catch(fn); return api; },
            always: function (fn) { p.then(fn, fn); return api; },
        };
        return api;
    }

    window.ChapterData = { load: load, json: json, prefetch: prefetch, jq: jq, jqJson: jqJson,
        candidates: candidates, base: DATA_BASE };
})();
