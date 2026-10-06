import './diagram-stage.css';

const SVG = 'http://www.w3.org/2000/svg';
const clamp = value => Math.max(0, Math.min(1, value));
const ease = value => { const t = clamp(value); return t * t * (3 - 2 * t); };
const range = (start, end, value) => ease((value - start) / (end - start));
const mix = (a, b, t) => a + (b - a) * t;

// Interpolate centres and scale. The SVG's meet setting preserves the source
// aspect ratio; its artwork clip prevents neighbouring panels entering the crop.
function cameraBetween(a, b, amount) {
  const width = Math.exp(mix(Math.log(a[2]), Math.log(b[2]), amount));
  const height = Math.exp(mix(Math.log(a[3]), Math.log(b[3]), amount));
  return [mix(a[0] + a[2] / 2, b[0] + b[2] / 2, amount) - width / 2,
    mix(a[1] + a[3] / 2, b[1] + b[3] / 2, amount) - height / 2, width, height];
}

function prepareSVG(source, key, label) {
  const xml = source.replace(/<!DOCTYPE[^>[]*(?:\[[\s\S]*?\])?\s*>/gi, '');
  const documentSVG = new DOMParser().parseFromString(xml, 'image/svg+xml');
  if (documentSVG.querySelector('parsererror') || documentSVG.documentElement.localName !== 'svg') throw new Error('The figure could not be read.');
  const element = document.importNode(documentSVG.documentElement, true);
  const prefix = `diagram-${key.replace(/[^a-z0-9_-]/gi, '-')}-`;
  element.querySelectorAll('script,foreignObject,iframe,object,embed,audio,video,animate,animateTransform,animateMotion,set,metadata').forEach(node => node.remove());
  const ids = new Map();
  for (const node of element.querySelectorAll('[id]')) { ids.set(node.id, prefix + node.id); node.id = prefix + node.id; }
  element.id = `${prefix}art`;
  const localReferences = value => value.replace(/url\(\s*(["']?)#([^\s)'";]+)\1\s*\)/g, (_, quote, id) => `url(#${ids.get(id) || prefix + id})`);
  for (const node of [element, ...element.querySelectorAll('*')]) {
    for (const attribute of [...node.attributes]) {
      if (/^on/i.test(attribute.name)) { node.removeAttributeNode(attribute); continue; }
      if (attribute.localName === 'href') {
        const value = attribute.value.trim();
        if (value.startsWith('#')) attribute.value = `#${ids.get(value.slice(1)) || prefix + value.slice(1)}`;
        else if (!/^data:image\/(png|jpe?g|gif|webp);base64,/i.test(value)) node.removeAttributeNode(attribute);
      } else if (/url\(/i.test(attribute.value)) {
        if (/url\(\s*["']?(?!#)[^"')]+/i.test(attribute.value)) node.removeAttributeNode(attribute);
        else attribute.value = localReferences(attribute.value);
      }
    }
  }
  for (const style of element.querySelectorAll('style')) {
    let css = localReferences(style.textContent).replace(/@import[^;]+;/gi, '');
    // The current publication uses a simple universal stroke rule. Scope every
    // selector so this figure cannot restyle controls or another inline SVG.
    css = css.replace(/(^|\})\s*([^{}]+)\{/g, (_, boundary, selectors) => `${boundary}${selectors.split(',').map(selector => `#${element.id} ${selector.trim()}`).join(',')}{`);
    style.textContent = css;
  }
  element.removeAttribute('width');
  element.removeAttribute('height');
  element.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  element.setAttribute('role', 'img');
  element.setAttribute('aria-label', label);
  element.setAttribute('focusable', 'false');
  element.classList.add('diagram-artwork');
  let defs = [...element.children].find(node => node.localName === 'defs');
  if (!defs) { defs = document.createElementNS(SVG, 'defs'); element.prepend(defs); }
  const clip = document.createElementNS(SVG, 'clipPath');
  clip.id = `${prefix}camera-crop`;
  clip.setAttribute('clipPathUnits', 'userSpaceOnUse');
  const crop = document.createElementNS(SVG, 'rect');
  clip.append(crop);
  defs.append(clip);
  const artwork = document.createElementNS(SVG, 'g');
  artwork.setAttribute('clip-path', `url(#${clip.id})`);
  [...element.children].filter(node => !['defs', 'title', 'desc', 'style'].includes(node.localName)).forEach(node => artwork.append(node));
  element.append(artwork);
  return { element, crop };
}

export function initDiagramStages(configs) {
  const configurations = Array.isArray(configs) ? configs : Object.values(configs);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const mobile = matchMedia('(max-width: 700px)');
  const landscape = matchMedia('(max-height: 540px) and (orientation: landscape)');
  const abort = new AbortController();
  let animation = 0;
  let previousTime = performance.now();
  let disposed = false;

  const stages = configurations.map(config => {
    const section = config.element || document.getElementById(config.key);
    const viewport = section?.querySelector('.diagram-viewport');
    if (!section || !viewport) return null;
    const captions = [...section.querySelectorAll('.diagram-caption')];
    const copy = section.querySelector('.diagram-copy');
    let transcript = section.querySelector('.diagram-transcript');
    if (!transcript) {
      transcript = document.createElement('div');
      transcript.className = 'diagram-transcript';
      for (const scene of config.scenes) {
        const heading = document.createElement('h3');
        const body = document.createElement('p');
        heading.textContent = scene.title;
        body.textContent = scene.body;
        transcript.append(heading, body);
      }
      section.append(transcript);
    }
    section.classList.add('diagram-chapter');
    section.dataset.ready = 'loading';
    section.dataset.scenes = String(config.scenes.length);
    viewport.setAttribute('aria-busy', 'true');
    const stage = { config, section, viewport, captions, copy, transcript, frames: [], progress: 0, target: 0, visible: false, initialized: false, svg: null, failed: false, overflow: false };
    configure(stage);
    return stage;
  }).filter(Boolean);

  function configure(stage) {
    stage.frames = stage.config.scenes.flatMap((scene, index) => {
      const views = mobile.matches && scene.mobileViews?.length ? scene.mobileViews : [scene.viewBox];
      return views.map((view, subview) => ({ box: Array.isArray(view) ? view : view.viewBox, scene: index, subview, focus: (!Array.isArray(view) && view.focus) || scene.focus }));
    });
    const staticView = reduced.matches || landscape.matches || stage.failed || stage.overflow;
    stage.section.dataset.reduced = String(staticView);
    stage.section.dataset.staticReason = reduced.matches ? 'reduced-motion' : landscape.matches ? 'short-landscape' : stage.failed ? 'figure-error' : stage.overflow ? 'text-size' : '';
    stage.section.dataset.views = String(stage.frames.length);
    stage.section.style.setProperty('--diagram-spans', String(stage.frames.length));
    stage.section.style.setProperty('--diagram-step-height', mobile.matches ? '88svh' : '78svh');
    stage.copy?.setAttribute('aria-hidden', String(!staticView));
    stage.transcript.hidden = staticView;
    for (const caption of stage.captions) {
      caption.setAttribute('aria-hidden', String(!staticView));
      caption.inert = !staticView;
    }
  }

  function paint(stage) {
    const staticView = reduced.matches || landscape.matches || stage.failed || stage.overflow;
    const position = clamp(stage.progress) * (stage.frames.length - 1);
    const first = Math.min(stage.frames.length - 1, Math.floor(position));
    const second = Math.min(stage.frames.length - 1, first + 1);
    const phase = position - first;
    const a = stage.frames[first], b = stage.frames[second];
    const cameraProgress = range(.26, .82, phase);
    const useNext = phase > .60;
    const focusFrame = useNext ? b : a;
    const active = focusFrame.scene;
    const box = staticView ? stage.config.fullViewBox : cameraBetween(a.box, b.box, cameraProgress);
    const serialized = box.map(value => value.toFixed(2)).join(' ');
    if (stage.svg) {
      stage.svg.element.setAttribute('viewBox', serialized);
      ['x', 'y', 'width', 'height'].forEach((name, index) => stage.svg.crop.setAttribute(name, String(box[index])));
    }
    stage.section.dataset.progress = stage.progress.toFixed(4);
    stage.section.dataset.targetProgress = stage.target.toFixed(4);
    stage.section.dataset.sceneIndex = String(active);
    stage.section.dataset.sceneId = stage.config.scenes[active].id;
    stage.section.dataset.focus = String(focusFrame.focus || 'whole');
    stage.section.dataset.viewIndex = String(useNext ? second : first);
    stage.section.dataset.camera = serialized;
    stage.section.style.setProperty('--diagram-progress', String(stage.progress));
    stage.section.style.setProperty('--diagram-caption-opacity', '1');
    stage.viewport.dataset.camera = serialized;
    stage.viewport.dataset.viewBox = serialized;
    stage.viewport.dataset.sceneIndex = String(active);
    stage.viewport.dataset.progress = stage.progress.toFixed(4);
    for (const [index, caption] of stage.captions.entries()) {
      const current = index === active;
      caption.classList.toggle('is-current', current);
      caption.setAttribute('aria-hidden', String(!staticView && !current));
      caption.inert = !staticView && !current;
    }
  }

  function requestFrame() {
    if (!disposed && !animation && !document.hidden) animation = requestAnimationFrame(render);
  }
  function render(now) {
    animation = 0;
    const dt = Math.min(.07, (now - previousTime) / 1000);
    previousTime = now;
    const follow = 1 - Math.exp(-dt * 12);
    let moving = false;
    for (const stage of stages) {
      if (!stage.visible || reduced.matches) { stage.progress = stage.target; continue; }
      const difference = stage.target - stage.progress;
      stage.progress = Math.abs(difference) < .00006 ? stage.target : stage.progress + difference * follow;
      paint(stage);
      moving ||= Math.abs(stage.target - stage.progress) > .00006;
    }
    if (moving) requestFrame();
  }
  function update() {
    for (const stage of stages) {
      const rect = stage.section.getBoundingClientRect();
      stage.visible = rect.bottom > 0 && rect.top < innerHeight;
      stage.target = clamp(-rect.top / Math.max(1, rect.height - innerHeight));
      stage.section.dataset.targetProgress = stage.target.toFixed(4);
      if (!stage.initialized || !stage.visible || reduced.matches) {
        stage.progress = stage.target;
        stage.initialized = true;
        paint(stage);
      }
    }
    requestFrame();
  }
  function preferencesChanged() {
    stages.forEach(stage => { stage.overflow = false; configure(stage); stage.initialized = false; });
    update();
  }
  function checkTextFit() {
    for (const stage of stages) {
      if (reduced.matches || landscape.matches || stage.failed || stage.overflow || !stage.copy) continue;
      const available = stage.copy.clientHeight;
      if (!available) continue;
      const exceeds = stage.captions.some(caption => {
        const height = [...caption.children].reduce((total, child) => {
          const style = getComputedStyle(child);
          return total + child.getBoundingClientRect().height + parseFloat(style.marginTop || 0) + parseFloat(style.marginBottom || 0);
        }, 0);
        return height > available + 2;
      });
      if (exceeds) {
        stage.overflow = true;
        configure(stage);
        stage.initialized = false;
      }
    }
    update();
  }
  const textObserver = new ResizeObserver(checkTextFit);
  for (const stage of stages) {
    if (stage.copy) textObserver.observe(stage.copy);
    stage.captions.forEach(caption => [...caption.children].forEach(child => textObserver.observe(child)));
  }
  function resize() {
    stages.forEach(stage => { stage.overflow = false; configure(stage); stage.initialized = false; });
    update();
    requestAnimationFrame(checkTextFit);
  }
  function visibilityChanged() {
    if (document.hidden) { cancelAnimationFrame(animation); animation = 0; }
    else update();
  }

  const ready = Promise.all(stages.map(async stage => {
    try {
      const response = await fetch(`${import.meta.env.BASE_URL}${stage.config.asset}`, { signal: abort.signal });
      if (!response.ok) throw new Error('Figure unavailable.');
      const source = await response.text();
      if (disposed) return;
      stage.svg = prepareSVG(source, stage.config.key, `${stage.config.title}: the complete source diagram, explored through scrolling.`);
      stage.viewport.replaceChildren(stage.svg.element);
      stage.viewport.setAttribute('aria-busy', 'false');
      stage.section.dataset.ready = 'true';
      paint(stage);
    } catch (error) {
      if (disposed || error.name === 'AbortError') return;
      stage.failed = true;
      stage.section.dataset.ready = 'error';
      stage.viewport.setAttribute('aria-busy', 'false');
      const message = document.createElement('p');
      message.className = 'diagram-unavailable';
      message.textContent = 'The figure could not load. The narrative and complete chapter remain available below.';
      stage.viewport.replaceChildren(message);
      configure(stage);
      paint(stage);
    }
  }));
  addEventListener('scroll', update, { passive: true });
  addEventListener('resize', resize, { passive: true });
  reduced.addEventListener('change', preferencesChanged);
  mobile.addEventListener('change', preferencesChanged);
  landscape.addEventListener('change', preferencesChanged);
  document.addEventListener('visibilitychange', visibilityChanged);
  update();
  return {
    ready,
    update,
    dispose() {
      disposed = true;
      abort.abort();
      cancelAnimationFrame(animation);
      removeEventListener('scroll', update);
      removeEventListener('resize', resize);
      reduced.removeEventListener('change', preferencesChanged);
      mobile.removeEventListener('change', preferencesChanged);
      landscape.removeEventListener('change', preferencesChanged);
      textObserver.disconnect();
      document.removeEventListener('visibilitychange', visibilityChanged);
    }
  };
}
