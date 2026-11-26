'use strict';
/* Lastbook front end. Plain JS, no external resources. Talks only to the local server. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fileUrl = p => '/' + String(p || '').split('/').map(encodeURIComponent).join('/');
const main = $('#main'), pageTop = $('#pageTop');
const i18n = globalThis.LastbookI18n;
const IN_WINDOW = location.protocol === 'lastbook:' || location.hostname === 'lastbook.invalid';   // the desktop app, not a browser over the server
if (IN_WINDOW) $('#sideSettings').hidden = false;   // Library and local AI (web/setup.html) is in the desktop app only
const CAN_CONTRIBUTE = IN_WINDOW && !document.documentElement.classList.contains('lb-embed');
if (CAN_CONTRIBUTE) $('#sideContribute').hidden = false;
if (IN_WINDOW && window.LBUpdate) LBUpdate.watch($('#sideUpdate'));   // the opt-in "Update available" row (web/update.js); hidden unless notices are on and found one
$('.skip').addEventListener('click', e => { e.preventDefault(); main.focus() });

/* ---------------------------------------------------------------- icons -- */
const I = {
  water: '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/><path d="M9 14a3 3 0 0 0 3 3"/>',
  hurt: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5h6v2M12 10v7M8.5 13.5h7"/>',
  food: '<path d="M4 11h16a8 8 0 0 1-16 0zM8 7c0-1 1-1 1-2M12 7c0-1 1-1 1-2M16 7c0-1 1-1 1-2"/>',
  power: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z"/>',
  shelter: '<path d="M14 14.8V5a2 2 0 0 0-4 0v9.8a4 4 0 1 0 4 0zM12 9v8"/>',
  sanitation: '<path d="M7 3h10v6H7zM5 9h14l-2 6H7zM9 15l-1 6h8l-1-6"/>',
  disaster: '<path d="M12 3 2 20h20zM12 10v4M12 17h.01"/>',
  comms: '<path d="M5 12a7 7 0 0 1 14 0M8 12a4 4 0 0 1 8 0"/><circle cx="12" cy="12" r="1.5"/><path d="M12 13.5V21M9 21h6"/>',
  grow: '<path d="M12 21v-9M12 12c0-4 3-7 8-7 0 5-3 7-8 7zM12 14c0-3-2-5-7-5 0 4 2 5 7 5z"/>',
  preserve: '<path d="M8 3h8v3H8zM7 6h10l1 3v10a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V9z"/><path d="M6 12h12"/>',
  health: '<path d="M12 21s-8-4.5-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 6.5-8 11-8 11z"/><path d="M8 12h2l1-2 2 4 1-2h2"/>',
  energy: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  land: '<path d="M3 20 9 9l4 6 3-4 5 9z"/><circle cx="17" cy="6" r="2"/>',
  repair: '<path d="M14.7 6.3a4 4 0 0 0 5 5L21 13l-8 8-3-3 6.3-6.3a4 4 0 0 0-5-5L9 9 6 6l2-2"/><path d="M4 20l5-5"/>',
  map: '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2zM9 4v14M15 6v14"/>',
  pin: '<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
  book: '<path d="M4 4h6a3 3 0 0 1 3 3v13a2 2 0 0 0-2-2H4zM20 4h-6a3 3 0 0 0-1 .2"/><path d="M20 4v14h-7"/>',
  video: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m10 9 5 3-5 3z"/>',
  wiki: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  page: '<path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6M9 13h7M9 17h7"/>',
  up: '<path d="M12 19V5M6 11l6-6 6 6"/>', back: '<path d="M15 18 9 12l6-6"/>', right: '<path d="m9 18 6-6-6-6"/>', down: '<path d="m6 9 6 6 6-6"/>',
  warn: '<path d="M12 3 2 20h20zM12 10v4M12 17h.01"/>', save: '<path d="M6 3h12v18l-6-4-6 4z"/>',
  ext: '<path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6"/>', prep: '<path d="M9 11l3 3 8-8"/><path d="M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9"/>',
  shelf: '<path d="M4 4v16M9 4v16M14 5l4 15M3 20h18"/>', search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
  play: '<path d="M7 4v16l13-8z"/>', speak: '<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16 9a3 3 0 0 1 0 6M18.5 6.5a7 7 0 0 1 0 11"/>', stopsq: '<rect x="6.5" y="6.5" width="11" height="11" rx="2"/>', clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  insp: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M15 5v14"/>',
  ask: '<path d="M4 5h16v11H9l-5 4z"/><path d="M9 9.5h6M9 12.5h4"/>', spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
};
const ico = (n, cls = '') => `<svg viewBox="0 0 24 24" aria-hidden="true" class="${cls}">${I[n] || I.book}</svg>`;
const KIND_ICO = { pdf: 'page', html: 'page', video: 'video', transcript: 'video', pptx: 'page', zim: 'wiki' };
// One colour per guide, used for its tile, header and cards.
const TC = { hurt: '#c62828', water: '#1565c0', power: '#c77700', food: '#d4570f', shelter: '#7b3fa0', sanitation: '#7a5232', disaster: '#b23c17', comms: '#00796b',
  grow: '#2e7d32', preserve: '#a0661a', health: '#c2185b', repair: '#455a64', energy: '#e09400', land: '#5d7a2e' };
// Short names for tiles; the full title shows on the guide page.
const SHORT = { hurt: 'Injury & illness', water: 'Drinking water', power: 'Power is out', food: 'Food & cooking', shelter: 'Too hot or cold', sanitation: 'Toilets & hygiene',
  disaster: 'Quake, fire, flood', comms: 'Contact & find way', grow: 'Grow food', preserve: 'Preserve food', health: 'Health care', repair: 'Repair & build', energy: 'Power systems', land: 'Land & resources' };
// A guide's short name: its translation's own (tile), the English one below, or its title.
const tname = t => t.tile || SHORT[t.id] || t.title;
const tcStyle = id => `style="--tc:${TC[id] || '#1a6b55'}"`;

/* ------------------------------------------------------------ storage -- */
const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem('sg.' + k)) ?? d } catch { return d } },
  set(k, v) { try { localStorage.setItem('sg.' + k, JSON.stringify(v)) } catch { } },
};
// A row as the lists show it: its title and the subtitle under it. Two rows that read the same are one row, whatever their keys.
const rowSub = x => x.sub && x.sub !== x.title ? x.sub : x.key[0] === 'w' ? 'Encyclopedia' : '';
const rowId = x => x.title + '|' + rowSub(x);
function remember(item) {  // {key,title,href,sub}
  const r = store.get('recent', []).filter(x => x.key !== item.key && rowId(x) !== rowId(item));
  r.unshift({ ...item, at: Date.now() });
  store.set('recent', r.slice(0, 40));
}
const isSaved = key => store.get('saved', []).some(x => x.key === key);
function savedCount() { const el = $('#savedN'); if (el) el.textContent = store.get('saved', []).length || '' }
function toggleSave(item, btn) {
  let s = store.get('saved', []);
  if (s.some(x => x.key === item.key)) { s = s.filter(x => x.key !== item.key); toast('Removed from Saved') }
  else { s.unshift({ ...item, at: Date.now() }); toast('Saved on this device') }
  store.set('saved', s);
  savedCount();
  if (btn) { btn.setAttribute('aria-pressed', isSaved(item.key)); const sp = $('span', btn); if (sp) sp.textContent = isSaved(item.key) ? 'Saved' : 'Save' }
}
const saveButton = item => `<button class="btn plain" title="Save" data-save='${esc(JSON.stringify(item))}' aria-pressed="${isSaved(item.key)}">${ico('save')}<span>${isSaved(item.key) ? 'Saved' : 'Save'}</span></button>`;
const watchedButton = (id, d) => {
  const w = isWatched(id, null, d);
  return `<button class="btn plain" id="markWatched" title="${w ? 'Mark as unwatched' : 'Mark as watched'}" aria-pressed="${w}">${ico('check')}<span>${w ? 'Watched' : 'Mark watched'}</span></button>`;
};
document.addEventListener('click', e => { const b = e.target.closest('[data-save]'); if (b) toggleSave(JSON.parse(b.dataset.save), b) });
let toastT;
function toast(msg) {
  let t = $('.toast'); if (!t) { t = document.createElement('div'); t.className = 'toast'; t.setAttribute('role', 'status'); document.body.append(t) }
  t.textContent = msg; t.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => t.hidden = true, 2200);
}
// Video watch progress: {id: {t, d, title, thumb, at}}
const vprog = () => store.get('vprog', {});
// Explicit watched states survive beyond vprog's 60-video limit: {id: boolean}
const vwatched = () => store.get('vwatched', {});
function setWatched(id, state) {
  const w = vwatched();
  if (state == null) delete w[id]; else w[id] = !!state;
  store.set('vwatched', w);
}
function isWatched(id, p, v) {
  const w = vwatched();
  if (w[id] !== undefined) return w[id];
  p = p || vprog()[id];
  const dur = (v && v.duration) || (p && p.d);
  return Boolean(p && p.t && dur && p.t >= dur * 0.9);
}
// This device's history is kept for every library opened on it (each download is its own library): show only what the open one holds
const HELD = {};
const held = ids => Promise.all(ids.map(id => HELD[id] ?? (HELD[id] = fetch('/api/doc/' + encodeURIComponent(id)).then(r => r.status !== 404 && r.status !== 400).catch(() => true)))).then(ok => ids.filter((_, i) => ok[i]));
async function resumable(n = 60) {
  const list = Object.entries(vprog()).filter(([id, v]) => !isWatched(id, v) && v.t > 10 && (!v.d || v.t < v.d - 15)).sort((a, b) => b[1].at - a[1].at).slice(0, n);
  const ok = new Set(await held(list.map(([id]) => id)));
  return list.filter(([id]) => ok.has(id));
}
async function recents() {   // documents and videos from another library leave the list; guides and articles stay
  const r = store.get('recent', []), ids = r.filter(x => /^[dv]:/.test(x.key)).map(x => x.key.slice(2));
  const ok = new Set(await held(ids)), seen = new Set();
  return r.filter(x => (!/^[dv]:/.test(x.key) || ok.has(x.key.slice(2))) && !seen.has(rowId(x)) && seen.add(rowId(x)));
}
function setVprog(id, data) { const p = vprog(); p[id] = { ...(p[id] || {}), ...data, at: Date.now() }; const keys = Object.keys(p).sort((a, b) => p[b].at - p[a].at).slice(0, 60); store.set('vprog', Object.fromEntries(keys.map(k => [k, p[k]]))) }

/* --------------------------------------------------------------- data -- */
async function api(u, opts) {
  const r = await fetch(u, opts);
  let d; try { d = await r.json() } catch { throw new Error('The library sent an unreadable reply.') }
  if (!r.ok || (d && d.error && !Array.isArray(d))) throw new Error(d && d.error || ('Server error ' + r.status));
  return d;
}
let LIB = null;
const libInfo = () => LIB || (LIB = api('/api/library').catch(() => { LIB = null; return {} }));   // what this library holds; a failed ask is asked again. An older server leaves out zims, pins and sources: then everything stays offered.
let TOPICS = null, TOPICS_LANG = 'en';
// The interface language chosen in Settings (web/i18n-app.js). The guides come in that language where a translation
// exists (content/topics-i18n/); English otherwise. Each language keeps its own offline copy.
const uiLang = () => (i18n && typeof i18n.language === 'function' && i18n.language()) || 'en';
async function topics() {
  const lang = uiLang();
  if (TOPICS && TOPICS_LANG === lang) return TOPICS;
  const key = lang === 'en' ? 'topicsCache' : 'topicsCache.' + lang;
  try { TOPICS = await api('/api/topics' + (lang === 'en' ? '' : '?lang=' + encodeURIComponent(lang))); store.set(key, TOPICS) }
  catch (e) { TOPICS = store.get(key, null); if (!TOPICS) throw e }
  TOPICS_LANG = lang;
  return TOPICS;
}
const topicById = id => (TOPICS || []).find(t => t.id === id);
const NOW_ORDER = ['hurt', 'water', 'power', 'food', 'shelter', 'sanitation', 'disaster', 'comms'];
const LEARN_ORDER = ['grow', 'preserve', 'health', 'repair', 'energy', 'land'];
const nowTopics = () => NOW_ORDER.map(topicById).filter(Boolean).concat((TOPICS || []).filter(t => t.mode === 'now' && !NOW_ORDER.includes(t.id)));
const learnTopics = () => LEARN_ORDER.map(topicById).filter(Boolean).concat((TOPICS || []).filter(t => t.mode === 'learn' && !LEARN_ORDER.includes(t.id)));

/* ------------------------------------------------------------ helpers -- */
const fmtDur = s => { if (!s) return ''; s = Math.round(s); const h = s / 3600 | 0, m = (s % 3600) / 60 | 0; return h ? `${h} h ${m} min` : m ? `${m} min` : `${s} s` };
const clock = s => { s = Math.max(0, Math.round(s || 0)); const h = s / 3600 | 0, m = (s % 3600) / 60 | 0, x = s % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0') };
const here = () => location.hash || '#/videos';
const fromQ = () => 'from=' + encodeURIComponent(here());
const pageImg = (id, p, w) => `/api/page/${encodeURIComponent(id)}/${p || 1}.png?w=${w}`;
const hostOf = u => { try { return new URL(u).host } catch { return u } };   // a web address shown as its site only
const askLink = (about, label = 'Ask about this') => `<a class="btn plain" title="${esc(label)}" href="#/ask?about=${encodeURIComponent(about)}&${fromQ()}">${ico('ask')}<span>${label}</span></a>`;

function hrefFor(item, src) {
  src = src || item.src || item;
  if (item.zim) return '#/wiki/' + item.zim.replace(/^\/?zim\//, '') + '?' + fromQ();
  if (!src || !src.id) return '#/';
  if (src.kind === 'video') return `#/watch/${encodeURIComponent(src.id)}?${item.t ? 't=' + item.t + '&' : ''}${fromQ()}`;
  return `#/read/${encodeURIComponent(src.id)}?${item.page ? 'p=' + item.page + '&' : ''}${fromQ()}`;
}
function srcText(s, page) {
  if (!s) return 'Source not found in this library copy';
  const bits = [`<strong>${esc(s.publisher || s.collection || 'Unknown publisher')}</strong>`];
  if (s.year) bits.push(esc(s.year));
  if (page) bits.push('page ' + page + (s.pages ? ' of ' + s.pages : ''));
  else if (s.kind === 'pdf' && s.pages) bits.push(s.pages + ' pages');
  if (s.duration) bits.push(fmtDur(s.duration) + (s.transcript ? ' · transcript' : ''));
  return bits.join(' · ');
}
// A reading card shows a picture of what you'll open: the actual page, the video frame, or an encyclopedia mark.
function rcard(item) {
  const s = item.src;
  let pv;
  if (item.zim) pv = `<span class="pv w">${ico('wiki')}</span>`;
  else if (s && s.kind === 'video') pv = `<span class="pv v">${s.thumb ? `<img loading="lazy" alt="" src="${fileUrl(s.thumb)}">` : ''}<span class="play"><span>${ico('play')}</span></span>${s.duration ? `<span class="pg">${clock(s.duration)}</span>` : ''}</span>`;
  else if (s && s.kind === 'pdf') pv = `<span class="pv"><img loading="lazy" alt="" src="${pageImg(s.id, item.page, 360)}" onerror="this.remove()"><span class="pg">${item.page ? 'p. ' + item.page : 'PDF'}</span></span>`;
  else pv = `<span class="pv w">${ico('page')}</span>`;
  const label = item.label || item.title || (s && s.title);
  const src = item.zim ? `<strong>Encyclopedia</strong> · ${esc(item.title || '')} · community-written` : `${s ? 'From “' + esc(s.title) + '” · ' : ''}${srcText(s, item.page)}<br>${esc(s ? s.trust : '')}`;
  return `<a class="rcard" href="${hrefFor(item)}">${pv}<span><b>${esc(label)}</b>${item.note ? `<p>${esc(item.note)}</p>` : ''}<span class="src">${src}</span></span></a>`;
}
function rowItem(item) {
  const s = item.src || null;
  let k = ico(item.zim ? 'wiki' : s ? KIND_ICO[s.kind] : 'page');
  if (s && s.kind === 'video' && s.thumb) k = `<img loading="lazy" alt="" src="${fileUrl(s.thumb)}">`;
  else if (s && s.kind === 'pdf' && (item.page || item.preview)) k = `<img loading="lazy" alt="" src="${pageImg(s.id, item.page, 200)}" onerror="this.remove()">`;
  const sub = item.zim ? 'Encyclopedia article · community-written' : srcText(s, item.page);
  return `<li><a class="row" href="${hrefFor(item)}"><span class="k">${k}</span><span><b>${esc(item.label || item.title || (s && s.title))}</b><small>${sub}</small></span></a></li>`;
}
function vcard(v, opts = {}) {
  const p = vprog()[v.id];
  const pct = p && p.t && (v.duration || p.d) ? Math.min(100, 100 * p.t / (v.duration || p.d)) : 0;
  const watched = isWatched(v.id, p, v);
  return `<a class="vcard" href="#/watch/${encodeURIComponent(v.id)}?${fromQ()}" ${opts.style || ''}>
    <span class="vthumb">${v.thumb ? `<img loading="lazy" alt="" src="${fileUrl(v.thumb)}" onerror="this.remove()">` : `<span class="ph">${ico('video')}</span>`}
      ${watched ? `<span class="vcheck" title="Watched" aria-label="Watched">${ico('check')}</span>` : ''}${v.transcript ? '<span class="cc" title="Has a transcript">CC</span>' : ''}${v.duration ? `<span class="dur">${clock(v.duration)}</span>` : ''}${pct > 2 ? `<span class="prog" style="width:${pct}%"></span>` : ''}<span class="play">${ico('play')}</span></span>
    <b>${esc(v.title)}</b><span class="vm">${esc(opts.sub || v.publisher || '')}</span></a>`;
}
function rail(html, cls = '') {
  return `<div class="rail-wrap"><button class="rail-btn l" aria-label="Scroll left" data-i18n-aria-label="nav.scrollLeft" data-i18n-lang hidden>${ico('back')}</button><div class="rail ${cls}">${html}</div><button class="rail-btn r" aria-label="Scroll right" data-i18n-aria-label="nav.scrollRight" data-i18n-lang>${ico('right')}</button></div>`;
}
// Translate the marked interface text inside markup that was just rendered into `root`
// (a page, or one section filled in later). Static page chrome is translated by the language policy itself.
function translateRendered(root = main) { i18n?.apply(root) }
// A message as plain text in the interface language, for text built into markup that has no element of its own.
function TR(key, english) { const el = document.createElement('span'); el.dataset.i18n = key; el.textContent = english; i18n?.apply(el); return el.textContent }
function wireRails(root = main) {
  $$('.rail-wrap', root).forEach(w => {
    const r = $('.rail', w), l = $('.rail-btn.l', w), rb = $('.rail-btn.r', w);
    const upd = () => { l.hidden = r.scrollLeft < 10; rb.hidden = r.scrollLeft + r.clientWidth > r.scrollWidth - 10 };
    l.onclick = () => r.scrollBy({ left: -r.clientWidth * .85, behavior: 'smooth' });
    rb.onclick = () => r.scrollBy({ left: r.clientWidth * .85, behavior: 'smooth' });
    r.addEventListener('scroll', upd, { passive: true }); upd();
  });
}
const secHead = (title, sub, link) => `<div class="sec-head"><div><h2>${title}</h2>${sub ? `<span class="sub">${sub}</span>` : ''}</div>${link || ''}</div>`;
function crumbs(list) {
  return `<nav class="crumbs" aria-labelledby="crumbLabel"><span class="sr" id="crumbLabel" data-i18n="nav.currentPath">You are here</span>${list.map((c, i) => i < list.length - 1 ? `<a href="${c[1]}">${esc(c[0])}</a><span aria-hidden="true">›</span>` : `<span aria-current="page">${esc(c[0])}</span>`).join('')}</nav>`;
}
// A label is [message key, English text]. A plain string is still accepted: it keeps its text, and the few
// common ones keep their translation.
const KNOWN_LABELS = { Back: 'nav.back', Videos: 'nav.videos', Library: 'nav.library', Search: 'search.label', Go: 'search.go', Filter: 'search.filter' };
const labelPair = (label, fallback) => Array.isArray(label) ? label : typeof label === 'string' ? [KNOWN_LABELS[label] || null, label] : fallback;
function backButton(from, fallback) {
  let [key, label] = labelPair(fallback, ['nav.back', 'Back']);
  const href = from?.startsWith('#') ? from : '#/';
  const m = /^#\/t\/([\w-]+)/.exec(href);
  if (m && topicById(m[1])) [key, label] = [null, tname(topicById(m[1]))];
  else if (href.startsWith('#/search')) [key, label] = ['search.results', 'Search results'];
  else if (href.startsWith('#/ask')) [key, label] = ['nav.backToChat', 'Back to chat'];
  else if (href.startsWith('#/saved')) [key, label] = ['nav.saved', 'Saved'];
  else if (href.startsWith('#/map')) [key, label] = ['nav.map', 'Map'];
  else if (href.startsWith('#/videos')) [key, label] = ['nav.videos', 'Videos'];
  else if (href.startsWith('#/guides')) [key, label] = ['nav.guides', 'Guides'];
  else if (href.startsWith('#/watch')) [key, label] = ['nav.video', 'Video'];
  else if (href.startsWith('#/read')) [key, label] = ['nav.backToPage', 'Back to page'];
  else if (href.startsWith('#/library') || href.startsWith('#/shelf') || href.startsWith('#/collection') || href.startsWith('#/encyclopedias') || href.startsWith('#/prepare')) [key, label] = ['nav.library', 'Library'];
  else if (href === '#/' || href === '#') [key, label] = ['nav.videos', 'Videos'];
  return `<a class="back" href="${esc(href)}" data-back>${ico('back')}<span${key ? ` data-i18n="${key}"` : ''}>${esc(label)}</span></a>`;
}
// Links into readers carry where you came from; refresh it at click time (sections may have opened since render).
document.addEventListener('click', e => {
  const a = e.target.closest('a[href^="#/read/"],a[href^="#/watch/"],a[href^="#/wiki/"],a[href^="#/collection"],a[href^="#/ask?about"]');
  if (!a || a.hasAttribute('data-back')) return;
  const h = a.getAttribute('href'), i = h.indexOf('from=');
  if (i > -1) a.setAttribute('href', h.slice(0, i) + 'from=' + encodeURIComponent(here()));
}, true);
// Prefer real history so scroll position and open sections come back exactly (not inside encyclopedia frames).
document.addEventListener('click', e => {
  const a = e.target.closest('a[data-back]');
  if (a && !location.hash.startsWith('#/wiki/') && navAt > 0 && navStack[navAt - 1] === a.getAttribute('href')) { e.preventDefault(); history.back() }
});
function errorBox(e, what) {
  return `<div class="err" role="alert"><b>${esc(what || 'Something went wrong.')}</b><br>${esc(e.message || e)}
  <br><span class="small">If this keeps happening, close Lastbook and open it again.</span></div>`;
}
// The window title, and on reading pages the toolbar's title and the line under it.
// bar: what the toolbar shows when it is not the page's own title (an article names itself; the toolbar names the encyclopedia).
const setTitle = (t, sub, bar) => { document.title = t ? t + ' · Lastbook' : 'Lastbook'; const b = $('#tbTitle'); b.textContent = b.title = bar ?? t ?? ''; if (sub !== undefined) $('#tbSub').textContent = $('#tbSub').title = sub };

/* ------------------------------------------------------------- router -- */
// Where this tab is in its history. Each entry carries its own index in history.state, so Back and Forward are known exactly:
// after going back several steps, after a page rewrote its address in place, and when a link leads to the page just left.
const navStack = JSON.parse(sessionStorage.getItem('sg.stack') || '[]');   // navStack[i]: the address at history index i
let navAt = +(sessionStorage.getItem('sg.at') || 0), navEnd = +(sessionStorage.getItem('sg.end') || 0), swapping = false;
const keepNav = () => { try { sessionStorage.setItem('sg.stack', JSON.stringify(navStack.slice(0, navEnd + 1))); sessionStorage.setItem('sg.at', navAt); sessionStorage.setItem('sg.end', navEnd) } catch { } };
const _replace = history.replaceState.bind(history);
// A page that rewrites its own address (the map, search as you type, an opened situation, a new chat) keeps its place.
history.replaceState = (state, title, url) => { _replace({ ...(state || {}), lb: navAt }, title, url); if (url != null) { navStack[navAt] = current = here(); keepNav() } };
const swap = h => { swapping = true; location.replace(h) };   // this entry becomes another page, in place
const _push = history.pushState.bind(history);
const pushHere = url => { navAt++; navEnd = navAt; navStack.length = navAt; _push({ lb: navAt }, '', url); navStack[navAt] = current = here(); keepNav(); barState() };   // a new entry, without loading the page again
const scrolls = JSON.parse(sessionStorage.getItem('sg.scroll') || '{}');
try { history.scrollRestoration = 'manual' } catch { }   // the page restores its own place (restoreScroll), once it is built
let current = null;
window.addEventListener('scroll', () => { if (current && !$('#wframe')) scrolls[current] = scrollY }, { passive: true });   // an article scrolls in its frame, which keeps its own place (wiki)
window.addEventListener('pagehide', () => sessionStorage.setItem('sg.scroll', JSON.stringify(scrolls)));
function parse() {
  const h = here().slice(1) || '/';
  const [path, qs] = h.split('?');
  return { parts: path.split('/').filter(Boolean).map(decodeURIComponent), q: new URLSearchParams(qs || '') };
}
// The sidebar row each page belongs to. Reading pages stay under Library, articles under Encyclopedias; search results select no row.
const NAV_OF = { '': 'videos', guides: 'guides', t: 'guides', ask: 'ask', videos: 'videos', watch: 'videos', map: 'map', library: 'library', learn: 'library', browse: 'library', shelf: 'library', collection: 'library', read: 'library', wiki: 'encyclopedias', search: '', saved: 'saved', 'not-found': 'library', encyclopedias: 'encyclopedias', prepare: 'prepare', about: 'about', contribute: 'contribute' };
let routeSeq = 0, leaving = null;  // routeSeq: the newest route; a slower earlier one stops when it sees it has been passed. leaving: cleanup hook for the current view (player, chat stream…)
const stale = me => me !== routeSeq;   // a view captures `const me = routeSeq` when it starts and asks stale(me) after each wait, before it touches the page
async function route() {
  const seq = ++routeSeq; searchSeq++;   // a search still being answered belongs to the page that asked
  const cameFromSide = !!(document.activeElement && document.activeElement.closest && document.activeElement.closest('.side,.tabbar'));
  const { parts, q } = parse();
  const h = here();
  const wf = $('#wframe'), wd = wf && wf.contentDocument;
  if (current) { if (!wf) scrolls[current] = scrollY; else if (wd && wd.readyState === 'complete') scrolls[current] = wf.contentWindow.scrollY }   // an article's place is its frame's
  const at = history.state && history.state.lb;
  if (typeof at === 'number') { navAt = at; navEnd = Math.max(navEnd, at) }   // back, forward, or a reload
  else {
    if (swapping) swapping = false;
    else if (current !== null || navStack.length) { navAt++; navEnd = navAt; navStack.length = navAt }   // a new page: what was ahead is gone
    else navAt = navEnd = 0;   // the first page of this tab
    _replace({ ...(history.state || {}), lb: navAt }, '');
  }
  navStack[navAt] = h; keepNav();
  sessionStorage.setItem('sg.scroll', JSON.stringify(scrolls));
  current = h;
  const y = typeof at === 'number' ? scrolls[h] : null;   // read now: while the page is rebuilt it scrolls (shorter, then taller), and those scrolls are recorded too
  const v = parts[0] || 'videos';
  document.body.className = v ? 'v-' + v : 'home';
  const showUpdate = v === 'about' && q.has('updates') && !$('#sideUpdate').hidden;
  const nav = showUpdate ? 'update' : v === 'read' && (q.get('from') || '').startsWith('#/about') ? 'about' : NAV_OF[v] || '';
  $$('[data-nav]').forEach(a => nav && (a.dataset.nav === nav || (a.dataset.also || '').split(' ').includes(nav)) ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'));
  const rows = $$('.side a.row-s'); rows.forEach(a => a.tabIndex = a.hasAttribute('aria-current') || (!nav && a === rows[0]) ? 0 : -1);   // the sidebar is one Tab stop; arrows move inside it
  savedCount();
  html.classList.remove('side-open', 'h1-gone'); h1seen.disconnect();
  railTitles();
  $('#tbActs').replaceChildren(); $('#tbTitle').textContent = $('#tbSub').textContent = ''; $('#tbTitle').title = $('#tbSub').title = ''; searchLive = null; main.classList.remove('own-title');
  if (leaving) { try { leaving() } catch { } leaving = null }
  window.onresize = null; main.onkeydown = pageTop.onkeydown = null;
  try {
    if (v !== 'map') MapView.stop();
    await topics().catch(() => { });
    if (stale(seq)) return;
    if (!v || v === 'guides') await home();
    else if (v === 't') await topicPage(parts[1], parts[2]);
    else if (v === 'ask') await Chat.page(main, parts.slice(1), q);
    else if (v === 'videos') await (parts[1] ? videoRow(parts[1], q) : videosHome());
    else if (v === 'watch') await watch(parts[1], q.get('t'), q.get('from'));
    else if (v === 'read') await reader(parts[1], +q.get('p') || 0, q.get('from'), q.get('view'));
    else if (v === 'wiki') await wiki(parts.slice(1).join('/'), q.get('from'), y);
    else if (v === 'search') await searchPage(q.get('q') || '', q.get('kind') || 'all');
    else if (v === 'library' || v === 'learn' || v === 'browse') await library();
    else if (v === 'prepare') await prepareHub();
    else if (v === 'encyclopedias') await encyclopedias(q.get('q') || '');
    else if (v === 'map') await MapView.page(main, q, () => !stale(seq));
    else if (v === 'saved') await savedPage();
    else if (v === 'not-found') await notFoundPage();
    else if (v === 'shelf') await shelfPage(parts[1], q.get('kind') || 'all', q.get('q') || '');
    else if (v === 'collection') await collectionPage(q.get('name') || '', q.get('from'));
    else if (v === 'contribute' && CAN_CONTRIBUTE) contributePage();
    else if (v === 'about') await about(q.has('updates'));
    else notFound();
    if (stale(seq)) return;   // a newer page has been opened meanwhile: it does the rest
  } catch (e) { if (stale(seq)) return; setTitle(''); document.body.className = 'v-error'; main.innerHTML = emptyState('warn', 'This page could not be opened', e.message || e) }   // v-error: not a reading page, so a phone keeps its tab bar
  translateRendered(); wireRails(); dock(); barState();
  $('#topQ').value = '';
  const big = $('main h1'); if (big) h1seen.observe(big);
  if (v === 'ask') { bandState(); return }  // the chat manages its own scroll position
  if (y != null && v !== 'wiki') restoreScroll(h, y); else if (v !== 'wiki') requestAnimationFrame(() => { if (!$('.sit.open', main)) scrollTo(0, 0) });
  if (y == null) startHere(cameFromSide);
  bandState(); alignTitle();
}
// Back, Forward or a reload return to the place the page was left. A page still filling in (pictures, results) may not be tall enough yet,
// so this tries again each frame for a moment (at most 2.5 s), and stops as soon as the person scrolls or the page changes.
function restoreScroll(h, y, w = window) {
  const stop = new AbortController(), end = performance.now() + 2500, o = { passive: true, signal: stop.signal };
  for (const ev of ['wheel', 'touchstart', 'keydown', 'mousedown']) addEventListener(ev, () => stop.abort(), o);
  let sh = 0, still = 0, seen = null;   // done once the place is reached and the page has stopped growing for a moment (sections still arriving would move it)
  const tick = () => {
    if (stop.signal.aborted || (w === window ? current !== h : !(w.frameElement && w.frameElement.isConnected))) return;   // another page, or another article in the frame
    const h2 = w.document.scrollingElement.scrollHeight;
    if (seen !== null && w.scrollY !== seen && h2 === sh) return stop.abort();   // it moved while the page did not grow: the person scrolled (an article's own wheel and key events never arrive in the Mac app)
    if (Math.abs(w.scrollY - y) > 1) w.scrollTo(0, y);
    seen = w.scrollY; still = h2 === sh && Math.abs(seen - y) <= 1 ? still + 1 : 0; sh = h2;
    if (still < 12 && performance.now() < end) requestAnimationFrame(tick); else stop.abort();
  };
  requestAnimationFrame(tick);
}
// On Windows the toolbar's title starts where the page's column does, as in Fluent's reading apps. On the Mac it follows Back and Forward.
function alignTitle() {
  const t = $('.tb-title'); if (!t || MAC) return;
  t.style.marginLeft = '';
  if (!t.offsetWidth) return;
  const d = main.getBoundingClientRect().left + parseFloat(getComputedStyle(main).paddingLeft) - t.getBoundingClientRect().left;
  if (d > 0 && d < 240) t.style.marginLeft = parseFloat(getComputedStyle(t).marginLeft) + d + 'px';
}
addEventListener('resize', alignTitle);
// After a new page: a person moving through the sidebar stays there, as in Finder or Settings, and Tab goes on to the toolbar and the page.
// Otherwise the next Tab starts at the top of the window (skip link, sidebar, toolbar, page), as after a full load. The marker it starts from
// is not a control; it carries the page's name, which a screen reader reads when focus lands on it.
let focusAfterRoute = null;   // a control the page asks to keep focus on when it has settled (Read aloud's Stop, after a page turn)
function startHere(fromSide) {
  const keep = focusAfterRoute; focusAfterRoute = null;
  if (keep && keep.isConnected && !keep.hidden) { keep.focus({ preventScroll: true }); return }
  if (fromSide && !(MAC && !wide.matches) && document.activeElement && document.activeElement.closest('.side,.tabbar')) return;
  const h1 = $('h1', main);
  pageTop.textContent = (h1 && h1.textContent.trim()) || document.title;
  pageTop.focus({ preventScroll: true });
}
window.addEventListener('hashchange', route);
let searchLive = null;   // on the search page, where the pane's field is the page's own (Windows), typing there updates the results
$('#topSearch').addEventListener('submit', e => { e.preventDefault(); if (searchLive) { searchLive($('#topQ').value.trim(), true); $('#topQ').blur(); return } location.hash = '#/search?q=' + encodeURIComponent($('#topQ').value.trim()) });
$('#topQ').addEventListener('input', () => { if (searchLive) searchLive($('#topQ').value.trim(), false, true) });

/* --------------------------------------------------------- the window -- */
const html = document.documentElement, MAC = html.classList.contains('plat-mac');
const wide = matchMedia('(min-width:900px)');
// The toolbar names the page once its large title has scrolled up under the toolbar.
const h1seen = new IntersectionObserver(es => html.classList.toggle('h1-gone', !es[es.length - 1].isIntersecting), { rootMargin: `-${(parseInt(getComputedStyle(html).getPropertyValue('--top-h')) || 52) + (parseInt(getComputedStyle(html).getPropertyValue('--cap-h')) || 0)}px 0px 0px 0px` });
// Windows' folded pane shows icons only. Use the translated row names as tooltips.
function railTitles() { const icons = html.classList.contains('compact') && !html.classList.contains('side-open'); $$('.side a.row-s').forEach(a => icons ? a.title = $('span', a).textContent : a.removeAttribute('title')) }
addEventListener('resize', railTitles);
// The toolbar's field says only 'Search' when it is too narrow for the whole hint, as Windows' and the Mac's own narrow fields do
function searchPlaceholder() {
  const q = $('#topQ');
  if (!q.clientWidth) return;
  const short = q.clientWidth < 175;
  if (i18n) {
    q.dataset.i18nPlaceholder = short ? 'search.label' : 'search.library';
    i18n.apply(q);
  } else q.placeholder = short ? 'Search' : 'Search the library';
}
new ResizeObserver(searchPlaceholder).observe($('#topQ'));
document.addEventListener('lastbook:languagechange', () => {
  railTitles(); searchPlaceholder();
  if (TOPICS && TOPICS_LANG !== uiLang()) { TOPICS = null; if (current !== null) route() }   // the guides, now in the chosen language
});
// At 900 and wider a page's .dock controls (view switch, Save, Ask) sit in the toolbar; narrower they stay in the page.
const docks = () => wide.matches || (!MAC && innerWidth >= 640);
function dock() {
  if (docks()) $$('.dock', main).forEach(el => { const mark = document.createElement('i'); mark.className = 'dock-home'; mark.hidden = true; el.before(mark); $('#tbActs').append(el) });
  else $$('#tbActs .dock').forEach(el => { const mark = $('.dock-home', main); if (mark) mark.replaceWith(el); else el.remove() });
}
wide.addEventListener('change', () => { html.classList.remove('side-open'); dock(); railTitles(); bandState() });
matchMedia('(min-width:640px)').addEventListener('change', () => { dock(); bandState() });   // an overlay sidebar left open does not come back open later
const pageBack = () => $('main a[data-back]');
function barState() { $('#tbBack').disabled = navAt < 1 && !pageBack(); $('#tbFwd').disabled = navAt >= navEnd }
function bandState() {
  if (MAC) return;
  const s = $('#topSearch'), searchInBand = html.classList.contains('compact') && getComputedStyle(s).visibility !== 'hidden' && getComputedStyle(s).display !== 'none';
  const was = html.classList.contains('no-bar'), now = !$('#tbActs').children.length && !searchInBand;
  html.classList.toggle('no-bar', now);
  if (was !== now && window.onresize) window.onresize();   // a page that measures itself (the map) measures again
}
addEventListener('resize', () => requestAnimationFrame(bandState));
$('#tbBack').onclick = () => { const a = pageBack(); if (navAt > 0) history.back(); else if (a) location.hash = a.getAttribute('href') };
$('#tbFwd').onclick = () => history.forward();
function toggleSide() {
  if (wide.matches) { html.classList.toggle('side-off'); try { localStorage.setItem('sg.side-off', html.classList.contains('side-off') ? '1' : '0') } catch { } window.LB_LAYOUT() }
  else html.classList.toggle('side-open');
  railTitles(); bandState();
}
$('#sideBtn').onclick = toggleSide;
if (!MAC) {
  $('#sideBtn').before($('#tbBack'));   // drawn first, top left, so reached first
  // the full pane holds its search field above the rows; the folded rail has it in the command bar
  const placeSearch = () => {
    const f = $('#topSearch'), side = $('#side'), inPane = innerWidth >= 640 && !html.classList.contains('compact');
    if (inPane && f.parentElement !== side) $('.side-nav', side).before(f);
    else if (!inPane && f.parentElement === side) $('.top-in').append(f);
  };
  placeSearch(); new MutationObserver(placeSearch).observe(html, { attributes: true, attributeFilter: ['class'] }); addEventListener('resize', placeSearch);
}
document.addEventListener('click', e => { if (html.classList.contains('side-open') && !e.target.closest('.side,#sideBtn')) { html.classList.remove('side-open'); railTitles() } });
function toggleInsp() { html.classList.toggle('insp-off'); const d = $('.about-src', main); if (d && !html.classList.contains('insp-off')) d.open = true; store.set('insp-off', html.classList.contains('insp-off')) }
if (store.get('insp-off', true)) html.classList.add('insp-off');   // off until asked for: the page keeps the width
document.addEventListener('click', e => { if (e.target.closest('[data-insp]')) toggleInsp() });
$('#side').addEventListener('keydown', e => {
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
  const rows = $$('.side a.row-s').filter(a => a.offsetParent), i = rows.indexOf(document.activeElement);
  if (i < 0) return;
  e.preventDefault(); rows[(i + (e.key === 'ArrowDown' ? 1 : rows.length - 1)) % rows.length].focus();
});
const SECTIONS = ['#/videos', '#/map', '#/ask'];
const findBox = () => [$('#bigQ'), $('#searchQ'), $('#topQ')].find(x => x && x.offsetParent) || $('#chatIn');
document.addEventListener('keydown', e => {
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName), cmd = MAC ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
  const is = c => e.code === 'Key' + c || (!e.code && (e.key || '').toUpperCase() === c);   // some input (assistive and remote tools) sends no key code
  if (e.key === '/' && !typing) { e.preventDefault(); findBox().focus() }
  else if (cmd && !e.altKey && !e.shiftKey && /^[1-3]$/.test(e.key)) { e.preventDefault(); location.hash = SECTIONS[e.key - 1] }
  else if (cmd && !e.altKey && !e.shiftKey && (is('F') || (!MAC && is('E')))) { e.preventDefault(); const f = findBox(); f.focus(); if (f.select) f.select() }
  else if (MAC && e.metaKey && e.ctrlKey && is('S')) { e.preventDefault(); toggleSide() }   // Windows apps have no key for this: the ☰ button
  else if (MAC ? e.metaKey && e.altKey && is('I') : e.ctrlKey && e.shiftKey && is('I')) { e.preventDefault(); if ($('.about-src', main)) toggleInsp() }
  else if (e.key === 'Escape') {
    if (html.classList.contains('side-open')) { html.classList.remove('side-open'); railTitles() }
    else if (document.activeElement === $('#topQ')) { $('#topQ').value = ''; $('#topQ').blur() }
  }
});
function notFound() { setTitle('Not found'); main.innerHTML = emptyState('search', 'That page isn’t here', 'The link may be from an older version of the guide.') }
const emptyState = (icon, title, text) => `<div class="empty"><span class="e-ico">${ico(icon)}</span><b>${esc(title)}</b><p>${esc(text)}</p><p class="e-act"><a class="btn plain" href="#/" data-i18n="nav.goToVideos">Go to Videos</a></p></div>`;
function searchBox(id, value, placeholder, buttonLabel) {
  const [key, button] = labelPair(buttonLabel, ['search.label', 'Search']);
  return `<form class="bigsearch" role="search" id="${id}F">${ico('search')}<label class="sr" for="${id}" data-i18n="search.label">Search</label><input id="${id}" type="search" autocomplete="off" value="${esc(value || '')}" placeholder="${esc(placeholder)}" enterkeyhint="search"><button${key ? ` data-i18n="${key}"` : ''}>${esc(button)}</button></form>`;
}

/* --------------------------------------------------------------- home -- */
// Example searches on Home, in the interface language: they are searches, so they have to be words the guides know.
const HOME_EXAMPLES = {
  en: { short: 'e.g. boil water', long: 'e.g. boil water, deep cut, no power',
        chips: ['boil water', 'cut won’t stop bleeding', 'fridge after power cut', 'burn', 'toilet not working', 'smell gas'] },
  nl: { short: 'bijv. water koken', long: 'bijv. water koken, diepe snee, geen stroom',
        chips: ['water koken', 'snee blijft bloeden', 'koelkast na stroomuitval', 'brandwond', 'wc werkt niet', 'ik ruik gas'] },
};
async function home() {
  setTitle('');
  const examples = HOME_EXAMPLES[uiLang()] || HOME_EXAMPLES.en;
  const tile = t => `<a class="need" href="#/t/${t.id}" ${tcStyle(t.id)}><span class="ico">${ico(t.id)}</span><b>${esc(tname(t))}</b><small>${esc(t.short || '')}</small></a>`;
  const me = routeSeq, cont = await continueItems();
  const pins = (await libInfo()).pins !== false;
  if (stale(me)) return;
  main.innerHTML = `
  <section class="hero">
    <h1 data-i18n="home.title">What do you need?</h1>
    <p class="lead" data-i18n="home.lead">Pick what’s happening, search in your own words, or ask the library a question.</p>
    ${searchBox('bigQ', '', innerWidth < 500 ? examples.short : examples.long)}
    <div class="chips examples" aria-label="Example searches">${examples.chips.map(x => `<a class="chip" href="#/search?q=${encodeURIComponent(x)}">${esc(x)}</a>`).join('')}</div>
  </section>
  ${secHead('<span data-i18n="guide.needHelpNow">Need help now</span>')}
  <div class="needs">${nowTopics().map(tile).join('')}</div>
  <div class="banners"><a class="banner chatb" href="#/ask"><span class="ico">${ico('ask')}</span><span><b>Ask the library</b><small>Get an answer built from the manuals, with the exact pages and video moments it came from</small></span><span class="go">${ico('right')}</span></a>
  <a class="banner map" href="#/map"><span class="ico">${ico('pin')}</span><span>${pins ? '<b>Find help nearby</b><small>Hospitals, pharmacies, water taps and fire stations on an offline map</small>' : '<b>Find a place</b><small>Main roads, towns and water on an offline map</small>'}</span><span class="go">${ico('right')}</span></a></div>
  ${cont.length ? secHead('Pick up where you left off') + rail(cont.join('')) : ''}
  <div id="homeVideos"></div>
  ${secHead('<span data-i18n="guide.learnSkill">Learn a skill</span>', 'Step-by-step routes for the weeks and months ahead', '<a href="#/library">All skills</a>')}
  ${rail(learnTopics().map(t => `<a class="skill" href="#/t/${t.id}" ${tcStyle(t.id)}><span class="ico">${ico(t.id)}</span><b>${esc(tname(t))}</b><small>${esc(t.short || '')}</small><span class="steps">${(t.route || []).length} steps</span></a>`).join(''), 'skills')}
  <a class="banner prep" href="#/prepare"><span class="ico">${ico('prep')}</span><span><b data-i18n="guide.getReady">Get ready before it happens</b><small>Store water and food, plan for outages, pack kits</small></span><span class="go">${ico('right')}</span></a>`;
  translateRendered();
  $('#bigQF').addEventListener('submit', e => { e.preventDefault(); location.hash = '#/search?q=' + encodeURIComponent($('#bigQ').value.trim()) });
  const ex = $('.examples', main), exEnd = () => { ex.classList.toggle('at-end', ex.scrollLeft + ex.clientWidth >= ex.scrollWidth - 4); ex.classList.toggle('at-start', ex.scrollLeft < 4) };
  ex.addEventListener('scroll', exEnd, { passive: true }); exEnd(); window.onresize = exEnd;
  try {
    const rows = await api('/api/videos');
    const g = rows.find(r => r.id === 'guides');
    if (g && $('#homeVideos')) { $('#homeVideos').innerHTML = secHead('Watch how it’s done', 'Videos picked for the guides', '<a href="#/videos">All videos</a>') + rail(g.items.slice(0, 14).map(v => vcard(v, { style: tcStyle(v.guide) })).join('')); translateRendered($('#homeVideos')); wireRails($('#homeVideos')) }
  } catch { }
}
async function continueItems() {
  const out = [], rec = await recents();
  (await resumable(12)).slice(0, 6)
    .forEach(([id, v]) => out.push(vcard({ id, title: v.title, thumb: v.thumb, duration: v.d }, { sub: 'Resume at ' + clock(v.t) })));
  rec.filter(r => !r.key.startsWith('v:')).slice(0, 8).forEach(r => out.push(`<a class="mini" href="${esc(r.href)}"><small>${esc(r.sub || '')}</small><b>${esc(r.title)}</b></a>`));
  return out;
}

/* -------------------------------------------------------------- guide -- */
function topicVideos(t) {
  const all = [...(t.choices || []).flatMap(c => c.read || []), ...(t.route || []).flatMap(s => s.read || []), ...(t.learn || []), ...(t.prepare || [])];
  const seen = new Set();
  return all.filter(i => i.src && i.src.kind === 'video' && !seen.has(i.src.id) && seen.add(i.src.id)).map(i => i.src);
}
async function topicPage(id, open) {
  const t = topicById(id);
  if (!t) return notFound();
  setTitle(t.title);
  remember({ key: 't:' + id, title: t.title, href: '#/t/' + id, sub: t.mode === 'learn' ? 'Learning route' : 'Guide' });
  const learn = t.mode === 'learn';
  const progress = store.get('progress', {});
  const sits = (t.choices || []).map(c => c.goto
    ? `<div class="sit"><a href="#/t/${esc(c.goto)}"><span class="dot"></span><span class="tx"><b>${esc(c.label)}</b>${c.hint ? `<span>${esc(c.hint)}</span>` : ''}</span><span class="chev">${ico('right')}</span></a></div>`
    : `<div class="sit${open === c.id ? ' open' : ''}" id="c-${esc(c.id)}">
      <button aria-expanded="${open === c.id}" aria-controls="cb-${esc(c.id)}" data-choice="${esc(c.id)}"><span class="dot"></span><span class="tx"><b>${esc(c.label)}</b>${c.hint ? `<span>${esc(c.hint)}</span>` : ''}</span><span class="chev">${ico('down')}</span></button>
      <div class="body" id="cb-${esc(c.id)}"><div class="rcards">${(c.read || []).map(rcard).join('') || '<p class="muted">Nothing picked for this yet — try searching.</p>'}</div></div></div>`).join('');
  const limLi = l => `<li>${esc(l.text)}${l.src ? ` <span class="lim-src">— <a href="${hrefFor(l)}">${esc(l.src.publisher || l.src.title)}${l.page ? ', p. ' + l.page : ''}</a></span>` : l.zim ? ` <span class="lim-src">— <a href="${hrefFor(l)}">encyclopedia</a></span>` : ''}</li>`;
  const LIM = 4, lims = t.limits || [];
  const limits = lims.length ? `<section class="limits" aria-labelledby="lim"><h2 id="lim">${ico('warn')}<span data-i18n="guide.stopAndGetHelp">Stop and get help when…</span></h2><ul>${lims.slice(0, LIM).map(limLi).join('')}</ul>${lims.length > LIM ? `<details><summary data-i18n="guide.showAllWarnings" data-i18n-count="${lims.length}">Show all ${lims.length} warnings</summary><ul>${lims.slice(LIM).map(limLi).join('')}</ul></details>` : ''}</section>` : '';
  const disagree = (t.gaps?.disagree || []).length ? `<div class="disagree"><b>Sources disagree</b><ul>${t.gaps.disagree.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : '';
  const route = (t.route || []).length ? `<h2 data-i18n="guide.route">Your learning route</h2><p class="muted small">Ticks are your own notes on this device. Reading or watching is not the same as practising safely.</p>
    <ol class="route">${t.route.map((s, i) => { const k = id + ':' + i, p = progress[k] || {}; return `<li class="step${p.practised ? ' done' : ''}"><h3>${esc(s.title.replace(/^\p{L}+ \d+:\s*/u, ''))}</h3>${s.goal ? `<p class="goal">${esc(s.goal)}</p>` : ''}
      <div class="rcards">${(s.read || []).map(rcard).join('')}</div>
      <div class="mark"><label><input type="checkbox" data-prog="${k}" data-f="read" ${p.read ? 'checked' : ''}> I’ve read this</label><label><input type="checkbox" data-prog="${k}" data-f="practised" ${p.practised ? 'checked' : ''}> I’ve practised it with someone who knows</label></div></li>` }).join('')}</ol>` : '';
  const sec = (icon, title, items) => items && items.length ? `<details class="more"><summary>${ico(icon)}<span>${title} <span class="n">· ${items.length}</span></span></summary><div class="body"><ul class="list">${items.map(i => rowItem({ ...i, preview: true })).join('')}</ul></div></details>` : '';
  const vids = topicVideos(t);
  const related = (t.related || []).map(topicById).filter(Boolean);
  main.innerHTML = `<div class="ghero" ${tcStyle(id)}><div class="ghero-in">${crumbs([[TR('nav.guides', 'Guides'), '#/guides'], [learn ? TR('guide.learnSkill', 'Learn a skill') : TR('guide.needHelpNow', 'Need help now'), learn ? '#/library' : '#/guides'], [tname(t)]])}
      <div class="row1"><span class="ico">${ico(t.id)}</span><h1>${esc(t.title)}</h1></div><p class="lead">${esc(t.intro || '')}</p>
      <div class="vactions" style="margin-bottom:0">${askLink('topic:' + id, 'Ask a question about this')}</div></div></div>
    <div class="gcols" ${tcStyle(id)}><div>
      ${(t.choices || []).length ? `<p class="ask" id="askh" data-i18n="${learn ? 'guide.whereStart' : 'guide.whatsHappening'}">${learn ? 'Where do you want to start?' : 'What’s happening?'}</p><div class="situations" aria-labelledby="askh">${sits}</div>` : ''}
      <div class="gnarrow">${limits}${disagree}</div>
      ${route}
      ${vids.length ? secHead('Videos for this', `${vids.length} picked video${vids.length > 1 ? 's' : ''}`) + rail(vids.map(v => vcard(v)).join('')) : ''}
      ${sec('prep', '<span data-i18n="guide.getReady">Get ready before it happens</span>', t.prepare)}
      ${sec('book', '<span data-i18n="guide.goDeeper">Go deeper: full manuals &amp; articles</span>', t.learn)}
      ${(t.gaps?.missing || []).length ? `<details class="more"><summary>${ico('warn')}<span data-i18n="guide.notInLibrary">Not in this library</span></summary><div class="body"><p class="muted small" style="margin-top:0">Looked for but not found when this guide was put together (October 2026):</p><ul>${t.gaps.missing.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div></details>` : ''}
      ${related.length ? `<h2 data-i18n="guide.related">Related guides</h2><div class="related">${related.map(r => `<a class="chip" href="#/t/${r.id}" ${tcStyle(r.id)}><span style="color:var(--tc)">${ico(r.id)}</span>${esc(tname(r))}</a>`).join('')}</div>` : ''}
    </div><aside class="gside" aria-label="Safety"></aside></div>`;
  i18n?.apply(main, el => el.dataset.i18nCount ? { count: +el.dataset.i18nCount } : undefined);
  // On wide screens the safety box sits beside the choices so it stays visible.
  const side = $('.gside', main), nar = $('.gnarrow', main);
  const placeSide = () => { if (!side || !nar) return; if (innerWidth >= 1050) { if (!side.firstChild) side.append(...nar.childNodes) } else if (side.firstChild) nar.append(...side.childNodes) };
  placeSide(); window.onresize = placeSide;
  $$('[data-choice]', main).forEach(b => b.addEventListener('click', () => {
    const c = b.closest('.sit'), on = !c.classList.contains('open');
    $$('.sit.open', main).forEach(x => { x.classList.remove('open'); $('button', x).setAttribute('aria-expanded', 'false') });
    if (on) { c.classList.add('open'); b.setAttribute('aria-expanded', 'true') }
    history.replaceState(null, '', '#/t/' + id + (on ? '/' + b.dataset.choice : ''));
    if (on) setTimeout(() => c.scrollIntoView({ block: 'start', behavior: 'smooth' }), 30);
  }));
  $$('[data-prog]', main).forEach(cb => cb.addEventListener('change', () => {
    const p = store.get('progress', {}); p[cb.dataset.prog] = { ...(p[cb.dataset.prog] || {}), [cb.dataset.f]: cb.checked }; store.set('progress', p);
    cb.closest('.step').classList.toggle('done', !!p[cb.dataset.prog].practised);
  }));
  if (open) { const c = $('#c-' + CSS.escape(open)); if (c) setTimeout(() => c.scrollIntoView({ block: 'start' }), 0) }
}

/* ------------------------------------------------------------- videos -- */
async function videosHome() {
  setTitle('Videos');
  main.innerHTML = `<h1>Videos</h1><p class="lead">Watch it done — practical how-tos first, then channels and courses.</p>
    <div class="vtools">${searchBox('vq', '', 'Search video titles')}</div>
    <div class="chips" style="margin-top:8px">${[['short', 'Under 10 min'], ['medium', '10–30 min'], ['long', 'Over 30 min']].map(([k, l]) => `<a class="chip" href="#/videos/all?len=${k}">${ico('clock')}${l}</a>`).join('')}</div>
    <div id="vrows"><p class="loading">Loading videos…</p></div>`;
  $('#vqF').addEventListener('submit', e => { e.preventDefault(); location.hash = '#/videos/all?q=' + encodeURIComponent($('#vq').value.trim()) });
  const me = routeSeq, rows = await api('/api/videos');
  const cont = (await resumable(20)).slice(0, 12);
  if (stale(me)) return;   // the person has gone to another page
  const GCOL = { health: 'hurt', water: 'water', food: 'food', power: 'power', outdoors: 'shelter', repair: 'repair', making: 'land' };
  $('#vrows').innerHTML =
    (cont.length ? secHead('Continue watching') + rail(cont.map(([id, v]) => vcard({ id, title: v.title, thumb: v.thumb, duration: v.d }, { sub: 'Resume at ' + clock(v.t) })).join('')) : '') +
    rows.map(r => secHead(esc(r.title), r.note ? esc(r.note) : '', `<a href="#/videos/${r.id}">See all ${r.count}</a>`) +
      rail(r.items.map(v => vcard(v, { style: tcStyle(v.guide || GCOL[r.id]) })).join(''))).join('') +
    `<p class="small muted" style="margin-top:24px">Only videos already downloaded are shown. Many have no captions, so the transcript search and the assistant can’t see what’s said in them.</p>`;
  wireRails();
}
async function videoRow(row, q) {
  const len = q.get('len') || '', sort = q.get('sort') || '', qq = q.get('q') || '';
  const base = `#/videos/${row}`;
  const qs = o => { const p = new URLSearchParams({ q: qq, len, sort, ...o }); for (const [k, v] of [...p]) if (!v) p.delete(k); const s = p.toString(); return base + (s ? '?' + s : '') };
  let off = 0;
  const me = routeSeq, first = await api(`/api/videos/${row}?q=${encodeURIComponent(qq)}&len=${len}&sort=${sort}&offset=0`);
  if (stale(me)) return;   // the person has gone to another page
  setTitle(first.title);
  main.innerHTML = `<div>${backButton('#/videos')}</div><h1 style="margin-top:12px">${esc(qq ? 'Videos: “' + qq + '”' : first.title)}</h1>${first.note ? `<p class="lead">${esc(first.note)}</p>` : ''}
    <div class="vtools">${searchBox('vq', qq, 'Search these videos', ['search.go', 'Go'])}
      <label class="sr" for="vsort">Sort</label><select id="vsort">${[['', 'Most useful first'], ['short', 'Shortest first'], ['new', 'Newest first'], ['az', 'A to Z']].map(([k, l]) => `<option value="${k}" ${k === sort ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
    <div class="chips" style="margin:8px 0 16px">${[['', 'Any length'], ['short', 'Under 10 min'], ['medium', '10–30 min'], ['long', 'Over 30 min']].map(([k, l]) => `<a class="chip ${k === len ? 'on' : ''}" href="${qs({ len: k })}">${l}</a>`).join('')}</div>
    <p class="muted small">${first.total.toLocaleString()} video${first.total === 1 ? '' : 's'}</p>
    <div class="vgrid" id="vg"></div><p id="vmore"></p>`;
  $('#vqF').addEventListener('submit', e => { e.preventDefault(); location.hash = qs({ q: $('#vq').value.trim() }) });
  $('#vsort').addEventListener('change', e => { location.hash = qs({ sort: e.target.value }) });
  const add = d => {
    $('#vg').insertAdjacentHTML('beforeend', d.items.map(v => vcard(v)).join('') || (off ? '' : '<div class="empty" style="grid-column:1/-1">No videos match. Try another word or length.</div>'));
    $('#vmore').innerHTML = d.more ? '<button class="btn plain" id="vmb">Show more videos</button>' : '';
    if (d.more) $('#vmb').onclick = async () => { off += 48; add(await api(`/api/videos/${row}?q=${encodeURIComponent(qq)}&len=${len}&sort=${sort}&offset=${off}`)) };
  };
  add(first);
}

// Video formats some computers can't play, by the code an MP4 file gives its video track: the name to show, and what to ask the player.
const UNPLAYABLE = { av01: ['AV1', 'video/mp4; codecs="av01.0.05M.08"'], vp09: ['VP9', 'video/mp4; codecs="vp09.00.10.08"'], hvc1: ['HEVC', 'video/mp4; codecs="hvc1.1.6.L93.B0"'], hev1: ['HEVC', 'video/mp4; codecs="hev1.1.6.L93.B0"'] };
// The format codes of an MP4 file's tracks ("av01", "mp4a"), read from the file's own index. [] when they can't be read (not an MP4, say).
// An MP4 is a row of boxes, each starting with its length and a four-letter name. This reads the start of each box until it finds
// the index ("moov"), then reads only that: never the pictures or the sound.
async function videoFormats(url) {
  let size = 0;
  const part = async (at, n) => {
    const r = await fetch(url, { headers: { Range: `bytes=${at}-${at + n - 1}` } });
    size = +(/\/(\d+)$/.exec(r.headers.get('Content-Range') || '') || [])[1] || 0;
    if (r.status !== 206 || !size) throw new Error('no byte range');
    return new DataView(await r.arrayBuffer());
  };
  const name = (v, at) => String.fromCharCode(v.getUint8(at), v.getUint8(at + 1), v.getUint8(at + 2), v.getUint8(at + 3));
  const found = [];
  const inside = (v, at, end) => {   // the boxes between at and end; a track's format is the first name in its "stsd" box
    while (at + 8 <= end) {
      let n = v.getUint32(at), head = 8;
      if (n === 1 && at + 16 <= end) { n = Number(v.getBigUint64(at + 8)); head = 16 } else if (n === 0) n = end - at;
      if (n < head || at + n > end) return;
      const type = name(v, at + 4);
      if (type === 'stsd' && n >= head + 16) found.push(name(v, at + head + 12));
      else if (['moov', 'trak', 'mdia', 'minf', 'stbl'].includes(type)) inside(v, at + head, at + n);
      at += n;
    }
  };
  for (let at = 0, i = 0; i < 64; i++) {
    const v = await part(at, 16);
    if (v.byteLength < 16) break;
    let n = v.getUint32(0);
    if (n === 1) n = Number(v.getBigUint64(8)); else if (n === 0) n = size - at;
    if (n < 8) break;
    if (name(v, 4) === 'moov') { if (n <= 32 * 1024 * 1024) { const m = await part(at, n); inside(m, 0, m.byteLength) } break }
    at += n;
    if (at + 16 > size) break;
  }
  return found;
}

async function watch(id, t, from) {
  const me = routeSeq, d = await api('/api/doc/' + encodeURIComponent(id));
  if (stale(me)) return;   // the person has gone to another page
  setTitle(d.title);
  const selfHref = `#/watch/${encodeURIComponent(id)}`;
  remember({ key: 'v:' + id, title: d.title, href: selfHref, sub: 'Video · ' + fmtDur(d.duration) });
  const p = vprog()[id];
  const start = t !== null && Number.isFinite(+t) && +t >= 0 ? +t : null;
  const resumeAt = start === null && p && p.t > 15 && (!d.duration || p.t < d.duration - 20) ? p.t : 0;
  const watched = isWatched(id, p, d);
  main.innerHTML = `<div class="rtop">${backButton(from, ['nav.videos', 'Videos'])}</div>
  <div class="watch">
    <div>
      <div class="player"><video id="vid" controls preload="metadata" playsinline src="${fileUrl(d.path)}${start !== null ? '#t=' + start : ''}"></video></div>
      <div class="video-speed"><label for="videoSpeed">Playback speed</label><select id="videoSpeed"><option value="0.5">0.5×</option><option value="0.75">0.75×</option><option value="1" selected>Normal</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></div>
      ${d.remote ? `<p class="small muted" style="margin:6px 0 0">Stored on the remote drive “${esc(d.remote)}”. It plays only while that computer is reachable.</p>` : ''}
      <h1 class="vtitle">${esc(d.title)}</h1>
      <div class="vmeta"><b>${esc(d.publisher || '')}</b><span>${fmtDur(d.duration)}</span>${d.upload_date ? `<span>${esc(d.upload_date.replace(/(\d{4})(\d\d)(\d\d)/, '$1-$2-$3'))}</span>` : ''}<span>${esc(d.trust)}</span></div>
      ${resumeAt ? `<div class="resume" id="resume"${watched ? ' hidden' : ''}>You stopped at ${clock(resumeAt)}. <button class="btn" id="resYes">Resume</button><button class="btn plain" id="resNo">Start over</button></div>` : ''}
      <div class="vactions dock">${saveButton({ key: 'v:' + id, title: d.title, href: selfHref, sub: 'Video · ' + fmtDur(d.duration) })}${watchedButton(id, d)}<a class="btn plain" title="Ask about this video" href="#/ask?about=${encodeURIComponent('video:' + id)}&${fromQ()}" id="askv">${ico('ask')}<span>Ask about this video</span></a></div>
      ${momentSection(true)}
      <div class="notice small">A video shows how one person did something. Watching isn’t practice, and it may not match current safety guidance — check a manual for anything risky.</div>
    </div>
    <section class="txpanel" id="tx" aria-label="Transcript"><header><h2>Transcript</h2><label class="sr" for="cueQ">Find in transcript</label><input id="cueQ" type="search" placeholder="Find words in the transcript"></header>
      <div class="cues" id="cues"><p class="muted" style="padding:12px 14px">Loading transcript…</p></div><div class="txnote" id="txnote"></div></section>
  </div>
  <div id="morev"></div>
  <details class="about-src"><summary>About this video</summary><div class="in"><dl><dt>Channel</dt><dd>${esc(d.publisher || '—')}</dd><dt>Kind</dt><dd>${esc(d.trust)}</dd><dt>Length</dt><dd>${fmtDur(d.duration) || 'unknown'}</dd>${d.notes ? `<dt>Note</dt><dd>${esc(d.notes)}</dd>` : ''}${d.source_url ? `<dt>Online original</dt><dd>${esc(hostOf(d.source_url))} <span class="muted">(online; not needed here)</span></dd>` : ''}</dl></div></details>`;
  const vid = $('#vid');
  wireMoments({ video: d, player: vid, start });
  const speed = $('#videoSpeed');
  speed.addEventListener('change', () => { vid.playbackRate = Number(speed.value) });
  // Native controls may also change the rate. Keep the visible control in sync.
  vid.addEventListener('ratechange', () => {
    const value = String(vid.playbackRate);
    if (![...speed.options].some(option => option.value === value)) speed.add(new Option(value + '×', value));
    speed.value = value;
  });
  if (d.thumb) vid.poster = fileUrl(d.thumb);
  vid.addEventListener('error', async () => {
    const say = why => vid.closest('.player')?.insertAdjacentHTML('afterend', `<div class="err">${why}</div>`);
    if (d.remote) return say(`This video is on the remote drive “${esc(d.remote)}”, which isn’t reachable right now. The transcript below still works.`);
    // Say why when the reason is the format: some library videos are AV1, which a computer without an AV1 decoder (a Mac before the M3) can't play.
    const f = (await videoFormats(fileUrl(d.path)).catch(() => [])).map(x => UNPLAYABLE[x]).find(x => x && !vid.canPlayType(x[1]));
    if (!vid.isConnected) return;   // the person has gone to another page
    say(f ? `This video is saved in the ${f[0]} format, which this computer can’t play in Lastbook. Try another video player that supports ${f[0]}, such as VLC: the file is in your Lastbook data folder, at <b style="overflow-wrap:anywhere">library-data/${esc(d.path)}</b>.`
      : `This video file couldn’t be played here. <a href="${fileUrl(d.path)}" target="_blank" rel="noopener">Open the file directly</a>.`);
  }, { once: true });
  if (resumeAt) {
    $('#resYes').onclick = () => { vid.currentTime = resumeAt; vid.play().catch(() => { }); $('#resume')?.remove() };
    $('#resNo').onclick = () => { vid.currentTime = 0; vid.play().catch(() => { }); $('#resume')?.remove() };
    vid.addEventListener('play', () => { $('#resume')?.remove() });
  }
  const updateWatchedBtn = () => {
    const b = $('#markWatched');
    if (!b) return;
    const w = isWatched(id, null, d);
    if (b.getAttribute('aria-pressed') === String(w)) return;
    b.setAttribute('aria-pressed', w);
    b.title = w ? 'Mark as unwatched' : 'Mark as watched';
    const sp = $('span', b); if (sp) sp.textContent = w ? 'Watched' : 'Mark watched';
    const res = $('#resume'); if (res) res.hidden = w;
  };
  const bWatched = $('#markWatched');
  if (bWatched) {
    bWatched.onclick = () => {
      const cur = isWatched(id, null, d);
      setWatched(id, !cur);
      updateWatchedBtn();
      toast(!cur ? 'Marked as watched' : 'Marked as unwatched');
    };
  }
  let lastSave = 0;
  let below90 = !((t || (resumeAt && !watched)) && (d.duration || vid.duration) && (t || (resumeAt && !watched)) >= (d.duration || vid.duration) * 0.9);
  const saveProg = () => {
    if (vid.currentTime > 3) {
      $('#resume')?.remove();
      setVprog(id, { t: vid.currentTime, d: d.duration || vid.duration, title: d.title, thumb: d.thumb });
    }
  };
  const onSeek = () => {
    const dur = d.duration || vid.duration;
    if (dur) below90 = vid.currentTime < dur * 0.9;
  };
  vid.addEventListener('seeking', onSeek);
  vid.addEventListener('seeked', onSeek);
  vid.addEventListener('loadedmetadata', () => {
    if (!d.duration && vid.duration) d.duration = vid.duration;
    const dur = d.duration || vid.duration;
    if (dur) {
      const pos = vid.currentTime || t || (resumeAt && $('#resume') && !$('#resume').hidden ? resumeAt : 0);
      below90 = pos < dur * 0.9;
    }
  });
  vid.addEventListener('timeupdate', () => {
    const dur = d.duration || vid.duration;
    if (dur) {
      if (vid.currentTime < dur * 0.9) {
        below90 = true;
      } else if (below90 && !vid.paused && !vid.seeking) {
        below90 = false;
        setWatched(id, true);
        updateWatchedBtn();
      }
    }
    if (Date.now() - lastSave > 4000) { lastSave = Date.now(); saveProg() }
  });
  vid.addEventListener('ended', () => {
    if (!isWatched(id, null, d)) {
      setWatched(id, true);
      updateWatchedBtn();
    }
  });
  vid.addEventListener('pause', saveProg);
  leaving = () => { saveProg(); vid.pause() };
  // keep "Ask about this video" pointing at the current moment
  vid.addEventListener('pause', () => { const a = $('#askv'); if (a) a.href = `#/ask?about=${encodeURIComponent('video:' + id + ':' + Math.round(vid.currentTime))}&${fromQ()}` });
  let cues = [];
  try {
    const tx = await api('/api/transcript/' + encodeURIComponent(id)); cues = tx.cues || [];
    if (stale(me)) return;
    $('#txnote').textContent = cues.length ? `${tx.source === 'authored' ? 'Captions written by the publisher' : /auto/.test(tx.source || '') ? 'Automatic captions' : 'Captions'} — may contain errors.` : '';
  } catch { }
  if (stale(me)) return;   // also when the request failed: the page open now has its own transcript
  const box = $('#cues');
  const draw = q => {
    const rx = q ? new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'ig') : null;
    const list = cues.filter(c => !rx || c.text.match(rx));
    box.innerHTML = list.length ? list.map(c => `<button class="cue" data-t="${c.t ?? ''}"><time>${c.t != null ? clock(c.t) : ''}</time><span>${rx ? esc(c.text).replace(rx, m => `<mark>${m}</mark>`) : esc(c.text)}</span></button>`).join('')
      : `<p class="muted" style="padding:12px 14px">${cues.length ? 'No matching words.' : 'No transcript was saved for this video, so search and the assistant can’t see what’s said in it.'}</p>`;
  };
  draw('');
  $('#cueQ').addEventListener('input', e => draw(e.target.value.trim()));
  box.addEventListener('click', e => { const b = e.target.closest('.cue'); if (b && b.dataset.t !== '') { vid.currentTime = +b.dataset.t; vid.play().catch(() => { }); if (innerWidth < 1000) scrollTo({ top: 0, behavior: 'smooth' }) } });
  let lastOn = null;
  vid.addEventListener('timeupdate', () => {
    const now = vid.currentTime; let on = null;
    for (const b of box.children) { if (b.dataset && b.dataset.t !== '' && +b.dataset.t <= now) on = b; else if (on) break }
    if (on !== lastOn) { lastOn && lastOn.classList.remove('on'); on && on.classList.add('on'); lastOn = on; if (on && !$('#cueQ').value && innerWidth >= 1000) on.scrollIntoView({ block: 'nearest' }) }
  });
  try {
    const rel = await api('/api/videos/related/' + encodeURIComponent(id));
    if (rel.length && !stale(me) && $('#morev')) { $('#morev').innerHTML = secHead('More like this') + rail(rel.map(v => vcard(v)).join('')); translateRendered($('#morev')); wireRails($('#morev')) }
  } catch { }
}

/* ------------------------------------------------------- video moments -- */
function momentSection(watching = false) {
  return `<section class="moments" aria-labelledby="momentsTitle">
    <header class="moments-head"><h2 id="momentsTitle">${watching ? 'Saved moments' : 'Video moments'} <span id="momentCount" class="moment-count"></span></h2>
      ${watching ? `<button class="btn plain" id="saveMoment" disabled>${ico('save')}<span>Save this moment</span></button>` : ''}</header>
    <p class="moments-hint">${watching ? 'Keep the parts you want to return to.' : 'Your saved places in videos.'} Kept on this device.</p>
    <div id="momentEditor"></div><ul class="moment-list" id="momentList"></ul>
    <p id="momentStatus" class="moment-status" role="status"></p>
  </section>`;
}

function wireMoments({ video = null, player = null, available = null, start = null } = {}) {
  const root = $('.moments'), list = $('#momentList', root), editor = $('#momentEditor', root);
  const status = $('#momentStatus', root), add = $('#saveMoment', root);
  let editing = null;
  const say = (text, error = false) => { status.textContent = text; status.classList.toggle('is-error', error) };
  const focusRow = key => {
    const button = $$('[data-moment-edit]', root).find(b => b.dataset.momentEdit === key);
    if (button) button.focus(); else if (add) add.focus(); else $('#momentsTitle').focus();
  };
  $('#momentsTitle').tabIndex = -1;
  const read = () => VideoMoments.readSaved().filter(VideoMoments.isMoment);
  const draw = () => {
    let items;
    try { items = read() } catch (e) { say(e.message, true); return }
    if (video) items = items.filter(x => x.videoId === video.id).sort((a, b) => a.time - b.time);
    $('#momentCount', root).textContent = items.length || '';
    list.innerHTML = items.length ? items.map(x => {
      const missing = available && !available.has(x.videoId), title = esc(x.title), time = clock(x.time);
      const content = `<span class="moment-time">${time}</span><span class="moment-name"><b>${title}</b>${!video ? `<small>${esc(x.videoTitle)}${missing ? ' · Not in this library' : ''}</small>` : ''}</span>`;
      const open = video ? `<button class="moment-open" data-moment-play="${x.time}" aria-label="Play ${title} at ${time}">${content}</button>`
        : missing ? `<span class="moment-open unavailable">${content}</span>`
          : `<a class="moment-open" href="${esc(VideoMoments.href(x))}" aria-label="Open ${title} at ${time}">${content}</a>`;
      return `<li>${open}<div class="moment-actions"><button data-moment-edit="${esc(x.key)}" aria-label="Rename ${title}">Rename</button><button data-moment-remove="${esc(x.key)}" aria-label="Remove ${title}">Remove</button></div></li>`;
    }).join('') : `<li class="moment-empty">${video ? 'Pause at a useful part, then choose Save this moment.' : 'No video moments saved.'}</li>`;
  };
  const close = () => {
    const key = editing && editing.key;
    editing = null; editor.replaceChildren(); focusRow(key);
  };
  const edit = (item, seconds) => {
    if (player) player.pause();
    const time = item ? item.time : Math.floor(seconds);
    editing = { key: item ? item.key : null, time };
    editor.innerHTML = `<form class="moment-form"><p class="moment-form-title">${item ? 'Rename moment' : 'Save moment'} <span class="moment-time">${clock(time)}</span></p>
      <label for="momentName">Name <span class="muted">(optional)</span></label>
      <input id="momentName" type="text" maxlength="120" autocomplete="off" placeholder="For example, tools needed" value="${esc(item ? item.title : '')}">
      <div class="moment-form-actions"><button class="btn" type="submit">${item ? 'Save changes' : 'Save moment'}</button><button class="btn plain" type="button" id="cancelMoment">Cancel</button></div></form>`;
    say('');
    $('#cancelMoment', editor).onclick = close;
    $('form', editor).onkeydown = e => { if (e.key === 'Escape') { e.preventDefault(); close() } };
    $('form', editor).onsubmit = e => {
      e.preventDefault();
      const title = $('#momentName', editor).value.trim() || 'Moment at ' + clock(editing.time);
      try {
        const item = editing.key ? VideoMoments.rename(editing.key, title) : VideoMoments.save(video, editing.time, title);
        editing = null; editor.replaceChildren(); draw(); savedCount(); focusRow(item.key);
        say('Moment saved on this device.');
      } catch (e) { say(e.message, true) }
    };
    $('#momentName', editor).focus();
  };
  if (player) {
    const ready = () => !player.error && player.readyState >= 1 && Number.isFinite(player.duration) && player.duration > 0;
    const update = () => { add.disabled = !ready() };
    player.addEventListener('loadedmetadata', update);
    player.addEventListener('durationchange', update);
    player.addEventListener('error', update);
    const checkStart = () => {
      if (ready() && start !== null && start >= player.duration)
        say('This position is beyond the end of this video.', true);
    };
    player.addEventListener('loadedmetadata', checkStart, { once: true });
    checkStart();
    update();
    add.onclick = () => {
      if (!ready()) return;
      const time = Math.floor(Math.min(player.currentTime, Math.max(0, player.duration - 0.001)));
      try { edit(read().find(x => x.videoId === video.id && x.time === time), time) }
      catch (e) { say(e.message, true) }
    };
  }
  list.onclick = e => {
    const play = e.target.closest('[data-moment-play]');
    if (play && player) {
      const time = +play.dataset.momentPlay;
      if (player.readyState < 1 || player.error) return say('This video is not ready to play.', true);
      if (time >= player.duration) return say('This moment is beyond the end of this video.', true);
      player.currentTime = time; player.play().catch(() => { }); say(''); return;
    }
    const rename = e.target.closest('[data-moment-edit]'), remove = e.target.closest('[data-moment-remove]');
    try {
      if (rename) {
        const item = read().find(x => x.key === rename.dataset.momentEdit);
        if (!item) return say('This moment is no longer saved.', true);
        edit(item);
      }
      if (remove) {
        const key = remove.dataset.momentRemove;
        VideoMoments.remove(key);
        if (editing && editing.key === key) { editing = null; editor.replaceChildren() }
        draw(); savedCount();
        const next = $('[data-moment-edit]', root);
        if (next) next.focus(); else if (add) add.focus(); else $('#momentsTitle').focus();
        say('Moment removed.');
      }
    } catch (e) { say(e.message, true) }
  };
  draw();
}

/* ------------------------------------------------------------- reader -- */
async function reader(id, page, from, view) {
  const me = routeSeq, d = await api('/api/doc/' + encodeURIComponent(id));
  if (stale(me)) return;   // the person has gone to another page
  if (d.kind === 'video') { swap('#/watch/' + encodeURIComponent(id) + (from ? '?from=' + encodeURIComponent(from) : '')); return }
  if (d.kind === 'transcript' && d.videoId) { swap('#/watch/' + encodeURIComponent(d.videoId) + (from ? '?from=' + encodeURIComponent(from) : '')); return }
  setTitle(d.title, [d.publisher, d.year, d.trust].filter(Boolean).join(' · '));
  const isPdf = d.kind === 'pdf', total = d.pages || 1;
  const isWeb = d.kind === 'html' && /\.x?html?$/i.test(d.path);   // a plain text file, such as a lecture transcript, reads as text in the page itself
  page = Math.min(Math.max(page || 1, 1), total);
  view = isPdf ? view || 'page' : isWeb ? view || 'web' : 'text';
  const key = 'd:' + id + (isPdf ? ':' + page : '');
  const selfHref = `#/read/${encodeURIComponent(id)}?p=${page}`;
  remember({ key: 'd:' + id, title: d.title, href: selfHref, sub: (isPdf ? 'Page ' + page + ' · ' : '') + (d.publisher || '') });
  const go = (p, v = view) => `#/read/${encodeURIComponent(id)}?p=${p}&view=${v}${from ? '&from=' + encodeURIComponent(from) : ''}`;
  const views = isPdf ? [['page', 'Page'], ['text', 'Text'], ['pdf', 'Whole PDF']] : isWeb ? [['web', 'Page'], ['text', 'Text only']] : [];
  main.innerHTML = `
    <div class="rtop">${backButton(from)}</div>
    <h1 class="rtitle">${esc(d.title)}</h1>
    <div class="rsrc"><b>${esc(d.publisher || '')}</b>${d.year ? ' · ' + esc(d.year) : ''} · ${esc(d.trust)}</div>
    <div class="rmodes">${views.length ? `<div class="seg dock" role="group" aria-label="How to show it">${views.map(([v, l]) => `<button data-view="${v}" aria-pressed="${v === view}">${l}</button>`).join('')}</div>` : ''}<span class="vactions dock">${askLink('doc:' + id + ':' + (isPdf ? page : 1), 'Ask')}<button class="btn plain" data-speak hidden title="Read aloud" aria-label="Read aloud">${ico('speak', 'i-speak')}${ico('stopsq', 'i-stop')}<span>Read aloud</span></button>${saveButton({ key, title: d.title + (isPdf ? ' — page ' + page : ''), href: selfHref, sub: d.publisher || d.kindLabel })}<button class="tb-btn insp-btn" data-insp aria-label="Show or hide the source details" title="Details">${ico('insp')}</button></span></div>
    <div id="docbody"></div>
    ${d.imageOnly ? '<div class="notice">This is a scanned document without searchable text, so search and the assistant can’t read it. Use the Page view.</div>' : ''}
    ${isPdf && view !== 'pdf' ? `<div class="rbar"><a class="btn plain nav" href="${go(page - 1)}" ${page <= 1 ? 'aria-disabled="true" style="opacity:.35;pointer-events:none"' : ''} aria-label="Previous page" data-i18n-aria-label="nav.previousPage" data-i18n-lang>${ico('back')}<span data-i18n="nav.previous">Previous</span></a>
      <span class="pnum"><label class="sr" for="pg">Page number</label>Page <input id="pg" inputmode="numeric" value="${page}"> of ${total}</span>
      <a class="btn nav" href="${go(page + 1)}" ${page >= total ? 'aria-disabled="true" style="opacity:.35;pointer-events:none"' : ''} aria-label="Next page" data-i18n-aria-label="nav.nextPage" data-i18n-lang><span data-i18n="nav.next">Next</span>${ico('right')}</a></div>` : ''}
    <details class="about-src"><summary>About this source</summary><div class="in"><p class="insp-h">${esc(d.title)}</p>
      <dl><dt>Publisher</dt><dd>${esc(d.publisher || '—')}</dd><dt>Kind</dt><dd>${esc(d.trust)} · ${esc(d.kindLabel)}</dd>
      ${d.edition ? `<dt>Edition</dt><dd>${esc(d.edition)}</dd>` : ''}${d.year ? `<dt>Year</dt><dd>${esc(d.year)}</dd>` : ''}
      <dt>Saved</dt><dd>${esc((d.retrieved_at || '').slice(0, 10) || 'unknown date')} · ${esc(d.collection)}</dd>
      ${d.notes ? `<dt>Note</dt><dd>${esc(d.notes)}</dd>` : ''}
      ${d.source_url ? `<dt>Online original</dt><dd>${esc(hostOf(d.source_url))} <span class="muted">(online; not needed to read this copy)</span></dd>` : ''}</dl>
      <p class="small muted">A reference copy, not advice checked for your situation. Check the date; older material can conflict with current guidance.</p>
      ${isPdf || isWeb || !IN_WINDOW ? `<p><a class="btn ghost" href="${fileUrl(d.path)}${isPdf ? '#page=' + page : ''}" target="_blank" rel="noopener">${ico('ext')}Open the original file</a></p>` : ''}</div></details>`;
  $$('[data-view]', main).forEach(b => b.addEventListener('click', () => swap(go(page, b.dataset.view))));
  // Read aloud (web/speak.js): this page's text, then on to the next page by itself, so a person whose hands are busy can keep listening.
  const sb = $('[data-speak]', main);
  if (sb) {
    let hadText = false;
    leaving = Speak.attach(sb, async () => {
      let t;
      try { t = await api(`/api/page/${encodeURIComponent(id)}/${isPdf ? page : 1}`) }
      catch { toast('This page could not be read aloud. Try again.'); return '' }   // shown, not only spoken: the sound may be off
      hadText = !!(t.text || '').trim();
      if (!hadText) toast('This page has no text that can be read aloud.');
      return hadText ? (isPdf ? `Page ${page}. ` : '') + t.text : 'This page has no text that can be read aloud.';
    }, isPdf && page < total ? () => { if (!hadText) return; try { sessionStorage.setItem('sg.speakOn', id) } catch { } location.hash = go(page + 1) } : null);
    let goingOn = null;
    try { goingOn = sessionStorage.getItem('sg.speakOn'); sessionStorage.removeItem('sg.speakOn') } catch { }
    // Reading went on to this page by itself: keyboard focus goes back to Stop when route() has finished and put it on the page's
    // start (startHere), so stopping is one key away, not a walk through the sidebar and toolbar while the voice goes on.
    if (goingOn === id) {
      focusAfterRoute = sb;
      Speak.ready().then(ok => {
        if (!ok || !sb.isConnected) return;
        sb.click();
        if (document.activeElement === $('#pageTop')) sb.focus({ preventScroll: true });   // the voices were listed after the page settled
      });
    }
  }
  if (innerWidth >= 1060 && !html.classList.contains('insp-off')) $('.about-src', main).open = true;
  const pg = $('#pg'); if (pg) pg.addEventListener('change', () => { const n = parseInt(pg.value, 10); if (n >= 1 && n <= total) location.hash = go(n) });
  const body = $('#docbody');
  if (view === 'page') {
    const w = Math.min(1600, Math.round(Math.min(innerWidth, 1000) * Math.min(2, devicePixelRatio || 1)));
    body.innerHTML = `<div class="pagewrap"><img class="pageimg" alt="Page ${page} of ${esc(d.title)}" src="${pageImg(id, page, w)}"></div>`;
    const img = $('img', body);
    img.addEventListener('error', () => { body.innerHTML = `<div class="notice">This page image couldn’t be made. <a href="${go(page, 'text')}">Show the text instead</a>.</div>` });
    if (page < total) { const n = new Image(); n.src = pageImg(id, page + 1, w) }
    let sx = null, sy = 0;
    const wrap = $('.pagewrap', body);
    wrap.addEventListener('touchstart', e => { if (e.touches.length === 1) { sx = e.touches[0].clientX; sy = e.touches[0].clientY } }, { passive: true });
    wrap.addEventListener('touchend', e => { if (sx == null) return; const dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy; sx = null; if (Math.abs(dx) > 70 && Math.abs(dx) > Math.abs(dy) * 1.5) { if (dx < 0 && page < total) location.hash = go(page + 1); if (dx > 0 && page > 1) location.hash = go(page - 1) } }, { passive: true });
  } else if (view === 'pdf') {
    body.innerHTML = `<iframe class="frame" title="${esc(d.title)}" src="${fileUrl(d.path)}#page=${page}"></iframe><p class="small muted">If the PDF doesn’t show here (some phones can’t), use Page view or open the original file.</p>`;
  } else if (view === 'web') {
    const own = /(^|\/)documents\/lastbook\//.test(d.path);   // Lastbook's own pages (Sources and permissions) take the window's look from the server (engine/saved_pages.py, OWN_LOOK); an older server's stays a white sheet
    body.innerHTML = `<iframe class="frame${own ? ' own' : ''}" title="${esc(d.title)}" src="${fileUrl(d.path)}"></iframe>`;
  } else {
    body.innerHTML = '<p class="loading">Loading text…</p>';
    try {
      const t = await api(`/api/page/${encodeURIComponent(id)}/${isPdf ? page : 1}`);
      const txt = (t.text || '').replace(/[ \t]{2,}/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
      body.innerHTML = `${isPdf || isWeb ? '<div class="notice small">Text pulled out of the original automatically — tables, diagrams and warning boxes can be lost or out of order. Check the Page view for anything important.</div>' : ''}<div class="pagetext">${esc(txt) || '<span class="muted">No text on this page (it may be a picture or blank).</span>'}</div>`;
    } catch (e) { body.innerHTML = errorBox(e, 'Couldn’t load the text.') }
  }
  if (!isPdf) return;
  main.onkeydown = e => {
    if (e.target.tagName === 'INPUT' || e.altKey || e.metaKey || e.ctrlKey || e.shiftKey) return;   // Shift+Arrow selects text
    let next = page;
    if (e.key === 'ArrowRight') next++;
    if (e.key === 'ArrowLeft') next--;
    if (next === page || next < 1 || next > total) return;
    e.preventDefault();
    location.hash = go(next);
  };
  // The router puts focus on this marker before the first Tab.
  if (view !== 'pdf') pageTop.onkeydown = main.onkeydown;
}

/* --------------------------------------------------------------- wiki -- */
const ZIMNAMES = { mdwiki: 'Medical encyclopedia (MDWiki)', wikipedia: 'Wikipedia (text only)', wikibooks: 'Wikibooks — how-to textbooks', appropedia: 'Appropedia — appropriate technology' };
const zimLabel = name => { for (const k in ZIMNAMES) if (name.startsWith(k)) return ZIMNAMES[k]; return name };
async function wiki(path, from, y) {
  const [zim, ...rest] = path.split('/');
  const art = rest.join('/');
  const title = (art.split('/').pop() || '').replace(/_/g, ' ') || zimLabel(zim);   // parse() already decoded each component
  setTitle(title, '', zimLabel(zim));
  const src = '/zim/' + encodeURIComponent(zim) + '/' + art.split('/').map(encodeURIComponent).join('/');
  const selfHref = '#/wiki/' + path.split('/').map(encodeURIComponent).join('/');
  const mainPage = zimMain(zim);
  main.innerHTML = `<div class="rtop">${backButton(from || '#/encyclopedias')}<span id="wsave" class="dock">${saveButton({ key: 'w:' + path, title, href: selfHref, sub: zimLabel(zim) })}</span></div>
    <h1 class="rtitle" id="wtitle">${esc(title)}</h1><div class="rsrc"><span class="zn">${esc(zimLabel(zim))} · </span>Community-written; check safety-critical steps against a manual${IN_WINDOW ? '' : ` · <a id="wopen" href="${src}" target="_blank" rel="noopener">open on its own</a>`}</div>
    <iframe class="frame" id="wframe" title="${esc(title)}" src="${src}"></iframe>`;
  const f = $('#wframe');
  // The toolbar names the encyclopedia, and the article once the article's own title has scrolled up out of the frame, as a large title does
  const barName = () => { const n = f.lbName, b = $('#tbTitle'), t = n && f.contentWindow.scrollY > n.at - 4 ? n.nt : zimLabel(zim); if (b.textContent !== t) b.textContent = b.title = t };
  // One scroller: the frame fills the rest of the window, so the page around it never scrolls as well
  const fit = () => { if (!f.isConnected) return; f.style.height = Math.max(160, innerHeight - (f.getBoundingClientRect().top + scrollY) - parseFloat(getComputedStyle(document.body).paddingBottom || 0)) + 'px' };
  fit(); window.onresize = fit;
  // The frame's scrolling is read from here, every frame while it moves and ten times a second when it rests. The Mac app runs no script in
  // an article, and then no listener on it is ever called, its scroll events included. Once the text goes under the frame's top edge the
  // platform's separator shows there; the toolbar names the article; the reading place is kept for Back; a wide table fades at its edges.
  let lastY = -1, moved = 0;
  const watch = () => {
    if (!f.isConnected) return;
    const fw = f.contentWindow, t = f.lbTidy, now = performance.now();
    if (fw && fw.document.readyState === 'complete') {
      const y = fw.scrollY;
      if (y !== lastY) { lastY = y; moved = now; f.classList.toggle('scrolled', y > 2); scrolls[current] = y; barName() }
      if (t) for (const b of t.boxes) if (b.lbX !== b.scrollLeft) { b.lbX = b.scrollLeft; moved = now; t.edge(b) }
    }
    if (now - moved < 500) requestAnimationFrame(watch); else setTimeout(watch, 100);
  };
  watch();
  let shown = null;
  f.addEventListener('load', async () => {
    try {
      const fd = f.contentDocument;
      lookOf(fd);
      if (!fd.getElementById('lb-article') && !fd.getElementById('lb-host')) {   // an older server adds no look of its own: the window's colour shows through, as engine/saved_pages.py does it
        const st = fd.createElement('style'); st.id = 'lb-host';
        st.textContent = 'html{--background-color-base:transparent!important}html,body,.mw-page-container,.mw-page-container-inner{background:transparent!important}.hatnote,.dablink,.rellink{--background-color-interactive-subtle:transparent!important;background:none!important}';
        (fd.head || fd.documentElement).appendChild(st);
      }
      f.lbTidy = null; try { f.lbTidy = tidyArticle(fd) } catch { }   // the article still reads as it came if this fails
      const fw = f.contentWindow;
      f.lbName = null;
      if (y && shown === null) restoreScroll(current, y, fw);   // Back to this article: its place, once (a link followed inside the frame starts at its top)
      const loc = f.contentWindow.location.pathname, t = fd.title || '';
      const m = /^\/zim\/([^/]+)\/(.*)$/.exec(loc); if (!m) return;
      const p = decodeURIComponent(m[1]) + '/' + m[2].split('/').map(decodeURIComponent).join('/');
      const href = '#/wiki/' + p.split('/').map(encodeURIComponent).join('/');
      const own = fd.querySelector('#firstHeading, h1'), raw = (own && own.textContent.trim()) || t;
      if (!m[2] && !raw) return;   // the bare address, on its way to the front page
      const front = decodeURIComponent(loc) === await mainPage;   // the front page is named by its file, such as App/IntroPage: the encyclopedia's name says it instead
      if (f.contentDocument !== fd) return;
      if (front && own) own.style.setProperty('display', 'none', 'important');   // the skin sets its own display, which the hidden attribute does not beat
      main.classList.toggle('own-title', front);   // then the app's heading names it
      const nt = front ? zimLabel(zim) : raw || p.split('/').pop().replace(/_/g, ' '), sub = front ? 'Encyclopedia' : zimLabel(zim);
      $('#wtitle').textContent = nt; if ($('#wopen')) $('#wopen').href = loc; setTitle(nt, '', zimLabel(zim));
      f.lbName = !front && own ? { nt, at: own.getBoundingClientRect().bottom + fw.scrollY } : null; barName();
      $('#wsave').innerHTML = saveButton({ key: 'w:' + p, title: nt, href, sub });
      fit();
      if (p !== shown) { shown = p; history.replaceState(null, '', href + (from ? '?from=' + encodeURIComponent(from) : '')); remember({ key: 'w:' + p, title: nt, href, sub }) }
    } catch { }
  });
}
// The address an encyclopedia's bare address leads to (a redirect from the server, a refresh page in the Mac app), asked once
const ZMAIN = {};
const zimMain = zim => ZMAIN[zim] || (ZMAIN[zim] = fetch('/zim/' + encodeURIComponent(zim) + '/').then(async r => {
  let u = r.redirected ? r.url : '';
  if (!u) { const m = /http-equiv=["']?refresh["']?[^>]*url=([^"'>]+)/i.exec(await r.text()); if (m) u = new URL(m[1].replace(/&amp;/g, '&').trim(), r.url).href }
  return u ? decodeURIComponent(new URL(u).pathname) : '';
}).catch(() => ''));
// A table wider than the column scrolls sideways inside its own box (.lb-wide, styled by engine/saved_pages.py), so the article never does.
// The box goes around the table, which keeps its table layout: a table made a scrolling block itself turns its width into a fixed one.
// The box fades at an edge with more to scroll to. A list in a table cell is indented when its bullets would fall outside the cell's edge.
// Only with the server's article look, which carries the box's style; an older server's page stays as it came.
function tidyArticle(fd) {
  const fw = fd.defaultView, root = fd.querySelector('.mw-parser-output') || fd.body;
  if (!root || !fd.getElementById('lb-article') || fd.documentElement.dataset.lbTidy) return;
  fd.documentElement.dataset.lbTidy = '-';   // first, so the tables are measured as they will show (the look then undoes the skin's narrow-page blocks)
  const scrolls = e => { for (let a = e.parentElement; a && a !== root; a = a.parentElement) if (fw.getComputedStyle(a).overflowX !== 'visible') return true; return false };
  const boxes = [];
  // A box beside a float would shrink to the room left there (it scrolls, so nothing holds it open), where the table itself would go below
  // the float: the box is held at least as wide as the table can be made, up to the column. A float wider than the column would hang out on
  // the left, where a box cannot scroll to: in its box it is not floated.
  const wrap = (t, cs) => {
    const box = fd.createElement('div'); box.className = 'lb-wide';
    box.style.margin = `${cs.marginTop} 0 ${cs.marginBottom}`;   // the space above and below, which inside the box would no longer meet its neighbours'
    if (cs.clear !== 'none') box.style.clear = cs.clear;
    t.before(box); box.append(t);
    t.style.setProperty('margin-top', '0', 'important'); t.style.setProperty('margin-bottom', '0', 'important');
    if (cs.float !== 'none') { t.style.setProperty('float', 'none', 'important'); t.style.setProperty('margin-left', '0', 'important'); t.style.setProperty('margin-right', '0', 'important') }
    box.style.width = 'min-content'; const least = box.offsetWidth; box.style.width = '';
    box.style.minWidth = `min(100%, ${least}px)`;
    boxes.push(box); return box;
  };
  for (const t of root.querySelectorAll('table')) {
    if (t.parentElement.closest('table,.lb-wide') || scrolls(t)) continue;   // inside another table, or a box that scrolls already (a navbox)
    const cs = fw.getComputedStyle(t);
    if (cs.position === 'absolute' || cs.position === 'fixed' || (cs.float !== 'none' && t.offsetWidth <= root.clientWidth)) continue;   // a floated box that fits (an infobox) stays beside the text
    wrap(t, cs);
  }
  // Anything else still wider than the column (a bar chart, a box of fixed width, a group set inline) gets a box too, now and after a resize.
  const de = fd.documentElement;
  const rest = () => {
    if (de.scrollWidth <= de.clientWidth + 1) return;
    const cw = root.getBoundingClientRect(), out = e => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right > cw.right + 1 || r.left < cw.left - 1) };
    const found = [];
    for (const e of root.querySelectorAll('*')) {
      if (!out(e) || e.closest('.lb-wide') || found.some(f => f.contains(e))) continue;
      const p = e.parentElement; if (p !== root && out(p) && !scrolls(e)) continue;   // its parent is the one to box
      if (scrolls(e) || /^(TD|TH|TR|TBODY|THEAD|CAPTION|LI|SPAN|A|B|I|SUP|SUB)$/.test(e.tagName)) continue;
      const cs = fw.getComputedStyle(e); if (cs.position === 'absolute' || cs.position === 'fixed') continue;
      found.push(e);
    }
    found.forEach(e => { const b = wrap(e, fw.getComputedStyle(e)); edge(b); ro.observe(b) });
  };
  for (const li of root.querySelectorAll('table li')) {
    const s = fw.getComputedStyle(li), list = li.parentElement;
    if (s.display !== 'list-item' || s.listStyleType === 'none' || s.listStylePosition !== 'outside' || list.dataset.lbIn) continue;
    const r = li.getBoundingClientRect(), cell = li.closest('td,th'), c = cell ? cell.getBoundingClientRect() : r, m = parseFloat(s.fontSize) * 1.4;
    const rtl = s.direction === 'rtl', room = rtl ? c.right - r.right : r.left - c.left;
    if (room < m) { list.dataset.lbIn = 1; list.style.setProperty(rtl ? 'margin-right' : 'margin-left', `calc(${fw.getComputedStyle(list)[rtl ? 'marginRight' : 'marginLeft']} + ${Math.ceil(m - room)}px)`) }
  }
  const edge = b => {
    const more = b.scrollWidth - b.clientWidth, s = Math.abs(b.scrollLeft), rtl = fw.getComputedStyle(b).direction === 'rtl';
    b.classList.toggle(rtl ? 'lb-l' : 'lb-r', more > 1 && s < more - 1); b.classList.toggle(rtl ? 'lb-r' : 'lb-l', more > 1 && s > 1);
  };
  const ro = new fw.ResizeObserver(es => es.forEach(e => edge(e.target.closest('.lb-wide'))));
  boxes.forEach(b => { edge(b); ro.observe(b); ro.observe(b.firstElementChild) });   // as a box scrolls, wiki() calls edge (it reads the scroll, see there)
  // What is left of the web page's machinery, which reads as a broken page offline: editing links where the link itself was taken out
  // ('(edit it)', '[edit on Wikidata]'), a template's styles error, a chart's source where the chart would be, an empty paragraph
  // holding only a line break (a gap under the title), and a note's mark written out as its counter ('[lower-alpha 1]' for '[a]').
  const tw = fd.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: n => /edit|<graph|content model|-alpha|-roman/i.test(n.data) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP });
  const gone = [], ab = n => { let s = ''; for (n++; n > 0; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(97 + (n - 1) % 26) + s; return s };
  for (let n; (n = tw.nextNode());) {
    const e = n.parentElement; if (!e || e === root) continue;
    const t = e.textContent.trim();
    if (/^[[(]\s*edit(\s+it|\s+on\s+wikidata)?\s*[\])]$/i.test(t) || (e.matches('.error') && /must have content model/.test(t))) gone.push(e);
    else if (/^<graph>[\s\S]*<\/graph>$/.test(t)) gone.push(e);
    else if (/<graph>[\s\S]*?<\/graph>/.test(n.data)) n.data = n.data.replace(/<graph>[\s\S]*?<\/graph>/g, '');
    else if (e.closest('sup.reference')) { const m = /^(lower|upper)-(alpha|roman) (\d+)$/.exec(n.data.trim()); if (m) { const k = +m[3], s = m[2] === 'alpha' ? ab(k - 1) : roman(k); n.data = m[1] === 'upper' ? s.toUpperCase() : s } }
  }
  for (const p of root.querySelectorAll('p')) if (!p.textContent.trim() && !p.querySelector('img,svg,video,audio,iframe,input,math,object')) gone.push(p);
  gone.forEach(e => e.style.setProperty('display', 'none', 'important'));
  rest(); let rt = 0; new fw.ResizeObserver(() => { clearTimeout(rt); rt = setTimeout(rest, 200) }).observe(root);
  fd.documentElement.dataset.lbTidy = boxes.length;
  return { boxes, edge };   // boxes: also those rest() adds later
}
const roman = n => { let s = ''; for (const [v, r] of [[1000, 'm'], [900, 'cm'], [500, 'd'], [400, 'cd'], [100, 'c'], [90, 'xc'], [50, 'l'], [40, 'xl'], [10, 'x'], [9, 'ix'], [5, 'v'], [4, 'iv'], [1, 'i']]) for (; n >= v; n -= v) s += r; return s };
// The article's stylesheet (engine/saved_pages.py) reads these: the window's text colours and its accent, which only this page knows
// (the system accent in the apps, Lastbook green in a browser).
function lookOf(fd) {
  const cs = getComputedStyle(html), r = fd.documentElement.style;
  const probe = document.createElement('i'); probe.style.color = 'var(--accent)'; probe.hidden = true; document.body.append(probe);
  r.setProperty('--lb-link', getComputedStyle(probe).color); probe.remove();
  for (const [k, v] of [['--lb-ink', '--ink'], ['--lb-ink2', '--ink2'], ['--lb-line', '--line2'], ['--lb-font', '--font'], ['--lb-display', '--display']]) { const x = cs.getPropertyValue(v).trim(); if (x) r.setProperty(k, x) }
}
const ZIMS = [['mdwiki_en_all_maxi_2025-11.zim', 'Medical encyclopedia', 'MDWiki: plain-language articles on conditions, medicines and first aid.', 'health'],
['wikibooks_en_all_maxi_2026-04.zim', 'Wikibooks', 'Open textbooks and how-to manuals, from cooking to electronics.', 'book'],
['appropedia_en_all_maxi_2026-02.zim', 'Appropedia', 'Appropriate technology: water, sanitation, energy and building projects.', 'repair'],
['wikipedia_en_all_nopic_2026-06.zim', 'Wikipedia', 'The full English encyclopedia, text only (no pictures).', 'wiki']];
const zimsHere = async () => { const here = (await libInfo()).zims; return here ? ZIMS.filter(z => here.includes(z[0])) : ZIMS };
async function encyclopedias(q) {
  setTitle('Encyclopedias');
  const me = routeSeq, zims = await zimsHere();
  if (stale(me)) return;
  if (!zims.length) { main.innerHTML = `<h1>Encyclopedias</h1><p class="lead">This download has no encyclopedias.</p>`; return }
  main.innerHTML = `<h1>Encyclopedias</h1><p class="lead">${['', 'One complete encyclopedia', 'Two complete encyclopedias', 'Three complete encyclopedias', 'Four complete encyclopedias'][zims.length]}. Community-written: good for background — use the guides’ manuals for safety-critical steps.</p>
  <div style="margin:16px 0">${searchBox('zq', q, 'e.g. tetanus, solar panel, sourdough')}</div><div id="zres"></div>
  ${secHead('Open one')}<div class="cards2">${zims.map(z => `<a class="card" href="#/wiki/${z[0]}/?from=${encodeURIComponent('#/encyclopedias')}"><span class="ico">${ico(z[3])}</span><b>${esc(z[1])}</b><small>${esc(z[2])}</small></a>`).join('')}</div>`;
  $('#zqF').addEventListener('submit', e => { e.preventDefault(); location.hash = '#/encyclopedias?q=' + encodeURIComponent($('#zq').value.trim()) });
  if (q) zimResults(q, $('#zres'), 40);
}
// heading: part of a wider search, shown under that heading only when something matched. Answers whether anything did.
async function zimResults(q, el, max = 8, heading = '') {
  el.innerHTML = heading ? '' : '<p class="loading">Searching the encyclopedias…</p>';
  try {
    const hits = await api('/api/collection-search?q=' + encodeURIComponent(q) + langQ());
    if (!hits.length) { el.innerHTML = heading ? '' : `<div class="empty"><span class="e-ico">${ico('wiki')}</span><b>No articles found</b><p>Try another word for the same thing.</p></div>`; return false }
    const ord = ['mdwiki', 'wikibooks', 'appropedia', 'wikipedia'];
    hits.sort((a, b) => ord.findIndex(k => a.collection.startsWith(k)) - ord.findIndex(k => b.collection.startsWith(k)));
    el.innerHTML = `${heading ? `<h2>${heading}</h2>` : ''}<ul class="list">${hits.slice(0, max).map(h => `<li><a class="row" href="#/wiki/${esc(h.path.replace(/^zim\//, ''))}?${fromQ()}"><span class="k">${ico('wiki')}</span><span><b>${esc(h.title)}</b><small>${esc(zimLabel(h.collection))}</small></span></a></li>`).join('')}</ul>`;
    return true;
  } catch (e) { el.innerHTML = heading ? '' : `<p class="muted">Encyclopedia search isn’t available right now (${esc(e.message)}).</p>`; return false }
}

/* ------------------------------------------------------------- search -- */
// A guide word only has to start with a search word, so she, her and his would find shelter, here and hissing.
const QSTOP = new Set('a an and are can do does for from get got have how i if in is it its me my need no not of on or our so that the this to was we what when where which who why will with without you your won don can t s she her hers his him'.split(' '));
// Words are split, folded and matched by web/words.js (loaded first), so accents, Chinese and other scripts work.
// Dutch function words, for a search typed in Dutch: "wat" would otherwise find "water" and "het" "hete".
const QSTOP_NL = new Set([...QSTOP, ...'ik je jij jou jouw hij zij ze we wij mijn ons onze het de een en of op aan bij van voor met naar om uit tot door over als dan dat die dit deze er wat wie waar hoe welke waarom wanneer is zijn was wordt heb hebt heeft hebben kan kun kunt moet moeten mag wil ga gaat doe doen niet wel ook nog maar al zo nu heel erg veel meer iets iemand mij me zich'.split(' ')]);
function topicMatches(q) {
  if (typeof SearchWords === 'undefined') return [];
  if (uiLang() !== 'nl') return SearchWords.rankTopics(q, TOPICS, QSTOP);
  // "wc" is the everyday Dutch word for a toilet, but two letters are too short for the search to count.
  return SearchWords.rankTopics(q.replace(/(^|[^\p{L}])wc(?=$|[^\p{L}])/giu, '$1toilet'), TOPICS, QSTOP_NL);
}
// The interface language for the server's searches: a Dutch search is looked up in the English words the manuals use.
const langQ = () => uiLang() === 'en' ? '' : '&lang=' + encodeURIComponent(uiLang());
let searchSeq = 0;
async function searchPage(q, kind) {
  setTitle(q ? 'Search: ' + q : 'Search');
  const kinds = [['all', 'Everything'], ['read', 'Manuals & pages'], ['video', 'Videos'], ['wiki', 'Encyclopedias']];
  main.innerHTML = `<h1>${q ? 'Results' : 'Search'}</h1>
  ${searchBox('searchQ', q, 'Describe it in everyday words')}
  <div class="chips" role="group" aria-label="Show" style="margin-top:12px" id="kinds">${kinds.map(([k, l]) => `<a class="chip ${k === kind ? 'on' : ''}" aria-pressed="${k === kind}" data-kind="${k}" href="#/search?q=${encodeURIComponent(q)}&kind=${k}">${l}</a>`).join('')}</div>
  <div id="sask"></div><div id="sout"></div>`;
  i18n?.apply(main);
  const input = $('#searchQ');
  $('#searchQF').addEventListener('submit', e => { e.preventDefault(); input.blur(); go(input.value.trim(), true) });
  let tmr;
  input.addEventListener('input', () => { clearTimeout(tmr); tmr = setTimeout(() => go(input.value.trim(), false), 350) });
  // as-you-type: update results and the address; a new search is one new history entry, not one per keystroke
  let fresh = true;   // the next change starts a new entry
  function go(nq, commit) {
    const h = '#/search?q=' + encodeURIComponent(nq) + (kind !== 'all' ? '&kind=' + kind : '');
    if (nq === q) { if (commit) fresh = true; return }
    if (fresh) pushHere(h); else history.replaceState(null, '', h);
    fresh = !!commit; q = nq; if (input.value !== nq) input.value = nq;
    $$('#kinds a').forEach(a => a.href = `#/search?q=${encodeURIComponent(nq)}&kind=${a.dataset.kind}`);
    askOffer(nq); results(nq, kind);
  }
  searchLive = (nq, commit, typing) => { clearTimeout(tmr); if (typing) tmr = setTimeout(() => go(nq, false), 350); else go(nq, commit) };
  setTimeout(() => { $('#topQ').value = q }, 0);   // after the router clears it: on Windows the pane's field is this page's field
  askOffer(q); results(q, kind);
  if (!q) setTimeout(() => findBox().focus(), 50);
}
function askOffer(q) {
  const el = $('#sask'); if (!el) return;
  el.innerHTML = q && q.split(/\s+/).length >= 2 ? `<a class="ghit" href="#/ask?q=${encodeURIComponent(q)}" style="--tc:var(--accent)"><span class="ico">${ico('ask')}</span><span><b>Ask the library: “${esc(q)}”</b><small>Get a written answer with the exact pages it came from</small></span></a>` : '';
}
async function results(q, kind) {
  const seq = ++searchSeq, out = $('#sout');
  if (!q) {
    out.innerHTML = `<p class="muted" style="margin-top:18px">Use the words you’d use with a friend. For example:</p><div class="chips wrapchips">${['clean drinking water', 'broken leg', 'carbon monoxide', 'keep food cold', 'ham radio license', 'plant potatoes', 'sharpen a knife', 'diarrhea in a child'].map(x => `<a class="chip" href="#/search?q=${encodeURIComponent(x)}">${esc(x)}</a>`).join('')}</div>`;
    return;
  }
  const g = kind === 'all' ? topicMatches(q) : [];
  out.innerHTML = `${g.length ? `<h2 data-i18n="search.startWithGuide">Start with a guide</h2>${g.map(({ t, c }) => `<a class="ghit" href="#/t/${t.id}${c ? '/' + c.id : ''}" ${tcStyle(t.id)}><span class="ico">${ico(t.id)}</span><span><b>${esc(tname(t))}${c ? ' — ' + esc(c.label) : ''}</b><small data-i18n="search.guideNote">Picked pages with exact page numbers and safety limits</small></span></a>`).join('')}` : ''}
    <div id="spass"></div><div id="svid"></div><div id="sres"></div><div id="szim"></div>`;
  translateRendered(out);
  if (kind === 'wiki') return zimResults(q, $('#szim'), 40);
  // Each part answers whether it found anything; "nothing matched" shows once, only when none did.
  const parts = kind === 'all' || kind === 'read' ? [passages(q, seq)] : [];
  const reqs = [api('/api/find?q=' + encodeURIComponent(q) + '&kind=' + (kind === 'video' ? 'video' : 'read') + langQ())];
  if (kind === 'all') reqs.push(api('/api/find?q=' + encodeURIComponent(q) + '&kind=video' + langQ()).catch(() => null));
  $('#sres').innerHTML = '<p class="loading">Searching…</p>';
  const found = (async () => {
    try {
      const [d, vd] = await Promise.all(reqs);
      if (seq !== searchSeq) return true;
      const vids = (kind === 'video' ? d : vd)?.results || [];
      if (kind === 'video') { $('#sres').innerHTML = vids.length ? `<div class="vgrid" style="margin-top:14px">${vids.map(r => vcard(r)).join('')}</div>` : ''; return vids.length > 0 }
      if (vids.length) { $('#svid').innerHTML = secHead('Videos', '', `<a href="#/search?q=${encodeURIComponent(q)}&kind=video">See all</a>`) + rail(vids.slice(0, 10).map(r => vcard(r)).join('')); translateRendered($('#svid')); wireRails($('#svid')) }
      $('#sres').innerHTML = d.results.length ? `<h2>In the manuals and saved pages</h2>
        ${d.english ? `<p class="small muted" data-i18n="search.inEnglish" data-i18n-query="${esc(d.english)}">Searched the English manuals for “${esc(d.english)}”</p>` : ''}
        ${d.expanded.length ? `<p class="small muted">Also looked for: ${d.expanded.slice(0, 10).map(esc).join(', ')}${d.mode === 'some words' ? ' · showing pages with some of your words' : ''}</p>` : ''}
        <div class="results">${d.results.map(resultCard).join('')}</div>` : '';
      i18n?.apply($('#sres'), el => el.dataset.i18nQuery ? { query: el.dataset.i18nQuery } : undefined);
      return d.results.length + vids.length > 0;
    } catch (e) { if (seq === searchSeq) $('#sres').innerHTML = errorBox(e, 'Search isn’t responding.') + '<p class="small muted">The library may be busy rebuilding its index. Try again in a minute.</p>'; return true }
  })();
  parts.push(found);
  if (kind === 'all') parts.push(found.then(() => seq === searchSeq && zimResults(q, $('#szim'), 6, 'In the encyclopedias')));
  const any = (await Promise.all(parts)).some(Boolean);
  if (seq === searchSeq && !g.length && !any) { $('#sres').innerHTML = emptySearch(q); offerNote(q) }
}
// Most relevant pages from the shared keyword + meaning-based retriever (the same one the assistant uses).
async function passages(q, seq) {
  try {
    const d = await api('/api/retrieve?q=' + encodeURIComponent(q) + '&k=6&kind=manual' + langQ());
    if (seq !== searchSeq || !d.results.length || !$('#spass')) return false;
    $('#spass').innerHTML = secHead('Most relevant pages', d.semantic && !d.semantic.chunks ? 'Matched by your words' : 'Matched by meaning as well as by words') + `<div class="rcards">${d.results.map(r => rcard({ src: { id: r.doc_id, kind: r.kind, title: r.title, publisher: r.publisher, year: r.year, pages: r.pages, trust: r.trust }, page: r.page, label: r.title, note: (r.excerpt || '').slice(0, 220) + '…' })).join('')}</div>`;
    return true;
  } catch { return false }
}
const emptySearch = q => `<div class="empty"><span class="e-ico">${ico('search')}</span><b>No results for “${esc(q)}”</b><p>Try fewer words, or another word for the same thing.</p><div id="noteOffer"></div></div>`;
/* Things I couldn't find (#116, engine/notes.py): when a search finds nothing, the person may keep a note of it, on this computer
   only. Nothing is kept unless they press the button. The engine answers only this computer, so elsewhere nothing is offered. */
let notesOpen = null;
const notesHere = () => notesOpen || (notesOpen = api('/api/not-found').then(() => true, () => { notesOpen = null; return false }));
function guideBefore() {   // the guide the person searched from, if any: the page before this run of searches
  for (let i = navAt - 1; i >= 0; i--) {
    const h = navStack[i] || '';
    if (h.startsWith('#/search')) continue;
    const m = h.match(/^#\/t\/([^/?]+)/);
    return m ? decodeURIComponent(m[1]) : null;
  }
  return null;
}
async function offerNote(q) {
  if (!(await notesHere())) return;
  const el = $('#noteOffer'); if (!el || !q) return;
  const guide = guideBefore(), t = guide && topicById(guide);
  el.innerHTML = `<p class="e-act"><button class="btn plain" id="keepNote">Keep a note of this</button></p>
    <p class="small muted">Saves “${esc(q)}”${t ? ` and the ${esc(tname(t))} guide` : ''} on this computer only, under Library → <a href="#/not-found">Things I couldn’t find</a>. Nothing is sent anywhere.</p>`;
  $('#keepNote').onclick = async () => {
    const b = $('#keepNote'); b.disabled = true;
    try {
      await api('/api/not-found', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ words: q, guide }) });
      el.innerHTML = `<p class="small" role="status">Kept. It’s in Library → <a href="#/not-found">Things I couldn’t find</a>, where you can delete it.</p>`;
    } catch (e) { b.disabled = false; el.insertAdjacentHTML('beforeend', `<p class="small" role="alert">${esc(e.message)}</p>`) }
  };
}
function resultCard(r) {
  const base = { src: r };
  return `<article class="result"><h3><a href="${hrefFor({ ...base, page: r.hits[0] && r.hits[0].page })}">${esc(r.title)}</a></h3>
    <div class="rsrc">${srcText(r)} · ${esc(r.trust)}</div>
    ${r.hits.slice(0, 2).map(h => `<a class="hit" href="${hrefFor({ ...base, page: h.page })}">${h.page ? `<b>Page ${h.page}:</b> ` : ''}${h.snippet}</a>`).join('')}</article>`;
}

/* ------------------------------------------------------------ library -- */
async function library() {
  setTitle('Library');
  const saved = store.get('saved', []).length, chats = (window.Chat ? Chat.count() : 0);
  const me = routeSeq, zims = await zimsHere();
  if (stale(me)) return;   // the person has gone to another page
  main.innerHTML = `<h1>Library</h1><p class="lead">Your saved things, learning routes, encyclopedias and every manual in the collection.</p>
  <div class="cards2 three" style="margin-top:16px">
    <a class="card" href="#/saved"><span class="ico">${ico('save')}</span><b>Saved</b><small>${saved ? saved + ' saved item' + (saved > 1 ? 's' : '') : 'Pages, videos and answers you keep'} on this device</small></a>
    <a class="card" href="#/ask"><span class="ico">${ico('ask')}</span><b>Chats</b><small>${chats ? chats + ' saved conversation' + (chats > 1 ? 's' : '') : 'Ask the library a question'}</small></a>
    <a class="card" href="#/prepare"><span class="ico">${ico('prep')}</span><b>Prepare your household</b><small>Getting-ready readings from every guide</small></a>
    <a class="card" href="#/not-found" id="nfCard" hidden><span class="ico">${ico('search')}</span><b>Things I couldn’t find</b><small id="nfCount">Notes you kept when a search found nothing</small></a>
  </div>
  ${secHead('<span data-i18n="guide.learnSkill">Learn a skill</span>', 'Step-by-step routes that start simple')}
  <div class="needs">${learnTopics().map(t => `<a class="need" href="#/t/${t.id}" ${tcStyle(t.id)}><span class="ico">${ico(t.id)}</span><b>${esc(tname(t))}</b><small>${esc(t.short || '')} · ${(t.route || []).length} steps</small></a>`).join('')}</div>
  ${zims.length ? secHead('Encyclopedias', 'Complete offline copies', '<a href="#/encyclopedias">Search them</a>') + `<div class="cards2">${zims.map(z => `<a class="card" href="#/wiki/${z[0]}/?from=${encodeURIComponent('#/library')}"><span class="ico">${ico(z[3])}</span><b>${esc(z[1])}</b><small>${esc(z[2])}</small></a>`).join('')}</div>` : ''}
  ${secHead('Browse by subject', 'Every manual, saved web page and video')}<div id="shelves"><p class="loading">Loading…</p></div>
  <p style="margin-top:20px"><a href="#/about">About this library and its sources</a>${IN_WINDOW ? ' · <a href="/ui/setup.html#manage">Library and local AI</a>' : ''}</p>`;
  translateRendered();
  if (await notesHere()) api('/api/not-found').then(d => {
    const c = $('#nfCard'); if (!c) return;
    c.hidden = false;
    if (d.notes.length) $('#nfCount').textContent = `${d.notes.length} note${d.notes.length > 1 ? 's' : ''} on this computer`;
  }).catch(() => { });
  try {
    const sh = await api('/api/shelves');
    if (stale(me)) return;
    $('#shelves').innerHTML = sh.filter(s => s.read + s.video).map(s => `<a class="shelfrow" href="#/shelf/${s.id}"><span><b>${esc(s.title)}</b><small>${s.read ? s.read.toLocaleString() + ' to read' : ''}${s.read && s.video ? ' · ' : ''}${s.video ? s.video.toLocaleString() + ' videos' : ''}</small></span>${ico('right')}</a>`).join('');
  } catch (e) { if (!stale(me)) $('#shelves').innerHTML = errorBox(e) }
}
async function prepareHub() {
  setTitle('Prepare your household');
  const list = nowTopics().filter(t => (t.prepare || []).length);
  main.innerHTML = `<h1>Prepare your household</h1>
  <p class="lead">Readings for getting ready before water, power or services stop — gathered from each guide. One area at a time.</p>
  <div class="notice">A shopping list or cart isn’t the same as supplies you own, and reading isn’t the same as a practised plan.</div>
  ${list.map(t => `<details class="more" ${tcStyle(t.id)}><summary><span class="prep-ico">${ico(t.id)}</span><span>${esc(tname(t))} <span class="n">· ${t.prepare.length}</span></span></summary><div class="body"><ul class="list">${t.prepare.map(i => rowItem({ ...i, preview: true })).join('')}</ul><p><a href="#/t/${t.id}">Open the full guide</a></p></div></details>`).join('')}`;
}
async function shelfPage(id, kind, q) {
  const me = routeSeq, sh = (await api('/api/shelves')).find(s => s.id === id);
  if (stale(me)) return;   // the person has gone to another page
  if (!sh) return notFound();
  setTitle(sh.title);
  main.innerHTML = `${backButton('#/library')}${crumbs([['Library', '#/library'], [sh.title]])}<h1>${esc(sh.title)}</h1>
  <div style="margin:14px 0 10px">${searchBox('shq', q, 'Filter by title or publisher', ['search.filter', 'Filter'])}</div>
  <div class="chips">${[['all', 'Everything'], ['read', 'To read'], ['video', 'Videos']].map(([k, l]) => `<a class="chip ${k === kind ? 'on' : ''}" href="#/shelf/${id}?kind=${k}&q=${encodeURIComponent(q)}">${l}</a>`).join('')}</div><div id="shres"><p class="loading">Loading…</p></div>`;
  $('#shqF').addEventListener('submit', e => { e.preventDefault(); location.hash = `#/shelf/${id}?kind=${kind}&q=` + encodeURIComponent($('#shq').value.trim()) });
  let off = 0;
  const load = async () => {
    const d = await api(`/api/shelf/${id}?kind=${kind}&q=${encodeURIComponent(q)}&offset=${off}`);
    if (stale(me)) return;
    const html = d.collections.map(c => `<section class="collection"><h3>${esc(c.collection)}</h3><div class="small muted">${esc(c.trust)} · ${c.count} item${c.count > 1 ? 's' : ''}</div><ul class="list">${c.items.map(r => rowItem({ src: r })).join('')}</ul>${c.count > c.items.length ? `<a class="btn ghost" href="#/collection?name=${encodeURIComponent(c.collection)}&${fromQ()}">See all ${c.count}</a>` : ''}</section>`).join('');
    if (!off) $('#shres').innerHTML = d.collections.length ? '' : '<div class="empty">Nothing here matches. Try another word.</div>';
    $('#shres').insertAdjacentHTML('beforeend', html);
    $('#moreb')?.remove();
    if (d.more) { $('#shres').insertAdjacentHTML('beforeend', '<p><button class="btn plain" id="moreb">Show more</button></p>'); $('#moreb').onclick = () => { off += 40; load() } }
  };
  await load();
}
async function collectionPage(name, from) {
  setTitle(name);
  main.innerHTML = `<div>${backButton(from, ['nav.library', 'Library'])}</div><h1 style="margin-top:12px">${esc(name)}</h1><ul class="list collection" id="cl"></ul><div id="cm"></div>`;
  let off = 0;
  const me = routeSeq, load = async () => {
    const d = await api('/api/collection?name=' + encodeURIComponent(name) + '&offset=' + off);
    if (stale(me)) return;
    $('#cl').insertAdjacentHTML('beforeend', d.items.map(r => rowItem({ src: r })).join(''));
    $('#cm').innerHTML = d.more ? '<button class="btn plain" id="cmb">Show more</button>' : '';
    if (d.more) $('#cmb').onclick = () => { off += 60; load() };
  };
  await load();
}

/* -------------------------------------------------------------- saved -- */
async function savedPage() {
  setTitle('Saved');
  const me = routeSeq;
  let all = [], savedError = '';
  try { all = VideoMoments.readSaved() } catch (e) { savedError = e.message }
  const moments = all.filter(VideoMoments.isMoment);
  const s = all.filter(x => x && x.kind !== 'video-moment'), r = await recents();
  const li = x => `<li><a class="row" href="${esc(x.href)}"><span class="k">${ico(x.key[0] === 'v' ? 'video' : x.key[0] === 'w' ? 'wiki' : x.key[0] === 't' ? 'book' : x.key[0] === 'a' ? 'ask' : 'page')}</span><span><b>${esc(x.title)}</b><small>${esc(rowSub(x))}</small></span></a></li>`;
  const cont = await resumable();
  const available = new Set(await held([...new Set(moments.map(x => x.videoId))]));
  if (stale(me)) return;
  main.innerHTML = `<h1>Saved</h1><p class="lead">Kept on this device only.</p>
  ${savedError ? `<div class="err" role="alert">${esc(savedError)}</div>` : moments.length ? momentSection() : ''}
  ${s.length ? `<div class="collection" style="margin-top:18px"><ul class="list">${s.map(li).join('')}</ul></div>` : !moments.length && !savedError ? `<div class="empty"><span class="e-ico">${ico('save')}</span><b>Nothing saved yet</b><p>Choose Save on any page, video, article or answer to keep it here.</p></div>` : ''}
  ${cont.length ? secHead('Continue watching') + rail(cont.map(([id, v]) => vcard({ id, title: v.title, thumb: v.thumb, duration: v.d }, { sub: 'Resume at ' + clock(v.t) })).join('')) : ''}
  ${secHead('Recently opened')}${r.length ? `<div class="collection"><ul class="list">${r.map(li).join('')}</ul></div><p><button class="btn plain" id="clr">Clear recent list</button></p>` : '<div class="empty"><p>Pages you open will appear here.</p></div>'}`;
  if (moments.length) wireMoments({ available });
  const c = $('#clr'); if (c) c.onclick = () => { store.set('recent', []); savedPage() };
}

// Library → Things I couldn't find: the person's own notes, each with Delete, and Delete all (asked first)
async function notFoundPage(confirmAll) {
  setTitle('Things I couldn’t find');
  const me = routeSeq;
  let notes;
  try { notes = (await api('/api/not-found')).notes } catch (e) {
    if (!stale(me)) main.innerHTML = `<h1>Things I couldn’t find</h1>${errorBox(e)}`; return }
  if (stale(me)) return;   // the person has gone to another page
  const day = s => { const d = new Date(s + 'T12:00:00'); return isNaN(d) ? s : d.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' }) };
  const li = n => { const t = n.guide && topicById(n.guide);
    return `<li class="row nf"><span class="k">${ico('search')}</span><span><b>“${esc(n.words)}”</b><small>${t ? `From the ${esc(tname(t))} guide · ` : ''}${esc(day(n.at))}</small></span><button class="btn plain" data-del="${esc(n.id)}" aria-label="Delete the note “${esc(n.words)}”">Delete</button></li>` };
  main.innerHTML = `<h1>Things I couldn’t find</h1><p class="lead">Notes you chose to keep when a search found nothing. They stay on this computer, and nothing is sent anywhere.</p>
    ${notes.length ? `<div class="collection" style="margin-top:18px"><ul class="list">${notes.slice().reverse().map(li).join('')}</ul></div>
      <p>${confirmAll ? `<span>${notes.length === 1 ? 'Delete this note?' : `Delete all ${notes.length} notes?`}</span> <button class="btn danger" id="nfYes">Delete all</button> <button class="btn plain" id="nfNo">Keep them</button>` : '<button class="btn plain" id="nfAll">Delete all</button>'}</p>`
      : `<div class="empty"><span class="e-ico">${ico('search')}</span><b>No notes</b><p>When a search finds nothing, you can keep a note of it here, to remember what the library was missing.</p></div>`}`;
  $$('[data-del]', main).forEach(b => b.onclick = async () => {
    b.disabled = true;
    try { await api('/api/not-found/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: b.dataset.del }) }) } catch { }
    await notFoundPage(); const f = $('[data-del]', main) || $('h1', main); if (f) f.focus();
  });
  if ($('#nfAll')) $('#nfAll').onclick = async () => { await notFoundPage(true); $('#nfNo').focus() };
  if ($('#nfNo')) $('#nfNo').onclick = async () => { await notFoundPage(); $('#nfAll').focus() };
  if ($('#nfYes')) $('#nfYes').onclick = async () => {
    try { await api('/api/not-found/delete-all', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }) } catch { }
    await notFoundPage();
  };
}

/* -------------------------------------------------------------- about -- */
// What the assistant cannot read, as a sentence: counts of none are left out, and one is one
const many = (n, one, more) => `${n.toLocaleString()} ${n === 1 ? one : more}`;
function blind(c) {
  if (!c) return '';
  const nv = c.videos - c.videos_with_text, parts = [];
  if (nv) parts.push(`${nv.toLocaleString()} of ${many(c.videos, 'video', 'videos')} ${nv === 1 ? 'has' : 'have'} no captions or transcript`);
  if (c.pdfs_image_only) parts.push(`${many(c.pdfs_image_only, 'PDF is a scan', 'PDFs are scans')} without text`);
  if (c.docs_without_text) parts.push(`${many(c.docs_without_text, 'document', 'documents')} gave no readable text when indexed`);
  if (!parts.length) return '';
  const t = parts.length > 1 ? parts.slice(0, -1).join(', ') + ' and ' + parts[parts.length - 1] : parts[0];
  return t[0].toUpperCase() + t.slice(1) + '. ';
}
// The optional local AI in the desktop app: what it is, where it runs, and its controls. '' in the server version.
function localAbout(st) {
  const l = st.local; if (!l) return '';
  const gb = n => (n / 1e9).toFixed(1) + ' GB';
  const where = (l.placement || []).filter(p => p.bytes > 2e8).map(p => `${gb(p.bytes)} on ${esc(p.device)}`).join(', ');
  const line = { ready: 'running now', stopped: 'available; your first question loads it and may take a while; it stops after 15 minutes unused', loading: 'starting' }[l.state];
  const btn = (a, t) => `<button class="btn plain" onclick="localAI('${a}')">${t}</button>`;
  return line ? `Local AI: ${esc(l.name)}, ${line}.${where ? ` It uses ${where}.` : ''} It reads text only.
      <span class="row">${l.state === 'ready' ? btn('stop', 'Stop it now') : ''}${btn('off', 'Turn off')}</span>`
    : l.state === 'off' ? `The local AI is turned off. ${btn('on', 'Turn on')}`
    : `Local AI: ${esc(l.message || { absent: 'not added. Add it in Library and local AI (about 17 GB).', checking: 'checking the file…', measuring: 'checking this computer’s memory…' }[l.state] || l.state)} ${l.state === 'absent' ? '<a class="btn plain" href="/ui/setup.html#manage">Add the local AI</a>' : ''}${btn('rescan', 'Look again')}`;
}
async function localAI(action) {
  try { await fetch('/api/assistant/local', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action }) }) } catch { }
  setTimeout(() => { if (location.hash.startsWith('#/about')) route() }, 400);
}

function contributePage() {
  setTitle('Contribute to Lastbook');
  main.innerHTML = `<section class="contribute">
    <h1 data-i18n="contribute.title">Contribute to Lastbook</h1>
    <p class="lead" data-i18n="contribute.welcome">We’re building Lastbook together. We need you.</p>
    <p class="contribute-help" data-i18n="contribute.help">Describe one idea and copy the prompt into your AI. You can review the change before it opens a pull request.</p>
    <div class="card contribute-card">
      <label for="contrib-idea"><span data-i18n="contribute.idea">Your idea</span> <span class="muted" data-i18n="contribute.optional">(optional)</span></label>
      <input id="contrib-idea" type="text" maxlength="300" placeholder="Example: Make offline map labels easier to read" data-i18n-placeholder="contribute.example">
      <label for="contrib-prompt" data-i18n="contribute.prompt">Prompt for your AI</label>
      <textarea id="contrib-prompt" rows="6" spellcheck="false"></textarea>
      <div class="contribute-actions">
        <button class="btn" id="copy-contrib" type="button" data-i18n="contribute.copy">Copy prompt</button>
        <a class="contribute-link" id="github-contrib" href="/contribute/github" target="_blank" rel="noopener"><span data-i18n="contribute.github">Open GitHub</span> <span aria-hidden="true">↗</span></a>
      </div>
      <p class="small muted contribute-note" data-i18n="contribute.local">Your idea stays on this device until you share it.</p>
      <p role="status" class="small" id="contrib-status"></p>
    </div>
  </section>`;
  const idea = $('#contrib-idea'), prompt = $('#contrib-prompt'), status = $('#contrib-status');
  const sync = () => {
    prompt.value = 'Read CONTRIBUTING.md in github.com/Immortal-Protocols/lastbook.\n\n'
      + (idea.value.trim() ? 'Make one focused change in a fork: ' + idea.value.trim()
         : 'Help me choose a small improvement and make one focused change in a fork.')
      + '\n\nRun the relevant tests and prepare a pull request. Explain what changed and what you tested. Wait for my approval before opening the PR.';
  };
  sync();
  idea.addEventListener('input', sync);
  $('#copy-contrib').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(prompt.value);
      status.dataset.i18n = 'contribute.copiedMessage';
      status.textContent = 'Prompt copied.';
      $('#copy-contrib').dataset.i18n = 'contribute.copied';
      $('#copy-contrib').textContent = 'Copied';
      translateRendered();
    } catch {
      prompt.focus();
      prompt.select();
      status.dataset.i18n = 'contribute.copyFallback';
      status.textContent = 'Prompt selected. Press your copy shortcut.';
      translateRendered(status);
    }
  });
}

async function about(showUpdate) {
  setTitle('About this library');
  let dl = {}, st = {};
  LIB = null;   // About shows the counts as they are now
  const me = routeSeq, s = await libInfo();
  const oldServer = s.zims === undefined;   // it still serves the reports; this code does not
  try { dl = await api('/api/download-status') } catch { }
  try { st = await fetch('/api/assistant/status').then(r => r.json()) } catch { }   // not api(): this answer names an error when no model is running, and still holds what is wanted
  if (stale(me)) return;
  const ch = dl.channels && dl.channels.counts, ix = st.index || {};
  const updateCard = IN_WINDOW && window.LBUpdate ? LBUpdate.card() : '';
  main.innerHTML = `<h1>About this library</h1>
  <p class="lead">Public manuals, health guides, courses, videos and encyclopedias kept on this computer, so it works when the internet and phones don’t.</p>
  <div class="cards2" style="margin-top:16px">
   ${showUpdate ? updateCard : ''}
   <div class="card"><b>What’s in it</b><small>${(s.pdfs || 0).toLocaleString()} PDF manuals (${(s.pdf_pages || 0).toLocaleString()} pages), ${(s.web_pages || 0).toLocaleString()} saved web pages, ${(s.videos || 0).toLocaleString()} downloaded videos and ${s.collections || 0} complete encyclopedias.</small></div>
   ${ch ? `<div class="card"><b>Still arriving</b><small>${ch.pending.toLocaleString()} more videos are queued and ${ch.downloading} downloading. Queued videos are not in the library yet — they appear only once downloaded.</small></div>` : ''}
   <div class="card"><b>Assistant</b><small>${localAbout(st) || (st.server ? `Model server on this computer: ${esc(st.server.model)} at ${esc(st.server.address)}, ${st.online ? 'available' : 'not answering'}. Change it in Library and local AI.` : st.online ? `Local model ${esc(st.model)} — available.` : 'No local model is running, so Chat can’t write answers right now. Guides, search, videos and the map all work without one.')} ${ix.chunks ? `Meaning-based index: ${ix.chunks.toLocaleString()} passages from ${ix.docs.toLocaleString()} documents${ix.pending ? `, ${ix.pending.toLocaleString()} still to index` : ''}.` : ''}</small></div>
   <div class="card"><b>What the assistant can’t see</b><small>${blind(st.coverage)}It also can’t see pictures in videos or raw map data. It reads text${st.vision === false ? '' : ' (and page images when it asks to)'} and says when it finds nothing.${st.coverage && st.coverage.remote_videos ? ` ${st.coverage.remote_videos} videos are stored on a remote drive and play only when that computer is reachable.` : ''}</small></div>
   ${showUpdate ? '' : updateCard}
  </div>
  <h2>How sources are labelled</h2><ul>
   <li><b>International health &amp; humanitarian guidance</b> — WHO, Red Cross / Red Crescent, MSF, UNICEF, Sphere, St John Ambulance.</li>
   <li><b>Hesperian community health guide</b> — “Where There Is No Doctor” and related books.</li>
   <li><b>Government guidance</b> — FEMA, CDC, EPA, USDA, NOAA, National Park Service and similar.</li>
   <li><b>University / extension service</b> — e.g. National Center for Home Food Preservation, UC extension.</li>
   <li><b>Manufacturer manual</b> — only for the exact model named.</li>
   <li><b>Community-written encyclopedia</b> and <b>hobbyist video</b> — background; check anything risky against a manual.</li></ul>
  <h2>What this guide does not do</h2><ul>
   <li>It points to original pages; the guides don’t write their own medical, chemical or electrical instructions. The assistant’s answers mark which sentences come from a cited page and which are its own wording.</li>
   <li>Nothing here replaces trained help. Each guide shows the sources’ own limits.</li>
   <li>Reading and watching are not the same as practising. Your ticks stay on this device.</li>
   ${s.pack ? '' : '<li>Shopping lists and carts in older reports are plans, not proof of supplies you own.</li>'}</ul>
  ${s.sources ? `<h2>Sources and credits</h2><p><a href="#/read/${encodeURIComponent(s.sources)}?${fromQ()}">Sources and permissions</a>: every publisher in this library, where it came from, and how to ask for something to be removed.</p>` : ''}
  ${IN_WINDOW ? '' : '<h2>Using it on a phone</h2><p>Phones on the same Wi-Fi (no internet needed) can use the guide when this computer starts it with <code>server.py --lan</code>. Phones need the access link shown in the terminal the first time.</p>'}
  ${oldServer ? '<h2>Other ways in</h2><p><a href="/reports/gap-closure-status.html" target="_blank">Gap closure report</a> · <a href="/reports/learning-pathways.html" target="_blank">Learning pathways report</a> · <a href="/reports/survival-tools-cart.html" target="_blank">Supplies planning</a></p>' : ''}`;
  if (updateCard) LBUpdate.mount(main);
}

route();
if ('serviceWorker' in navigator && /^(127\.0\.0\.1|localhost)$/.test(location.hostname)) navigator.serviceWorker.register('/sw.js').catch(() => { });
