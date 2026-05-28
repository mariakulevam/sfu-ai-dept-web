/**
 * Сайт кафедры СИИ • ИКИТ • СФУ
 */
(function () {
    'use strict';

    // ── Переключатель темы (светлая / тёмная) ──────────────
    const THEME_KEY = 'sfu-theme';
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', function () {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            if (isDark) {
                document.documentElement.removeAttribute('data-theme');
                try { localStorage.setItem(THEME_KEY, 'light'); } catch (e) {}
            } else {
                document.documentElement.setAttribute('data-theme', 'dark');
                try { localStorage.setItem(THEME_KEY, 'dark'); } catch (e) {}
            }
        });
    }

    // ── Sidebar collapse (сворачивание) ───────────────────
    const COLLAPSE_KEY = 'sfu_sidebar_collapsed';
    const body = document.body;
    const collapseBtn = document.getElementById('sidebar-collapse');

    // Восстанавливаем состояние при загрузке
    if (localStorage.getItem(COLLAPSE_KEY) === '1') {
        body.classList.add('sidebar-collapsed');
    }

    if (collapseBtn) {
        collapseBtn.addEventListener('click', () => {
            body.classList.toggle('sidebar-collapsed');
            const isCollapsed = body.classList.contains('sidebar-collapsed');
            localStorage.setItem(COLLAPSE_KEY, isCollapsed ? '1' : '0');
            collapseBtn.setAttribute('aria-label', isCollapsed ? 'Развернуть меню' : 'Свернуть меню');
            collapseBtn.setAttribute('title', isCollapsed ? 'Развернуть меню' : 'Свернуть меню');
        });
    }

    // ── Sidebar (для авторизованных) — мобильное открытие ──
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

        sidebar.querySelectorAll('.sidebar__link').forEach((link) => {
            link.addEventListener('click', () => {
                if (window.innerWidth <= 1024) closeSidebar();
            });
        });

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
