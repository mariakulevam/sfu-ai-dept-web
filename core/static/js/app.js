/**
 * Сайт кафедры СИИ • ИКИТ • СФУ
 */
(function () {
    'use strict';

    // Бургер-меню для мобильных
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
