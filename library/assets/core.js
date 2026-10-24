/*
 * Lõi dùng chung của Thư viện: cài đặt hiển thị, tiến độ đọc, bookmark,
 * danh sách chương và vài tiện ích. Nạp đồng bộ trong <head> để áp màu nền
 * trước khi trang được vẽ (không nháy trắng/đen khi mở trang).
 * Mọi dữ liệu chỉ nằm trong trình duyệt này (localStorage).
 */
(function () {
    'use strict';
    var KEYS = {
        settings: 'reader_settings_v1',
        pointer: 'reading_progress_v1',      // { truyện: chương đang đọc }
        read: 'read_chapters_v1',            // { truyện: "1-120,125" }
        positions: 'chapter_positions_v1',   // { truyện: { chương: [đoạn, tổng, lúc] } }
        marks: 'bookmarked_stories',
    };
    var MAX_POSITIONS = 200;

    function load(key, fallback) {
        try { var v = JSON.parse(localStorage.getItem(key)); return v == null ? fallback : v; } catch (e) { return fallback; }
    }
    function save(key, value) {
        try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* đầy bộ nhớ / bị chặn */ }
    }
    function norm(id) { return /^\d+$/.test(id) ? String(parseInt(id, 10)) : String(id); }
    function esc(text) {
        return String(text).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }
    var COMBINING = new RegExp('[̀-ͯ]', 'g');
    function fold(text) { return String(text).normalize('NFD').replace(COMBINING, '').replace(/[đĐ]/g, 'd').toLowerCase(); }
    function fmt(n) { return Number(n).toLocaleString('vi-VN'); }

    // ───────── cài đặt hiển thị ─────────
    var DEFAULTS = { size: 19, line: 1.75, width: 'md', theme: 'warm', font: 'sans', align: 'left', spacing: 'md', wake: false };
    var WIDTHS = { sm: '32em', md: '38em', lg: '46em' };
    var SPACING = { sm: '0.6em', md: '1em', lg: '1.5em' };
    var FONTS = {
        sans: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        serif: '"Noto Serif", "Times New Roman", Times, serif',   // Georgia thiếu chữ Việt dấu chồng
        literata: 'Literata, "Noto Serif", "Times New Roman", serif',
    };
    var THEME_COLORS = { warm: '#15130f', black: '#000000', sepia: '#f2e8d5', light: '#fbfaf7' };

    function getSettings() {
        var s = Object.assign({}, DEFAULTS, load(KEYS.settings, {}));
        if (s.theme === 'dark') s.theme = 'warm';            // tên cũ
        if (!THEME_COLORS[s.theme]) s.theme = DEFAULTS.theme;
        if (!FONTS[s.font]) s.font = DEFAULTS.font;
        if (!WIDTHS[s.width]) s.width = DEFAULTS.width;
        return s;
    }
    function applySettings(s) {
        var root = document.documentElement;
        root.setAttribute('data-theme', s.theme);
        root.style.setProperty('--read-size', s.size + 'px');
        root.style.setProperty('--read-line', String(s.line));
        root.style.setProperty('--read-width', WIDTHS[s.width]);
        root.style.setProperty('--read-font', FONTS[s.font]);
        root.style.setProperty('--read-align', s.align === 'justify' ? 'justify' : 'left');
        root.style.setProperty('--para-gap', SPACING[s.spacing] || SPACING.md);
        var meta = document.querySelector('meta[name="theme-color"]');
        if (!meta) { meta = document.createElement('meta'); meta.name = 'theme-color'; document.head.appendChild(meta); }
        meta.content = THEME_COLORS[s.theme];
        if (s.font === 'literata' && !document.getElementById('font-literata')) {
            var link = document.createElement('link');
            link.id = 'font-literata';
            link.rel = 'stylesheet';
            link.href = 'https://fonts.googleapis.com/css2?family=Literata:opsz,wght@7..72,400;7..72,600&display=swap';
            document.head.appendChild(link);
        }
    }
    var settings = getSettings();
    applySettings(settings);

    // ───────── tiến độ đọc ─────────
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
        set.forEach(function (id) { if (/^\d+$/.test(id)) nums.push(+id); else other.push(id); });
        nums.sort(function (a, b) { return a - b; });
        var out = [];
        for (var i = 0; i < nums.length; i++) {
            var start = nums[i];
            while (i + 1 < nums.length && nums[i + 1] === nums[i] + 1) i++;
            out.push(start === nums[i] ? String(start) : start + '-' + nums[i]);
        }
        return out.concat(other).join(',');
    }
    var progress = {
        pointer: function (story) { return load(KEYS.pointer, {})[story] || null; },
        allPointers: function () { return load(KEYS.pointer, {}); },
        setPointer: function (story, data) { var all = load(KEYS.pointer, {}); all[story] = data; save(KEYS.pointer, all); },
        readSet: function (story) { return decodeRead(load(KEYS.read, {})[story]); },
        isRead: function (set, id) { return set.has(norm(id)); },
        markRead: function (story, id) {
            var all = load(KEYS.read, {}), set = decodeRead(all[story]);
            if (set.has(norm(id))) return;
            set.add(norm(id)); all[story] = encodeRead(set); save(KEYS.read, all);
        },
        positions: function (story) { return load(KEYS.positions, {})[story] || {}; },
        position: function (story, id) {
            var p = (load(KEYS.positions, {})[story] || {})[norm(id)];
            return p ? { para: p[0], total: p[1], at: p[2] } : null;
        },
        setPosition: function (story, id, para, total) {
            var all = load(KEYS.positions, {}), map = all[story] || (all[story] = {});
            map[norm(id)] = [para, total, Date.now()];
            var keys = Object.keys(map);
            if (keys.length > MAX_POSITIONS) {
                keys.sort(function (a, b) { return map[a][2] - map[b][2]; });
                keys.slice(0, keys.length - MAX_POSITIONS).forEach(function (k) { delete map[k]; });
            }
            save(KEYS.positions, all);
        },
    };

    // ───────── bookmark ─────────
    var marks = {
        list: function () {
            var list = load(KEYS.marks, []);
            if (!Array.isArray(list)) return [];
            // ID truyện cũ 4 chữ số (0216) → 6 chữ số (000216)
            var fixed = list.map(function (s) { return /^\d{4}$/.test(s) ? ('00' + s) : s; });
            fixed = fixed.filter(function (s, i) { return fixed.indexOf(s) === i; });
            if (fixed.join() !== list.join()) save(KEYS.marks, fixed);
            return fixed;
        },
        has: function (slug) { return marks.list().indexOf(slug) >= 0; },
        toggle: function (slug) {
            var list = marks.list(), i = list.indexOf(slug);
            if (i >= 0) list.splice(i, 1); else list.push(slug);
            save(KEYS.marks, list);
            return i < 0;
        },
    };

    // ───────── dữ liệu ─────────
    function fetchJSON(url) {
        return fetch(url).then(function (res) {
            if (!res.ok) throw new Error(res.status + ' ' + url);
            return res.json();
        });
    }
    // Danh sách chương của một truyện: chapters.json (nhẹ), thiếu thì lấy từ list.json.
    function fetchStory(slug, storyDir, libraryDir) {
        return fetchJSON(storyDir + 'chapters.json').catch(function () {
            return fetchJSON(libraryDir + 'list.json').then(function (list) {
                var s = list.find(function (x) { return x.slug === slug; });
                if (!s) throw new Error('Không có truyện ' + slug);
                return s;
            });
        });
    }
    // Danh sách truyện: stories.json (nhẹ), thiếu thì list.json.
    function fetchStories(libraryDir) {
        return fetchJSON(libraryDir + 'stories.json').catch(function () {
            return fetchJSON(libraryDir + 'list.json').then(function (list) {
                return list.map(function (s) {
                    return { slug: s.slug, title: s.title, date: s.date, timestamp: s.timestamp,
                        count: (s.chapters || []).length, first: s.chapters && s.chapters[0] ? s.chapters[0].id : '' };
                });
            });
        });
    }

    // ───────── biểu tượng (nét, 24×24) ─────────
    var PATHS = {
        back: '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
        list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
        prev: '<path d="m15 18-6-6 6-6"/>',
        next: '<path d="m9 18 6-6-6-6"/>',
        bookmark: '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>',
        search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
        close: '<path d="M18 6 6 18M6 6l12 12"/>',
        play: '<path d="M7 4v16l13-8z"/>',
        up: '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
        edit: '<path d="M17 3a2.85 2.85 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/>',
        check: '<path d="M20 6 9 17l-5-5"/>',
        sort: '<path d="m3 16 4 4 4-4"/><path d="M7 20V4"/><path d="m21 8-4-4-4 4"/><path d="M17 4v16"/>',
        book: '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>',
    };
    function icon(name, extra) {
        return '<svg class="ico' + (extra ? ' ' + extra : '') + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + PATHS[name] + '</svg>';
    }

    // ───────── bảng trượt từ dưới lên (cài đặt, danh sách chương) ─────────
    function sheet(title) {
        var backdrop = document.createElement('div');
        backdrop.className = 'sheet-backdrop';
        backdrop.hidden = true;
        var panel = document.createElement('section');
        panel.className = 'sheet';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-modal', 'true');
        panel.setAttribute('aria-label', title);
        panel.hidden = true;
        panel.innerHTML = '<div class="sheet-head"><h2>' + esc(title) + '</h2>'
            + '<button class="icon-btn" type="button" data-close aria-label="Đóng">' + icon('close') + '</button></div>'
            + '<div class="sheet-body"></div>';
        document.body.appendChild(backdrop);
        document.body.appendChild(panel);
        var lastFocus = null, onOpen = null;
        function open() {
            lastFocus = document.activeElement;
            backdrop.hidden = panel.hidden = false;
            document.documentElement.classList.add('sheet-open');
            requestAnimationFrame(function () { panel.classList.add('in'); backdrop.classList.add('in'); });
            if (onOpen) onOpen();
            panel.querySelector('[data-close]').focus({ preventScroll: true });
        }
        function close() {
            panel.classList.remove('in'); backdrop.classList.remove('in');
            document.documentElement.classList.remove('sheet-open');
            setTimeout(function () { backdrop.hidden = panel.hidden = true; }, 200);
            if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true });
        }
        backdrop.addEventListener('click', close);
        panel.querySelector('[data-close]').addEventListener('click', close);
        document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) close(); });
        return {
            body: panel.querySelector('.sheet-body'), panel: panel,
            open: open, close: close, isOpen: function () { return !panel.hidden; },
            onOpen: function (fn) { onOpen = fn; },
        };
    }

    // ───────── danh sách chương (trang truyện + trang đọc) ─────────
    var GROUP = 100, SEARCH_LIMIT = 200;
    function chapterList(root, opts) {
        // opts: { slug, chapters, base, currentId (chương đang mở), order: 'asc'|'desc' }
        var chapters = opts.chapters, order = opts.order || 'asc';
        var readSet = progress.readSet(opts.slug), positions = progress.positions(opts.slug);
        var pointer = progress.pointer(opts.slug);
        var pointerIdx = pointer ? chapters.findIndex(function (c) { return norm(c.id) === norm(pointer.chapter); }) : -1;
        var focusIdx = opts.currentId ? chapters.findIndex(function (c) { return norm(c.id) === norm(opts.currentId); }) : pointerIdx;

        root.innerHTML = '<div class="chap-tools">'
            + '<label class="search">' + icon('search') + '<input type="search" placeholder="Số chương hoặc tên…" enterkeyhint="go" aria-label="Tìm chương"></label>'
            + '<select aria-label="Nhóm chương"></select></div>'
            + '<p class="chap-note" hidden></p><ol class="chap-list"></ol>';
        var input = root.querySelector('input'), select = root.querySelector('select');
        var note = root.querySelector('.chap-note'), list = root.querySelector('.chap-list');

        function groups() {
            var out = [];
            for (var g = 0; g * GROUP < chapters.length; g++) out.push(g);
            return order === 'desc' ? out.reverse() : out;
        }
        function fillGroups() {
            select.innerHTML = '';
            if (chapters.length <= GROUP) { select.hidden = true; return; }
            select.hidden = false;
            var hot = focusIdx >= 0 ? Math.floor(focusIdx / GROUP) : -1;
            groups().forEach(function (g) {
                var a = g * GROUP + 1, b = Math.min((g + 1) * GROUP, chapters.length);
                var opt = document.createElement('option');
                opt.value = g;
                opt.textContent = (order === 'desc' ? b + '–' + a : a + '–' + b) + (g === hot ? ' • đang đọc' : '');
                select.appendChild(opt);
            });
            select.value = hot >= 0 ? hot : groups()[0];
        }
        function state(i) {
            var c = chapters[i], read = progress.isRead(readSet, c.id), pos = positions[norm(c.id)];
            if (opts.currentId && i === focusIdx) return ['here', 'Đang mở'];
            if (i === pointerIdx && pointer) {
                if (read && pointer.para >= (pointer.total || 1) - 2) return ['read', 'Vừa đọc xong'];
                return ['current', pointer.para > 0 ? 'Đang đọc · đoạn ' + (pointer.para + 1) : 'Đang đọc'];
            }
            if (read) return ['read', 'Đã đọc'];
            if (pos && pos[0] > 0) return ['partial', 'Đọc dở · đoạn ' + (pos[0] + 1)];
            return ['', ''];
        }
        function row(i) {
            var c = chapters[i], st = state(i);
            return '<li><a class="chap' + (st[0] ? ' is-' + st[0] : '') + '" href="' + opts.base + encodeURIComponent(c.id) + '/">'
                + '<span class="chap-no">' + (i + 1) + '</span>'
                + '<span class="chap-name">' + esc(c.name || 'Chương ' + (i + 1)) + '</span>'
                + (st[1] ? '<span class="chap-state">' + (st[0] === 'read' ? icon('check') : '') + esc(st[1]) + '</span>' : '')
                + '</a></li>';
        }
        function matches(q) {
            q = q.trim();
            var out = [];
            if (/^\d+$/.test(q)) {
                var n = parseInt(q, 10);
                if (chapters[n - 1]) out.push(n - 1);
                var byId = chapters.findIndex(function (c) { return norm(c.id) === String(n); });
                if (byId >= 0 && out.indexOf(byId) < 0) out.push(byId);
                var re = new RegExp('(^|\\D)' + n + '(\\D|$)');
                chapters.forEach(function (c, i) { if (out.indexOf(i) < 0 && re.test(c.name || '')) out.push(i); });
                return out;
            }
            var words = fold(q).split(/\s+/).filter(Boolean);
            chapters.forEach(function (c, i) {
                var name = fold(c.name || '');
                if (words.every(function (w) { return name.indexOf(w) >= 0; })) out.push(i);
            });
            return out;
        }
        function render() {
            var idx = [], q = input.value;
            if (q.trim()) {
                var found = matches(q);
                idx = found.slice(0, SEARCH_LIMIT);
                note.textContent = found.length
                    ? fmt(found.length) + ' chương khớp' + (found.length > SEARCH_LIMIT ? ' · hiện ' + SEARCH_LIMIT + ' đầu tiên' : '') + ' · Enter để mở chương đầu'
                    : 'Không có chương nào khớp.';
                note.hidden = false;
            } else {
                note.hidden = true;
                var g = select.hidden ? 0 : +select.value;
                var start = select.hidden ? 0 : g * GROUP, end = select.hidden ? chapters.length : Math.min(start + GROUP, chapters.length);
                for (var i = start; i < end; i++) idx.push(i);
                if (order === 'desc') idx.reverse();
            }
            list.innerHTML = idx.map(row).join('');
        }
        var timer = null;
        input.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(render, 120); });
        input.addEventListener('keydown', function (e) {
            if (e.key !== 'Enter') return;
            var first = list.querySelector('a');
            if (first) location.href = first.href;
        });
        select.addEventListener('change', function () { input.value = ''; render(); if (opts.onGroupChange) opts.onGroupChange(); });
        fillGroups();
        render();
        return {
            setOrder: function (o) { order = o; fillGroups(); render(); },
            refresh: function () {
                readSet = progress.readSet(opts.slug); positions = progress.positions(opts.slug); pointer = progress.pointer(opts.slug);
                pointerIdx = pointer ? chapters.findIndex(function (c) { return norm(c.id) === norm(pointer.chapter); }) : -1;
                render();
            },
            focusEl: function () { return list.querySelector('.is-here, .is-current'); },
        };
    }

    window.Lib = {
        settings: {
            get: function () { return Object.assign({}, settings); },
            set: function (patch) { settings = Object.assign(settings, patch); save(KEYS.settings, settings); applySettings(settings); },
            reset: function () { settings = Object.assign({}, DEFAULTS); save(KEYS.settings, settings); applySettings(settings); },
            DEFAULTS: DEFAULTS,
        },
        progress: progress, marks: marks,
        fetchJSON: fetchJSON, fetchStory: fetchStory, fetchStories: fetchStories,
        icon: icon, sheet: sheet, chapterList: chapterList,
        esc: esc, fold: fold, norm: norm, fmt: fmt,
    };
})();
