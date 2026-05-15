/**
 * Сайт кафедры СИИ • ИКИТ • СФУ
 */
(function () {
    'use strict';

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

    // ── Аватарка пользователя из localStorage ──────────────
    const AVATAR_KEY = 'sfu_user_avatar';
    const savedAvatar = localStorage.getItem(AVATAR_KEY);

    function applyAvatar(dataUrl) {
        document.querySelectorAll('.sidebar__user-avatar, .topbar__user-avatar, .profile-avatar').forEach((el) => {
            el.style.backgroundImage = `url('${dataUrl}')`;
            el.classList.add('has-photo');
        });
    }

    function clearAvatar() {
        document.querySelectorAll('.sidebar__user-avatar, .topbar__user-avatar, .profile-avatar').forEach((el) => {
            el.style.backgroundImage = '';
            el.classList.remove('has-photo');
        });
    }

    if (savedAvatar) {
        applyAvatar(savedAvatar);
    }

    // Загрузка аватарки из профиля
    const avatarInput = document.getElementById('avatar-upload');
    const avatarRemoveBtn = document.getElementById('avatar-remove');

    if (avatarInput) {
        avatarInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (!file) return;
            if (!file.type.startsWith('image/')) {
                alert('Можно загружать только изображения.');
                return;
            }
            if (file.size > 2 * 1024 * 1024) {
                alert('Размер файла не должен превышать 2 МБ.');
                return;
            }
            const reader = new FileReader();
            reader.onload = (evt) => {
                const dataUrl = evt.target.result;
                localStorage.setItem(AVATAR_KEY, dataUrl);
                applyAvatar(dataUrl);
            };
            reader.readAsDataURL(file);
        });
    }

    if (avatarRemoveBtn) {
        avatarRemoveBtn.addEventListener('click', () => {
            if (confirm('Удалить фото профиля?')) {
                localStorage.removeItem(AVATAR_KEY);
                clearAvatar();
            }
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
