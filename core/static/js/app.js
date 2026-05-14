/**
 * Сайт кафедры СИИ • ИКИТ • СФУ
 */
(function () {
    'use strict';

    // ── Sidebar (для авторизованных) ──────────────────────
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebarOverlay = document.getElementById('sidebar-overlay');

    function closeSidebar() {
        if (!sidebar) return;
        sidebar.classList.remove('is-open');
        if (sidebarOverlay) sidebarOverlay.classList.remove('is-active');
    }

    if (sidebar && sidebarToggle) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('is-open');
            if (sidebarOverlay) {
                sidebarOverlay.classList.toggle('is-active');
            }
        });

        if (sidebarOverlay) {
            sidebarOverlay.addEventListener('click', closeSidebar);
        }

        // Закрываем сайдбар при клике на любую ссылку (на мобильных)
        sidebar.querySelectorAll('.sidebar__link').forEach((link) => {
            link.addEventListener('click', () => {
                if (window.innerWidth <= 1024) closeSidebar();
            });
        });

        // Закрываем по Esc
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeSidebar();
        });
    }

    // ── Бургер-меню для публичной шапки (для гостей) ──────
    const burger = document.querySelector('[data-burger]');
    const nav = document.querySelector('.site-nav');

    if (burger && nav) {
        burger.addEventListener('click', () => {
            nav.classList.toggle('site-nav--open');
            const isOpen = nav.classList.contains('site-nav--open');
            burger.setAttribute('aria-expanded', String(isOpen));
        });

        nav.querySelectorAll('.site-nav__link').forEach((link) => {
            link.addEventListener('click', () => {
                nav.classList.remove('site-nav--open');
            });
        });
    }
})();
