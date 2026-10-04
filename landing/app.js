(() => {
  'use strict';

  const root = document.documentElement;
  const themeToggle = document.querySelector('[data-theme-toggle]');
  const modes = ['system', 'light', 'dark'];
  const themeNames = { system: 'sistema', light: 'claro', dark: 'escuro' };
  const themeIcons = { system: 'i-system', light: 'i-sun', dark: 'i-moon' };
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');

  const updateTheme = () => {
    const mode = modes.includes(root.dataset.theme) ? root.dataset.theme : 'system';
    const next = modes[(modes.indexOf(mode) + 1) % modes.length];
    themeToggle?.setAttribute('aria-label', `Tema: ${themeNames[mode]}. Alterar para ${themeNames[next]}.`);
    themeToggle?.setAttribute('title', `Tema: ${themeNames[mode]}`);
    themeToggle?.querySelector('use')?.setAttribute('href', `#${themeIcons[mode]}`);
    const dark = mode === 'dark' || (mode === 'system' && systemTheme.matches);
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#181816' : '#f7f7f5');
    document.querySelector('link[rel="icon"]')?.setAttribute('href', dark ? './assets/favicon.svg' : './assets/favicon-light.svg');
  };

  themeToggle?.addEventListener('click', () => {
    const current = modes.indexOf(root.dataset.theme);
    root.dataset.theme = modes[(current + 1) % modes.length];
    try { localStorage.setItem('concurse-landing-theme', root.dataset.theme); } catch (_) {}
    updateTheme();
  });
  systemTheme.addEventListener?.('change', updateTheme);
  updateTheme();

  const menuToggle = document.querySelector('[data-menu-toggle]');
  const navigation = document.querySelector('#site-navigation');
  const mobileBreakpoint = window.matchMedia('(max-width: 760px)');
  const setMenu = (expanded, returnFocus = false) => {
    navigation?.classList.toggle('is-open', expanded);
    menuToggle?.setAttribute('aria-expanded', String(expanded));
    menuToggle?.setAttribute('aria-label', expanded ? 'Fechar menu' : 'Abrir menu');
    menuToggle?.querySelector('use')?.setAttribute('href', expanded ? '#i-close' : '#i-menu');
    if (returnFocus) menuToggle?.focus();
  };

  menuToggle?.addEventListener('click', () => setMenu(menuToggle.getAttribute('aria-expanded') !== 'true'));
  navigation?.addEventListener('click', (event) => {
    if (event.target.closest('a')) setMenu(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && menuToggle?.getAttribute('aria-expanded') === 'true') setMenu(false, true);
  });
  document.addEventListener('click', (event) => {
    if (mobileBreakpoint.matches && !event.target.closest('.site-header')) setMenu(false);
  });
  document.addEventListener('focusin', (event) => {
    if (mobileBreakpoint.matches && !event.target.closest('.site-header')) setMenu(false);
  });
  mobileBreakpoint.addEventListener?.('change', () => setMenu(false));

  const tabs = Array.from(document.querySelectorAll('.preview-tabs [role="tab"]'));
  const setTab = (tab, moveFocus = false) => {
    tabs.forEach((item) => {
      const selected = item === tab;
      item.setAttribute('aria-selected', String(selected));
      item.setAttribute('tabindex', selected ? '0' : '-1');
      const panel = document.getElementById(item.getAttribute('aria-controls'));
      if (panel) panel.hidden = !selected;
    });
    if (moveFocus) tab.focus();
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => setTab(tab));
    tab.addEventListener('keydown', (event) => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next !== undefined) { event.preventDefault(); setTab(tabs[next], true); }
    });
  });

  const status = document.querySelector('[data-copy-status]');
  let statusTimer;
  const showStatus = (message) => {
    if (!status) return;
    clearTimeout(statusTimer);
    status.textContent = message;
    statusTimer = setTimeout(() => { status.textContent = ''; }, 5000);
  };
  const selectHash = (button) => {
    const hash = button.closest('.checksum')?.querySelector('code');
    if (!hash) return;
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(hash);
    selection?.removeAllRanges();
    selection?.addRange(range);
  };
  document.querySelectorAll('[data-copy]').forEach((button) => {
    button.addEventListener('click', async () => {
      const hash = button.dataset.copy;
      if (!hash || !/^[a-f0-9]{64}$/i.test(hash)) return;
      try {
        if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(hash);
        showStatus(`${button.dataset.copyLabel} copiado.`);
      } catch (_) {
        selectHash(button);
        showStatus('SHA-256 selecionado. Use a opção Copiar do seu dispositivo.');
      }
    });
  });
})();
