/* Shared appearance controller. Load synchronously in <head>, before styles. */
(() => {
  'use strict';
  if (window.MostSupportTheme) return;
  const key = 'most-support-theme';
  const modes = ['light', 'dark', 'system'];
  const root = document.documentElement;
  const media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  const words = {
    ru: {title:'Оформление', subtitle:'Выберите удобный режим.', light:'Светлая', dark:'Тёмная', system:'Как на устройстве', group:'Цветовая тема', done:'Готово', close:'Закрыть', note:'По умолчанию — светлая тема. Режим «Как на устройстве» следует настройкам устройства. Ваш выбор сохраняется в этом браузере.'},
    en: {title:'Appearance', subtitle:'Choose a comfortable display mode.', light:'Light', dark:'Dark', system:'Device setting', group:'Colour theme', done:'Done', close:'Close', note:'The default theme is light. Device setting follows your device appearance. Your choice is saved in this browser.'},
    tg: {title:'Намуди зоҳирӣ', subtitle:'Реҷаи бароҳатро интихоб кунед.', light:'Равшан', dark:'Торик', system:'Мисли дастгоҳ', group:'Мавзӯи ранг', done:'Тайёр', close:'Пӯшидан', note:'Пешфарз мавзӯи равшан аст. Реҷаи «Мисли дастгоҳ» ба танзимоти дастгоҳ пайравӣ мекунад. Интихоб дар ин браузер нигоҳ дошта мешавад.'},
    uz: {title:'Ko‘rinish', subtitle:'O‘zingizga qulay rejimni tanlang.', light:'Yorug‘', dark:'Qorong‘i', system:'Qurilmadagi kabi', group:'Rang mavzusi', done:'Tayyor', close:'Yopish', note:'Standart mavzu — yorug‘. «Qurilmadagi kabi» rejimi qurilma sozlamalariga amal qiladi. Tanlovingiz shu brauzerda saqlanadi.'},
    kk: {title:'Көрініс', subtitle:'Өзіңізге ыңғайлы режимді таңдаңыз.', light:'Ашық', dark:'Қараңғы', system:'Құрылғыдағыдай', group:'Түс тақырыбы', done:'Дайын', close:'Жабу', note:'Әдепкі тақырып — ашық. «Құрылғыдағыдай» режимі құрылғы баптауларын қолданады. Таңдауыңыз осы браузерде сақталады.'},
    ky: {title:'Көрүнүш', subtitle:'Ыңгайлуу режимди тандаңыз.', light:'Ачык', dark:'Караңгы', system:'Түзмөктөгүдөй', group:'Түс темасы', done:'Даяр', close:'Жабуу', note:'Демейки тема — ачык. «Түзмөктөгүдөй» режими түзмөктүн жөндөөлөрүн колдонот. Тандооңуз ушул браузерде сакталат.'},
    be: {title:'Афармленне', subtitle:'Выберыце зручны рэжым.', light:'Светлая', dark:'Цёмная', system:'Як на прыладзе', group:'Каляровая тэма', done:'Гатова', close:'Закрыць', note:'Па змаўчанні — светлая тэма. Рэжым «Як на прыладзе» выкарыстоўвае налады прылады. Ваш выбар захоўваецца ў гэтым браўзеры.'},
    hi: {title:'दिखावट', subtitle:'अपनी पसंद का मोड चुनें।', light:'हल्की', dark:'गहरी', system:'डिवाइस के अनुसार', group:'रंग थीम', done:'हो गया', close:'बंद करें', note:'डिफ़ॉल्ट थीम हल्की है। «डिवाइस के अनुसार» मोड डिवाइस की सेटिंग का पालन करता है। आपकी पसंद इस ब्राउज़र में सहेजी जाती है।'}
  };
  let preference = 'light';
  let storage = null;
  let dialog = null;
  let opener = null;
  try {
    storage = window.localStorage;
    const saved = storage.getItem(key);
    if (modes.includes(saved)) preference = saved;
  } catch (_) {}
  const resolved = () => preference === 'system' ? (media && media.matches ? 'dark' : 'light') : preference;
  const dictionary = () => words[(root.lang || 'ru').toLowerCase().split('-')[0]] || words.ru;
  const svg = path => `<svg class="ms-theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="${path}"/></svg>`;
  const icons = {
    light: 'M12 3V1m0 22v-2M3 12H1m22 0h-2M5.6 5.6 4.2 4.2m15.6 15.6-1.4-1.4M5.6 18.4l-1.4 1.4M19.8 4.2l-1.4 1.4M17 12a5 5 0 1 1-10 0 5 5 0 0 1 10 0',
    dark: 'M20.7 13a9 9 0 1 1-9.7-9.7A7 7 0 0 0 20.7 13Z',
    close: 'm6 6 12 12M18 6 6 18',
    check: 'm5 12 4 4L19 6'
  };
  function updateControls() {
    const text = dictionary();
    document.querySelectorAll('[data-theme-open]').forEach(button => {
      button.setAttribute('data-i18n-skip', '');
      button.setAttribute('aria-label', text.title);
      button.setAttribute('title', text.title);
      button.setAttribute('aria-haspopup', 'dialog');
      button.setAttribute('aria-controls', 'most-support-theme-dialog');
      button.setAttribute('aria-expanded', String(Boolean(dialog && dialog.open)));
      const appearance = resolved();
      if (button.dataset.themeIcon !== appearance) {
        button.innerHTML = svg(icons[appearance]);
        button.dataset.themeIcon = appearance;
      }
      if (dialog) button.hidden = false;
    });
    if (!dialog) return;
    dialog.querySelector('[data-theme-title]').textContent = text.title;
    dialog.querySelector('[data-theme-subtitle]').textContent = text.subtitle;
    dialog.querySelector('[data-theme-note]').textContent = text.note;
    dialog.querySelector('[data-theme-group]').setAttribute('aria-label', text.group);
    dialog.querySelector('[data-theme-done]').textContent = text.done;
    dialog.querySelector('[data-theme-close]').setAttribute('aria-label', text.close);
    dialog.querySelectorAll('[data-theme-choice]').forEach(button => {
      const mode = button.dataset.themeChoice;
      button.querySelector('.ms-theme-option-label').textContent = text[mode];
      button.setAttribute('aria-pressed', String(mode === preference));
    });
  }
  function apply() {
    const theme = resolved();
    root.dataset.theme = theme;
    root.dataset.themeMode = preference;
    root.style.colorScheme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#0f1e20' : '#faf8f2');
    updateControls();
    window.dispatchEvent(new CustomEvent('most-support-themechange', {detail: {mode: preference, theme}}));
  }
  function setMode(mode) {
    if (!modes.includes(mode)) return false;
    preference = mode;
    try { storage?.setItem(key, mode); } catch (_) {}
    apply();
    return true;
  }
  function close() {
    if (dialog && dialog.open) dialog.close();
  }
  function open(trigger) {
    if (!dialog) return false;
    if (dialog.open) return true;
    opener = trigger instanceof HTMLElement ? trigger : document.activeElement;
    dialog.showModal();
    updateControls();
    dialog.querySelector('[aria-pressed="true"]')?.focus();
    return true;
  }
  function initialize() {
    if (dialog) return;
    dialog = document.createElement('dialog');
    dialog.id = 'most-support-theme-dialog';
    dialog.className = 'ms-theme-dialog';
    dialog.setAttribute('data-i18n-skip', '');
    dialog.setAttribute('aria-labelledby', 'most-support-theme-title');
    dialog.setAttribute('aria-describedby', 'most-support-theme-subtitle');
    dialog.innerHTML = `<div class="ms-theme-heading"><div><h2 id="most-support-theme-title" data-theme-title></h2><p id="most-support-theme-subtitle" data-theme-subtitle></p></div><button type="button" class="ms-theme-close" data-theme-close>${svg(icons.close)}</button></div><div class="ms-theme-options" data-theme-group role="group">${modes.map(mode => `<button type="button" class="ms-theme-option" data-theme-choice="${mode}" aria-pressed="false"><span class="ms-theme-preview ms-theme-preview-${mode}" aria-hidden="true"><span class="ms-preview-top"></span><span class="ms-preview-hero"></span><span class="ms-preview-cards"><i></i><i></i></span><span class="ms-preview-nav"></span></span><span class="ms-theme-option-label"></span><span class="ms-theme-check" aria-hidden="true">${svg(icons.check)}</span></button>`).join('')}</div><p class="ms-theme-note" data-theme-note></p><button type="button" class="ms-theme-done" data-theme-done></button>`;
    document.body.appendChild(dialog);
    dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
    dialog.addEventListener('close', () => {
      updateControls();
      if (opener && opener.isConnected && !opener.hidden) opener.focus({preventScroll:true});
      opener = null;
    });
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const box = dialog.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) close();
    });
    document.addEventListener('click', event => {
      if (!(event.target instanceof Element)) return;
      const trigger = event.target.closest('[data-theme-open]');
      if (trigger) { open(trigger); return; }
      const choice = event.target.closest('[data-theme-choice]');
      if (choice && dialog.contains(choice)) setMode(choice.dataset.themeChoice);
      if (event.target.closest('[data-theme-close], [data-theme-done]') && dialog.contains(event.target)) close();
    });
    new MutationObserver(updateControls).observe(root, {attributes:true, attributeFilter:['lang']});
    apply();
  }
  window.MostSupportTheme = Object.freeze({getMode: () => preference, getTheme: resolved, setMode, open});
  const systemChanged = () => { if (preference === 'system') apply(); };
  if (media?.addEventListener) media.addEventListener('change', systemChanged);
  else if (media?.addListener) media.addListener(systemChanged);
  window.addEventListener('storage', event => {
    if (event.storageArea && storage && event.storageArea !== storage) return;
    if (event.key === key || event.key === null) {
      preference = modes.includes(event.newValue) ? event.newValue : 'light';
      apply();
    }
  });
  apply();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, {once:true});
  else initialize();
})();
