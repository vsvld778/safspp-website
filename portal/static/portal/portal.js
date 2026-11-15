document.documentElement.classList.add('js');
(() => {
  const toggle = document.querySelector('[data-menu-toggle]');
  const menu = document.getElementById('portal-navigation');
  if (!toggle || !menu) return;
  const close = () => {
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Открыть меню');
    menu.classList.remove('is-open');
  };
  toggle.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
    menu.classList.toggle('is-open', open);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
      close();
      toggle.focus();
    }
  });
  document.addEventListener('click', (event) => {
    if (!menu.contains(event.target) && !toggle.contains(event.target)) close();
  });
  menu.addEventListener('click', (event) => {
    if (event.target.closest('a')) close();
  });
  const media = window.matchMedia('(min-width: 761px)');
  media.addEventListener('change', close);
})();
