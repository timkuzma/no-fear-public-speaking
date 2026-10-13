// Timings adapted from the primary sources in docs/landing-motion-notes.md.
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const easeOut = "cubic-bezier(.22,1,.36,1)";
const contextAnimations = new WeakMap();

export function animateContextChange(panel) {
  contextAnimations.get(panel)?.cancel();
  if (reducedMotion.matches || !panel.animate) return;
  const animation = panel.animate(
    [{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "translateY(0)" }],
    { duration: 220, easing: easeOut },
  );
  contextAnimations.set(panel, animation);
}

export function mountLandingMotion(root) {
  if (!root) return () => {};
  let observer;
  const animations = new Set();
  const animate = (element, distance, duration, delay = 0) => {
    if (reducedMotion.matches || !element.animate) return;
    const animation = element.animate(
      [{ opacity: 0, transform: `translateY(${distance}px)` }, { opacity: 1, transform: "translateY(0)" }],
      { duration, delay, easing: easeOut, fill: "backwards" },
    );
    animations.add(animation);
    animation.finished.then(() => animations.delete(animation)).catch(() => animations.delete(animation));
  };
  if (!reducedMotion.matches) {
    root.querySelectorAll("[data-enter]").forEach((element, index) => animate(element, 16, 480, index * 60));
    if ("IntersectionObserver" in window) {
      observer = new IntersectionObserver((entries) => {
        entries.forEach(({ target, isIntersecting }) => {
          if (!isIntersecting) return;
          animate(target, 18, 420);
          observer.unobserve(target);
        });
      }, { threshold: 0.12, rootMargin: "0px 0px -32px 0px" });
      root.querySelectorAll("[data-reveal]").forEach((element) => observer.observe(element));
    }
  }
  const cancel = () => {
    observer?.disconnect();
    animations.forEach((animation) => animation.cancel());
    animations.clear();
    contextAnimations.get(root.querySelector("#landing-context-panel"))?.cancel();
  };
  const onPreferenceChange = () => { if (reducedMotion.matches) cancel(); };
  reducedMotion.addEventListener("change", onPreferenceChange);
  return () => {
    cancel();
    reducedMotion.removeEventListener("change", onPreferenceChange);
  };
}
