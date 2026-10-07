import './identity.css';

const clamp = value => Math.max(0, Math.min(1, value));
const smooth = (start, end, value) => {
  const t = clamp((value - start) / (end - start));
  return t * t * (3 - 2 * t);
};
const mix = (a, b, t) => a + (b - a) * t;

// The same words remain in the scene as the description contracts into the name.
// Measure the local typeface once per resize; scroll frames need no layout reads.
export function createIdentity(container, requestFrame) {
  const element = document.createElement('div');
  element.id = 'opening-identity';
  element.className = 'opening-identity';
  element.innerHTML = `
    <h1 id="site-title" class="sr-only">synSPORT.</h1>
    <p class="sr-only">Synthetic data generation applied to sport</p>
    <div class="identity-words" aria-hidden="true">
      <span class="identity-piece identity-syn"><span class="identity-source">Syn</span><span class="identity-target">syn</span></span>
      <span class="identity-piece identity-tail">thetic</span>
      <span class="identity-piece identity-data">data generation</span>
      <span class="identity-piece identity-applied">applied to</span>
      <span class="identity-piece identity-sport"><span class="identity-source">sport</span><span class="identity-target">SPORT</span></span>
      <span class="identity-piece identity-dot">.</span>
      <p class="identity-static-description">Synthetic data generation applied to sport</p>
    </div>`;
  container.append(element);
  const parts = Object.fromEntries(['syn', 'tail', 'data', 'applied', 'sport', 'dot'].map(name => [name, element.querySelector(`.identity-${name}`)]));
  let layout;
  let disposed = false;

  function measure() {
    const probe = document.createElement('span');
    probe.className = 'identity-measure';
    probe.setAttribute('aria-hidden', 'true');
    element.append(probe);
    const widths = {};
    for (const [key, text, weight] of [
      ['synFrom', 'Syn', 850], ['synTo', 'syn', 850], ['tail', 'thetic', 850],
      ['data', 'data generation', 500], ['applied', 'applied to', 500],
      ['sportFrom', 'sport', 850], ['sportTo', 'SPORT', 850], ['dot', '.', 850],
    ]) {
      probe.textContent = text;
      probe.style.fontWeight = weight;
      widths[key] = probe.getBoundingClientRect().width;
    }
    probe.remove();
    const width = container.clientWidth;
    const height = container.clientHeight;
    const phraseScale = Math.min(width * .8 / Math.max(widths.data, widths.synFrom + widths.tail), height * .104 / 100, .96);
    const finalWidth = widths.synTo + widths.sportTo + widths.dot;
    const finalScale = Math.min(width * .88 / finalWidth, height * .30 / 100, 3.5);
    const lineHeight = 120 * phraseScale;
    const phraseTop = height * .50 - lineHeight * 1.4;
    const firstLeft = (width - (widths.synFrom + widths.tail) * phraseScale) / 2;
    const lastWidth = widths.applied + 25 + widths.sportFrom;
    const lastLeft = (width - lastWidth * phraseScale) / 2;
    layout = {
      width, height, phraseScale, finalScale, widths,
      finalX: (width - finalWidth * finalScale) / 2,
      finalY: height * .50 - 50 * finalScale,
      phrase: {
        syn: [firstLeft, phraseTop],
        tail: [firstLeft + widths.synFrom * phraseScale, phraseTop],
        data: [(width - widths.data * phraseScale) / 2, phraseTop + lineHeight],
        applied: [lastLeft, phraseTop + lineHeight * 2],
        sport: [lastLeft + (widths.applied + 25) * phraseScale, phraseTop + lineHeight * 2],
      },
    };
    requestFrame();
  }

  function transform(part, x, y, scale, opacity = 1) {
    // Set type at its displayed size so both the small phrase and large name stay sharp.
    part.style.fontSize = `${(scale * 100).toFixed(3)}px`;
    part.style.transform = `translate3d(${x.toFixed(3)}px, ${y.toFixed(3)}px, 0)`;
    part.style.opacity = opacity.toFixed(4);
  }

  function update(progress, reduced) {
    if (!layout) measure();
    const { height, phraseScale, finalScale, widths, finalX, phrase } = layout;
    const blend = reduced ? 1 : smooth(.73, .89, progress);
    const arrival = reduced ? 1 : smooth(.58, .65, progress);
    const finalY = reduced ? height * .72 - 50 * finalScale : layout.finalY;
    const scale = mix(phraseScale, finalScale, blend);
    const revealShift = reduced ? 0 : (1 - arrival) * 36;
    element.style.opacity = arrival.toFixed(4);
    element.classList.toggle('is-static', reduced);
    element.dataset.progress = blend.toFixed(4);
    element.dataset.phase = reduced || progress >= .89 ? 'identity' : progress >= .73 ? 'transform' : 'phrase';

    transform(parts.syn, mix(phrase.syn[0], finalX, blend), mix(phrase.syn[1], finalY, blend) + revealShift, scale);
    transform(parts.sport, mix(phrase.sport[0], finalX + widths.synTo * finalScale, blend), mix(phrase.sport[1], finalY, blend) + revealShift, scale);

    const changeCase = smooth(.04, .34, blend);
    for (const part of [parts.syn, parts.sport]) {
      part.querySelector('.identity-source').style.opacity = String(1 - changeCase);
      part.querySelector('.identity-target').style.opacity = String(changeCase);
    }

    const tailFade = 1 - smooth(.02, .34, blend);
    const wordsFade = 1 - smooth(.04, .40, blend);
    transform(parts.tail, phrase.tail[0] + 45 * blend, phrase.tail[1] - 26 * blend + revealShift, phraseScale, tailFade);
    transform(parts.data, phrase.data[0], phrase.data[1] - 30 * blend + revealShift, phraseScale * (1 - .07 * blend), wordsFade);
    transform(parts.applied, phrase.applied[0] - 32 * blend, phrase.applied[1] + 24 * blend + revealShift, phraseScale, wordsFade);

    const dotReveal = smooth(.77, 1, blend);
    transform(parts.dot, finalX + (widths.synTo + widths.sportTo) * finalScale, finalY + (1 - dotReveal) * 12, finalScale, dotReveal);
    element.style.setProperty('--identity-description-y', `${Math.min(height - 95, finalY + finalScale * 104)}px`);
    return blend;
  }

  measure();
  document.fonts.ready.then(() => { if (!disposed) measure(); });
  return {
    update,
    resize: measure,
    dispose() { disposed = true; element.remove(); },
  };
}
