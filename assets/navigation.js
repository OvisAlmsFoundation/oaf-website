/* Keep the shared sticky header compact after scrolling, without moving content. */
(() => {
  const header = document.querySelector('.site-header');
  if (!header) return;

  let pending = false;
  const update = () => {
    pending = false;
    // Separate thresholds keep tiny scroll changes from toggling the header.
    if (window.scrollY > 64) header.classList.add('is-compact');
    else if (window.scrollY <= 0) header.classList.remove('is-compact');
  };
  window.addEventListener('scroll', () => {
    if (!pending) {
      pending = true;
      window.requestAnimationFrame(update);
    }
  }, { passive: true });
  window.addEventListener('pageshow', update);
  update();
})();
