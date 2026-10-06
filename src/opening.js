import * as THREE from 'three';
import { createThrow } from './judoka.js';
import './opening.css';

const clamp = (value) => Math.max(0, Math.min(1, value));
const smooth = (start, end, value) => { const t = clamp((value - start) / (end - start)); return t * t * (3 - 2 * t); };
const mix = (a, b, t) => a + (b - a) * t;

function makeBelt() {
  const belt = new THREE.Group();
  const material = new THREE.MeshStandardMaterial({ color: '#29352f', roughness: .91, side: THREE.DoubleSide });
  const stitchMaterial = new THREE.LineDashedMaterial({ color: '#7b8c7a', dashSize: .012, gapSize: .008, transparent: true, opacity: .7 });
  function ribbon(points, width, vertical = false) {
    const curve = new THREE.CatmullRomCurve3(points.map(point => new THREE.Vector3(...point)));
    const vertices = [], indices = [], edges = [[], []];
    const count = 90;
    for (let i = 0; i <= count; i++) {
      const point = curve.getPoint(i / count);
      const tangent = curve.getTangent(i / count).normalize();
      const side = vertical ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(-tangent.y, tangent.x, .06).normalize();
      const normal = new THREE.Vector3().crossVectors(tangent, side).normalize();
      for (const [edge, depth] of [[-1, 1], [1, 1], [1, -1], [-1, -1]]) {
        const p = point.clone().addScaledVector(side, edge * width / 2).addScaledVector(normal, depth * .013);
        vertices.push(p.x, p.y, p.z);
      }
      edges[0].push(point.clone().addScaledVector(side, width * .39).addScaledVector(normal, .016));
      edges[1].push(point.clone().addScaledVector(side, -width * .39).addScaledVector(normal, .016));
      if (i < count) for (let face = 0; face < 4; face++) {
        const a = i * 4 + face, b = i * 4 + (face + 1) % 4;
        indices.push(a, b, a + 4, b, b + 4, a + 4);
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    const group = new THREE.Group();
    group.add(new THREE.Mesh(geometry, material));
    for (const edge of edges) {
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(edge), stitchMaterial);
      line.computeLineDistances();
      group.add(line);
    }
    return group;
  }
  const wrap = Array.from({ length: 81 }, (_, i) => {
    const angle = i / 80 * Math.PI * 2;
    return [Math.sin(angle) * 1.1, .18, Math.cos(angle) * .43];
  });
  belt.add(ribbon(wrap, .24, true));
  belt.add(ribbon(wrap.map(([x, y, z]) => [x * 1.025, y - .065, z * 1.04]), .22, true));
  belt.add(ribbon([[.02, .08, .49], [-.14, -.2, .6], [-.34, -.6, .68], [-.58, -.99, .57]], .24));
  belt.add(ribbon([[.12, .11, .53], [.27, -.25, .65], [.47, -.65, .53], [.5, -1.01, .46]], .245));
  belt.add(ribbon([[-.2, -.01, .51], [-.13, .08, .69], [.07, .23, .71], [.21, .23, .52]], .235));
  return belt;
}

export function initOpening({ container, loader, onReady = () => {} }) {
  const base = import.meta.env.BASE_URL;
  const root = document.documentElement;
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const abort = new AbortController();
  let renderer, scene, camera, belt, movement;
  let ready = false, disposed = false, visible = true, frame = 0;
  let progress = 0, targetProgress = 0, pointerX = 0, pointerY = 0, currentX = 0, currentY = 0;
  let lastTime = performance.now();
  const started = lastTime;
  const canvas = document.createElement('canvas');
  canvas.className = 'opening-canvas';
  canvas.setAttribute('aria-hidden', 'true');
  container.classList.add('opening-art');
  container.innerHTML = `<div class="opening-halo" aria-hidden="true"></div>
    <svg class="opening-contours" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true"></svg>
    <div class="opening-portrait"><img src="${base}media/judoka.png" width="1024" height="1536" alt="A judoka in dark silhouette" fetchpriority="high" draggable="false"></div>
    <div class="opening-grain" aria-hidden="true"></div>`;
  loader.classList.add('opening-loader');
  loader.setAttribute('aria-label', 'Loading synSPORT');
  loader.innerHTML = `<div class="opening-belt-fallback" aria-hidden="true"><svg viewBox="0 0 240 160"><path d="M25 54C60 22 180 22 215 54L212 76C166 62 76 62 28 76Z"/><path d="M110 63L92 78 71 141 98 149 124 78ZM125 64L142 78 170 135 146 149 115 78Z"/><path d="M96 60L137 54 146 76 105 82Z"/></svg></div>
    <p class="opening-loading-label" role="status">Preparing the opening</p>
    <div class="opening-load-line" aria-hidden="true"><span></span></div>
    <button type="button" class="opening-continue">Continue to synSPORT <span aria-hidden="true">↗</span></button>`;
  const portrait = container.querySelector('img');
  const contours = container.querySelector('svg');
  for (const [cx, cy, radius] of [[-190, 300, 300], [1300, 320, 160], [440, 1050, 220]]) {
    for (let ring = 0; ring < 4; ring++) {
      let d = '';
      for (let i = 0; i <= 140; i++) {
        const angle = i / 140 * Math.PI * 2;
        const r = radius + ring * 150 + 28 * Math.sin(3 * angle + .8) + 45 * Math.cos(2 * angle);
        d += `${i ? 'L' : 'M'}${(cx + Math.cos(angle) * r).toFixed(1)},${(cy + Math.sin(angle) * r * .8).toFixed(1)}`;
      }
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', `${d}Z`);
      contours.append(path);
    }
  }

  function requestFrame() {
    if (!disposed && !frame && !document.hidden && (visible || !ready)) frame = requestAnimationFrame(render);
  }
  function clearBelt() {
    if (!belt) return;
    scene.remove(belt);
    const materials = new Set();
    belt.traverse(item => { item.geometry?.dispose(); if (item.material) materials.add(item.material); });
    materials.forEach(material => material.dispose());
    belt = null;
  }
  function finish() {
    if (ready || disposed) return;
    ready = true;
    clearTimeout(deadline);
    clearBelt();
    if (renderer) container.append(canvas);
    loader.style.setProperty('--loaded', '1');
    loader.classList.add('opening-ready');
    loader.setAttribute('aria-hidden', 'true');
    loader.inert = true;
    setTimeout(() => { if (!disposed) loader.hidden = true; }, 400);
    container.dataset.ready = 'true';
    onReady();
    requestFrame();
  }
  function fallback() {
    abort.abort();
    movement?.dispose();
    movement = null;
    container.dataset.renderer = 'static';
    finish();
    requestFrame();
  }
  const deadline = setTimeout(fallback, 6500);
  const continueButton = loader.querySelector('button');
  continueButton.addEventListener('click', finish);

  function resize() {
    const width = Math.max(1, container.clientWidth);
    const height = Math.max(1, container.clientHeight);
    if (renderer) {
      renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    }
    requestFrame();
  }
  function render(now) {
    frame = 0;
    if (disposed) return;
    const dt = Math.min((now - lastTime) / 1000, .06);
    lastTime = now;
    const follow = 1 - Math.exp(-dt * 11);
    progress = mix(progress, targetProgress, follow);
    currentX = mix(currentX, pointerX, follow);
    currentY = mix(currentY, pointerY, follow);
    const reduced = reducedMotion.matches;
    const p = reduced ? 0 : progress;
    const hasMovement = !!movement && !reduced;
    const reveal = hasMovement ? smooth(.21, .37, p) : 0;
    const dark = root.dataset.theme === 'dark';
    container.style.setProperty('--opening-portrait', String(1 - reveal));
    container.style.setProperty('--opening-scale', String(reduced ? 1 : 1 + .10 * smooth(0, .13, p) - .36 * smooth(.15, .36, p)));
    container.style.setProperty('--opening-progress', String(p));
    container.style.setProperty('--opening-x', String(reduced ? 0 : currentX));
    container.style.setProperty('--opening-y', String(reduced ? 0 : currentY));
    container.dataset.progress = p.toFixed(3);
    if (renderer) {
      const mobile = container.clientWidth < 700;
      if (!ready && belt) {
        const seconds = (now - started) / 1000;
        belt.rotation.set(.24, -.28 + Math.sin(seconds * .7) * .22, -.025);
        belt.scale.setScalar(.60);
        belt.position.y = .15;
        camera.position.set(0, .10, mobile ? 5.6 : 5.2);
        camera.lookAt(0, -.25, 0);
      } else {
        const pullback = smooth(.28, .52, p);
        const detail = smooth(.53, .7, p) * (1 - smooth(.82, 1, p));
        const distance = mobile ? 10.7 : mix(6.6, 7.6, pullback) - detail * .55;
        camera.position.set(currentX * .10, .5 + currentY * .055, distance);
        camera.lookAt(0, mobile ? .25 : .30, 0);
        if (movement) {
          movement.group.rotation.y = reduced ? 0 : currentX * .012;
          const state = movement.update(clamp((p - .34) / .60), reveal, dark);
          container.dataset.filmFrame = String(state.frame);
          container.dataset.targetFrame = String(state.target);
        }
      }
      renderer.render(scene, camera);
    }
    if ((!ready && renderer) || Math.abs(progress - targetProgress) > .00008 || Math.abs(currentX - pointerX) > .001 || Math.abs(currentY - pointerY) > .001) requestFrame();
  }

  function pointerMove(event) {
    if (event.pointerType !== 'mouse' || reducedMotion.matches || !ready) return;
    const rect = container.getBoundingClientRect();
    pointerX = (event.clientX - rect.left) / rect.width * 2 - 1;
    pointerY = (event.clientY - rect.top) / rect.height * 2 - 1;
    requestFrame();
  }
  function pointerLeave() { pointerX = pointerY = 0; requestFrame(); }
  function preferenceChange() {
    pointerLeave();
    requestFrame();
  }
  function visibilityChange() {
    if (document.hidden && frame) { cancelAnimationFrame(frame); frame = 0; }
    else requestFrame();
  }
  const observer = new IntersectionObserver(entries => {
    visible = entries[0].isIntersecting;
    if (!visible && ready && frame) { cancelAnimationFrame(frame); frame = 0; }
    if (visible) requestFrame();
  });
  observer.observe(container);
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(container);
  const themeObserver = new MutationObserver(requestFrame);
  themeObserver.observe(root, { attributes: true, attributeFilter: ['data-theme'] });
  container.addEventListener('pointermove', pointerMove);
  container.addEventListener('pointerleave', pointerLeave);
  reducedMotion.addEventListener('change', preferenceChange);
  document.addEventListener('visibilitychange', visibilityChange);

  async function prepare() {
    const imageReady = portrait.decode().catch(() => { portrait.hidden = true; });
    if (!reducedMotion.matches) {
      try {
        renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'low-power' });
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.setClearColor(0x000000, 0);
        scene = new THREE.Scene();
        camera = new THREE.PerspectiveCamera(34, 1, .1, 40);
        scene.add(new THREE.HemisphereLight('#f6f4e9', '#283b2d', 1.8));
        const light = new THREE.DirectionalLight('#ffffff', 3.4);
        light.position.set(-2, 5, 4);
        scene.add(light);
        belt = makeBelt();
        scene.add(belt);
        loader.prepend(canvas);
        loader.classList.add('opening-webgl');
        container.dataset.renderer = 'webgl';
        resize();
        canvas.addEventListener('webglcontextlost', event => {
          event.preventDefault();
          renderer = null;
          canvas.hidden = true;
          fallback();
        });
        const loadedMovement = await createThrow({ onFrame: requestFrame, signal: abort.signal, base });
        if (disposed || abort.signal.aborted) loadedMovement.dispose();
        else { movement = loadedMovement; scene.add(movement.group); }
      } catch {
        container.dataset.renderer = 'static';
        loader.classList.remove('opening-webgl');
      }
    } else container.dataset.renderer = 'static';
    loader.style.setProperty('--loaded', '.8');
    await imageReady;
    finish();
  }
  prepare();

  return {
    update(value) { targetProgress = clamp(value); requestFrame(); },
    dispose() {
      disposed = true;
      abort.abort();
      clearTimeout(deadline);
      cancelAnimationFrame(frame);
      observer.disconnect();
      resizeObserver.disconnect();
      themeObserver.disconnect();
      container.removeEventListener('pointermove', pointerMove);
      container.removeEventListener('pointerleave', pointerLeave);
      reducedMotion.removeEventListener('change', preferenceChange);
      document.removeEventListener('visibilitychange', visibilityChange);
      continueButton.removeEventListener('click', finish);
      movement?.dispose();
      clearBelt();
      renderer?.dispose();
      canvas.remove();
    }
  };
}
