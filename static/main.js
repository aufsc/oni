/* 所有页面共用：主题切换 / 年份 / 移动端菜单 / 分类折叠 */
(() => {
    const root = document.documentElement;

    function toggleTheme() {
        const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
        root.dataset.theme = next;
        try { localStorage.setItem('theme', next); } catch (e) {}
        document.dispatchEvent(new CustomEvent('themechange', { detail: next }));
    }
    document.querySelectorAll('.theme-toggle').forEach(b => b.addEventListener('click', toggleTheme));

    document.querySelectorAll('[data-year]').forEach(el => { el.textContent = new Date().getFullYear(); });

    // 移动端菜单
    const hamburger = document.getElementById('hamburger-btn');
    const menu = document.getElementById('mobile-menu');
    if (hamburger && menu) {
        const setOpen = open => {
            menu.classList.toggle('active', open);
            hamburger.setAttribute('aria-expanded', String(open));
        };
        hamburger.addEventListener('click', () => setOpen(!menu.classList.contains('active')));
        menu.querySelectorAll('a').forEach(a => a.addEventListener('click', () => setOpen(false)));
        document.addEventListener('click', e => {
            if (!hamburger.contains(e.target) && !menu.contains(e.target)) setOpen(false);
        });
        document.addEventListener('keydown', e => { if (e.key === 'Escape') setOpen(false); });
    }

    // 分类折叠
    document.addEventListener('click', e => {
        const head = e.target.closest('.category-header');
        if (!head) return;
        const block = head.parentElement;
        head.setAttribute('aria-expanded', String(block.classList.toggle('collapsed') === false));
    });
})();