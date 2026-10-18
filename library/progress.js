/*
 * Tiến độ đọc: nhớ chương + đoạn đang đọc của từng truyện và các chương đã đọc.
 * Dữ liệu chỉ nằm trong trình duyệt này (localStorage), không gửi đi đâu.
 * Dùng chung cho trang đọc chương (tự chạy) và trang truyện (window.ReadingProgress).
 */
(function () {
    'use strict';
    var KEY_POS = 'reading_progress_v1';
    var KEY_READ = 'read_chapters_v1';
    var KEY_CHAPTERS = 'chapter_positions_v1';   // vị trí riêng của từng chương
    var MAX_CHAPTER_POSITIONS = 200;              // mỗi truyện giữ N chương đọc gần nhất

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
        // { idChương: [đoạn, tổngĐoạn, thờiĐiểm] } của một truyện.
        chapterPositions: function (story) { return load(KEY_CHAPTERS)[story] || {}; },
        chapterPos: function (story, id) {
            var pos = (load(KEY_CHAPTERS)[story] || {})[norm(id)];
            return pos ? { para: pos[0], total: pos[1], at: pos[2] } : null;
        },
        setChapterPos: function (story, id, para, total) {
            var all = load(KEY_CHAPTERS), map = all[story] || (all[story] = {});
            map[norm(id)] = [para, total, Date.now()];
            var keys = Object.keys(map);
            if (keys.length > MAX_CHAPTER_POSITIONS) {
                keys.sort(function (a, b) { return map[a][2] - map[b][2]; });
                keys.slice(0, keys.length - MAX_CHAPTER_POSITIONS).forEach(function (k) { delete map[k]; });
            }
            save(KEY_CHAPTERS, all);
        },
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
        var mine = RP.chapterPos(ids.story, ids.chapter);
        if (para > 0 || mine) RP.setChapterPos(ids.story, ids.chapter, para, blocks.length);
        // Chỉ mở chương ra xem (chưa cuộn) thì không cướp chỗ "Đọc tiếp" của chương đang đọc dở.
        var pointer = RP.get(ids.story);
        if (para > 0 || atEnd() || !pointer || pointer.chapter === ids.chapter) {
            RP.set(ids.story, {
                chapter: ids.chapter, para: para, total: blocks.length,
                chapterName: text('chapterTitle'), storyTitle: text('title'), at: Date.now(),
            });
        }
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
        applyDisplay();   // nội dung đã có: biết chương có bản gốc tiếng Trung hay không
        var own = RP.chapterPos(ids.story, ids.chapter);
        var saved = RP.get(ids.story);
        var from = own || (saved && saved.chapter === ids.chapter ? saved : null);   // dữ liệu cũ chỉ có vị trí của truyện
        var resume = from && from.para > 0 && !location.hash ? from.para : 0;
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

    // ───────── tuỳ chỉnh hiển thị (cỡ chữ, nền, phông, Việt/Trung) ─────────
    var applyDisplay = function () {};
    function setupDisplaySettings() {
        var KEY = 'reader_settings_v1';
        var DEFAULTS = { size: 18, line: 1.7, width: 'md', theme: 'dark', font: 'sans', mode: 'vi' };
        var WIDTHS = { sm: '34rem', md: '42rem', lg: '56rem', full: 'none' };
        var FONTS = {
            sans: 'system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif',
            // Georgia thiếu chữ Việt có dấu chồng (ấ, ầ…) nên không dùng.
            serif: '"Noto Serif", "Times New Roman", Times, serif',
        };
        var THEMES = {
            sepia: { bg: '#f4ecd8', text: '#3b2f24', dim: '#8a7560', bar: 'rgba(244,236,216,.94)', line: '#ddcfae', btn: '#ebe0c8', btnText: '#4a3b2c', accent: '#9a3412' },
            light: { bg: '#fafafa', text: '#1f2937', dim: '#6b7280', bar: 'rgba(250,250,250,.94)', line: '#e4e4e7', btn: '#f1f1f4', btnText: '#27272a', accent: '#1d4ed8' },
        };
        var settings = Object.assign({}, DEFAULTS, load(KEY));
        var style = document.createElement('style');
        document.head.appendChild(style);

        function hasCn() {
            var cn = content.querySelectorAll('.cn-text');
            for (var i = 0; i < cn.length; i++) if (cn[i].textContent.trim()) return true;
            return false;
        }

        applyDisplay = function () {
            var s = settings, t = THEMES[s.theme];
            var css = '.vi-text{font-size:' + s.size + 'px!important;line-height:' + s.line + '!important;font-family:' + FONTS[s.font] + '!important}'
                + '.cn-text{font-size:' + Math.round(s.size * 0.85) + 'px!important;line-height:' + s.line + '!important}'
                + '.cn-text:empty{display:none!important}'
                + '.max-w-2xl{max-width:' + WIDTHS[s.width] + '!important}';
            if (t) {
                css += 'html,body{background:' + t.bg + '!important}body{color:' + t.text + '!important}'
                    + '.vi-text,#title,.text-zinc-200{color:' + t.text + '!important}'
                    + '.cn-text,.text-zinc-500{color:' + t.dim + '!important}'
                    + '#chapterTitle{color:' + t.accent + '!important}'
                    + '.sticky{background:' + t.bar + '!important}'
                    + '.border-zinc-800,.sticky{border-color:' + t.line + '!important}'
                    + '.bg-zinc-900{background:' + t.btn + '!important;color:' + t.btnText + '!important;border-color:' + t.line + '!important}';
            }
            style.textContent = css;
            // Chương không có bản gốc tiếng Trung thì luôn hiện tiếng Việt (không đổi lựa chọn đã lưu).
            var mode = s.mode !== 'vi' && blocks.length && !hasCn() ? 'vi' : s.mode;
            document.body.classList.remove('mode-vi', 'mode-cn');
            if (mode !== 'both') document.body.classList.add('mode-' + mode);
        };

        function change(key, value) {
            var keep = blocks.length ? currentPara() : -1;   // giữ đúng đoạn đang đọc khi chữ to/nhỏ đi
            settings[key] = value;
            save(KEY, settings);
            applyDisplay();
            if (keep > 0) scrollToPara(keep);
            render();
        }

        // Nút "Aa" trên thanh tiêu đề; trang cũ không có thanh thì nổi ở góc phải.
        var button = document.createElement('button');
        button.type = 'button';
        button.textContent = 'Aa';
        button.title = 'Tuỳ chỉnh hiển thị';
        button.setAttribute('aria-label', 'Tuỳ chỉnh hiển thị');
        button.className = 'bg-zinc-900';
        button.style.cssText = 'flex:none;border:1px solid #3f3f46;border-radius:8px;padding:3px 10px;margin-left:10px;'
            + 'font:600 13px/1.4 system-ui,sans-serif;cursor:pointer;color:#d4d4d8;';
        var row = document.querySelector('.sticky .flex.items-center.justify-between');
        if (row && row.children.length >= 2) row.insertBefore(button, row.children[1]);
        else {
            button.style.cssText += 'position:fixed;right:16px;bottom:20px;z-index:60;padding:10px 14px;';
            document.body.appendChild(button);
        }

        var panel = document.createElement('div');
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-label', 'Tuỳ chỉnh hiển thị');
        panel.hidden = true;
        panel.style.cssText = 'position:fixed;right:12px;z-index:70;width:min(320px,calc(100vw - 24px));background:#18181b;color:#e4e4e7;'
            + 'border:1px solid #3f3f46;border-radius:12px;padding:12px 14px;box-shadow:0 12px 32px #000a;font:14px/1.4 system-ui,sans-serif;';
        document.body.appendChild(panel);

        var BTN = 'flex:1;background:#27272a;color:#e4e4e7;border:1px solid #3f3f46;border-radius:8px;padding:7px 4px;font:inherit;cursor:pointer;';
        var ON = 'background:#2563eb;border-color:#2563eb;color:#fff;';
        function rowEl(label) {
            var wrap = document.createElement('div');
            wrap.style.cssText = 'margin:8px 0;';
            var title = document.createElement('div');
            title.textContent = label;
            title.style.cssText = 'color:#a1a1aa;font-size:12px;margin-bottom:5px;';
            var line = document.createElement('div');
            line.style.cssText = 'display:flex;gap:6px;align-items:center;';
            wrap.appendChild(title); wrap.appendChild(line); panel.appendChild(wrap);
            return line;
        }
        function btn(parent, text, onClick, active, disabled) {
            var b = document.createElement('button');
            b.type = 'button';
            b.textContent = text;
            b.style.cssText = BTN + (active ? ON : '') + (disabled ? 'opacity:.4;cursor:default;' : '');
            b.disabled = !!disabled;
            b.onclick = onClick;
            parent.appendChild(b);
            return b;
        }
        function stepper(label, value, onMinus, onPlus) {
            var line = rowEl(label);
            btn(line, '−', onMinus);
            var v = document.createElement('span');
            v.textContent = value;
            v.style.cssText = 'flex:1.2;text-align:center;font-variant-numeric:tabular-nums;';
            line.appendChild(v);
            btn(line, '+', onPlus);
        }
        function choice(label, key, options, disabledKeys) {
            var line = rowEl(label);
            options.forEach(function (o) {
                btn(line, o[1], function () { change(key, o[0]); }, settings[key] === o[0], disabledKeys && disabledKeys.indexOf(o[0]) >= 0);
            });
        }
        function render() {
            if (panel.hidden) return;
            panel.textContent = '';
            stepper('Cỡ chữ', settings.size + 'px',
                function () { change('size', Math.max(13, settings.size - 1)); },
                function () { change('size', Math.min(30, settings.size + 1)); });
            stepper('Giãn dòng', settings.line.toFixed(1),
                function () { change('line', Math.max(1.3, Math.round((settings.line - 0.1) * 10) / 10)); },
                function () { change('line', Math.min(2.4, Math.round((settings.line + 0.1) * 10) / 10)); });
            choice('Độ rộng', 'width', [['sm', 'Hẹp'], ['md', 'Vừa'], ['lg', 'Rộng'], ['full', 'Hết']]);
            choice('Nền', 'theme', [['dark', 'Tối'], ['sepia', 'Sepia'], ['light', 'Sáng']]);
            choice('Phông chữ', 'font', [['sans', 'Không chân'], ['serif', 'Có chân']]);
            var noCn = blocks.length && !hasCn();
            choice(noCn ? 'Hiển thị · chương này không có bản gốc' : 'Hiển thị', 'mode',
                [['vi', 'Việt'], ['both', 'Song ngữ'], ['cn', 'Trung']], noCn ? ['both', 'cn'] : null);
            var foot = document.createElement('div');
            foot.style.cssText = 'display:flex;justify-content:space-between;align-items:center;margin-top:10px;';
            var hint = document.createElement('span');
            hint.textContent = 'Lưu cho mọi truyện trên máy này';
            hint.style.cssText = 'color:#71717a;font-size:12px;';
            var reset = document.createElement('button');
            reset.type = 'button';
            reset.textContent = 'Mặc định';
            reset.style.cssText = 'background:none;border:0;color:#93c5fd;font:inherit;cursor:pointer;padding:4px;';
            reset.onclick = function () {
                var keep = blocks.length ? currentPara() : -1;
                settings = Object.assign({}, DEFAULTS);
                save(KEY, settings); applyDisplay();
                if (keep > 0) scrollToPara(keep);
                render();
            };
            foot.appendChild(hint); foot.appendChild(reset); panel.appendChild(foot);
        }
        function open() {
            panel.style.top = (Math.max(headerHeight(), 0) + 8) + 'px';
            panel.hidden = false;
            render();
        }
        function close() { panel.hidden = true; }
        button.addEventListener('click', function (e) { e.stopPropagation(); panel.hidden ? open() : close(); });
        // Bấm trong bảng (kể cả nút vừa bị vẽ lại) không tính là bấm ra ngoài.
        panel.addEventListener('click', function (e) { e.stopPropagation(); });
        document.addEventListener('click', function () { if (!panel.hidden) close(); });
        document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });

        applyDisplay();
    }

    setupDisplaySettings();
    if (!start()) {
        var observer = new MutationObserver(function () { if (start()) observer.disconnect(); });
        observer.observe(content, { childList: true });
    }
})();
