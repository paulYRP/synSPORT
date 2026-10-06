import './style.css';
import { initOpening } from './opening.js';

const base = import.meta.env.BASE_URL;
const root = document.documentElement;
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
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

const credits = `<h1>Sources &amp; credits</h1><p>The scientific narrative follows the final Framework and Objective chapters. Each complete chapter includes its references and the evidence supporting its statements.</p>
  <ul class="credit-list"><li><a href="${base}chapters/framework.html">Framework: source comparison and evaluation approach</a></li><li><a href="${base}chapters/objective.html">Objective: the judo prediction question and evidence</a></li></ul>
  <h2>Opening footage</h2><p>The movement adapts <a href="https://commons.wikimedia.org/wiki/File:JudoVideo.net_Okuri-ashi-barai.webm">JudoVideo.net: Okuri-ashi-barai</a> by canaljudovideo (2013), licensed under <a href="https://creativecommons.org/licenses/by/3.0/">Creative Commons Attribution 3.0</a>. Changes include cropping, foreground extraction, monochrome treatment and scroll-controlled playback. The original athletes and author do not endorse this project.</p><p>The opening portrait is a project illustration. The recorded movement retains the camera viewpoint of the original footage.</p>
  <h2>Figures and typography</h2><p>The complete chapters retain the source figures and their captions. The Framework comparison incorporates attributed diagrams from <em>Practical Synthetic Data Generation</em>; rights in those original images remain with their respective owners.</p><p>Roboto is distributed under the <a href="${base}fonts/OFL.txt">SIL Open Font License</a>.</p>
  <h2>Design references</h2><p><a href="https://www.usavionix.com/">USAvionix</a> informed the connection between scale, context and scrolling. <a href="https://landonorris.com/">Lando Norris</a> informed the opening composition, and <a href="https://bleibtgleich.dev/">bleibtgleich</a> informed the navigation panels.</p>
  <h2>Design evidence</h2><ul class="credit-list"><li>Mörth, Bruckner and Smit (2023). <a href="https://doi.org/10.1109/TVCG.2022.3205769">ScrollyVis: Interactive Visual Authoring of Guided Dynamic Narratives for Scientific Scrollytelling.</a> <em>IEEE Transactions on Visualization and Computer Graphics.</em></li><li>Mittenentzwei et al. (2023). <a href="https://doi.org/10.1016/j.cag.2023.06.011">Investigating user behavior in slideshows and scrollytelling as narrative genres in medical visualization.</a> <em>Computers &amp; Graphics.</em></li><li>Soares et al. (2022). <a href="https://doi.org/10.1007/s10664-021-10114-1">The effects of continuous integration on software development: a systematic literature review.</a> <em>Empirical Software Engineering.</em></li></ul>`;
document.querySelector('[data-credits]').addEventListener('click', event => {
  chapterRequest++;
  openReader('Sources & credits', event.currentTarget);
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
const states = {
  framework: ['THE WHOLE PROCESS', 'SIX CONNECTED DIMENSIONS', 'A SHARED EVALUATION'],
  objective: ["THE COACH’S QUESTION", 'COMPLEMENTARY EVIDENCE', 'MEASUREMENT STAGES', 'THE INTENDED OUTPUT'],
};
const captions = ['TIME DEFINES THE QUESTION', 'OBSERVATIONS AND ASSUMPTIONS STAY DISTINCT', 'SCHEMATIC · MEASUREMENT STAGES', 'CONCEPTUAL · NO FITTED PREDICTIONS'];
const stories = [...document.querySelectorAll('[data-story]')].map(element => ({ element, visual: element.querySelector('.story-visual'), steps: [...element.querySelectorAll('.story-step')], active: -1 }));
let updateFrame = 0;
let openingProgress = 0;
function updateScroll() {
  updateFrame = 0;
  const height = innerHeight;
  const rect = openingSection.getBoundingClientRect();
  openingProgress = Math.max(0, Math.min(1, -rect.top / Math.max(1, rect.height - height)));
  opening.update(openingProgress);
  const position = document.querySelector('#chapter-position');
  const objectiveTop = document.querySelector('#objective').getBoundingClientRect().top;
  const frameworkTop = document.querySelector('#framework').getBoundingClientRect().top;
  position.textContent = objectiveTop < height * .45 ? 'OBJECTIVE · THE JUDO QUESTION' : frameworkTop < height * .45 ? 'FRAMEWORK · THE APPROACH' : 'SYNTHETIC DATA · SPORT';
  for (const story of stories) {
    const focus = height * (innerWidth <= 650 ? .77 : .54);
    let best = Infinity, active = 0;
    story.steps.forEach((step, index) => {
      const r = step.getBoundingClientRect();
      const distance = Math.abs((r.top + r.bottom) / 2 - focus);
      if (distance < best) { best = distance; active = index; }
    });
    if (active !== story.active) {
      story.active = active;
      story.visual.dataset.active = String(active);
      story.visual.querySelector('[data-visual-state]').textContent = states[story.element.dataset.story][active];
      story.steps.forEach((step, index) => step.classList.toggle('is-active', index === active));
      const caption = story.visual.querySelector('[data-objective-caption]');
      if (caption) caption.textContent = captions[active];
      const panels = story.visual.querySelectorAll('.framework-map,.evaluation-map,.question-focus,.evidence-cards,.mass-timeline,.prediction-card');
      for (const panel of panels) {
        const show = reducedMotion.matches ? panel.matches('.framework-map,.mass-timeline') : panel.matches('.framework-map') ? active !== 2 : panel.matches('.evaluation-map') ? active === 2 : panel.matches('.question-focus') ? active === 0 : panel.matches('.evidence-cards') ? active === 1 : panel.matches('.mass-timeline') ? active === 2 : active === 3;
        panel.setAttribute('aria-hidden', String(!show));
      }
    }
  }
}
function scheduleUpdate() { if (!updateFrame) updateFrame = requestAnimationFrame(updateScroll); }
addEventListener('scroll', scheduleUpdate, { passive: true });
addEventListener('resize', scheduleUpdate, { passive: true });
reducedMotion.addEventListener('change', () => { stories.forEach(story => story.active = -1); scheduleUpdate(); });
addEventListener('hashchange', scheduleUpdate);
scheduleUpdate();
const initialAnchor = document.getElementById(location.hash.slice(1));
if (initialAnchor) requestAnimationFrame(() => initialAnchor.scrollIntoView({ behavior: 'instant' }));
