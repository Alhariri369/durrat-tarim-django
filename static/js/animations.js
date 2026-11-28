/**
 * Durrat Tarim – Editorial UI Interactions & Accessibility Helpers
 */
(() => {
  'use strict';

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  /* ============================================================
     Scroll Reveal (Intersection Observer)
     ============================================================ */
  function initScrollReveal() {
    const items = document.querySelectorAll('.reveal');
    if (!items.length) return;

    if (prefersReducedMotion.matches || !('IntersectionObserver' in window)) {
      items.forEach(el => el.classList.add('revealed'));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('revealed');
            observer.unobserve(entry.target);
          }
        });
      },
      {
        threshold: 0.08,
        rootMargin: '0px 0px -24px 0px',
      }
    );

    items.forEach(el => observer.observe(el));
  }

  /* ============================================================
     Active Nav Link Highlight
     ============================================================ */
  function highlightActiveNav() {
    const currentPath = window.location.pathname;
    document.querySelectorAll('[data-nav-link]').forEach(link => {
      const href = link.getAttribute('href');
      if (href === currentPath || (href !== '/' && currentPath.startsWith(href))) {
        link.classList.add('text-primary', 'bg-primary/8');
        link.classList.remove('text-secondary/80');
        link.setAttribute('aria-current', 'page');
      }
    });
  }

  /* ============================================================
     WhatsApp Floating Concierge Button
     ============================================================ */
  function initWhatsAppFloat() {
    const btn = document.querySelector('[data-whatsapp-float]');
    if (!btn) return;

    const syncVisibility = () => {
      if (window.scrollY > 280) {
        btn.classList.remove('translate-y-20', 'opacity-0', 'pointer-events-none');
        btn.classList.add('translate-y-0', 'opacity-100');
      } else {
        btn.classList.add('translate-y-20', 'opacity-0', 'pointer-events-none');
        btn.classList.remove('translate-y-0', 'opacity-100');
      }
    };

    syncVisibility();
    window.addEventListener('scroll', syncVisibility, { passive: true });
  }

  /* ============================================================
     Mobile Menu Drawer (with Escape & Icon State)
     ============================================================ */
  function initMobileMenu() {
    const toggle = document.querySelector('[data-mobile-toggle]');
    const menu = document.querySelector('[data-mobile-menu]');
    if (!toggle || !menu) return;

    const openIcon = toggle.querySelector('[data-icon-open]');
    const closeIcon = toggle.querySelector('[data-icon-close]');

    const setMenuOpen = (open, restoreFocus = false) => {
      menu.classList.toggle('hidden', !open);
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'إغلاق القائمة' : 'فتح القائمة');
      document.body.classList.toggle('overflow-hidden', open);
      if (openIcon && closeIcon) {
        openIcon.classList.toggle('hidden', open);
        closeIcon.classList.toggle('hidden', !open);
      }
      if (!open && restoreFocus) {
        toggle.focus();
      }
    };

    toggle.addEventListener('click', () => {
      const isOpen = !menu.classList.contains('hidden');
      setMenuOpen(!isOpen);
    });

    menu.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => setMenuOpen(false));
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !menu.classList.contains('hidden')) {
        setMenuOpen(false, true);
      }
    });
  }

  /* ============================================================
     FAQ Accordion
     ============================================================ */
  function initFAQ() {
    const toggles = document.querySelectorAll('[data-faq-toggle]');
    if (!toggles.length) return;

    toggles.forEach(button => {
      button.addEventListener('click', () => {
        const panelId = button.getAttribute('aria-controls');
        const content = panelId ? document.getElementById(panelId) : button.nextElementSibling;
        if (!content) return;

        const isOpen = button.getAttribute('aria-expanded') === 'true';

        toggles.forEach(other => {
          if (other !== button) {
            const otherId = other.getAttribute('aria-controls');
            const otherPanel = otherId ? document.getElementById(otherId) : other.nextElementSibling;
            const otherIcon = other.querySelector('[data-faq-icon]');
            other.setAttribute('aria-expanded', 'false');
            if (otherIcon) otherIcon.classList.remove('rotate-180');
            if (otherPanel) otherPanel.hidden = true;
          }
        });

        button.setAttribute('aria-expanded', String(!isOpen));
        const icon = button.querySelector('[data-faq-icon]');
        if (icon) icon.classList.toggle('rotate-180', !isOpen);
        content.hidden = isOpen;
      });
    });
  }

  /* ============================================================
     Header Elevation on Scroll
     ============================================================ */
  function initHeaderElevation() {
    const header = document.querySelector('[data-header]');
    if (!header) return;

    const update = () => {
      if (window.scrollY > 24) {
        header.classList.add('shadow-sm');
      } else {
        header.classList.remove('shadow-sm');
      }
    };

    update();
    window.addEventListener('scroll', update, { passive: true });
  }

  /* ============================================================
     Form Ergonomics: Error Focus & In-Flight Submit Spinner
     ============================================================ */
  function initFormEnhancements() {
    // 1. Wire aria-invalid / aria-describedby for server-rendered field errors & focus first invalid field
    let firstInvalid = document.querySelector('[aria-invalid="true"]');

    document.querySelectorAll('[data-field-group]').forEach(group => {
      const errorEl = group.querySelector('[data-field-error]');
      const input = group.querySelector('input, textarea, select');
      if (errorEl && input) {
        input.setAttribute('aria-invalid', 'true');
        if (errorEl.id) {
          input.setAttribute('aria-describedby', errorEl.id);
        }
        input.classList.add('border-red-500');
        if (!firstInvalid) {
          firstInvalid = input;
        }
      }
    });

    if (firstInvalid && typeof firstInvalid.focus === 'function') {
      firstInvalid.focus({ preventScroll: false });
    }

    // 2. Prevent double-submit on POST forms while preserving button width & label
    document.querySelectorAll('form[method="post"], form[method="POST"]').forEach(form => {
      form.addEventListener('submit', (event) => {
        if (form.dataset.submitting === 'true') {
          event.preventDefault();
          return;
        }
        if (typeof form.checkValidity === 'function' && !form.checkValidity()) {
          return;
        }

        const submitBtn = form.querySelector('button[type="submit"]');
        if (!submitBtn) return;

        form.dataset.submitting = 'true';
        const rect = submitBtn.getBoundingClientRect();
        if (rect.width > 0) {
          submitBtn.style.minWidth = `${Math.ceil(rect.width)}px`;
        }
        submitBtn.disabled = true;
        submitBtn.setAttribute('aria-busy', 'true');
        submitBtn.classList.add('opacity-80', 'cursor-wait');

        if (!submitBtn.hasAttribute('data-icon-only') && !submitBtn.querySelector('[data-submit-spinner]')) {
          const spinner = document.createElement('span');
          spinner.setAttribute('data-submit-spinner', '');
          spinner.setAttribute('aria-hidden', 'true');
          spinner.className = 'ms-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent align-middle';
          submitBtn.appendChild(spinner);
        }
      });
    });
  }

  function init() {
    initScrollReveal();
    highlightActiveNav();
    initWhatsAppFloat();
    initMobileMenu();
    initFAQ();
    initHeaderElevation();
    initFormEnhancements();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
