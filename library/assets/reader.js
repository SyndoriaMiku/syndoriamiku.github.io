/* Trang đọc chương: /library/<truyện>/<chương>/ (chỉ tiếng Việt). */
(function () {
    'use strict';
    var L = window.Lib, icon = L.icon, esc = L.esc;
    var parts = location.pathname.split('/').filter(Boolean);
    if (parts.length && /\.html?$/.test(parts[parts.length - 1])) parts.pop();
    var at = parts.lastIndexOf('library');
    var slug = parts[at + 1], chapterId = parts[at + 2];
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

    document.body.innerHTML =
        '<div class="read-progress" aria-hidden="true"><span></span></div>'
        + '<header class="topbar">'
        + '<a class="icon-btn" href="../" aria-label="Về trang truyện">' + icon('back') + '</a>'
        + '<div class="topbar-title"><div class="t1" id="tStory">Đang tải…</div><div class="t2" id="tChapter"></div></div>'
        + '<button class="icon-btn" type="button" id="btnList" aria-label="Danh sách chương">' + icon('list') + '</button>'
        + '<button class="icon-btn text" type="button" id="btnSettings" aria-label="Tuỳ chỉnh hiển thị">Aa</button>'
        + '</header>'
        + '<main class="reader" id="reader"><div class="reader-inner">'
        + '<div class="loading" id="loading">Đang tải chương…</div>'
        + '</div></main>'
        + '<nav class="bottombar" aria-label="Chuyển chương">'
        + '<a class="btn" id="barPrev" aria-label="Chương trước">' + icon('prev') + '<span>Trước</span></a>'
        + '<button class="btn pos" type="button" id="barPos" aria-label="Danh sách chương">…</button>'
        + '<a class="btn primary" id="barNext" aria-label="Chương sau"><span>Sau</span>' + icon('next') + '</a>'
        + '</nav>';

    var $ = function (id) { return document.getElementById(id); };
    var inner = document.querySelector('.reader-inner');
    var topbar = document.querySelector('.topbar');
    var blocks = [], story = null, chapters = [], index = -1;

    // ───────── tải dữ liệu ─────────
    function decode(b64) {
        try {
            var bin = atob(b64 || ''), bytes = new Uint8Array(bin.length);
            for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
            return new TextDecoder('utf-8').decode(bytes).normalize('NFC');
        } catch (e) { return ''; }
    }
    Promise.all([
        L.fetchJSON('./data.json'),
        L.fetchStory(slug, '../', '../../').catch(function () { return null; }),
    ]).then(function (res) {
        render(res[0], res[1]);
    }).catch(function () {
        inner.innerHTML = '<div class="error">Không tải được chương này.<br><br><a class="btn" href="../">Về trang truyện</a></div>';
    });

    function render(data, info) {
        story = info;
        chapters = (info && info.chapters) || [];
        index = chapters.findIndex(function (c) { return L.norm(c.id) === L.norm(chapterId); });
        var chap = chapters[index] || {};
        var storyTitle = (info && info.title) || data.title || '';
        var chapterTitle = chap.name || data.chapter_title || 'Chương ' + (index + 1);
        document.title = chapterTitle + ' · ' + storyTitle;
        $('tStory').textContent = storyTitle;
        $('tChapter').textContent = chapterTitle;

        var paras = (data.content || []).map(function (item) { return decode(item.vi); });
        var words = paras.join(' ').split(/\s+/).filter(Boolean).length;
        var minutes = Math.max(1, Math.round(words / 230));
        var pos = index >= 0 ? 'Chương ' + L.fmt(index + 1) + '/' + L.fmt(chapters.length) + ' · ' : '';
        inner.innerHTML = '<header class="chapter-head">'
            + '<a class="story-link" href="../">' + esc(storyTitle) + '</a>'
            + '<h1>' + esc(chapterTitle) + '</h1>'
            + '<div class="chapter-meta">' + pos + '~' + minutes + ' phút đọc</div></header>'
            + '<article class="text" id="text"></article>'
            + '<nav class="chapter-end" aria-label="Hết chương"><div class="end-label">Hết chương</div>'
            + '<div class="end-nav"><a class="btn" id="endPrev">' + icon('prev') + 'Chương trước</a>'
            + '<a class="btn primary" id="endNext">Chương sau' + icon('next') + '</a></div>'
            + '<button class="link-btn" type="button" id="endList">Danh sách chương</button></nav>';
        var text = $('text'), frag = document.createDocumentFragment();
        paras.forEach(function (p) { var el = document.createElement('p'); el.textContent = p; frag.appendChild(el); });
        text.appendChild(frag);
        blocks = Array.prototype.slice.call(text.children);

        setupNav();
        setupProgress(storyTitle, chapterTitle);
        $('endList').onclick = openList;
        updateBar();
    }

    // ───────── chuyển chương ─────────
    function link(el, chap, label) {
        if (chap) { el.href = '../' + encodeURIComponent(chap.id) + '/'; el.removeAttribute('aria-disabled'); }
        else { el.removeAttribute('href'); el.setAttribute('aria-disabled', 'true'); }
        if (label) el.title = label;
    }
    function setupNav() {
        var prev = chapters[index - 1], next = chapters[index + 1];
        [$('barPrev'), $('endPrev')].forEach(function (el) { link(el, prev, prev && prev.name); });
        [$('barNext'), $('endNext')].forEach(function (el) { link(el, next, next && next.name); });
        if (!next) $('endNext').innerHTML = 'Đã hết truyện';
        $('barPos').textContent = index >= 0 ? L.fmt(index + 1) + ' / ' + L.fmt(chapters.length) : 'Mục lục';
        [$('barNext'), $('endNext')].forEach(function (el) {
            el.addEventListener('click', function () { L.progress.markRead(slug, chapterId); });
        });
        if (next) {  // tải sẵn chương sau để bấm là hiện ngay
            var pre = document.createElement('link');
            pre.rel = 'prefetch'; pre.href = '../' + encodeURIComponent(next.id) + '/data.json';
            document.head.appendChild(pre);
        }
        document.addEventListener('keydown', function (e) {
            if (e.altKey || e.ctrlKey || e.metaKey || /input|select|textarea/i.test(e.target.tagName) || listSheet.isOpen() || settingsSheet.isOpen()) return;
            if (e.key === 'ArrowLeft' && prev) location.href = $('barPrev').href;
            if (e.key === 'ArrowRight' && next) { L.progress.markRead(slug, chapterId); location.href = $('barNext').href; }
        });
    }

    // ───────── tiến độ đọc ─────────
    var restoring = false, userMoved = false, saveTimer = null;
    function topOffset() { return document.body.classList.contains('bars-hidden') ? 0 : topbar.getBoundingClientRect().bottom; }
    function currentPara() {
        var top = topOffset() + 8, lo = 0, hi = blocks.length - 1, ans = blocks.length - 1;
        while (lo <= hi) {
            var mid = (lo + hi) >> 1;
            if (blocks[mid].getBoundingClientRect().bottom > top) { ans = mid; hi = mid - 1; } else lo = mid + 1;
        }
        return ans;
    }
    function atEnd() { return window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 300; }
    function scrollToPara(i) {
        var el = blocks[Math.min(i, blocks.length - 1)];
        if (!el) return;
        restoring = true;
        window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - topOffset() - 16);
        setTimeout(function () { restoring = false; }, 150);
    }
    function setupProgress(storyTitle, chapterTitle) {
        if (!blocks.length) return;
        function record() {
            if (restoring) return;
            var para = atEnd() ? blocks.length - 1 : currentPara();
            var mine = L.progress.position(slug, chapterId);
            if (para > 0 || mine) L.progress.setPosition(slug, chapterId, para, blocks.length);
            // Chỉ mở ra xem (chưa cuộn) thì không lấy chỗ "Đọc tiếp" của chương đang đọc dở.
            var pointer = L.progress.pointer(slug);
            if (para > 0 || atEnd() || !pointer || pointer.chapter === chapterId) {
                L.progress.setPointer(slug, { chapter: chapterId, para: para, total: blocks.length,
                    chapterName: chapterTitle, storyTitle: storyTitle, at: Date.now() });
            }
            if (para >= blocks.length - 2 || atEnd()) L.progress.markRead(slug, chapterId);
        }
        var own = L.progress.position(slug, chapterId), pointer = L.progress.pointer(slug);
        var from = own || (pointer && pointer.chapter === chapterId ? pointer : null);
        var resume = from && from.para > 0 && !location.hash ? from.para : 0;
        if (resume) {
            requestAnimationFrame(function () { scrollToPara(resume); });
            setTimeout(function () { if (!userMoved) scrollToPara(resume); }, 500);
            toast('Tiếp tục ở đoạn ' + (resume + 1) + '/' + blocks.length, 'Về đầu chương', function () { window.scrollTo(0, 0); });
        }
        ['wheel', 'touchstart', 'keydown', 'mousedown'].forEach(function (t) {
            window.addEventListener(t, function () { userMoved = true; }, { passive: true, once: true });
        });
        window.addEventListener('scroll', function () { clearTimeout(saveTimer); saveTimer = setTimeout(record, 400); }, { passive: true });
        window.addEventListener('pagehide', record);
        document.addEventListener('visibilitychange', function () { if (document.hidden) record(); });
        setTimeout(record, resume ? 1000 : 300);
    }

    // ───────── thanh trên/dưới tự ẩn, thanh tiến độ ─────────
    var lastY = window.scrollY;
    function updateBar() {
        var max = document.documentElement.scrollHeight - window.innerHeight;
        document.querySelector('.read-progress span').style.width = (max > 0 ? Math.min(100, 100 * window.scrollY / max) : 100) + '%';
    }
    window.addEventListener('scroll', function () {
        var y = window.scrollY, dy = y - lastY;
        if (Math.abs(dy) > 6) {
            var hide = dy > 0 && y > 120 && !atEnd();
            document.body.classList.toggle('bars-hidden', hide);
            lastY = y;
        }
        updateBar();
    }, { passive: true });
    // Chạm vào giữa trang để hiện/ẩn thanh (không tính khi đang bôi đen chữ hay bấm link).
    document.getElementById('reader').addEventListener('click', function (e) {
        if (e.target.closest('a, button') || String(window.getSelection())) return;
        document.body.classList.toggle('bars-hidden');
    });

    function toast(message, action, onAction) {
        var el = document.createElement('div');
        el.className = 'toast';
        el.setAttribute('role', 'status');
        el.innerHTML = '<span>' + esc(message) + '</span>';
        if (action) {
            var b = document.createElement('button');
            b.className = 'link-btn'; b.type = 'button'; b.textContent = action;
            b.onclick = function () { onAction(); el.remove(); };
            el.appendChild(b);
        }
        document.body.appendChild(el);
        setTimeout(function () { el.remove(); }, 6000);
    }

    // ───────── danh sách chương ─────────
    var listSheet = L.sheet('Danh sách chương'), listView = null;
    function openList() { listSheet.open(); }
    listSheet.onOpen(function () {
        if (!listView) {
            listView = L.chapterList(listSheet.body, { slug: slug, chapters: chapters, base: '../', currentId: chapterId });
        } else listView.refresh();
        var el = listView.focusEl();
        if (el) el.scrollIntoView({ block: 'center' });
    });
    $('btnList').onclick = openList;
    $('barPos').onclick = openList;

    // ───────── tuỳ chỉnh hiển thị ─────────
    var settingsSheet = L.sheet('Hiển thị');
    var wakeLock = null;
    function applyWake() {
        var on = L.settings.get().wake;
        if (on && 'wakeLock' in navigator && !document.hidden) {
            navigator.wakeLock.request('screen').then(function (l) { wakeLock = l; }).catch(function () {});
        } else if (!on && wakeLock) { wakeLock.release(); wakeLock = null; }
    }
    document.addEventListener('visibilitychange', function () { if (!document.hidden) applyWake(); });
    applyWake();

    function change(patch) {
        var keep = blocks.length ? currentPara() : -1;
        L.settings.set(patch);
        if (keep > 0) scrollToPara(keep);
        if ('wake' in patch) applyWake();
        drawSettings();
    }
    function seg(label, key, options, value) {
        return '<div class="set-row"><div class="set-label">' + label + '</div><div class="seg">'
            + options.map(function (o) {
                return '<button type="button" data-k="' + key + '" data-v="' + o[0] + '" aria-pressed="' + (value === o[0]) + '">' + o[1] + '</button>';
            }).join('') + '</div></div>';
    }
    function drawSettings() {
        var s = L.settings.get();
        var themes = [['warm', 'Tối ấm', '#15130f', '#d9d1c3'], ['black', 'Đen', '#000', '#c9c3b8'],
            ['sepia', 'Sepia', '#f1e7d3', '#3d3226'], ['light', 'Sáng', '#faf9f6', '#2b2823']];
        var html = '<div class="set-row"><div class="set-label">Nền</div><div class="swatches">'
            + themes.map(function (t) {
                return '<button type="button" class="swatch" data-k="theme" data-v="' + t[0] + '" aria-pressed="' + (s.theme === t[0])
                    + '" style="background:' + t[2] + ';color:' + t[3] + '">' + t[1] + '</button>';
            }).join('') + '</div></div>'
            + '<div class="set-row"><div class="set-label"><span>Cỡ chữ</span></div><div class="stepper">'
            + '<button type="button" data-step="size" data-d="-1" aria-label="Giảm cỡ chữ">A−</button><output>' + s.size + 'px</output>'
            + '<button type="button" data-step="size" data-d="1" aria-label="Tăng cỡ chữ">A+</button></div></div>'
            + '<div class="set-row"><div class="set-label">Giãn dòng</div><div class="stepper">'
            + '<button type="button" data-step="line" data-d="-0.1" aria-label="Giảm giãn dòng">−</button><output>' + s.line.toFixed(2).replace(/0$/, '') + '</output>'
            + '<button type="button" data-step="line" data-d="0.1" aria-label="Tăng giãn dòng">+</button></div></div>'
            + seg('Phông chữ', 'font', [['sans', 'Hệ thống'], ['serif', 'Có chân'], ['literata', 'Literata']], s.font)
            + seg('Khoảng cách đoạn', 'spacing', [['sm', 'Gọn'], ['md', 'Vừa'], ['lg', 'Thoáng']], s.spacing)
            + seg('Căn lề', 'align', [['left', 'Trái'], ['justify', 'Đều hai bên']], s.align)
            + (window.matchMedia('(min-width: 720px)').matches ? seg('Độ rộng cột chữ', 'width', [['sm', 'Hẹp'], ['md', 'Vừa'], ['lg', 'Rộng']], s.width) : '')
            + ('wakeLock' in navigator ? '<div class="set-row"><label class="switch"><span>Giữ màn hình sáng khi đọc</span>'
                + '<input type="checkbox" data-k="wake"' + (s.wake ? ' checked' : '') + '></label></div>' : '')
            + '<div class="set-foot"><button type="button" class="link-btn" data-reset>Khôi phục mặc định</button></div>';
        settingsSheet.body.innerHTML = html;
    }
    settingsSheet.body.addEventListener('click', function (e) {
        var b = e.target.closest('button');
        if (!b) return;
        var s = L.settings.get();
        if (b.dataset.reset != null) {
            var keep = blocks.length ? currentPara() : -1;
            L.settings.reset(); applyWake();
            if (keep > 0) scrollToPara(keep);
            drawSettings(); return;
        }
        if (b.dataset.step === 'size') change({ size: Math.min(30, Math.max(14, s.size + +b.dataset.d)) });
        else if (b.dataset.step === 'line') change({ line: Math.min(2.4, Math.max(1.3, Math.round((s.line + +b.dataset.d) * 100) / 100)) });
        else if (b.dataset.k) { var p = {}; p[b.dataset.k] = b.dataset.v; change(p); }
    });
    settingsSheet.body.addEventListener('change', function (e) {
        if (e.target.dataset.k === 'wake') change({ wake: e.target.checked });
    });
    settingsSheet.onOpen(drawSettings);
    $('btnSettings').onclick = function () { settingsSheet.open(); };
})();
