// Parallax scroll effect for grid background
// Uses scroll percentage (0-1) so grid feels endless on any page length
if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  let ticking = false;
  document.addEventListener(
    "scroll",
    () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          const scrollable =
            document.documentElement.scrollHeight - window.innerHeight;
          const progress = scrollable > 0 ? window.scrollY / scrollable : 0;
          document.body.style.setProperty(
            "--scroll-progress",
            progress.toFixed(3),
          );
          ticking = false;
        });
        ticking = true;
      }
    },
    { passive: true },
  );
}
