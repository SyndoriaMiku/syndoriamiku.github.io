/* Trang truyện: /library/<truyện>/ (hoặc /library/story.html?id=<truyện>). */
(function () {
    'use strict';
    var L = window.Lib, icon = L.icon, esc = L.esc;
    var params = new URLSearchParams(location.search);
    var isTemplate = /\/story\.html$/.test(location.pathname);
    var slug = params.get('id');
    if (!slug && !isTemplate) {
        var parts = location.pathname.split('/').filter(Boolean);
        if (parts.length && /\.html?$/.test(parts[parts.length - 1])) parts.pop();
        slug = parts[parts.length - 1];
    }
    var storyDir = isTemplate ? './' + encodeURIComponent(slug || '') + '/' : './';
    var libDir = isTemplate ? './' : '../';

    document.body.innerHTML =
        '<header class="topbar">'
        + '<a class="icon-btn" href="' + libDir + '" aria-label="Về thư viện">' + icon('back') + '</a>'
        + '<div class="topbar-title"><div class="t1" id="tTitle">Thư viện</div></div>'
        + '</header>'
        + '<main class="wrap" id="main"><div class="loading">Đang tải…</div></main>';
    var main = document.getElementById('main');

    if (!slug) { main.innerHTML = '<div class="error">Không tìm thấy truyện.</div>'; return; }

    L.fetchStory(slug, storyDir, libDir).then(render).catch(function () {
        main.innerHTML = '<div class="error">Không tìm thấy truyện này.<br><br><a class="btn" href="' + libDir + '">Về thư viện</a></div>';
    });

    function render(story) {
        var chapters = story.chapters || [];
        document.title = story.title;
        var order = 'asc';
        main.innerHTML = '<section class="hero">'
            + '<h1>' + esc(story.title) + '</h1>'
            + '<div class="hero-meta"><span>' + L.fmt(chapters.length) + ' chương</span>'
            + (story.date ? '<span>Cập nhật ' + esc(story.date) + '</span>' : '') + '</div>'
            + '<div class="hero-progress" id="progress" hidden></div>'
            + '<div class="hero-actions">'
            + '<a class="btn primary" id="cta">' + icon('play') + '<span id="ctaText"></span></a>'
            + '<button class="btn square" type="button" id="mark"></button>'
            + '</div></section>'
            + '<div class="section-head"><h2>Danh sách chương</h2>'
            + '<button class="icon-btn" type="button" id="order" aria-label="Đảo thứ tự">' + icon('sort') + '</button></div>'
            + '<div class="sticky-tools" id="list"></div>';

        // Tiêu đề hiện trên thanh trên cùng khi đã cuộn qua phần đầu trang.
        var heading = main.querySelector('.hero h1');
        new IntersectionObserver(function (e) {
            document.getElementById('tTitle').textContent = e[0].isIntersecting ? 'Thư viện' : story.title;
        }).observe(heading);

        var view = L.chapterList(document.getElementById('list'), { slug: slug, chapters: chapters, base: storyDir });
        // Ô tìm/nhóm dính ở trên, danh sách cuộn bên dưới.
        var listRoot = document.getElementById('list');
        listRoot.classList.remove('sticky-tools');
        listRoot.querySelector('.chap-tools').classList.add('sticky-tools');

        function drawProgress() {
            var readSet = L.progress.readSet(slug), pointer = L.progress.pointer(slug);
            var done = chapters.filter(function (c) { return L.progress.isRead(readSet, c.id); }).length;
            var idx = pointer ? chapters.findIndex(function (c) { return L.norm(c.id) === L.norm(pointer.chapter); }) : -1;
            var cta = document.getElementById('cta'), text = document.getElementById('ctaText');
            if (!chapters.length) { cta.setAttribute('aria-disabled', 'true'); text.textContent = 'Chưa có chương'; }
            else if (idx >= 0) {
                var chap = chapters[idx];
                var finished = L.progress.isRead(readSet, chap.id) && pointer.para >= (pointer.total || 1) - 2;
                if (finished && idx < chapters.length - 1) chap = chapters[++idx];
                cta.href = storyDir + encodeURIComponent(chap.id) + '/';
                text.textContent = (finished && idx === chapters.length - 1 ? 'Đọc lại: ' : 'Đọc tiếp: ') + (chap.name || 'Chương ' + (idx + 1));
            } else {
                cta.href = storyDir + encodeURIComponent(chapters[0].id) + '/';
                text.textContent = 'Bắt đầu đọc';
            }
            var box = document.getElementById('progress');
            if (done || idx >= 0) {
                var pct = chapters.length ? Math.round(100 * done / chapters.length) : 0;
                box.innerHTML = '<div class="label"><span>Đã đọc ' + L.fmt(done) + '/' + L.fmt(chapters.length) + ' chương</span><span>' + pct + '%</span></div>'
                    + '<div class="bar"><span style="width:' + pct + '%"></span></div>';
                box.hidden = false;
            }
        }
        function drawMark() {
            var on = L.marks.has(slug), b = document.getElementById('mark');
            b.setAttribute('aria-pressed', on);
            b.setAttribute('aria-label', on ? 'Bỏ lưu truyện' : 'Lưu truyện');
            b.title = on ? 'Bỏ lưu truyện' : 'Lưu truyện';
            b.innerHTML = icon('bookmark');
        }
        document.getElementById('mark').onclick = function () { L.marks.toggle(slug); drawMark(); };
        document.getElementById('order').onclick = function () {
            order = order === 'asc' ? 'desc' : 'asc';
            view.setOrder(order);
            this.setAttribute('aria-label', order === 'asc' ? 'Mới nhất lên đầu' : 'Cũ nhất lên đầu');
        };
        drawProgress();
        drawMark();

        // Đang đọc giữa truyện dài: đưa chương đó vào tầm mắt.
        var focus = view.focusEl();
        if (focus && chapters.length > 8) {
            requestAnimationFrame(function () {
                var y = focus.getBoundingClientRect().top + window.scrollY - window.innerHeight / 2;
                if (y > window.innerHeight / 2) window.scrollTo(0, y);
            });
        }
        // Quay lại bằng nút Back: trình duyệt giữ trang cũ, cập nhật lại tiến độ.
        window.addEventListener('pageshow', function (e) { if (e.persisted) { drawProgress(); view.refresh(); } });
    }
})();
