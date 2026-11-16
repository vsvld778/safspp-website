/* Apply released edits and let the owner edit an isolated preview. */
(() => {
  'use strict';
  const script = document.currentScript;
  const surface = script.dataset.surface;
  const origin = new URL(script.src).origin;
  const editing = location.origin === origin && new URLSearchParams(location.search).get('editorial') === surface;
  const layout = {
    site: {main:'#main', dialog:'#detail-dialog', header:'body > header', footer:'body > footer', nav:'#navigation'},
    personal: {main:'main', header:'.site-header', footer:'.site-footer', aside:'#portal-navigation'},
    organization: {main:'#org-view', dialog:'#org-dialog', header:'.org-topbar', footer:'.org-footer', aside:'.org-sidebar', nav:'#org-mobile-nav'},
    application: {main:'.view-fade', dialog:'#modal', header:'.topbar', footer:'.footer', aside:'.sidebar', nav:'.bottom-nav'},
  }[surface];
  if (!layout) return;
  const rootPage = {site:'home', organization:'overview', application:'home'};
  const personalPages = {'/cabinet/':'entry','/login/':'login','/signup/':'signup','/cases/':'cases','/cases/new/':'case-new'};
  const blocked = '[data-editorial-ui],[data-no-translate],[data-editorial-private],.record-row,.case-message,script,style,svg,noscript,textarea';
  const attributes = ['alt','title','aria-label','placeholder'];
  const identity = ['lang','path','kind','field','source'];
  const savedForPage = new Map();
  let current = '', rules = [], originals = [], mode = 'text', selected = null;
  let revision = 0, csrf = '', panel, ready = false, dirty = false, saving = false, scheduled = false;
  const lang = () => document.documentElement.lang.split('-')[0];

  function page() {
    if (surface === 'personal') {
      return script.dataset.page || personalPages[location.pathname] || (/^\/cases\/[a-f0-9-]+\/$/.test(location.pathname) ? 'case' : '');
    }
    const raw = location.hash.slice(1);
    if (['main','main-content','navigation','org-main'].includes(raw)) return current || rootPage[surface];
    if (surface === 'organization' && raw.startsWith('request/')) return 'request';
    return /^[a-z0-9_-]+(?:\/[a-z0-9_-]+){0,2}$/.test(raw) ? raw : rootPage[surface];
  }

  function routePath(key, draft) {
    return (draft ? '/admin/editorial/draft/' : '/api/public/editorial/') + surface + '/' + key.split('/').map(encodeURIComponent).join('/') + '/';
  }

  async function request(path, options = {}) {
    const response = await fetch(origin + path, {cache:'no-store', credentials:editing ? 'same-origin' : 'omit', ...options});
    if (response.redirected || response.status === 403) throw new Error('Откройте предпросмотр после входа в админку.');
    if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Сервер редактора пока недоступен.');
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || 'Ошибка редактора.');
    return body;
  }

  const textNodes = element => [...element.childNodes].filter(node => node.nodeType === Node.TEXT_NODE);
  const backgroundUrl = /url\(["']?([^"')]+)["']?\)/;
  function source(element, kind, field) {
    if (kind === 'block') return element.tagName + '/' + element.id + '/' + element.className;
    if (kind === 'image') return field === 'src' ? element.getAttribute('src') : getComputedStyle(element).backgroundImage.match(backgroundUrl)?.[1];
    return /^\d+$/.test(field) ? textNodes(element)[Number(field)]?.nodeValue?.trim() : element.getAttribute(field)?.trim();
  }

  function signature(element, kind, field) {
    let value = source(element, kind, field) || '';
    if (kind === 'image') {
      try { value = new URL(value, document.baseURI).pathname.split('/').pop(); } catch {}
    }
    let sum = 2166136261;
    for (const ch of value) sum = Math.imul(sum ^ ch.codePointAt(0), 16777619);
    return (sum >>> 0).toString(16).padStart(8, '0');
  }

  function address(element) {
    const anchor = Object.entries(layout).find(([, selector]) => element.closest(selector));
    const root = anchor ? element.closest(anchor[1]) : document.body;
    const path = [];
    while (element !== root) {
      path.unshift(Array.prototype.indexOf.call(element.parentElement.children, element));
      element = element.parentElement;
    }
    return [anchor?.[0] || 'body', ...path].join('.');
  }

  function find(path) {
    const [anchor, ...indices] = path.split('.');
    const root = anchor === 'body' ? document.body : layout[anchor] && document.querySelector(layout[anchor]);
    return indices.reduce((node, index) => node?.children[Number(index)], root);
  }

  function attribute(element, field, value) {
    const original = element.getAttribute(field);
    const set = next => next === null ? element.removeAttribute(field) : element.setAttribute(field, next);
    set(value);
    originals.push(() => { if (element.getAttribute(field) === value) set(original); });
  }

  function undo() {
    for (const restore of originals.reverse()) restore();
    originals = [];
  }

  function apply() {
    undo();
    for (const rule of rules) {
      if (rule.lang !== lang()) continue;
      const element = find(rule.path);
      if (!element || element.closest(blocked) || rule.source !== signature(element, rule.kind, rule.field)) continue;
      if (rule.kind === 'block' && rule.value) {
        attribute(element, editing ? 'data-editorial-muted' : 'data-editorial-hidden', '');
      } else if (rule.kind === 'image') {
        const url = origin + (editing ? '/admin/editorial/images/' : '/editorial-images/') + rule.value + '/';
        if (rule.field === 'src') {
          attribute(element, 'srcset', null);
          attribute(element, 'src', url);
        } else {
          const initial = element.style.backgroundImage;
          element.style.backgroundImage = getComputedStyle(element).backgroundImage.replace(backgroundUrl, 'url("' + url + '")');
          originals.push(() => { element.style.backgroundImage = initial; });
        }
      } else if (rule.kind === 'text') {
        if (/^\d+$/.test(rule.field)) {
          const node = textNodes(element)[Number(rule.field)];
          if (!node) continue;
          const initial = node.nodeValue;
          const value = initial.replace(initial.trim(), () => rule.value);
          node.nodeValue = value;
          originals.push(() => { if (node.nodeValue === value) node.nodeValue = initial; });
        } else {
          attribute(element, rule.field, rule.value);
        }
      }
    }
  }

  const status = message => { if (panel) panel.querySelector('[data-status]').textContent = message; };

  function clear() {
    if (selected) selected.el.removeAttribute('data-editorial-selected');
    selected = null;
    panel?.querySelector('[data-field]').replaceChildren();
  }

  async function load() {
    const target = page();
    if (!target || target === current) return;
    if (dirty && current) savedForPage.set(current, {rules, revision});
    current = target;
    ready = dirty = false;
    rules = [];
    clear();
    undo();
    status('Загружаем страницу…');
    try {
      const result = await request(routePath(target, editing));
      if (current !== target) return;
      const pending = savedForPage.get(target);
      rules = pending?.rules || result.rules;
      revision = pending?.revision ?? result.version;
      csrf = result.csrf || '';
      ready = true;
      dirty = Boolean(pending);
      apply();
      status('Страница: ' + target + ' · выберите элемент');
    } catch (error) {
      if (current === target && editing) status(error.message);
    }
  }

  async function save(action) {
    if (!ready || saving) return;
    saving = true;
    const target = current, sent = rules;
    try {
      const result = await request(routePath(target, true), {
        method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':csrf},
        body:JSON.stringify({rules:sent,version:revision,action}),
      });
      if (target === current) {
        revision = result.version;
        dirty = sent !== rules;
        status(action === 'publish' ? 'Опубликовано' : 'Черновик сохранён');
      }
      const pending = savedForPage.get(target);
      if (pending && sent !== pending.rules) pending.revision = result.version;
      else savedForPage.delete(target);
    } catch (error) { status(error.message); }
    finally { saving = false; }
  }

  function target(element) {
    while (element && document.body.contains(element) && element !== document.body && !element.closest(blocked)) {
      let fields;
      if (mode === 'text') fields = [...textNodes(element).flatMap((node, i) => node.nodeValue.trim() ? [String(i)] : []), ...attributes.filter(attr => element.getAttribute(attr)?.trim())];
      if (mode === 'image') fields = element.tagName === 'IMG' ? ['src'] : source(element, 'image', 'background') ? ['background'] : [];
      if (mode === 'block') fields = element.matches('section,article,aside,.panel,.card,.feature-card,.page-heading,.page-header,.split,.cta-box') && !element.querySelector('form,[data-editorial-private]') ? ['hidden'] : [];
      if (fields?.length) return {el:element, fields, field:fields[0]};
      element = element.parentElement;
    }
    return null;
  }

  function editField() {
    if (!selected) return;
    undo();
    const {el, fields, field} = selected;
    const rule = {kind:mode, field, path:address(el), lang:lang(), source:signature(el, mode, field)};
    const match = item => identity.every(key => item[key] === rule[key]);
    const prior = rules.find(match);
    const host = panel.querySelector('[data-field]');
    host.replaceChildren();
    const set = (value, restore = false) => {
      rules = rules.filter(item => !match(item));
      if (!restore) rules.push({...rule,value});
      dirty = true;
      status('Изменения в предпросмотре');
      apply();
    };
    if (fields.length > 1) {
      const picker = document.createElement('select');
      for (const name of fields) picker.add(new Option(/^\d+$/.test(name) ? source(el,'text',name).slice(0,60) : name, name, false, name === field));
      picker.addEventListener('change', () => { selected.field = picker.value; editField(); });
      host.append(picker);
    }
    const input = document.createElement(mode === 'text' ? 'textarea' : 'input');
    input.setAttribute('aria-label', {text:'Новый текст',block:'Показывать блок',image:'Загрузить изображение'}[mode]);
    if (mode === 'text') {
      input.maxLength = 5000;
      input.rows = 3;
      input.value = prior?.value ?? source(el, mode, field);
      input.addEventListener('input', () => set(input.value));
    } else if (mode === 'block') {
      input.type = 'checkbox';
      input.checked = !prior?.value;
      input.addEventListener('change', () => set(!input.checked));
      host.append('Показывать блок ');
    } else {
      input.type = 'file';
      input.accept = 'image/jpeg,image/png,image/webp';
      input.addEventListener('change', async () => {
        if (!input.files?.[0]) return;
        const active = current;
        const body = new FormData();
        body.append('image',input.files[0]);
        input.disabled = true;
        try {
          const result = await request('/admin/editorial/upload/',{method:'POST',headers:{'X-CSRFToken':csrf},body});
          if (active === current && selected?.el === el && rule.lang === lang() && mode === 'image') set(result.key);
        } catch (error) { status(error.message); }
        finally { input.disabled = false; }
      });
    }
    const restore = document.createElement('button');
    restore.type = 'button';
    restore.textContent = 'Вернуть исходное';
    restore.addEventListener('click', () => { set(null, true); editField(); });
    host.append(input, restore);
    apply();
    if (mode === 'text') input.focus();
  }

  function showEditor() {
    panel = document.createElement('aside');
    panel.className = 'most-editorial';
    panel.dataset.editorialUi = '';
    panel.innerHTML = '<div class="most-editorial-bar"><strong>Редактор страницы</strong> <label>Редактировать <select aria-label="Тип элемента"><option value="text">Тексты и подписи</option><option value="image">Изображения</option><option value="block">Видимость блоков</option><option value="browse">Навигация</option></select></label> <button type="button" data-action="save">Сохранить черновик</button> <button type="button" data-action="publish">Опубликовать</button></div><p data-status role="status"></p><div data-field></div>';
    document.body.append(panel);
    panel.querySelector('select').addEventListener('change', event => { mode = event.target.value; clear(); });
    panel.addEventListener('click', event => { if (event.target.dataset.action) save(event.target.dataset.action); });
    document.addEventListener('click', event => {
      if (mode === 'browse' || !ready || !(event.target instanceof Element) || event.target.closest('[data-editorial-ui],[data-language-switch],.language-flag,[data-set-language],[data-action="app:language"],[data-theme-open]')) return;
      const picked = target(event.target);
      if (!picked) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      clear();
      selected = picked;
      selected.el.setAttribute('data-editorial-selected', '');
      editField();
    }, true);
    document.addEventListener('submit', event => {
      event.preventDefault();
      event.stopImmediatePropagation();
      status('Формы в предпросмотре не отправляются.');
    }, true);
    window.addEventListener('beforeunload', event => {
      if (dirty || savedForPage.size) { event.preventDefault(); event.returnValue = ''; }
    });
  }

  function refresh() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      if (page() !== current) load();
      else if (rules.length) apply();
    });
  }

  function start() {
    const css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = new URL('editorial.css?v=1', script.src).href;
    document.head.append(css);
    if (editing) showEditor();
    new MutationObserver(records => {
      if (records.some(record => !record.target.closest?.('[data-editorial-ui]'))) refresh();
    }).observe(document.body,{childList:true,subtree:true});
    new MutationObserver(() => { clear(); refresh(); }).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
    window.addEventListener('hashchange', refresh);
    load();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true});
  else start();
})();
