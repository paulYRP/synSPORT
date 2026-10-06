import * as THREE from 'three';

// The upper half carries the filmed luminance; the lower half carries its matte.
// Sharing a decoder keeps clothing and silhouette aligned during reverse seeking.
export async function createThrow({ onFrame, signal, base }) {
  const response = await fetch(`${base}media/motion.json`, { signal });
  if (!response.ok) throw new Error('Movement metadata is unavailable.');
  const metadata = await response.json();
  const video = document.createElement('video');
  video.muted = true;
  video.playsInline = true;
  video.preload = 'auto';
  video.setAttribute('playsinline', '');
  video.src = `${base}media/throw.mp4`;
  let destroyed = false;
  const unload = () => {
    video.pause();
    video.removeAttribute('src');
    video.load();
  };
  await new Promise((resolve, reject) => {
    const done = (error) => {
      video.removeEventListener('loadeddata', loaded);
      video.removeEventListener('error', failed);
      signal.removeEventListener('abort', aborted);
      if (error) { unload(); reject(error); } else resolve();
    };
    const loaded = () => done();
    const failed = () => done(new Error('Movement video is unavailable.'));
    const aborted = () => done(new DOMException('Loading cancelled.', 'AbortError'));
    video.addEventListener('loadeddata', loaded, { once: true });
    video.addEventListener('error', failed, { once: true });
    signal.addEventListener('abort', aborted, { once: true });
    if (signal.aborted) aborted(); else video.load();
  });
  const texture = new THREE.VideoTexture(video);
  texture.minFilter = texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  const material = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    uniforms: { film: { value: texture }, night: { value: 0 }, reveal: { value: 0 } },
    vertexShader: `varying vec2 filmUV;
      void main(){filmUV=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
    fragmentShader: `uniform sampler2D film;uniform float night;uniform float reveal;varying vec2 filmUV;
      void main(){
        float gray=texture2D(film,vec2(filmUV.x,.5+filmUV.y*.5)).r;
        float alpha=smoothstep(.035,.965,texture2D(film,vec2(filmUV.x,filmUV.y*.5)).r);
        if(alpha<.003)discard;
        float light=.027+(.24+night*.24)*pow(gray,.68);
        gl_FragColor=vec4(vec3(light*.94,light,light*.96),alpha*reveal);
      }`
  });
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(4.2 * 640 / 690, 4.2), material);
  const group = new THREE.Group();
  group.add(plane);
  let desiredFrame = 0;
  let shownFrame = 0;
  let seeking = false;
  let seekTimer;

  function seek() {
    if (destroyed || seeking || desiredFrame === shownFrame) return;
    seeking = true;
    video.currentTime = Math.min(video.duration - .001, (desiredFrame + .2) / metadata.fps);
    // A stalled decoder must not create an endless rendering loop.
    clearTimeout(seekTimer);
    seekTimer = setTimeout(() => { seeking = false; }, 1000);
  }
  const seeked = () => {
    clearTimeout(seekTimer);
    shownFrame = Math.max(0, Math.min(metadata.frames - 1, Math.floor(video.currentTime * metadata.fps)));
    texture.needsUpdate = true;
    seeking = false;
    onFrame();
    if (shownFrame !== desiredFrame) seek();
  };
  video.addEventListener('seeked', seeked);

  return {
    group,
    update(progress, reveal, dark) {
      desiredFrame = Math.round(Math.max(0, Math.min(1, progress)) * (metadata.frames - 1));
      if (reveal > .005) seek();
      group.visible = reveal > .005;
      material.uniforms.night.value = dark ? 1 : 0;
      material.uniforms.reveal.value = reveal;
      const first = metadata.bounds[0];
      const last = metadata.bounds.at(-1);
      const displayedProgress = shownFrame / (metadata.frames - 1);
      const centre = (first[0] + first[2]) / 2 + ((last[0] + last[2] - first[0] - first[2]) / 2) * displayedProgress;
      const bottom = metadata.bounds[shownFrame][3];
      plane.position.set(-(centre / 640 - .5) * 4.2 * 640 / 690, -1.48 - (.5 - bottom / 690) * 4.2, 0);
      return { frame: shownFrame, target: desiredFrame };
    },
    dispose() {
      destroyed = true;
      clearTimeout(seekTimer);
      video.removeEventListener('seeked', seeked);
      plane.geometry.dispose();
      material.dispose();
      texture.dispose();
      unload();
    }
  };
}
