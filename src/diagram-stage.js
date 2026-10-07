import './diagram-stage.css';
import { diagramLayers } from '../content/diagram-layers.js';

const SVG = 'http://www.w3.org/2000/svg';
const clamp = value => Math.max(0, Math.min(1, value));
const ease = value => { const t = clamp(value); return t * t * (3 - 2 * t); };
const range = (start, end, value) => ease((value - start) / (end - start));
const mix = (a, b, t) => a + (b - a) * t;
const svgNode = name => document.createElementNS(SVG, name);

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

  const originalChildren = [...element.children];
  const axes = element.querySelector(`#${prefix}axes_1`);
  const axesChildren = axes ? [...axes.children] : [];
  const sourceGroup = svgNode('g');
  sourceGroup.classList.add('diagram-source');
  originalChildren.filter(node => !['defs', 'title', 'desc', 'style'].includes(node.localName)).forEach(node => sourceGroup.append(node));
  element.append(sourceGroup);

  const links = svgNode('g');
  links.classList.add('diagram-relations');
  links.setAttribute('aria-hidden', 'true');
  element.append(links);
  const markers = svgNode('defs');
  const arrow = svgNode('marker');
  arrow.id = `${prefix}relation-arrow`;
  arrow.setAttribute('viewBox', '0 0 8 8');
  arrow.setAttribute('refX', '7');
  arrow.setAttribute('refY', '4');
  arrow.setAttribute('markerWidth', '5');
  arrow.setAttribute('markerHeight', '5');
  arrow.setAttribute('orient', 'auto');
  const tip = svgNode('polygon');
  tip.setAttribute('points', '0,0 8,4 0,8');
  tip.setAttribute('fill', '#667b6d');
  arrow.append(tip);
  markers.append(arrow);
  element.append(markers);
  const layers = (diagramLayers[key] || []).map((definition, index) => {
    const nodes = definition.ids ? definition.ids.map(id => element.querySelector(`#${prefix}${id}`))
      : definition.axesChildren ? definition.axesChildren.map(i => axesChildren[i])
        : definition.children.map(i => originalChildren[i]);
    if (nodes.some(node => !node)) throw new Error('The diagram structure does not match its published artwork.');
    const group = svgNode('g');
    group.classList.add('diagram-layer');
    group.dataset.layerKey = definition.key;
    group.dataset.sourceCount = String(nodes.length);
    group.setAttribute('aria-label', definition.label);
    group.setAttribute('aria-hidden', 'true');
    for (const [nodeIndex, node] of nodes.entries()) {
      if (!node.id) node.id = `${prefix}component-${index}-${nodeIndex}`;
      const reference = svgNode('use');
      reference.setAttribute('href', `#${node.id}`);
      group.append(reference);
    }
    element.append(group);
    return { ...definition, group, index, pose: [0, 0, 1], opacity: 0 };
  });
  // Retain only relationships that are explicit in the published diagrams.
  // Other source brackets and mappings return in the complete overview.
  const connections = key === 'framework'
    ? ['objective', 'structure', 'generation', 'constraints', 'utility'].map((name, index) => [
      `dimension-${name}`, `dimension-${['structure', 'generation', 'constraints', 'utility', 'risk'][index]}`
    ])
    : [['questionnaire', 'synthetic-records'], ['measurements', 'synthetic-records'], ['knowledge', 'synthetic-records'], ['synthetic-records', 'coach-output'], ['regulatory-comparison', 'coach-output']];
  const relationships = connections.map(([from, to]) => {
    const line = svgNode('polyline');
    line.dataset.from = from;
    line.dataset.to = to;
    line.setAttribute('fill', 'none');
    line.setAttribute('vector-effect', 'non-scaling-stroke');
    line.setAttribute('marker-end', `url(#${arrow.id})`);
    links.append(line);
    return { from, to, line };
  });
  return { element, source: sourceGroup, layers, links, relationships };
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
    const transcript = section.querySelector('.diagram-transcript');
    section.classList.add('diagram-chapter');
    section.dataset.ready = 'loading';
    section.dataset.scenes = String(config.scenes.length);
    viewport.setAttribute('aria-busy', 'true');
    const stage = { config, section, viewport, captions, copy, transcript, frames: [], progress: 0, target: 0, visible: false, initialized: false, svg: null, failed: false, overflow: false };
    configure(stage);
    return stage;
  }).filter(Boolean);

  function isStatic(stage) { return reduced.matches || landscape.matches || stage.failed || stage.overflow; }

  function configure(stage) {
    stage.frames = stage.config.scenes.flatMap((scene, sceneIndex) => (scene.layers || [null]).map(layer => ({ scene: sceneIndex, layer })));
    const staticView = isStatic(stage);
    stage.section.dataset.reduced = String(staticView);
    stage.section.dataset.staticReason = reduced.matches ? 'reduced-motion' : landscape.matches ? 'short-landscape' : stage.failed ? 'figure-error' : stage.overflow ? 'text-size' : '';
    stage.section.dataset.views = String(stage.frames.length);
    stage.section.style.setProperty('--diagram-spans', String(stage.frames.length - 1));
    stage.section.style.setProperty('--diagram-step-height', mobile.matches ? '78svh' : '69svh');
    stage.copy?.setAttribute('aria-hidden', String(!staticView));
    if (stage.transcript) stage.transcript.hidden = staticView;
    for (const caption of stage.captions) {
      caption.setAttribute('aria-hidden', String(!staticView));
      caption.inert = !staticView;
    }
  }

  function paint(stage) {
    const staticView = isStatic(stage);
    const position = clamp(stage.progress) * (stage.frames.length - 1);
    const first = Math.min(stage.frames.length - 1, Math.floor(position));
    const second = Math.min(stage.frames.length - 1, first + 1);
    const phase = position - first;
    const a = stage.frames[first], b = stage.frames[second];
    // Hold each arrangement while it is read, then travel to the next one.
    const travel = range(.22, .83, phase);
    const focusFrame = phase > .56 ? b : a;
    const active = focusFrame.scene;
    let separation = a.layer ? 1 : 0;
    separation = mix(separation, b.layer ? 1 : 0, travel);
    if (staticView) separation = 0;
    const fullBox = stage.config.fullViewBox;
    const [,, width, sourceHeight] = fullBox;
    // The separated scene fills the available viewport without stretching art.
    const height = width * stage.viewport.clientHeight / Math.max(1, stage.viewport.clientWidth);
    const cameraHeight = mix(sourceHeight, height, separation);
    const serialized = [0, 0, width, cameraHeight].map(value => Number(value.toFixed(3))).join(' ');

    if (stage.svg) {
      const { element, source, layers, links, relationships } = stage.svg;
      element.setAttribute('viewBox', serialized);
      source.style.opacity = String(1 - range(0, .42, separation));
      const layerIndex = key => layers.findIndex(layer => layer.key === key);
      const startIndex = a.layer ? layerIndex(a.layer) : b.layer ? layerIndex(b.layer) : 0;
      const endIndex = b.layer ? layerIndex(b.layer) : startIndex;
      const currentIndex = mix(startIndex, endIndex, travel);
      const sizes = layers.map(layer => {
        const scale = Math.min(width * .84 / layer.box[2], height * (mobile.matches ? .80 : .68) / layer.box[3]);
        return { scale, height: layer.box[3] * scale };
      });
      const centers = sizes.map((size, index) => index === 0 ? 0 : 1);
      for (let index = 1; index < sizes.length; index++) centers[index] = centers[index - 1] + (sizes[index - 1].height + sizes[index].height) / 2 + height * .13;
      const cameraY = mix(centers[startIndex], centers[endIndex], travel);
      const activeKey = separation > .5 ? focusFrame.layer : null;
      for (const [index, layer] of layers.entries()) {
        const distance = index - currentIndex;
        const depth = 1 - Math.min(Math.abs(distance), 2.5) * .095;
        const targetScale = sizes[index].scale * depth;
        const targetX = width * (.5 + Math.sin(index * 1.5) * Math.min(Math.abs(distance), 1) * .065);
        const targetY = height * .5 + centers[index] - cameraY;
        const scale = Math.exp(mix(0, Math.log(targetScale), separation));
        const x = mix(0, targetX - (layer.box[0] + layer.box[2] / 2) * targetScale, separation);
        const y = mix(0, targetY - (layer.box[1] + layer.box[3] / 2) * targetScale, separation);
        const opacity = range(0, .24, separation) * (1 - Math.min(Math.abs(distance) * .42, .87));
        layer.pose = [x, y, scale];
        layer.opacity = opacity;
        layer.group.setAttribute('transform', `translate(${x.toFixed(3)} ${y.toFixed(3)}) scale(${scale.toFixed(5)})`);
        layer.group.style.opacity = String(opacity);
        layer.group.dataset.pose = layer.pose.map(value => value.toFixed(5)).join(' ');
        layer.group.dataset.active = String(layer.key === activeKey);
        layer.group.dataset.depth = depth.toFixed(3);
      }
      // Links follow their own source and destination components as those move.
      links.style.opacity = String(range(.55, 1, separation));
      for (const relationship of relationships) {
        const from = layers.find(layer => layer.key === relationship.from);
        const to = layers.find(layer => layer.key === relationship.to);
        const [fx, fy, fs] = from.pose, [tx, ty, ts] = to.pose;
        const downward = to.index > from.index;
        const x1 = fx + (from.box[0] + from.box[2] / 2) * fs;
        const y1 = fy + (from.box[1] + from.box[3] * (downward ? 1 : 0)) * fs;
        const x2 = tx + (to.box[0] + to.box[2] / 2) * ts;
        const y2 = ty + (to.box[1] + to.box[3] * (downward ? 0 : 1)) * ts;
        const middle = (y1 + y2) / 2;
        relationship.line.setAttribute('points', `${x1},${y1} ${x1},${middle} ${x2},${middle} ${x2},${y2}`);
        const distance = Math.max(Math.abs(from.index - currentIndex), Math.abs(to.index - currentIndex));
        relationship.line.style.opacity = String(.3 * clamp(2 - distance));
      }
      stage.section.dataset.activeLayer = activeKey || '';
    }
    stage.section.dataset.layout = separation < .001 ? 'overview' : separation > .999 ? 'focused' : 'separating';
    stage.section.dataset.separation = separation.toFixed(4);
    stage.section.dataset.progress = stage.progress.toFixed(4);
    stage.section.dataset.targetProgress = stage.target.toFixed(4);
    stage.section.dataset.settled = String(stage.progress === stage.target);
    stage.section.dataset.sceneIndex = String(active);
    stage.section.dataset.sceneId = stage.config.scenes[active].id;
    stage.section.dataset.focus = focusFrame.layer || 'whole';
    stage.section.dataset.viewIndex = String(phase > .56 ? second : first);
    stage.section.dataset.camera = serialized;
    stage.section.style.setProperty('--diagram-progress', String(stage.progress));
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
    const follow = 1 - Math.exp(-dt * 13);
    let moving = false;
    for (const stage of stages) {
      if (!stage.visible || reduced.matches) { stage.progress = stage.target; continue; }
      const difference = stage.target - stage.progress;
      stage.progress = Math.abs(difference) < .00006 ? stage.target : stage.progress + difference * follow;
      // Finish on the exact scroll position before stopping the frame loop.
      if (Math.abs(stage.target - stage.progress) <= .00006) stage.progress = stage.target;
      paint(stage);
      moving ||= stage.target !== stage.progress;
    }
    if (moving) requestFrame();
  }
  function update() {
    for (const stage of stages) {
      const rect = stage.section.getBoundingClientRect();
      stage.visible = rect.bottom > 0 && rect.top < innerHeight;
      stage.target = clamp(-rect.top / Math.max(1, rect.height - innerHeight));
      stage.section.dataset.targetProgress = stage.target.toFixed(4);
      stage.section.dataset.settled = String(stage.progress === stage.target);
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
      if (isStatic(stage) || !stage.copy) continue;
      const available = stage.copy.clientHeight;
      if (!available) continue;
      const exceeds = stage.captions.some(caption => {
        const height = [...caption.children].reduce((total, child) => {
          const style = getComputedStyle(child);
          return total + child.getBoundingClientRect().height + parseFloat(style.marginTop || 0) + parseFloat(style.marginBottom || 0);
        }, 0);
        return height > available + 2;
      });
      if (exceeds) { stage.overflow = true; configure(stage); stage.initialized = false; }
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
      stage.svg = prepareSVG(source, stage.config.key, `${stage.config.title}: the complete source diagram, explored through connected components.`);
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
