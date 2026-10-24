/* Trang Thư viện: /library/ */
(function () {
    'use strict';
    var L = window.Lib, icon = L.icon, esc = L.esc;
    var VIEW_KEY = 'library_view_v1';   // tab + cách sắp xếp, chỉ để tiện cho người xem
    var view = { tab: 'all', sort: 'updated' };
    try { Object.assign(view, JSON.parse(localStorage.getItem(VIEW_KEY)) || {}); } catch (e) { /* bỏ qua */ }

    document.body.innerHTML =
        '<main class="wrap">'
        + '<header class="lib-head"><h1>Thư viện</h1>'
        + '<a class="icon-btn" href="editor.html" aria-label="Biên tập truyện" title="Biên tập truyện">' + icon('edit') + '</a></header>'
        + '<div id="continue"></div>'
        + '<div class="lib-tools">'
        + '<label class="search">' + icon('search') + '<input type="search" id="q" placeholder="Tìm truyện (không cần dấu)…" aria-label="Tìm truyện"></label>'
        + '<div class="tabs" role="toolbar" aria-label="Lọc truyện">'
        + '<button type="button" data-tab="all">Tất cả</button>'
        + '<button type="button" data-tab="reading">Đang đọc</button>'
        + '<button type="button" data-tab="saved">Đã lưu</button>'
        + '</div></div>'
        + '<div class="list-head"><span id="count"></span>'
        + '<select id="sort" aria-label="Sắp xếp"><option value="updated">Mới cập nhật</option>'
        + '<option value="recent">Đọc gần đây</option><option value="title">Tên A–Z</option></select></div>'
        + '<ul class="story-list" id="list"><li class="loading" style="padding-top:20vh">Đang tải…</li></ul>'
        + '<footer class="lib-foot"></footer>'
        + '</main>';

    var stories = [], pointers = {}, readCache = {};
    L.fetchStories('./').then(function (list) {
        stories = list;
        pointers = L.progress.allPointers();
        drawContinue();
        draw();
    }).catch(function () {
        document.getElementById('list').innerHTML = '<li class="empty">Không tải được danh sách truyện.</li>';
    });

    function readCount(slug) {
        if (!(slug in readCache)) readCache[slug] = L.progress.readSet(slug).size;
        return readCache[slug];
    }
    function progressOf(s) {
        var done = readCount(s.slug);
        return s.count ? Math.min(100, Math.round(100 * done / s.count)) : 0;
    }

    function drawContinue() {
        var best = null;
        stories.forEach(function (s) {
            var p = pointers[s.slug];
            if (p && (!best || (p.at || 0) > (best.p.at || 0))) best = { s: s, p: p };
        });
        var box = document.getElementById('continue');
        if (!best) { box.innerHTML = ''; return; }
        var pct = progressOf(best.s);
        box.innerHTML = '<a class="continue-card" href="./' + encodeURIComponent(best.s.slug) + '/' + encodeURIComponent(best.p.chapter) + '/">'
            + '<div class="kicker">Đọc tiếp</div>'
            + '<div class="title">' + esc(best.s.title) + '</div>'
            + '<div class="sub">' + esc(best.p.chapterName || 'Chương ' + best.p.chapter)
            + (best.p.para > 0 && best.p.total ? ' · đoạn ' + (best.p.para + 1) + '/' + best.p.total : '') + '</div>'
            + (best.s.count > 1 ? '<div class="bar"><span style="width:' + pct + '%"></span></div>' : '')
            + '</a>';
    }

    function draw() {
        var words = L.fold(document.getElementById('q').value).split(/\s+/).filter(Boolean);
        var saved = L.marks.list();
        var list = stories.filter(function (s) {
            if (view.tab === 'reading' && !pointers[s.slug]) return false;
            if (view.tab === 'saved' && saved.indexOf(s.slug) < 0) return false;
            if (!words.length) return true;
            var hay = L.fold(s.title || '') + ' ' + s.slug;
            return words.every(function (w) { return hay.indexOf(w) >= 0; });
        });
        list.sort(function (a, b) {
            if (view.sort === 'title') return (a.title || '').localeCompare(b.title || '', 'vi');
            if (view.sort === 'recent') {
                var pa = pointers[a.slug], pb = pointers[b.slug];
                return ((pb && pb.at) || 0) - ((pa && pa.at) || 0) || (b.timestamp || 0) - (a.timestamp || 0);
            }
            return (b.timestamp || 0) - (a.timestamp || 0);
        });
        document.querySelectorAll('.tabs button').forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.tab === view.tab); });
        document.getElementById('sort').value = view.sort;

        var el = document.getElementById('list');
        if (!list.length) {
            var msg = words.length ? 'Không có truyện nào khớp.'
                : view.tab === 'reading' ? 'Chưa đọc truyện nào trên máy này.'
                : view.tab === 'saved' ? 'Chưa lưu truyện nào. Bấm biểu tượng bookmark ở trang truyện để lưu.' : 'Thư viện trống.';
            el.innerHTML = '<li class="empty">' + msg + '</li>';
        } else {
            el.innerHTML = list.map(function (s) {
                var p = pointers[s.slug], pct = progressOf(s), mark = saved.indexOf(s.slug) >= 0;
                var meta = '<span>' + L.fmt(s.count || 0) + ' chương</span>' + (s.date ? '<span>' + esc(s.date) + '</span>' : '');
                if (p) meta += '<span class="reading">' + (s.count > 1 ? 'Đã đọc ' + L.fmt(readCount(s.slug)) + '/' + L.fmt(s.count) : 'Đang đọc') + '</span>';
                return '<li><a class="story" href="./' + encodeURIComponent(s.slug) + '/">'
                    + '<div class="story-body"><h2 class="story-title">' + esc(s.title || s.slug) + '</h2>'
                    + '<div class="story-meta">' + meta + '</div>'
                    + (p && s.count > 1 ? '<div class="bar"><span style="width:' + pct + '%"></span></div>' : '')
                    + '</div>'
                    + (mark ? '<span class="mark" title="Đã lưu">' + icon('bookmark') + '</span>' : '')
                    + '</a></li>';
            }).join('');
        }
        document.getElementById('count').textContent = list.length === stories.length
            ? L.fmt(stories.length) + ' truyện' : L.fmt(list.length) + ' / ' + L.fmt(stories.length) + ' truyện';
    }
    function remember() { try { localStorage.setItem(VIEW_KEY, JSON.stringify(view)); } catch (e) { /* bỏ qua */ } }

    var timer = null;
    document.getElementById('q').addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(draw, 120); });
    document.querySelector('.tabs').addEventListener('click', function (e) {
        var b = e.target.closest('button[data-tab]');
        if (!b) return;
        view.tab = b.dataset.tab; remember(); draw();
    });
    document.getElementById('sort').addEventListener('change', function () { view.sort = this.value; remember(); draw(); });
    window.addEventListener('pageshow', function (e) {
        if (e.persisted && stories.length) { pointers = L.progress.allPointers(); readCache = {}; drawContinue(); draw(); }
    });
})();
