/**
 * Cloudflare Worker phát dữ liệu chương từ bucket R2 cho trang syndoriamiku.github.io.
 *
 * Triển khai: Cloudflare → Workers & Pages → Worker → Edit code → dán toàn bộ file này → Deploy.
 * Settings → Bindings → R2 bucket, tên biến BUCKET → chọn bucket chứa dữ liệu (vd. stv-library).
 *
 * Chỉ đọc. App trên máy (r2_store.py) ghi thẳng vào bucket mỗi lần lưu truyện.
 *   - Chương: library/<truyện>/<chương>/data.json.gz, stories/<truyện>/data.json.gz — trả nguyên gzip,
 *     chapter-data.js trong trình duyệt tự giải nén. Cache 10 phút.
 *   - Danh mục: library/list.json, library/stories.json, library/<truyện>/chapters.json,
 *     stories/list.json — JSON, cache 1 phút để truyện/chương mới hiện nhanh.
 */

const ALLOWED_ORIGINS = [
  /^https:\/\/syndoriamiku\.github\.io$/,
  /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/, // chạy thử trên máy
];
const CHAPTER_KEY = /^(library\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+|stories\/[A-Za-z0-9_.-]+)\/data\.json\.gz$/;
const CATALOG_KEY = /^(library\/(list|stories)\.json|library\/[A-Za-z0-9_-]+\/chapters\.json|stories\/list\.json)$/;
const CHAPTER_CACHE = 'public, max-age=600'; // sửa chương: ≤ 10 phút sau người đọc thấy bản mới
const CATALOG_CACHE = 'public, max-age=60';  // truyện/chương mới: ≤ 1 phút

function corsHeaders(request) {
  const origin = request.headers.get('Origin') || '';
  const headers = {
    'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
    'Access-Control-Max-Age': '86400',
    'Vary': 'Origin',
  };
  if (ALLOWED_ORIGINS.some((re) => re.test(origin))) headers['Access-Control-Allow-Origin'] = origin;
  return headers;
}

function reply(status, body, headers) {
  return new Response(body, { status, headers });
}

export default {
  async fetch(request, env) {
    const cors = corsHeaders(request);
    if (request.method === 'OPTIONS') return reply(204, null, cors);
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return reply(405, 'Method not allowed', { ...cors, Allow: 'GET, HEAD, OPTIONS' });
    }

    const key = new URL(request.url).pathname.replace(/^\/+/, '');
    const isChapter = CHAPTER_KEY.test(key);
    if (!isChapter && !CATALOG_KEY.test(key)) {
      return reply(404, 'Not found', { ...cors, 'Cache-Control': 'no-store' });
    }

    // onlyIf: R2 tự xử lý If-None-Match / If-Modified-Since → không đọc lại nội dung khi trình duyệt đã có.
    const object = await env.BUCKET.get(key, { onlyIf: request.headers });
    if (object === null) {
      return reply(404, 'Not found', { ...cors, 'Cache-Control': 'no-store' });
    }

    const headers = new Headers(cors);
    headers.set('Content-Type', isChapter ? 'application/gzip' : 'application/json; charset=utf-8');
    headers.set('Cache-Control', isChapter ? CHAPTER_CACHE : CATALOG_CACHE);
    headers.set('ETag', object.httpEtag);
    headers.set('X-Content-Type-Options', 'nosniff');

    if (!('body' in object) || !object.body) {
      return reply(304, null, headers); // điều kiện onlyIf không thoả = trình duyệt đã có bản mới nhất
    }
    headers.set('Content-Length', String(object.size));
    return reply(200, request.method === 'HEAD' ? null : object.body, headers);
  },
};
