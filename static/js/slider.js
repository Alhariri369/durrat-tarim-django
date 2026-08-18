(() => {
    const slider = document.querySelector("[data-featured-slider]");
    if (!slider) return;

    const slides = [...slider.querySelectorAll("[data-slide]")];
    const dots = [...slider.querySelectorAll("[data-slide-dot]")];
    const previous = slider.querySelector("[data-slide-previous]");
    const next = slider.querySelector("[data-slide-next]");
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const autoplayDelay = Number(slider.dataset.autoplay || 0);
    let current = 0;
    let timer = null;
    let touchStartX = null;

    const show = (index, focusDot = false) => {
        current = (index + slides.length) % slides.length;
        slides.forEach((slide, slideIndex) => {
            const active = slideIndex === current;
            slide.hidden = !active;
            slide.setAttribute("aria-hidden", String(!active));
        });
        dots.forEach((dot, dotIndex) => {
            const active = dotIndex === current;
            dot.setAttribute("aria-current", active ? "true" : "false");
            dot.tabIndex = active ? 0 : -1;
        });
        if (focusDot && dots[current]) dots[current].focus();
    };

    const stop = () => {
        window.clearInterval(timer);
        timer = null;
    };
    const start = () => {
        stop();
        if (autoplayDelay > 0 && slides.length > 1 && !reduceMotion.matches && !document.hidden) {
            timer = window.setInterval(() => show(current + 1), autoplayDelay);
        }
    };

    previous?.addEventListener("click", () => show(current - 1));
    next?.addEventListener("click", () => show(current + 1));
    dots.forEach((dot, index) => dot.addEventListener("click", () => show(index)));
    slider.addEventListener("keydown", (event) => {
        if (event.key === "ArrowRight") show(current - 1, true);
        if (event.key === "ArrowLeft") show(current + 1, true);
        if (event.key === "Home") show(0, true);
        if (event.key === "End") show(slides.length - 1, true);
    });
    slider.addEventListener("touchstart", (event) => {
        touchStartX = event.changedTouches[0].clientX;
    }, { passive: true });
    slider.addEventListener("touchend", (event) => {
        if (touchStartX === null) return;
        const distance = event.changedTouches[0].clientX - touchStartX;
        if (Math.abs(distance) > 50) show(current + (distance > 0 ? -1 : 1));
        touchStartX = null;
    }, { passive: true });
    slider.addEventListener("mouseenter", stop);
    slider.addEventListener("mouseleave", start);
    slider.addEventListener("focusin", stop);
    slider.addEventListener("focusout", (event) => {
        if (!slider.contains(event.relatedTarget)) start();
    });
    document.addEventListener("visibilitychange", () => document.hidden ? stop() : start());
    reduceMotion.addEventListener?.("change", start);

    show(0);
    start();
})();
