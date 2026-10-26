/* 文章页：目录高亮 / 移动端目录 / Giscus / 图片预览 */
(() => {
    const $ = s => document.querySelector(s);
    const article = $('#markdown-content');
    if (!article) return;

    const MOBILE_BP = 1100;
    const sidebar = $('#sidebar');
    const tocBtn = $('#mobile-toc-toggle');

    // 任务列表允许点击
    article.querySelectorAll('input[type="checkbox"]').forEach(c => c.removeAttribute('disabled'));

    // ===== 目录（HTML 由 build.py 生成，这里只管交互） =====
    const headings = Array.from(article.querySelectorAll('h1,h2,h3,h4,h5,h6')).filter(h => h.id);
    const tocLinks = Array.from(document.querySelectorAll('#toc a'));

    const collapseToc = () => {
        sidebar.classList.add('collapsed');
        tocBtn.classList.add('collapsed');
        tocBtn.setAttribute('aria-expanded', 'false');
    };

    $('#toc').addEventListener('click', e => {
        const link = e.target.closest('a[href^="#"]');
        if (!link) return;
        e.preventDefault();
        const id = link.getAttribute('href').slice(1);
        const target = document.getElementById(id);
        if (!target) return;
        window.scrollTo({ top: target.getBoundingClientRect().top + window.scrollY - 80, behavior: 'smooth' });
        history.replaceState(null, '', '#' + id);          // 地址栏带锚点，可分享
        if (window.innerWidth <= MOBILE_BP) collapseToc();
    });

    tocBtn.addEventListener('click', () => {
        const collapsed = sidebar.classList.toggle('collapsed');
        tocBtn.classList.toggle('collapsed');
        tocBtn.setAttribute('aria-expanded', String(!collapsed));
    });

    // ===== 滚动监听（只用一个 scroll 监听） =====
    let ticking = false;
    function onScroll() {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(() => {
            ticking = false;
            const atBottom = document.documentElement.scrollHeight - window.scrollY - window.innerHeight < 50;
            let id = '';
            if (atBottom) {
                id = headings.length ? headings[headings.length - 1].id : '';
            } else {
                for (let i = headings.length - 1; i >= 0; i--) {
                    if (headings[i].getBoundingClientRect().top <= 130) { id = headings[i].id; break; }
                }
            }
            tocLinks.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + id));
            if (window.scrollY > 20 && !sidebar.classList.contains('collapsed')) collapseToc();
        });
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    // ===== Giscus（未配置时不加载） =====
    const giscus = $('.giscus');
    const giscusTheme = () => document.documentElement.dataset.theme === 'dark' ? 'dark_dimmed' : 'light';
    if (giscus && giscus.dataset.repo) {
        const s = document.createElement('script');
        s.src = 'https://giscus.app/client.js';
        const attrs = {
            'data-repo': giscus.dataset.repo, 'data-repo-id': giscus.dataset.repoId,
            'data-category': giscus.dataset.category, 'data-category-id': giscus.dataset.categoryId,
            'data-mapping': 'pathname', 'data-strict': '0', 'data-reactions-enabled': '1',
            'data-emit-metadata': '0', 'data-input-position': 'bottom',
            'data-theme': giscusTheme(), 'data-lang': 'zh-CN', 'crossorigin': 'anonymous',
        };
        Object.entries(attrs).forEach(([k, v]) => s.setAttribute(k, v));
        s.async = true;
        giscus.appendChild(s);
    }
    document.addEventListener('themechange', () => {
        const frame = $('iframe.giscus-frame');
        if (frame) frame.contentWindow.postMessage({ giscus: { setConfig: { theme: giscusTheme() } } }, 'https://giscus.app');
    });

    // ===== 图片预览：滚轮/双指缩放、拖动平移、左右滑动切换、键盘操作 =====
    const lb = $('#lightbox'), stage = $('#lb-stage'), lbImg = $('#lb-img');
    const prevBtn = $('#lb-prev'), nextBtn = $('#lb-next'), closeBtn = $('#lb-close');
    const imgs = Array.from(article.querySelectorAll('img')).filter(i => !i.closest('.giscus-container'));
    let idx = 0, scale = 1, x = 0, y = 0, opener = null;
    const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

    const apply = () => {
        lbImg.style.transform = `translate(${x}px,${y}px) scale(${scale})`;
        stage.classList.toggle('zoomed', scale > 1);
    };
    const resetZoom = () => { scale = 1; x = y = 0; apply(); };

    function show(i) {
        idx = i;
        lbImg.src = imgs[i].currentSrc || imgs[i].src;
        lbImg.alt = imgs[i].alt || '';
        resetZoom();
        prevBtn.hidden = i === 0;
        nextBtn.hidden = i === imgs.length - 1;
    }
    function openLb(i, from) {
        opener = from;
        lb.hidden = false;
        document.body.style.overflow = 'hidden';
        show(i);
        closeBtn.focus();
    }
    function closeLb() {
        lb.hidden = true;
        document.body.style.overflow = '';
        lbImg.removeAttribute('src');
        if (opener) opener.focus({ preventScroll: true });
    }
    const step = d => { const n = idx + d; if (n >= 0 && n < imgs.length) show(n); };

    imgs.forEach((im, i) => {
        im.tabIndex = 0;
        im.setAttribute('role', 'button');
        im.addEventListener('click', e => { e.stopPropagation(); openLb(i, im); });
        im.addEventListener('keydown', e => { if (e.key === 'Enter') openLb(i, im); });
    });
    prevBtn.addEventListener('click', () => step(-1));
    nextBtn.addEventListener('click', () => step(1));
    closeBtn.addEventListener('click', closeLb);

    // Pointer Events：鼠标 / 触摸统一处理
    const pts = new Map();
    let startDist = 0, startScale = 1, drag = null, moved = false;
    const dist = () => { const [a, b] = [...pts.values()]; return Math.hypot(a.x - b.x, a.y - b.y); };

    stage.addEventListener('pointerdown', e => {
        stage.setPointerCapture(e.pointerId);
        pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
        lbImg.classList.add('no-anim');
        moved = false;
        if (pts.size === 2) { startDist = dist(); startScale = scale; drag = null; }
        else drag = { ox: e.clientX - x, oy: e.clientY - y, sx: e.clientX, sy: e.clientY };
    });
    stage.addEventListener('pointermove', e => {
        if (!pts.has(e.pointerId)) return;
        pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (pts.size === 2) {
            scale = clamp(startScale * dist() / startDist, 0.5, 5);
            moved = true;
            apply();
        } else if (drag) {
            if (Math.abs(e.clientX - drag.sx) + Math.abs(e.clientY - drag.sy) > 4) moved = true;
            if (scale > 1) {
                x = e.clientX - drag.ox; y = e.clientY - drag.oy;
                stage.classList.add('panning');
                apply();
            }
        }
    });
    const endPointer = e => {
        if (!pts.has(e.pointerId)) return;
        pts.delete(e.pointerId);
        lbImg.classList.remove('no-anim');
        stage.classList.remove('panning');
        if (pts.size === 0 && drag) {
            const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
            if (scale === 1 && Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) step(dx < 0 ? 1 : -1);   // 滑动切图
            else if (!moved && scale === 1 && e.target === stage) closeLb();                              // 点击背景关闭
            drag = null;
        } else if (pts.size === 1) {
            const p = [...pts.values()][0];
            drag = { ox: p.x - x, oy: p.y - y, sx: p.x, sy: p.y };
        }
    };
    stage.addEventListener('pointerup', endPointer);
    stage.addEventListener('pointercancel', endPointer);
    stage.addEventListener('wheel', e => {
        e.preventDefault();
        scale = clamp(scale + (e.deltaY > 0 ? -0.2 : 0.2), 0.5, 5);
        apply();
    }, { passive: false });

    document.addEventListener('keydown', e => {
        if (lb.hidden) return;
        if (e.key === 'Escape') closeLb();
        else if (e.key === 'ArrowLeft') step(-1);
        else if (e.key === 'ArrowRight') step(1);
        else if (e.key === 'Tab') {                      // 焦点限制在预览层内
            const f = [closeBtn, prevBtn, nextBtn].filter(b => !b.hidden);
            const i = f.indexOf(document.activeElement);
            e.preventDefault();
            f[(i + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
        }
    });
})();