import './style.css';
import { initOpening } from './opening.js';
import { initDiagramStages } from './diagram-stage.js';
import { diagramScenes } from '../content/diagram-scenes.js';

const base = import.meta.env.BASE_URL;
const root = document.documentElement;
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const escapeHtml = value => String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));

document.querySelector('#diagram-stories').innerHTML = Object.values(diagramScenes).map(chapter => `
  <section id="${chapter.key}" class="diagram-chapter" aria-labelledby="${chapter.key}-title">
    <div class="diagram-sticky">
      <div class="diagram-heading"><h2 id="${chapter.key}-title">${chapter.title}<span class="accent">.</span></h2></div>
      <div class="diagram-viewport" data-diagram="${chapter.key}" role="group" aria-label="${chapter.title} diagram">
        <img class="diagram-fallback" src="${base}${chapter.asset}" alt="Complete ${chapter.title} diagram" loading="lazy">
      </div>
      <div class="diagram-copy" aria-hidden="true">
        ${chapter.scenes.map((scene, index) => `<article class="diagram-caption${index === 0 ? ' is-current' : ''}" data-scene-index="${index}"><h3>${escapeHtml(scene.title)}</h3><p>${escapeHtml(scene.body)}</p></article>`).join('')}
      </div>
      <div class="diagram-track" aria-hidden="true"><i></i></div>
      <div class="diagram-actions"><button class="source-link" data-figure="${chapter.key}">View complete diagram <span aria-hidden="true">↗</span></button><button class="source-link" data-read="${chapter.key}">Read full ${chapter.title} <span aria-hidden="true">↗</span></button></div>
    </div>
    <div class="diagram-transcript sr-only">${chapter.scenes.map(scene => `<h3>${escapeHtml(scene.title)}</h3><p>${escapeHtml(scene.body)}</p>`).join('')}</div>
  </section>`).join('');

const menu = document.querySelector('#site-menu');
const menuToggle = document.querySelector('#menu-toggle');
const reader = document.querySelector('#reader');
const content = document.querySelector('#reader-content');
const readerTitle = document.querySelector('#reader-title');
const toc = document.querySelector('#reader-toc');
let readerTrigger;
let chapterPromise;
let chapterRequest = 0;

root.classList.add('enhanced');
window.synsportRevision = __BUILD_REVISION__;
document.querySelector('#build-version').textContent = __BUILD_REVISION__ === 'local' ? 'Local preview' : `Revision ${__BUILD_REVISION__.slice(0, 7)}`;

function syncTheme() {
  const dark = root.dataset.theme === 'dark';
  const button = document.querySelector('#theme-toggle');
  button.setAttribute('aria-label', `Switch to ${dark ? 'light' : 'dark'} appearance`);
  button.setAttribute('aria-pressed', String(dark));
  document.querySelector('meta[name="theme-color"]').content = dark ? '#181f1b' : '#eeeee6';
}
document.querySelector('#theme-toggle').addEventListener('click', () => {
  root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
  try { localStorage.setItem('synsport-theme', root.dataset.theme); } catch { /* Appearance still works without storage. */ }
  syncTheme();
});
syncTheme();

function syncDialogState() {
  document.body.style.overflow = menu.open || reader.open ? 'hidden' : '';
  menuToggle.setAttribute('aria-expanded', String(menu.open));
}
menuToggle.addEventListener('click', () => { menu.showModal(); syncDialogState(); });
document.querySelector('#menu-close').addEventListener('click', () => menu.close());
menu.addEventListener('close', syncDialogState);
menu.querySelectorAll('a').forEach(link => link.addEventListener('click', () => menu.close()));
document.querySelector('#reader-close').addEventListener('click', () => reader.close());
reader.addEventListener('close', () => { chapterRequest++; syncDialogState(); readerTrigger?.focus({ preventScroll: true }); });

function openReader(title, trigger) {
  reader.dataset.view = 'chapter';
  document.querySelector('#reader-kind').textContent = 'THE COMPLETE CHAPTER';
  readerTrigger = trigger;
  readerTitle.textContent = title;
  content.innerHTML = '<p role="status">Loading the chapter…</p>';
  toc.replaceChildren();
  if (!reader.open) reader.showModal();
  reader.scrollTop = 0;
  syncDialogState();
}

function installReaderLinks() {
  content.querySelectorAll('img[src]').forEach(img => {
    const source = img.getAttribute('src');
    if (!/^(https?:|data:|\/)/.test(source)) img.src = `${base}${source}`;
    img.loading = 'lazy';
    const link = document.createElement('a');
    link.href = img.src;
    link.target = '_blank';
    link.rel = 'noopener';
    link.setAttribute('aria-label', `Open ${img.alt || 'diagram'} at full size`);
    img.replaceWith(link);
    link.append(img);
  });
  content.querySelectorAll('a[href^="http"]').forEach(link => { link.target = '_blank'; link.rel = 'noopener'; });
  const headings = [...content.querySelectorAll('h1[id],h2[id],h3[id]')];
  const topLevel = Math.min(...headings.map(heading => Number(heading.tagName.slice(1))));
  for (const heading of headings) {
    const link = document.createElement('a');
    link.href = `#${heading.id}`;
    link.textContent = heading.textContent;
    if (Number(heading.tagName.slice(1)) > topLevel) link.className = 'sub-item';
    toc.append(link);
  }
}

async function readChapter(key, anchor, trigger) {
  const request = ++chapterRequest;
  openReader(key === 'framework' ? 'Framework' : 'Objective', trigger);
  const standalone = document.querySelector('#reader-standalone');
  standalone.hidden = false;
  standalone.href = `${base}chapters/${key}.html`;
  try {
    chapterPromise ||= import('../content/chapters.json').then(module => module.default);
    const publication = await chapterPromise;
    if (request !== chapterRequest || !reader.open) return;
    const chapter = publication.chapters[key];
    content.innerHTML = chapter.html;
    installReaderLinks();
    if (anchor) requestAnimationFrame(() => content.querySelector(`#${CSS.escape(`${key}-${anchor}`)}`)?.scrollIntoView({ behavior: 'instant', block: 'start' }));
  } catch {
    chapterPromise = null;
    content.innerHTML = `<p>The reading panel could not load. <a href="${base}chapters/${key}.html">Open the complete chapter</a>.</p>`;
  }
}
document.querySelectorAll('[data-read]').forEach(button => button.addEventListener('click', () => readChapter(button.dataset.read, button.dataset.anchor, button)));
document.querySelectorAll('[data-figure]').forEach(button => button.addEventListener('click', () => {
  chapterRequest++;
  const chapter = diagramScenes[button.dataset.figure];
  openReader(`${chapter.title} diagram`, button);
  reader.dataset.view = 'figure';
  document.querySelector('#reader-kind').textContent = 'THE COMPLETE FIGURE';
  const link = document.querySelector('#reader-standalone');
  link.hidden = false;
  link.href = `${base}${chapter.asset}`;
  content.innerHTML = `<figure><img src="${base}${chapter.asset}" alt="Complete ${chapter.title} diagram"><figcaption>Open the figure at full size to inspect its labels. The complete chapter includes the source references and explanation.</figcaption></figure>`;
  installReaderLinks();
}));

const credits = `<h1>Sources &amp; credits</h1><p>The scientific narrative follows the final Framework and Objective chapters. Each complete chapter includes its references and the evidence supporting its statements.</p>
  <ul class="credit-list"><li><a href="${base}chapters/framework.html">Framework: source comparison and evaluation approach</a></li><li><a href="${base}chapters/objective.html">Objective: the judo prediction question and evidence</a></li></ul>
  <h2>Opening footage</h2><p>The movement adapts <a href="https://commons.wikimedia.org/wiki/File:JudoVideo.net_Okuri-ashi-barai.webm">JudoVideo.net: Okuri-ashi-barai</a> by canaljudovideo (2013), licensed under <a href="https://creativecommons.org/licenses/by/3.0/">Creative Commons Attribution 3.0</a>. Changes include cropping, foreground extraction, monochrome treatment and scroll-controlled playback. The original athletes and author do not endorse this project.</p><p>The opening portrait is a project illustration. The recorded movement retains the camera viewpoint of the original footage.</p>
  <h2>Figures and typography</h2><p>The complete chapters retain the source figures and their captions. The Framework comparison incorporates attributed diagrams from <em>Practical Synthetic Data Generation</em>; rights in those original images remain with their respective owners.</p><p>Roboto is distributed under the <a href="${base}fonts/OFL.txt">SIL Open Font License</a>.</p>
  <h2>Design references</h2><p><a href="https://www.usavionix.com/">USAvionix</a> informed the connection between scale, context and scrolling. <a href="https://landonorris.com/">Lando Norris</a> informed the opening composition, and <a href="https://bleibtgleich.dev/">bleibtgleich</a> informed the navigation panels.</p>
  <h2>Design evidence</h2><ul class="credit-list"><li>Mörth, Bruckner and Smit (2023). <a href="https://doi.org/10.1109/TVCG.2022.3205769">ScrollyVis: Interactive Visual Authoring of Guided Dynamic Narratives for Scientific Scrollytelling.</a> <em>IEEE Transactions on Visualization and Computer Graphics.</em></li><li>Mittenentzwei et al. (2023). <a href="https://doi.org/10.1016/j.cag.2023.06.011">Investigating user behavior in slideshows and scrollytelling as narrative genres in medical visualization.</a> <em>Computers &amp; Graphics.</em></li><li>Soares et al. (2022). <a href="https://doi.org/10.1007/s10664-021-10114-1">The effects of continuous integration on software development: a systematic literature review.</a> <em>Empirical Software Engineering.</em></li></ul>`;
document.querySelector('[data-credits]').addEventListener('click', event => {
  chapterRequest++;
  openReader('Sources & credits', event.currentTarget);
  document.querySelector('#reader-kind').textContent = 'SOURCES & CREDITS';
  document.querySelector('#reader-standalone').hidden = true;
  content.innerHTML = credits;
  installReaderLinks();
});

reader.addEventListener('click', event => {
  const link = event.target.closest('a[href^="#"]');
  if (!link) return;
  const target = reader.querySelector(`#${CSS.escape(link.hash.slice(1))}`);
  if (target) { event.preventDefault(); target.scrollIntoView({ behavior: reducedMotion.matches ? 'instant' : 'smooth', block: 'start' }); }
});

const openingSection = document.querySelector('#home');
const opening = initOpening({ container: document.querySelector('#opening-art'), loader: document.querySelector('#loader'), onReady: () => scheduleUpdate() });
const diagramStages = initDiagramStages(diagramScenes);
let updateFrame = 0;

function updateScroll() {
  updateFrame = 0;
  const height = innerHeight;
  const rect = openingSection.getBoundingClientRect();
  const progress = Math.max(0, Math.min(1, -rect.top / Math.max(1, rect.height - height)));
  opening.update(progress);
  diagramStages.update();
  document.querySelector('.site-header').classList.toggle('has-content', document.querySelector('#introduction').getBoundingClientRect().top <= 100);
}
function scheduleUpdate() {
  if (!updateFrame) updateFrame = requestAnimationFrame(updateScroll);
}
addEventListener('scroll', scheduleUpdate, { passive: true });
addEventListener('resize', scheduleUpdate, { passive: true });
reducedMotion.addEventListener('change', scheduleUpdate);
addEventListener('hashchange', scheduleUpdate);
scheduleUpdate();
diagramStages.ready.then(scheduleUpdate);

const initialAnchor = document.getElementById(location.hash.slice(1));
if (initialAnchor) {
  // A direct chapter link takes precedence over the browser's saved scroll
  // position. Align again after fonts and figures settle, unless the reader
  // has already interacted with the page.
  const restoration = history.scrollRestoration;
  history.scrollRestoration = 'manual';
  const navigation = new AbortController();
  let interacted = false;
  const finish = () => { navigation.abort(); history.scrollRestoration = restoration; };
  const cancel = () => { interacted = true; finish(); };
  for (const event of ['wheel', 'touchstart', 'pointerdown', 'keydown']) {
    addEventListener(event, cancel, { once: true, passive: true, signal: navigation.signal });
  }
  const align = () => { if (!interacted) initialAnchor.scrollIntoView({ behavior: 'instant' }); };
  requestAnimationFrame(align);
  const loaded = document.readyState === 'complete' ? Promise.resolve() : new Promise(resolve => addEventListener('load', resolve, { once: true }));
  Promise.all([diagramStages.ready, document.fonts.ready, loaded]).then(() => {
    requestAnimationFrame(() => requestAnimationFrame(() => { align(); finish(); }));
  });
}
