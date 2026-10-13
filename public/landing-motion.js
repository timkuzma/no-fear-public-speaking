// Timings adapted from the primary sources in docs/landing-motion-notes.md.
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const easeOut = "cubic-bezier(.22,1,.36,1)";
const contextAnimations = new WeakMap();

export function animateContextChange(panel) {
  contextAnimations.get(panel)?.cancel();
  if (reducedMotion.matches || !panel.animate) return;
  const target = panel.querySelector('[aria-hidden="false"]');
  const animation = target.animate(
    [{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "translateY(0)" }],
    { duration: 220, easing: easeOut },
  );
  contextAnimations.set(panel, animation);
}

export function mountLandingMotion(root) {
  if (!root) return () => {};
  // Scrolling keeps all content in its final state. Animate explicit interactions only.
  const cancel = () => {
    contextAnimations.get(root.querySelector("#landing-context-copy"))?.cancel();
  };
  const onPreferenceChange = () => { if (reducedMotion.matches) cancel(); };
  reducedMotion.addEventListener("change", onPreferenceChange);
  return () => {
    cancel();
    reducedMotion.removeEventListener("change", onPreferenceChange);
  };
}
