// External script keeps theme initialization compatible with Manifest V3 CSP.
(() => {
  const key = 'talentmatch-theme';
  const root = document.documentElement;
  const valid = value => value === 'light' || value === 'dark';
  const preferred = window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  let theme = preferred;
  try {
    const saved = localStorage.getItem(key);
    if (valid(saved)) theme = saved;
  } catch { /* System preference remains available when local storage is blocked. */ }
  root.setAttribute('data-theme', theme);

  document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('themeToggle');
    let changed = false;
    function apply(value) {
      root.setAttribute('data-theme', value);
      button?.setAttribute('aria-label', `Switch to ${value === 'light' ? 'dark' : 'light'} theme`);
      try { localStorage.setItem(key, value); } catch { /* chrome.storage also persists the choice. */ }
    }
    apply(theme);
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local.get([key], result => {
        if (!chrome.runtime.lastError && !changed && valid(result[key])) apply(result[key]);
      });
    }
    button?.addEventListener('click', () => {
      changed = true;
      const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
      apply(next);
      if (typeof chrome !== 'undefined' && chrome.storage?.local) {
        chrome.storage.local.set({ [key]: next });
      }
    });
  }, { once: true });
})();
