// Tiny enhancement hooks; keep bundle-free.
document.addEventListener('DOMContentLoaded', () => {
  // Ripple-ish click effect for primary buttons (demo)
  document.querySelectorAll('a.bg-blue-600, button.bg-blue-600').forEach(btn => {
    btn.addEventListener('click', () => btn.classList.add('ring-2','ring-blue-300'));
    btn.addEventListener('blur', () => btn.classList.remove('ring-2','ring-blue-300'));
  });
});
