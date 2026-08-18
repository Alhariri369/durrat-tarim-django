// Select ALL theme toggle buttons (desktop and mobile)
const themeToggleBtns = document.querySelectorAll('#theme-toggle, #theme-toggle-mobile');
const htmlElement = document.documentElement;

const applyTheme = (theme, persist = true) => {
    const isDark = theme === 'dark';

    if (isDark) {
        htmlElement.classList.add('dark');
        htmlElement.setAttribute('data-bs-theme', 'dark'); // Legacy BS support
        if (persist) localStorage.setItem('theme', 'dark');
    } else {
        htmlElement.classList.remove('dark');
        htmlElement.setAttribute('data-bs-theme', 'light'); // Legacy BS support
        if (persist) localStorage.setItem('theme', 'light');
    }

    // Update the innerHTML for BOTH buttons so they stay in sync
    themeToggleBtns.forEach(btn => {
        if (isDark) {
            btn.innerHTML = '<span>☀️</span> <span>الوضع الفاتح</span>';
        } else {
            btn.innerHTML = '<span>🌙</span> <span>الوضع الداكن</span>';
        }
    });
};

// 1. Initial Load Logic
const savedTheme = localStorage.getItem('theme');
const systemMediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

if (savedTheme === 'dark' || (!savedTheme && systemMediaQuery.matches)) {
    applyTheme('dark', false);
} else {
    applyTheme('light', false);
}

// 2. Handle Click (Attach listener to ALL buttons)
const initEventListeners = () => {
    themeToggleBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const isDark = htmlElement.classList.contains('dark');
            // If it is currently dark, switch to light, and vice versa
            applyTheme(isDark ? 'light' : 'dark');
        });
    });
};

// Check if buttons exist yet, if not, wait for them
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initEventListeners);
} else {
    initEventListeners();
}

// 3. System Sync: Update live if OS settings change (only if user hasn't overridden)
systemMediaQuery.addEventListener('change', (e) => {
    if (!localStorage.getItem('theme')) {
        applyTheme(e.matches ? 'dark' : 'light', false);
    }
});