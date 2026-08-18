/**
 * Durrat Tarim – Premium Scroll Reveal & Interactions
 */
(() => {
  'use strict';

  /* ============================================================
     Scroll Reveal (Intersection Observer)
     ============================================================ */
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  function initScrollReveal() {
    if (prefersReducedMotion.matches) {
      document.querySelectorAll('.reveal').forEach(el => el.classList.add('revealed'));
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
        threshold: 0.12,
        rootMargin: '0px 0px -40px 0px',
      }
    );

    document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
    return observer;
  }

  /* ============================================================
     Counter Animation
     ============================================================ */
  function animateCounters() {
    if (prefersReducedMotion.matches) return;
    const counters = document.querySelectorAll('[data-counter]');
    if (!counters.length) return;

    const counterObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (!entry.isIntersecting) return;
          const el = entry.target;
          const target = parseInt(el.dataset.counter, 10);
          const duration = parseInt(el.dataset.duration, 10) || 2000;
          const suffix = el.dataset.suffix || '';
          const start = performance.now();

          function update(now) {
            const elapsed = now - start;
            const progress = Math.min(elapsed / duration, 1);
            // Ease-out expo
            const eased = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
            const current = Math.floor(target * eased);
            el.textContent = current.toLocaleString('ar-EG') + suffix;
            if (progress < 1) {
              requestAnimationFrame(update);
            }
          }
          requestAnimationFrame(update);
          counterObserver.unobserve(el);
        });
      },
      { threshold: 0.6 }
    );

    counters.forEach(el => counterObserver.observe(el));
  }

  /* ============================================================
     Smooth Scroll for Anchor Links
     ============================================================ */
  function initSmoothScroll() {
    document.addEventListener('click', (e) => {
      const link = e.target.closest('a[href^="#"]');
      if (!link) return;
      const target = document.querySelector(link.getAttribute('href'));
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  /* ============================================================
     Parallax Tilt on Hover
     ============================================================ */
  function initTilt() {
    if (prefersReducedMotion.matches) return;
    const cards = document.querySelectorAll('[data-tilt]');

    cards.forEach(card => {
      card.addEventListener('mousemove', (e) => {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;
        const rotateX = ((y - centerY) / centerY) * -8;
        const rotateY = ((x - centerX) / centerX) * 8;
        card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.02, 1.02, 1.02)`;
      });

      card.addEventListener('mouseleave', () => {
        card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) scale3d(1, 1, 1)';
      });
    });
  }

  /* ============================================================
     Active Nav Link Highlight
     ============================================================ */
  function highlightActiveNav() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('[data-nav-link]');
    navLinks.forEach(link => {
      const href = link.getAttribute('href');
      if (href === currentPath || (href !== '/' && currentPath.startsWith(href))) {
        link.classList.add('text-accent', 'bg-accent/5');
      }
    });
  }

  /* ============================================================
     WhatsApp Floating Button Pulse
     ============================================================ */
  function initWhatsAppFloat() {
    const btn = document.querySelector('[data-whatsapp-float]');
    if (!btn) return;
    // Show after scroll
    let shown = false;
    window.addEventListener('scroll', () => {
      if (!shown && window.scrollY > 400) {
        btn.classList.remove('translate-y-24', 'opacity-0');
        btn.classList.add('translate-y-0', 'opacity-100');
        shown = true;
      }
    }, { passive: true });
  }

  /* ============================================================
     Mobile Menu Toggle
     ============================================================ */
  function initMobileMenu() {
    const toggle = document.querySelector('[data-mobile-toggle]');
    const menu = document.querySelector('[data-mobile-menu]');
    if (!toggle || !menu) return;

    toggle.addEventListener('click', () => {
      const isOpen = !menu.classList.contains('hidden');
      if (isOpen) {
        menu.classList.add('hidden');
        toggle.setAttribute('aria-expanded', 'false');
        document.body.classList.remove('overflow-hidden');
      } else {
        menu.classList.remove('hidden');
        toggle.setAttribute('aria-expanded', 'true');
        document.body.classList.add('overflow-hidden');
      }
    });

    // Close on link click
    menu.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        menu.classList.add('hidden');
        toggle.setAttribute('aria-expanded', 'false');
        document.body.classList.remove('overflow-hidden');
      });
    });
  }

  /* ============================================================
     FAQ Accordion
     ============================================================ */
  function initFAQ() {
    document.querySelectorAll('[data-faq-toggle]').forEach(button => {
      button.addEventListener('click', () => {
        const content = button.nextElementSibling;
        const isOpen = button.getAttribute('aria-expanded') === 'true';

        // Close all others
        document.querySelectorAll('[data-faq-toggle]').forEach(other => {
          if (other !== button) {
            other.setAttribute('aria-expanded', 'false');
            other.querySelector('[data-faq-icon]').style.transform = 'rotate(0deg)';
            other.nextElementSibling.style.maxHeight = '0';
          }
        });

        if (isOpen) {
          button.setAttribute('aria-expanded', 'false');
          button.querySelector('[data-faq-icon]').style.transform = 'rotate(0deg)';
          content.style.maxHeight = '0';
        } else {
          button.setAttribute('aria-expanded', 'true');
          button.querySelector('[data-faq-icon]').style.transform = 'rotate(45deg)';
          content.style.maxHeight = content.scrollHeight + 'px';
        }
      });
    });
  }

  /* ============================================================
     Header Shrink on Scroll
     ============================================================ */
  function initHeaderShrink() {
    const header = document.querySelector('[data-header]');
    if (!header) return;
    let lastScroll = 0;

    window.addEventListener('scroll', () => {
      const currentScroll = window.scrollY;
      if (currentScroll > 80) {
        header.classList.add('shadow-lg', 'py-2');
        header.classList.remove('py-4');
      } else {
        header.classList.remove('shadow-lg', 'py-2');
        header.classList.add('py-4');
      }
      lastScroll = currentScroll;
    }, { passive: true });
  }

  /* ============================================================
     Initialize Everything
     ============================================================ */
  function init() {
    initScrollReveal();
    animateCounters();
    initSmoothScroll();
    initTilt();
    highlightActiveNav();
    initWhatsAppFloat();
    initMobileMenu();
    initFAQ();
    initHeaderShrink();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
