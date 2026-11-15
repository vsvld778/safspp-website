/* Organization workspace. Server data is never persisted in browser storage. */
(() => {
  'use strict';
  const DEMO = document.body.dataset.mode === 'demo';
  const DEMO_KEY = 'most-org-demo-v1';
  const view = document.querySelector('#org-view');
  const dialog = document.querySelector('#org-dialog');
  const picker = document.querySelector('#organization-picker');
  const feedback = document.querySelector('#org-feedback');
  const h = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clone = value => JSON.parse(JSON.stringify(value));
  const now = () => new Date().toISOString();
  const uid = () => window.crypto.randomUUID ? window.crypto.randomUUID() : '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, c => (Number(c) ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> Number(c) / 4).toString(16));
  const date = value => value && Number.isFinite(new Date(value).getTime()) ? new Date(value.length === 10 ? value + 'T12:00:00' : value).toLocaleDateString('ru-RU', {day:'numeric',month:'short',year:'numeric'}) : 'Без даты';
  const paths = {home:'M3 11 12 3l9 8M5 10v11h14V10M9 21v-7h6v7',file:'M5 3h10l4 4v14H5zM15 3v5h4M8 12h8M8 16h6',projects:'M3 7h7l2 3h9v11H3zM3 7V4h7l2 3h9v3',chat:'M4 4h16v12H9l-5 5zM8 8h8M8 12h5',services:'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',documents:'M7 3h10v15H7zM4 6v15h10M10 7h4M10 11h4',organization:'M4 21V7h9v14M13 11h7v10M2 21h20M7 10h3M7 14h3M7 18h3M16 14h2M16 18h2M6 7V3h5v4',reports:'M4 21V3M4 21h17M8 17v-5M13 17V8M18 17V4',plus:'M12 5v14M5 12h14',close:'m6 6 12 12M18 6 6 18',check:'m5 12 4 4L19 6',calendar:'M4 5h16v16H4zM7 3v4M17 3v4M4 10h16M8 14h2M14 14h2',edit:'m4 16 11-11 4 4L8 20H4zM13 7l4 4',trash:'M3 6h18M8 6V3h8v3M6 6l1 15h10l1-15M10 10v7M14 10v7',search:'M20 20l-5-5M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0',people:'M16 21v-3c0-4-12-4-12 0v3M10 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M17 4c4 0 4 6 0 6M20 21v-4c0-2-1-3-3-3',heart:'M12 21S2 15 2 8c0-6 8-7 10-1 2-6 10-5 10 1 0 7-10 13-10 13',more:'M5 12h.1M12 12h.1M19 12h.1'};
  const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.file}"/></svg>`;
  const nav = [['overview','home','Обзор'],['requests','file','Заявки'],['projects','projects','Проекты'],['messages','chat','Сообщения'],['services','services','Услуги'],['documents','documents','Документы'],['organization','organization','Организация'],['reports','reports','Отчёты']];
  const categories = {consultation:'Консультация',adaptation:'Адаптация',prearrival:'Подготовка к приезду',referral:'Совместная помощь',event:'Мероприятие',funding:'Поддержка проекта',information:'Информация',team:'Доступ команды',other:'Другой вопрос'};
  const projectStatuses = {planned:'Запланирован',active:'В работе',paused:'Приостановлен',completed:'Завершён'};
  const documentCategories = {agreement:'Соглашение',report:'Отчёт',template:'Шаблон',other:'Другой документ'};
  const roles = {manager:'Руководитель',editor:'Редактор',viewer:'Наблюдатель'};
  const languages = {ru:'Русский',ky:'Кыргызча',uz:'O‘zbekcha',tg:'Тоҷикӣ',kk:'Қазақша',en:'English',be:'Беларуская',hi:'हिन्दी'};
  const emptyData = () => ({profile:{city:'',website:'',description:'',languages:[]},projects:[],services:[],documents:[]});
  const emptyDemo = () => ({version:1,revision:0,data:emptyData(),requests:[],details:{},exampleLoaded:false});
  let session = null, workspace = {revision:0,data:emptyData()}, requests = [], demo = null, undo = null;
  let ready = false, epoch = 0, detailEpoch = 0, writing = false, opener = null, filter = '';
  const details = new Map();
  let route = location.hash.slice(1) || 'overview';
  const canWrite = () => Boolean(session?.capabilities?.canWrite && session.intakeMode !== 'disabled');
  const canManage = () => Boolean(session?.capabilities?.canManage && session.intakeMode !== 'disabled');
  const isClosed = item => ['resolved','closed'].includes(item.status);
  const button = (label, action, style = '', attrs = '') => `<button type="button" class="btn ${style}" data-action="${action}" ${attrs}>${h(label)}</button>`;
  const link = (label, hash, style = '') => `<a class="btn ${style}" href="#${hash}">${h(label)}</a>`;
  const tag = (label, style = '') => `<span class="tag ${style}">${h(label)}</span>`;
  const statusTag = item => tag(item.statusLabel || item.status, item.status === 'waiting' ? 'warm' : isClosed(item) ? 'gray' : 'blue');
  const projectName = id => !id ? 'Без проекта' : workspace.data.projects.find(p => p.id === id)?.title || 'Архивный проект';
  const heading = (title, subtitle = '', action = '') => `<div class="page-heading"><div><h1>${h(title)}</h1>${subtitle ? `<p class="subtitle">${h(subtitle)}</p>` : ''}</div>${action}</div>`;
  const empty = (title, text, ico = 'file', action = '') => `<section class="empty"><span class="icon-box">${icon(ico)}</span><h2>${h(title)}</h2><p>${h(text)}</p>${action}</section>`;
  function notify(message, error = false, extra = '') { feedback.innerHTML = `<div class="notice ${error ? 'error' : ''} feedback" role="${error ? 'alert' : 'status'}"><span>${h(message)}</span>${extra}</div>`; }
  function secureURL(value) { try { const u = new URL(String(value)); return u.protocol === 'https:' && !u.username && !u.password ? u.href : ''; } catch (_) { return ''; } }
  function apiURL(path, organization = session?.organization?.id) { const url = new URL('/partners/api/' + path, location.origin); if (organization) url.searchParams.set('organization', organization); return url; }
  async function api(path, options = {}, organization) {
    const response = await fetch(apiURL(path, organization), {credentials:'same-origin',cache:'no-store',...options,headers:{Accept:'application/json',...(options.body ? {'Content-Type':'application/json','X-CSRFToken':session?.csrfToken || ''} : {}),...options.headers}});
    let data; try { data = await response.json(); } catch (_) { const error=new Error(response.status===403?'Срок действия формы истёк или доступ изменился. Обновите кабинет и повторите.':'Сервер вернул неожиданный ответ. Попробуйте ещё раз.'); error.status=response.status; throw error; }
    if (!response.ok) { const error = new Error(data.message || ({401:'Сессия завершилась. Войдите снова.',403:'Доступ к организации изменился.',409:'Рабочее пространство изменено в другой вкладке или другим участником.',429:'Слишком много изменений подряд. Подождите немного и повторите.'}[response.status]) || 'Не удалось сохранить. Проверьте данные и повторите.'); error.status=response.status; error.fields=data.fields; throw error; }
    return data;
  }
  function validateWorkspace(value) { return value && Number.isInteger(value.revision) && value.data?.profile && ['projects','services','documents'].every(k => Array.isArray(value.data[k])); }
  function persistDemo(next) { localStorage.setItem(DEMO_KEY, JSON.stringify(next)); demo = next; workspace = {revision:next.revision,data:next.data}; requests=next.requests; details.clear(); Object.entries(next.details).forEach(([id,item]) => details.set(id,item)); }
  function demoSession() { return {user:{name:'Демо-пользователь'},organizations:[{id:'demo',name:'Демонстрационная организация',kind:'ngo'}],organization:{id:'demo',name:'Демонстрационная организация',kind:'ngo'},membership:{role:'manager'},members:[{name:'Демо-пользователь',role:'manager'}],capabilities:{canWrite:true,canManage:true},intakeMode:'demo',cases:[]}; }
  async function boot(organization) {
    const run = ++epoch; detailEpoch++; ready=false; details.clear(); feedback.innerHTML=''; picker.disabled=true;
    view.setAttribute('aria-busy','true'); view.innerHTML='<div class="loading"><span class="loading-dot" aria-hidden="true"></span><h1>Открываем ваше пространство</h1><p>Проверяем доступ к организации.</p></div>';
    try {
      if (DEMO) {
        let saved=null; try { saved=JSON.parse(localStorage.getItem(DEMO_KEY)); } catch (error) { if (error.name !== 'SyntaxError') throw new Error('Хранилище браузера недоступно. Для демо разрешите локальное сохранение.'); }
        demo = saved?.version === 1 && validateWorkspace(saved) && Array.isArray(saved.requests) && saved.details && typeof saved.details === 'object' ? saved : emptyDemo();
        session=demoSession(); workspace={revision:demo.revision,data:demo.data}; requests=demo.requests; Object.entries(demo.details).forEach(([id,item]) => details.set(id,item));
      } else {
        const selected=organization || new URL(location.href).searchParams.get('organization');
        const nextSession=await api('session/',{},selected);
        if (run !== epoch) return;
        session=nextSession;
        if (!session.organization || !session.membership) { throw Object.assign(new Error('Координатор должен подтвердить организацию и добавить вас в её команду.'),{status:403}); }
        const [nextWorkspace, nextRequests]=await Promise.all([api('workspace/'),api('requests/')]);
        if (run !== epoch) return;
        if (!validateWorkspace(nextWorkspace) || !Array.isArray(nextRequests.requests)) throw new Error('Не удалось прочитать рабочее пространство. Обновите страницу.');
        workspace=nextWorkspace; requests=nextRequests.requests;
      }
      if (run !== epoch) return;
      ready=true; updateShell(); render();
    } catch (error) {
      if (run !== epoch) return;
      view.removeAttribute('aria-busy');
      document.querySelector('#org-banner').innerHTML='';
      picker.innerHTML='<option>Доступ не подключён</option>';
      const denied=error.status===403, loggedOut=error.status===401;
      view.innerHTML=empty(loggedOut ? 'Войдите в кабинет' : denied ? 'Доступ организации ещё не подключён' : 'Не удалось открыть кабинет', error.message, 'organization', loggedOut ? '<a class="btn" href="/login/?next=/partners/">Войти</a>' : button('Проверить ещё раз','reload'));
      renderNav();
    }
  }
  function updateShell() {
    picker.innerHTML=session.organizations.map(org => `<option value="${h(org.id)}" ${String(org.id)===String(session.organization.id)?'selected':''}>${h(org.name)}</option>`).join('');
    picker.disabled=writing || session.organizations.length < 2;
    const avatar=document.querySelector('#org-avatar'); avatar.textContent=(session.user?.name || session.organization.name || 'М').slice(0,1); avatar.title=session.user?.name || '';
    let text=DEMO ? 'Демонстрационный режим · данные остаются в браузере' : session.intakeMode==='test' ? 'Тестовый режим · используйте только вымышленные данные' : session.intakeMode==='disabled' ? 'Рабочее пространство · изменения временно отключены' : 'Рабочее пространство организации';
    if (!DEMO && session.membership.role==='viewer') text+=' · доступ для просмотра';
    document.querySelector('#org-banner').innerHTML=`<div class="mode-banner ${session.intakeMode==='test'?'test':''}"><span>${h(text)}</span>${DEMO ? '<button class="text-button" type="button" data-action="demo-reset">Сбросить демо</button>' : `<span>${h(roles[session.membership.role] || session.membership.role)}</span>`}</div>`;
    renderNav();
  }
  function renderNav() {
    const active=route.startsWith('request/')?'requests':route;
    document.querySelector('#org-navigation').innerHTML=nav.map(([id,ico,label]) => `<a class="nav-item" href="#${id}" ${active===id?'aria-current="page"':''}>${icon(ico)}<span>${label}</span>${id==='requests'&&ready&&requests.some(r=>r.status==='waiting')?`<span class="nav-count">${requests.filter(r=>r.status==='waiting').length}</span>`:''}</a>`).join('');
    const mobile=[nav[0],nav[1],nav[2],nav[3],['more','more','Ещё']];
    document.querySelector('#org-mobile-nav').innerHTML=mobile.map(([id,ico,label]) => `<a href="#${id}" ${(active===id || id==='more'&&['services','documents','organization','reports'].includes(active))?'aria-current="page"':''}>${icon(ico)}<span>${label}</span></a>`).join('');
  }
  function requestRow(item) { return `<a class="record-row" href="#request/${h(item.id)}"><span class="icon-box blue">${icon('file')}</span><div class="row-copy"><strong>${h(item.title)}</strong><p>${h(item.reference)} · ${h(categories[item.category] || item.category)}</p><div class="record-meta"><span>${h(date(item.updatedAt))}</span>${item.isTest?'<span>Тестовая запись</span>':''}${DEMO?'<span>Локальное демо</span>':''}</div></div>${statusTag(item)}</a>`; }
  function assignedCases(all = false) {
    const cases=!['employer','staffing'].includes(session.organization.kind) && Array.isArray(session.cases) ? session.cases : [];
    if (!cases.length) return '';
    return `<div class="section-heading"><h2>Назначенные обращения</h2>${!all&&cases.length>3?'<a href="#requests">Все обращения</a>':''}</div><p class="small muted assigned-note">Координатор предоставил организации доступ к этим задачам.</p><div class="record-list">${(all?cases:cases.slice(0,3)).map(item => {const url=/^\/partners\/cases\/[a-f0-9-]+\/$/i.test(item.url||'')?item.url:'';return `<${url?'a':'div'} class="record-row" ${url?`href="${h(url)}"`:''}><span class="icon-box">${icon('people')}</span><div class="row-copy"><strong>${h(item.reference)}</strong><p>${h(item.summary)}</p>${item.nextStep?`<p>${h(item.nextStep)}</p>`:''}</div>${statusTag(item)}</${url?'a':'div'}>`;}).join('')}</div>`;
  }
  function overview() {
    const active=workspace.data.projects.filter(p=>p.status==='active'), open=requests.filter(r=>!isClosed(r)), waiting=requests.filter(r=>r.status==='waiting');
    const deadlines=workspace.data.projects.filter(p=>p.deadline && p.status!=='completed').sort((a,b)=>a.deadline.localeCompare(b.deadline)).slice(0,4);
    const recent=[...requests].sort((a,b)=>(b.updatedAt||'').localeCompare(a.updatedAt||'')).slice(0,3);
    return `${heading('Вместе можно больше.','Ваши проекты, поддержка фонда и понятный следующий шаг.', '<span class="edition">ПРОСТРАНСТВО<br><b>организации</b></span>')}<div class="home-layout"><div class="main-column"><section class="hero"><div class="hero-kicker">МОСТ К ОБЩЕМУ РЕЗУЛЬТАТУ</div><h2>Работать вместе.<br><em>Помогать точнее.</em></h2><p>Расскажите, какая поддержка нужна вашей организации. Сохраним договорённости и продолжим разговор здесь.</p>${canWrite()?button(DEMO?'Создать демо-заявку':'Создать заявку','request-new'):link('Посмотреть заявки','requests')}</section><div class="quick-grid"><a class="quick-card" href="#projects"><span class="icon-box">${icon('projects')}</span><div><strong>Ваши проекты</strong><p>Задачи и сроки, которые объединяют команду.</p></div></a><a class="quick-card" href="#services"><span class="icon-box gold">${icon('services')}</span><div><strong>Возможности организации</strong><p>Соберите каталог услуг для совместной работы.</p></div></a></div><div class="stats"><div class="stat"><strong>${active.length}</strong><p>Проектов в работе</p></div><div class="stat"><strong>${open.length}</strong><p>Открытых заявок</p></div><div class="stat"><strong>${waiting.length}</strong><p>Ждут вашего ответа</p></div></div><div class="section-heading"><h2>Заявки в фонд</h2><a href="#requests">Все заявки</a></div>${recent.length?`<div class="record-list">${recent.map(requestRow).join('')}</div>`:empty('Начните с одного вопроса','Опишите, какая поддержка нужна вашей организации. Заявка и ответы останутся в этом кабинете.','chat',canWrite()?button(DEMO?'Сохранить в демо':'Создать заявку','request-new'): '')}${assignedCases()}</div><aside class="right-column"><section class="panel"><div class="card-head"><h2>Ближайшие шаги</h2>${icon('calendar')}</div>${deadlines.length?`<div class="next-list">${deadlines.map(p=>`<a class="next-item" href="#projects">${icon('calendar')}<div><strong>${h(p.title)}</strong><p>${h(date(p.deadline))}</p></div></a>`).join('')}</div>`:'<p class="muted">Добавьте проект и плановую дату. Здесь появятся ближайшие сроки вашей команды.</p>'}<div class="space-top">${link('Открыть проекты','projects','light full')}</div></section><section class="side-help-card"><span class="icon-box">${icon('chat')}</span><h2 class="space-top">Разговор<br>продолжается.</h2><p>Ответы фонда и уточнения команды сохраняются внутри каждой заявки.</p>${link('Перейти к сообщениям','messages','light full')}</section>${DEMO&&!demo.exampleLoaded?`<section class="panel"><h2>Посмотреть в действии</h2><p class="muted">Добавьте два учебных проекта и три вымышленные заявки. Они никуда не отправляются.</p><div class="space-top">${button('Показать пример','demo-example','light full')}</div></section>`:''}</aside></div>`;
  }
  function requestList(messages = false) {
    const filtered=requests.filter(r=>(r.title+' '+r.reference+' '+(categories[r.category]||'')).toLocaleLowerCase().includes(filter.toLocaleLowerCase()));
    return heading(messages?'Сообщения':'Заявки в фонд',messages?'Откройте заявку, чтобы прочитать ответы и продолжить разговор.':'Вопросы организации, решения фонда и следующий шаг.', !messages&&canWrite()?button(DEMO?'Создать демо-заявку':'Создать заявку','request-new'):'')+`<div class="toolbar"><label class="search">${icon('search')}<input id="request-search" type="search" value="${h(filter)}" placeholder="Найти заявку" aria-label="Найти заявку"></label>${button('Обновить','reload','light')}</div><div id="request-results">${filtered.length?`<div class="record-list">${filtered.map(requestRow).join('')}</div>`:empty(requests.length?'Ничего не найдено':messages?'Переписки пока нет':'Заявок пока нет',requests.length?'Попробуйте другое слово или номер заявки.':messages?'Здесь появятся ответы фонда по заявкам вашей организации.':'Опишите, какая поддержка нужна вашей организации.','chat')}</div>${!messages?assignedCases(true):''}`;
  }
  function projectsPage() {
    const items=workspace.data.projects;
    return heading('Проекты','Общие задачи команды. Плановые сроки и текущий этап.',canWrite()?button('Добавить проект','project-new'):'')+(items.length?`<div class="cards">${items.map(p=>`<article class="panel"><div class="card-head"><span class="icon-box">${icon('projects')}</span>${tag(projectStatuses[p.status]||p.status,p.status==='completed'?'gray':'blue')}</div><h2 class="record-title">${h(p.title)}</h2><p class="record-description">${h(p.description || 'Описание пока не добавлено.')}</p><div class="record-meta">${icon('calendar')}<span>${h(date(p.deadline))}</span></div><div class="record-actions">${canWrite()?button('Изменить','project-edit','light',`data-id="${h(p.id)}"`)+button('Создать заявку','project-request','',`data-id="${h(p.id)}"`):''}</div></article>`).join('')}</div>`:empty('У каждого дела есть первый шаг','Добавьте название проекта, ближайшую цель и плановую дату.','projects',canWrite()?button('Добавить проект','project-new') : ''));
  }
  function servicesPage() {
    return heading('Услуги организации','Внутренний каталог для вашей команды. Записи не публикуются на сайте автоматически.',canWrite()?button('Добавить услугу','service-new'):'')+(workspace.data.services.length?`<div class="cards">${workspace.data.services.map(s=>`<article class="panel"><div class="card-head"><span class="icon-box gold">${icon('services')}</span>${tag(s.available?'Доступна':'Приостановлена',s.available?'':'gray')}</div><h2 class="record-title">${h(s.title)}</h2><div class="record-meta">${h(categories[s.category]||s.category)}</div><p class="record-description">${h(s.description)}</p>${canWrite()?`<div class="record-actions">${button('Изменить','service-edit','light',`data-id="${h(s.id)}"`)}${button('Обсудить с фондом','service-request','',`data-id="${h(s.id)}"`)}</div>`:''}</article>`).join('')}</div>`:empty('Что может ваша команда?','Опишите услуги и направления, в которых организация готова участвовать.','services',canWrite()?button('Добавить услугу','service-new'):''));
  }
  function documentsPage() {
    return heading('Документы','Каталог ссылок на соглашения, отчёты и шаблоны. Файлы в кабинет не загружаются.',canWrite()?button('Добавить ссылку','document-new'):'')+(workspace.data.documents.length?`<div class="cards">${workspace.data.documents.map(d=>`<article class="panel"><div class="card-head"><span class="icon-box blue">${icon('documents')}</span>${tag(documentCategories[d.category]||d.category,'gray')}</div><h2 class="record-title">${h(d.title)}</h2><p class="record-description">${h(d.note)}</p><div class="record-meta">${h(projectName(d.projectId))}</div><div class="record-actions">${secureURL(d.url)?`<a class="btn" href="${h(secureURL(d.url))}" target="_blank" rel="noopener noreferrer">Открыть документ</a>`:'<span class="small muted">Проверьте адрес документа.</span>'}${canWrite()?button('Изменить','document-edit','light',`data-id="${h(d.id)}"`):''}</div></article>`).join('')}</div>`:empty('Важное — в одном месте','Добавьте HTTPS-ссылку на документ. Проверьте права доступа в сервисе, где хранится файл.','documents',canWrite()?button('Добавить ссылку','document-new'):''));
  }
  function organizationPage() {
    const p=workspace.data.profile;
    return heading('Организация','Профиль команды и действующий доступ к общему пространству.')+`<div class="cards"><section class="panel"><div class="card-head"><h2>${h(session.organization.name)}</h2><span class="icon-box">${icon('organization')}</span></div>${canManage()?`<form data-form="profile"><div class="form-error" role="alert"></div>${field('Город','city',p.city,{max:120})}${field('Сайт организации','website',p.website,{type:'url',max:500,hint:'Полный адрес, начинающийся с https://.'})}${field('О вашей работе','description',p.description,{area:true,max:3000})}<fieldset class="language-fields"><legend>Языки общения</legend>${Object.entries(languages).map(([value,label])=>`<label class="check-field"><input type="checkbox" name="languages" value="${value}" ${(p.languages||[]).includes(value)?'checked':''}>${label}</label>`).join('')}</fieldset>${writeConfirmation()}<button class="btn" type="submit">Сохранить профиль</button></form>`:`<dl class="facts"><div><dt>Город</dt><dd>${h(p.city||'Не указан')}</dd></div><div><dt>Сайт</dt><dd>${secureURL(p.website)?`<a href="${h(secureURL(p.website))}" target="_blank" rel="noopener noreferrer">${h(p.website)}</a>`:'Не указан'}</dd></div><div><dt>О работе</dt><dd>${h(p.description||'Описание пока не добавлено')}</dd></div><div><dt>Языки</dt><dd>${h((p.languages||[]).map(k=>languages[k]||k).join(', ')||'Не указаны')}</dd></div></dl><p class="small muted space-top">Профиль изменяет руководитель организации.</p>`}</section><section class="panel"><h2>Участники команды</h2><p class="muted">Доступ подтверждает администратор фонда. Заявка на изменение сама по себе не добавляет участников и не меняет роли.</p><div class="space-top">${(session.members||[]).map(m=>`<div class="team-row"><span class="avatar">${h(m.name?.slice(0,1)||'М')}</span><strong>${h(m.name)}</strong>${tag(roles[m.role]||m.role,'gray')}</div>`).join('')||'<p class="muted">Список участников пока недоступен.</p>'}</div>${canWrite()?`<div class="space-top">${button('Запросить изменение доступа','team-request','light full')}</div>`:''}<div class="notice space-top"><strong>Ваша роль: ${h(roles[session.membership.role]||session.membership.role)}</strong>${session.membership.role==='viewer'?'Можно просматривать записи и переписку.':session.membership.role==='editor'?'Можно вести проекты, услуги, документы и переписку. Профиль организации меняет руководитель.':'Можно вести рабочее пространство и обновлять профиль организации.'}</div></section></div>`;
  }
  function reportsPage() {
    return heading('Отчёты','Сводка по загруженным записям организации. Без оценок и показателей, которых нет в данных.',button('Скачать CSV','report-export'))+`<div class="cards"><section class="panel"><h2>Заявки в фонд</h2><table class="report-table"><thead><tr><th>Показатель</th><th>Количество</th></tr></thead><tbody><tr><td>Загружено заявок</td><td>${requests.length}</td></tr><tr><td>Открытые</td><td>${requests.filter(r=>!isClosed(r)).length}</td></tr><tr><td>Ждут ответа организации</td><td>${requests.filter(r=>r.status==='waiting').length}</td></tr><tr><td>Завершённые</td><td>${requests.filter(isClosed).length}</td></tr></tbody></table></section><section class="panel"><h2>Работа команды</h2><table class="report-table"><thead><tr><th>Показатель</th><th>Количество</th></tr></thead><tbody>${Object.entries(projectStatuses).map(([key,label])=>`<tr><td>Проекты: ${label.toLocaleLowerCase()}</td><td>${workspace.data.projects.filter(p=>p.status===key).length}</td></tr>`).join('')}<tr><td>Услуги в каталоге</td><td>${workspace.data.services.length}</td></tr><tr><td>Ссылки на документы</td><td>${workspace.data.documents.length}</td></tr></tbody></table></section></div><div class="notice space-top">CSV содержит названия, номера, этапы и даты загруженных проектов и заявок. Тексты переписки и документы в выгрузку не включаются.${DEMO?' Все данные этого отчёта относятся к демонстрации.':''}</div>`;
  }
  function render() {
    if (!ready) return;
    renderNav(); view.removeAttribute('aria-busy');
    if (route.startsWith('request/')) { renderRequest(route.slice(8)); return; }
    const pages={overview,requests:()=>requestList(),projects:projectsPage,messages:()=>requestList(true),services:servicesPage,documents:documentsPage,organization:organizationPage,reports:reportsPage,more:()=>heading('Все разделы','Рабочие инструменты вашей организации.')+`<div class="menu-grid">${nav.map(([id,ico,title])=>`<a class="quick-card" href="#${id}"><span class="icon-box">${icon(ico)}</span><strong>${title}</strong></a>`).join('')}</div>`};
    if (!Object.hasOwn(pages,route)) route='overview';
    document.title=(nav.find(n=>n[0]===route)?.[2]||'Кабинет организации')+' — Мост поддержки';
    view.innerHTML=pages[route]();
  }
  async function renderRequest(id) {
    const run=++detailEpoch;
    if (!/^[a-z0-9-]+$/i.test(id)) { view.innerHTML=empty('Заявка не найдена','Откройте заявку из списка.','file',link('К заявкам','requests')); return; }
    view.setAttribute('aria-busy','true'); view.innerHTML='<div class="loading"><h1>Открываем заявку</h1></div>';
    try {
      const detail=DEMO?details.get(id):await api('requests/'+encodeURIComponent(id)+'/');
      if (run!==detailEpoch || route!=='request/'+id) return;
      if (!detail?.request || !Array.isArray(detail.messages)) throw new Error('Заявка не найдена или доступ к ней изменился.');
      details.set(id,detail); const r=detail.request;
      document.title=r.reference+' — Мост поддержки';
      view.innerHTML=`<div class="toolbar">${link('К заявкам','requests','light')}</div>${heading(r.title,r.reference+(DEMO?' · локальное демо':''))}<div class="detail-layout"><div><section class="panel"><div class="card-head"><h2>Вопрос организации</h2>${statusTag(r)}</div><p class="detail-body">${h(r.body)}</p></section><div class="section-heading"><h2>Переписка по заявке</h2></div>${detail.messages.length?`<div class="thread">${detail.messages.map(m=>`<article class="message ${m.isOwn?'mine':''}"><div class="message-header"><strong>${h(m.authorName)}${m.isStaff?' · фонд':''}</strong><time datetime="${h(m.createdAt)}">${h(date(m.createdAt))}</time></div><p>${h(m.body)}</p></article>`).join('')}</div>`:'<div class="notice">Сообщений пока нет. Дополнения и ответы появятся здесь.</div>'}${DEMO?'<div class="notice warm">Демонстрация: сообщения остаются в браузере. Сотрудники фонда их не получают.</div>':''}${canWrite()&&!isClosed(r)?`<section class="panel"><h2>Добавить сообщение</h2><form data-form="message" data-id="${h(id)}" class="space-top"><div class="form-error" role="alert"></div>${field('Ваше сообщение','body','',{area:true,required:true,max:4000})}${writeConfirmation()}<button class="btn" type="submit">${DEMO?'Сохранить в демо':'Отправить сообщение'}</button></form></section>`:isClosed(r)?'<div class="notice">Заявка завершена. История переписки сохранена.</div>':'<div class="notice">У вас доступ для просмотра переписки.</div>'}</div><aside class="panel"><dl class="facts"><div><dt>Категория</dt><dd>${h(categories[r.category]||r.category)}</dd></div><div><dt>Проект</dt><dd>${h(projectName(r.projectId))}</dd></div><div><dt>Создана</dt><dd>${h(date(r.createdAt))}</dd></div><div><dt>Обновлена</dt><dd>${h(date(r.updatedAt))}</dd></div></dl><p class="small muted space-top">${DEMO?'Статусы примеров вымышлены.':'Этап заявки меняет сотрудник фонда.'}</p></aside></div>`;
    } catch (error) { if(run===detailEpoch && route==='request/'+id)view.innerHTML=empty('Не удалось открыть заявку',error.message,'file',button('Повторить','request-retry','',`data-id="${h(id)}"`)); }
    finally { if(run===detailEpoch && route==='request/'+id)view.removeAttribute('aria-busy'); }
  }
  function field(label, name, value = '', opts = {}) {
    const attrs=`name="${name}" ${opts.required?'required':''} ${opts.max?`maxlength="${opts.max}"`:''}`;
    return `<label class="field">${h(label)}${opts.area?`<textarea ${attrs} rows="4">${h(value)}</textarea>`:`<input ${attrs} type="${opts.type||'text'}" value="${h(value)}">`}${opts.hint?`<small>${h(opts.hint)}</small>`:''}</label>`;
  }
  const select = (label,name,options,current='',required=false) => `<label class="field">${h(label)}<select name="${name}" ${required?'required':''}>${Object.entries(options).map(([key,text])=>`<option value="${h(key)}" ${key===current?'selected':''}>${h(text)}</option>`).join('')}</select></label>`;
  const projectOptions = () => Object.fromEntries([['','Без проекта'],...workspace.data.projects.map(p=>[p.id,p.title])]);
  function writeConfirmation(privacy = false) {
    if (DEMO) return '<p class="small muted space-top">Сохранится только в демонстрации этого браузера. Фонд эти данные не получит.</p>';
    if (session.intakeMode==='test') return '<label class="check-field"><input type="checkbox" name="testDataOnly" required>Я использую только вымышленные данные и понимаю, что это тестовая запись.</label>';
    return privacy?`<label class="check-field"><input type="checkbox" name="privacyConsent" required><span>Согласен с условиями обработки данных для рассмотрения этой заявки${secureURL(session.policyUrl)?` — <a href="${h(secureURL(session.policyUrl))}" target="_blank" rel="noopener noreferrer">прочитать условия</a>`:''}.</span></label>`:'';
  }
  function confirmations(data) { return !DEMO&&session.intakeMode==='test'?{testDataOnly:data.has('testDataOnly')}:!DEMO&&data.has('privacyConsent')?{privacyConsent:true}:{}; }
  function openModal(title,body,subtitle='') {
    if (!dialog.open) opener=document.activeElement;
    dialog.innerHTML=`<div class="dialog-head"><div><h2 id="org-dialog-title">${h(title)}</h2>${subtitle?`<p>${h(subtitle)}</p>`:''}</div><button type="button" class="close-dialog" data-action="close" aria-label="Закрыть">${icon('close')}</button></div><div class="dialog-body">${body}</div>`;
    if (!dialog.open) dialog.showModal();
    const first=dialog.querySelector('input:not([type=hidden]),textarea,select'); if(first)first.focus({preventScroll:true});
  }
  function closeModal() { if(dialog.open)dialog.close(); }
  function editor(kind,id) {
    if (!canWrite()) return;
    const keys={project:'projects',service:'services',document:'documents'}, list=workspace.data[keys[kind]], item=list.find(x=>x.id===id), v=item||{};
    let fields=field('Название','title',v.title,{required:true,max:180});
    if(kind==='project')fields+=field('Цель и ближайшие шаги','description',v.description,{area:true,max:3000})+`<div class="form-grid">${select('Этап проекта','status',projectStatuses,v.status||'planned')}${field('Плановая дата','deadline',v.deadline,{type:'date'})}</div>`;
    if(kind==='service')fields+=select('Направление','category',categories,v.category||'consultation')+field('Что предлагает организация','description',v.description,{area:true,max:2000})+`<label class="check-field"><input type="checkbox" name="available" ${!item||v.available?'checked':''}>Услуга доступна для совместной работы</label><p class="small muted">Запись остаётся во внутреннем каталоге организации.</p>`;
    if(kind==='document')fields+=field('Ссылка на документ','url',v.url,{type:'url',required:true,max:500,hint:'Только https://. Доступ к файлу регулируется сервисом, где он хранится.'})+`<div class="form-grid">${select('Тип документа','category',documentCategories,v.category||'other')}${select('Проект','projectId',projectOptions(),v.projectId||'')}</div>`+field('Примечание','note',v.note,{area:true,max:2000});
    const titles={project:'проект',service:'услугу',document:'ссылку на документ'};
    openModal((item?'Изменить ':'Добавить ')+titles[kind],`<form data-form="${kind}" data-id="${h(id||'')}"><div class="form-error" role="alert"></div>${fields}${writeConfirmation()}<div class="form-actions">${item?button('Удалить',kind+'-delete','light',`data-id="${h(id)}"`):''}<button class="btn" type="submit">Сохранить</button></div></form>`);
  }
  function newRequest(preset = {}) {
    if(!canWrite())return;
    openModal(preset.category==='team'?'Запросить изменение доступа':DEMO?'Создать демо-заявку':'Новая заявка в фонд',`<form data-form="request"><div class="form-error" role="alert"></div>${field('Коротко о вопросе','title',preset.title,{required:true,max:180})}${select('Категория','category',categories,preset.category||'consultation')}${select('Проект','projectId',projectOptions(),preset.projectId||'')}${field('Что требуется вашей организации','body',preset.body,{area:true,required:true,max:6000,hint:'Опишите цель, важные обстоятельства и удобный следующий шаг. Не добавляйте паспортные номера и банковские реквизиты.'})}${writeConfirmation(true)}<div class="form-actions"><button class="btn" type="submit">${DEMO?'Сохранить в демо':'Отправить заявку'}</button></div></form>`,DEMO?'Учебная заявка сохранится только в этом браузере.':preset.category==='team'?'Опишите, кому и какой доступ нужен. Изменения внесёт администратор после проверки.':'Заявку увидят участники вашей организации и сотрудники фонда.');
  }
  async function saveWorkspace(next, confirmation) {
    if(DEMO){const update=clone(demo);update.data=next;update.revision++;persistDemo(update);return;}
    const result=await api('workspace/',{method:'PUT',body:JSON.stringify({revision:workspace.revision,data:next,...confirmation})});
    if (!Number.isInteger(result.revision)) throw new Error('Не удалось подтвердить сохранение. Обновите рабочее пространство.');
    workspace={revision:result.revision,data:result.data||next,updatedAt:result.updatedAt};
  }
  function formError(form,error) {
    const target=form.querySelector('.form-error');
    const fieldText=error.fields ? Object.values(error.fields).flat().map(String).join('\n') : '';
    target.className='form-error notice error'; target.innerHTML=h(error.message)+(fieldText?'<br>'+h(fieldText):'')+(error.status===409?'<p>Ваш ввод остаётся в форме. Скопируйте нужный текст перед обновлением.</p>'+button('Загрузить актуальные данные','reload','light'):error.status===401?'<p><a href="/login/?next=/partners/">Войти снова</a></p>':''); target.tabIndex=-1;target.focus();
  }
  const str=(data,key,max)=>String(data.get(key)||'').trim().slice(0,max);
  async function submit(form,data) {
    const name=form.dataset.form, id=form.dataset.id;
    if(name==='demo-reset'){undo=clone(demo);persistDemo(emptyDemo());closeModal();route='overview';location.hash='overview';render();notify('Демонстрация очищена. Сброс можно отменить до перезагрузки страницы.',false,button('Отменить сброс','demo-undo','light'));return;}
    if(!canWrite())throw new Error('У вас нет доступа к изменению записей.');
    const confirm=confirmations(data);
    if(!DEMO&&session.intakeMode==='test'&&!confirm.testDataOnly)throw new Error('Подтвердите использование только вымышленных данных.');
    if(name==='request') {
      const payload={title:str(data,'title',180),category:str(data,'category',30),body:str(data,'body',6000),projectId:str(data,'projectId',36),...confirm};
      let result;
      if(DEMO){const next=clone(demo),time=now(),rid=uid(),record={id:rid,reference:'DEMO-'+String(next.requests.length+1).padStart(3,'0'),title:payload.title,category:payload.category,body:payload.body,projectId:payload.projectId,status:'new',statusLabel:'Сохранена в демо',isTest:true,createdAt:time,updatedAt:time};result={request:record,messages:[]};next.requests.unshift(record);next.details[rid]=result;persistDemo(next);}else result=await api('requests/',{method:'POST',body:JSON.stringify(payload)});
      if(!result.request?.id)throw new Error('Не удалось получить номер заявки. Обновите список перед повторной отправкой.');
      if(!DEMO){requests=[result.request,...requests.filter(r=>r.id!==result.request.id)];details.set(result.request.id,result);}
      closeModal();go('request/'+result.request.id);notify(DEMO?'Заявка сохранена в демо. В фонд она не отправлена.':'Заявка создана. Номер: '+result.request.reference);return;
    }
    if(name==='message'){
      const body=str(data,'body',4000);let result;
      if(DEMO){const next=clone(demo),detail=next.details[id];if(!detail)throw new Error('Заявка не найдена.');detail.messages.push({id:uid(),body,authorName:'Вы · демонстрация',isOwn:true,isStaff:false,createdAt:now()});detail.request.updatedAt=now();const record=next.requests.find(r=>r.id===id);if(record)record.updatedAt=detail.request.updatedAt;persistDemo(next);result=detail;}else result=await api('requests/'+encodeURIComponent(id)+'/',{method:'POST',body:JSON.stringify({body,...confirm})});
      details.set(id,result);if(!DEMO&&result.request){requests=requests.map(r=>r.id===id?result.request:r);}render();notify(DEMO?'Сообщение сохранено только в демо.':'Сообщение отправлено.');return;
    }
    const next=clone(workspace.data);
    if(name==='profile') {
      if(!canManage())throw new Error('Профиль меняет руководитель организации.');
      const website=str(data,'website',500);if(website&&!secureURL(website))throw new Error('Укажите адрес сайта, начинающийся с https://.');
      next.profile={city:str(data,'city',120),website,description:str(data,'description',3000),languages:data.getAll('languages').filter(k=>Object.hasOwn(languages,k))};
    } else if(name==='delete') {
      const key=form.dataset.collection;if(!['projects','services','documents'].includes(key))throw new Error('Неизвестный раздел.');
      next[key]=next[key].filter(item=>item.id!==id);
      if(key==='projects')next.documents=next.documents.map(d=>d.projectId===id?{...d,projectId:''}:d);
    } else {
      const keys={project:'projects',service:'services',document:'documents'},key=keys[name];if(!key)throw new Error('Неизвестное действие.');
      const item={id:id||uid(),title:str(data,'title',180)};
      if(name==='project')Object.assign(item,{description:str(data,'description',3000),status:str(data,'status',20),deadline:str(data,'deadline',10)});
      if(name==='service')Object.assign(item,{description:str(data,'description',2000),category:str(data,'category',30),available:data.has('available')});
      if(name==='document'){const url=str(data,'url',500);if(!secureURL(url))throw new Error('Нужна полная HTTPS-ссылка без логина и пароля в адресе.');Object.assign(item,{url,category:str(data,'category',20),note:str(data,'note',2000),projectId:str(data,'projectId',36)});}
      if(id)next[key]=next[key].map(row=>row.id===id?item:row);else{if(next[key].length>=100)throw new Error('В этом разделе уже 100 записей. Удалите ненужные перед добавлением.');next[key].unshift(item);}
    }
    await saveWorkspace(next,confirm);closeModal();render();notify(name==='delete'?'Запись удалена.':DEMO?'Изменения сохранены в демо этого браузера.':'Изменения сохранены.');
  }
  function confirmDelete(kind,id) {
    const collection={project:'projects',service:'services',document:'documents'}[kind],item=workspace.data[collection].find(r=>r.id===id);if(!item)return;
    openModal('Удалить запись?',`<form data-form="delete" data-collection="${collection}" data-id="${h(id)}"><div class="form-error" role="alert"></div><p>${h(item.title)}</p><p class="small muted space-top">${kind==='project'?'Ссылки документов на проект будут сняты. Созданные заявки сохранятся.':'Удалится запись из кабинета. Исходный документ или внешний сервис не изменится.'}</p>${writeConfirmation()}<div class="form-actions">${button('Оставить','close','light')}<button type="submit" class="btn danger">Удалить</button></div></form>`);
  }
  function seedExample() {
    if(!DEMO||demo.exampleLoaded)return;
    const next=clone(demo),time=now(),p1=uid(),p2=uid();
    const day=offset=>{const d=new Date();d.setDate(d.getDate()+offset);return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');};
    next.data.projects.push({id:p1,title:'Пример: знакомство с городом',description:'Учебный проект. Встреча для новых жителей: полезные адреса и подготовка к первым обращениям.',status:'active',deadline:day(14)},{id:p2,title:'Пример: встреча с работодателями',description:'Вымышленный пример совместного мероприятия. Согласовать темы и формат встречи.',status:'planned',deadline:day(30)});
    [['Пример: материалы для вводной встречи','information','in_progress','Пример: в работе',p1],['Пример: согласование формата встречи','event','waiting','Пример: ждёт уточнения',p2],['Пример: консультация по подготовке проекта','consultation','resolved','Пример: завершена',p1]].forEach(([title,category,status,statusLabel,projectId],index)=>{const id=uid(),r={id,reference:'DEMO-EX-'+(index+1),title,category,status,statusLabel,projectId,isTest:true,body:'Синтетический пример для знакомства с кабинетом. Реальной заявки, организации или ответа фонда здесь нет.',createdAt:time,updatedAt:time};next.requests.push(r);next.details[id]={request:r,messages:index===1?[{id:uid(),body:'Пример сообщения: уточните предполагаемую дату и количество участников. Это вымышленный текст для демонстрации переписки.',authorName:'Учебный координатор · пример',isStaff:false,isOwn:false,createdAt:time}]:[]};});
    next.exampleLoaded=true;next.revision++;persistDemo(next);render();notify('Добавлены два учебных проекта и три вымышленные заявки. Данные никуда не отправлены.');
  }
  function exportReport() {
    const rows=[['Тип','Номер','Название','Этап','Проект','Плановая дата','Обновлено'],...requests.map(r=>['Заявка',r.reference,r.title,r.statusLabel||r.status,projectName(r.projectId),'',r.updatedAt]),...workspace.data.projects.map(p=>['Проект',p.id,p.title,projectStatuses[p.status]||p.status,'',p.deadline,''])];
    const cell=value=>{let text=String(value??'');if(/^[\s]*[=+\-@\t\r\n]/.test(text)||/^[\t\r\n]/.test(text))text="'"+text;return '"'+text.replace(/"/g,'""')+'"';};
    const blob=new Blob(['\ufeff'+rows.map(row=>row.map(cell).join(';')).join('\r\n')],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=DEMO?'most-organization-demo.csv':'most-organization-report.csv';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function go(next){if(dialog.open)closeModal();if(route===next){render();return;}location.hash=next;}
  async function action(name,el) {
    const id=el.dataset.id;
    if(name==='close')return closeModal();
    if(name==='reload'){closeModal();return boot(session?.organization?.id);}
    if(name==='request-retry')return renderRequest(id);
    if(!ready)return;
    if(name==='report-export')return exportReport();
    if(name==='demo-example')return seedExample();
    if(name==='demo-reset'&&DEMO)return openModal('Сбросить демонстрацию?',`<form data-form="demo-reset"><div class="form-error" role="alert"></div><p>Учебные проекты, заявки и ваши записи демо будут удалены из этого браузера. Сброс можно отменить до перезагрузки страницы.</p><div class="form-actions">${button('Оставить','close','light')}<button class="btn danger" type="submit">Сбросить демо</button></div></form>`);
    if(name==='demo-undo'&&DEMO&&undo){persistDemo(undo);undo=null;render();return notify('Демонстрационные записи восстановлены.');}
    if(!canWrite())return;
    if(name==='request-new')return newRequest();
    if(name==='team-request')return newRequest({category:'team',title:'Изменение доступа команды'});
    if(name==='project-request')return newRequest({projectId:id,title:'Поддержка проекта: '+(workspace.data.projects.find(p=>p.id===id)?.title||''),category:'funding'});
    if(name==='service-request'){const item=workspace.data.services.find(s=>s.id===id);if(item)return newRequest({category:item.category,title:'Совместная работа: '+item.title,body:item.description});return;}
    const match=name.match(/^(project|service|document)-(new|edit|delete)$/);if(match)return match[2]==='delete'?confirmDelete(match[1],id):editor(match[1],id);
  }
  document.addEventListener('click',async event=>{const el=event.target.closest('[data-action]');if(!el||!el.closest('.org-shell,.org-sidebar,#org-dialog'))return;try{await action(el.dataset.action,el);}catch(error){notify(error.message||'Не удалось выполнить действие.',true);}});
  document.addEventListener('submit',async event=>{
    const form=event.target;if(!form.matches('[data-form]'))return;event.preventDefault();if(writing||!form.reportValidity())return;
    const submitter=event.submitter;writing=true;if(submitter)submitter.disabled=true;picker.disabled=true;
    try{await submit(form,new FormData(form));}catch(error){formError(form,error);}finally{writing=false;if(submitter?.isConnected)submitter.disabled=false;if(ready)picker.disabled=session.organizations.length<2;}
  });
  document.addEventListener('input',event=>{if(event.target.id!=='request-search')return;filter=event.target.value;const filtered=requests.filter(r=>(r.title+' '+r.reference+' '+(categories[r.category]||'')).toLocaleLowerCase().includes(filter.toLocaleLowerCase()));document.querySelector('#request-results').innerHTML=filtered.length?`<div class="record-list">${filtered.map(requestRow).join('')}</div>`:empty('Ничего не найдено','Попробуйте другое слово или номер заявки.','search');});
  picker.addEventListener('change',()=>{if(writing)return;route='overview';history.replaceState(null,'',location.pathname+'?organization='+encodeURIComponent(picker.value)+'#overview');boot(picker.value);});
  window.addEventListener('hashchange',()=>{if(location.hash==='#org-main'){document.querySelector('#org-main').focus();return;}detailEpoch++;route=location.hash.slice(1)||'overview';filter='';closeModal();render();document.querySelector('#org-main').focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});});
  dialog.addEventListener('close',()=>{if(opener?.isConnected)opener.focus({preventScroll:true});opener=null;});
  dialog.addEventListener('click',event=>{if(event.target!==dialog)return;const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeModal();});
  boot();
})();
