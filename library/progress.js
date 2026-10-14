/*
 * Tiến độ đọc: nhớ chương + đoạn đang đọc của từng truyện và các chương đã đọc.
 * Dữ liệu chỉ nằm trong trình duyệt này (localStorage), không gửi đi đâu.
 * Dùng chung cho trang đọc chương (tự chạy) và trang truyện (window.ReadingProgress).
 */
(function () {
    'use strict';
    var KEY_POS = 'reading_progress_v1';
    var KEY_READ = 'read_chapters_v1';

    function load(key) {
        try { return JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch (e) { return {}; }
    }
    function save(key, value) {
        try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* đầy bộ nhớ / bị chặn: bỏ qua */ }
    }
    // ID chương dạng số so theo giá trị ("0068" = "68") để đổi độ dài ID không mất dữ liệu.
    function norm(id) { return /^\d+$/.test(id) ? String(parseInt(id, 10)) : String(id); }

    // Chương đã đọc lưu gọn thành các khoảng: "1-120,125,130-131".
    function decodeRead(text) {
        var set = new Set();
        (text || '').split(',').forEach(function (part) {
            var m = /^(\d+)-(\d+)$/.exec(part);
            if (m) { for (var i = +m[1]; i <= +m[2]; i++) set.add(String(i)); }
            else if (part) set.add(part);
        });
        return set;
    }
    function encodeRead(set) {
        var nums = [], other = [];
        set.forEach(function (id) { /^\d+$/.test(id) ? nums.push(+id) : other.push(id); });
        nums.sort(function (a, b) { return a - b; });
        var out = [];
        for (var i = 0; i < nums.length; i++) {
            var start = nums[i];
            while (i + 1 < nums.length && nums[i + 1] === nums[i] + 1) i++;
            out.push(start === nums[i] ? String(start) : start + '-' + nums[i]);
        }
        return out.concat(other).join(',');
    }

    var RP = window.ReadingProgress = {
        get: function (story) { return load(KEY_POS)[story] || null; },
        set: function (story, data) { var all = load(KEY_POS); all[story] = data; save(KEY_POS, all); },
        readSet: function (story) { return decodeRead(load(KEY_READ)[story]); },
        isRead: function (set, id) { return set.has(norm(id)); },
        markRead: function (story, id) {
            var all = load(KEY_READ), set = decodeRead(all[story]);
            if (set.has(norm(id))) return;
            set.add(norm(id)); all[story] = encodeRead(set); save(KEY_READ, all);
        },
        norm: norm,
    };

    // ───────── trang đọc chương ─────────
    function pageIds() {
        var parts = location.pathname.split('/').filter(Boolean);
        if (parts.length && /\.html?$/.test(parts[parts.length - 1])) parts.pop();
        var i = parts.lastIndexOf('library');
        if (i >= 0 && parts.length === i + 3) return { story: parts[i + 1], chapter: parts[i + 2] };
        i = parts.lastIndexOf('stories');
        if (i >= 0 && parts.length === i + 2) return { story: 'stories/' + parts[i + 1], chapter: '' };
        return null;
    }

    var content = document.getElementById('content');
    var ids = pageIds();
    if (!content || !ids) return;

    var blocks = [];
    var restoring = false, userMoved = false, saveTimer = null, toast = null;

    function headerHeight() {
        var bar = document.querySelector('.sticky');
        return bar ? bar.getBoundingClientRect().bottom : 0;
    }
    // Đoạn đầu tiên còn nhìn thấy dưới thanh tiêu đề (tìm nhị phân, chương rất dài vẫn nhanh).
    function currentPara() {
        var top = Math.max(headerHeight(), 0) + 8, lo = 0, hi = blocks.length - 1, ans = blocks.length - 1;
        while (lo <= hi) {
            var mid = (lo + hi) >> 1;
            if (blocks[mid].getBoundingClientRect().bottom > top) { ans = mid; hi = mid - 1; } else lo = mid + 1;
        }
        return ans;
    }
    function atEnd() {
        return window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 300;
    }
    function text(id) { var el = document.getElementById(id); return el ? el.textContent.trim() : ''; }

    function record() {
        if (!blocks.length || restoring) return;
        // Cuối chương thường thấy cùng lúc vài đoạn ngắn: coi như đã tới đoạn cuối.
        var para = atEnd() ? blocks.length - 1 : currentPara();
        RP.set(ids.story, {
            chapter: ids.chapter, para: para, total: blocks.length,
            chapterName: text('chapterTitle'), storyTitle: text('title'), at: Date.now(),
        });
        if (ids.chapter && (para >= blocks.length - 2 || atEnd())) RP.markRead(ids.story, ids.chapter);
    }
    function scheduleRecord() { clearTimeout(saveTimer); saveTimer = setTimeout(record, 400); }

    function scrollToPara(index) {
        var block = blocks[Math.min(index, blocks.length - 1)];
        if (!block) return;
        restoring = true;
        window.scrollTo(0, block.getBoundingClientRect().top + window.scrollY - headerHeight() - 12);
        setTimeout(function () { restoring = false; }, 150);
    }

    function showToast(para, total) {
        toast = document.createElement('div');
        toast.setAttribute('role', 'status');
        toast.style.cssText = 'position:fixed;left:50%;bottom:20px;transform:translateX(-50%);z-index:60;max-width:calc(100% - 32px);'
            + 'background:#18181b;border:1px solid #3f3f46;color:#e4e4e7;border-radius:999px;padding:8px 8px 8px 16px;'
            + 'font:14px/1.3 system-ui,sans-serif;display:flex;gap:10px;align-items:center;box-shadow:0 8px 24px #0008;';
        var label = document.createElement('span');
        label.textContent = '↩ Tiếp tục ở đoạn ' + (para + 1) + '/' + total;
        var top = document.createElement('button');
        top.textContent = 'Về đầu chương';
        top.style.cssText = 'background:#27272a;color:#fff;border:0;border-radius:999px;padding:6px 12px;font:inherit;cursor:pointer;white-space:nowrap;';
        top.onclick = function () { window.scrollTo(0, 0); hideToast(); };
        toast.appendChild(label); toast.appendChild(top);
        document.body.appendChild(toast);
        setTimeout(hideToast, 6000);
    }
    function hideToast() { if (toast) { toast.remove(); toast = null; } }

    function start() {
        blocks = Array.prototype.slice.call(content.querySelectorAll('.story-block'));
        if (!blocks.length) return false;
        var saved = RP.get(ids.story);
        var resume = saved && saved.chapter === ids.chapter && saved.para > 0 && !location.hash ? saved.para : 0;
        if (resume) {
            scrollToPara(resume);
            // Kiểu chữ (Tailwind CDN) có thể nạp sau làm lệch bố cục: căn lại nếu người đọc chưa cuộn.
            window.addEventListener('load', function () { if (!userMoved) scrollToPara(resume); });
            setTimeout(function () { if (!userMoved) scrollToPara(resume); }, 800);
            showToast(resume, blocks.length);
        }
        ['wheel', 'touchstart', 'keydown', 'mousedown'].forEach(function (type) {
            window.addEventListener(type, function () { userMoved = true; }, { passive: true, once: true });
        });
        window.addEventListener('scroll', scheduleRecord, { passive: true });
        window.addEventListener('pagehide', record);
        document.addEventListener('visibilitychange', function () { if (document.hidden) record(); });
        ['nextBtn', 'nextBtnTop'].forEach(function (id) {
            var btn = document.getElementById(id);
            if (btn) btn.addEventListener('click', function () { if (ids.chapter) RP.markRead(ids.story, ids.chapter); });
        });
        // Ghi ngay khi mở chương (kể cả chưa cuộn) để "Đọc tiếp" trỏ đúng chương mới nhất.
        setTimeout(record, resume ? 1000 : 300);
        return true;
    }

    if (!start()) {
        var observer = new MutationObserver(function () { if (start()) observer.disconnect(); });
        observer.observe(content, { childList: true });
    }
})();
