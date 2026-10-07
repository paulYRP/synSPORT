import { test, expect, openSite, openChapter, scrollDiagram, scrollOpening, cameraBox, layerTransforms, expectCaptionMatches, expectChapterEntry } from './helpers.js';

test('the published-base opening loads and scrolls through readable chapters', async ({ page }) => {
  await openSite(page);
  for (const id of ['framework', 'objective']) {
    const section = page.locator(`#${id}`);
    await section.scrollIntoViewIfNeeded();
    await expect(section).toBeInViewport();
    await expect(section.locator('h1,h2,h3').first()).toBeVisible();
  }
  await page.locator('#home').scrollIntoViewIfNeeded();
  await expect(page.locator('#home')).toBeInViewport();
  const sizes = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: innerWidth }));
  expect(sizes.width, 'Reading should not require horizontal page scrolling').toBeLessThanOrEqual(sizes.viewport + 1);
});

test('the menu opens both full chapters and returns to the narrative', async ({ page }) => {
  await openSite(page);
  for (const id of ['framework', 'objective']) {
    await openChapter(page, id);
    const reader = page.locator('#reader');
    await expect(reader.locator('h1,h2,h3').first()).toBeVisible();
    expect((await reader.innerText()).trim().length, 'The chapter should contain the full readable text').toBeGreaterThan(250);
    await page.locator('#reader-close').click();
    await expect(reader).toBeHidden();
    await expect(page.locator(`#${id}`)).toBeInViewport();
  }
});

test('keyboard dismissal and theme controls remain usable', async ({ page }) => {
  await openSite(page);
  await page.locator('#menu-toggle').click();
  await expect(page.locator('#site-menu')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#site-menu')).toBeHidden();
  await expect(page.locator('#menu-toggle')).toBeFocused();

  const before = await page.locator('html').getAttribute('data-theme');
  await page.locator('#theme-toggle').click();
  await expect(page.locator('html')).not.toHaveAttribute('data-theme', before ?? '');
  await openChapter(page, 'objective');
  await page.keyboard.press('Escape');
  await expect(page.locator('#reader')).toBeHidden();
  await expect(page.locator('[data-read="objective"]').first()).toBeFocused();
});

test('reduced motion keeps the full narrative accessible', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'reduced-motion', 'This check exercises the reduced-motion layout.');
  await openSite(page);
  expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBeTruthy();
  for (const id of ['framework', 'objective']) {
    const section = page.locator(`#${id}`);
    await section.scrollIntoViewIfNeeded();
    await expect(section).toHaveAttribute('data-reduced', 'true');
    await expect(section).toHaveAttribute('data-ready', 'true');
    for (const caption of await section.locator('.diagram-caption').all()) {
      await caption.scrollIntoViewIfNeeded();
      await expect(caption).toBeVisible();
      await expect(caption).toHaveAttribute('aria-hidden', 'false');
    }
    const box = await cameraBox(section);
    expect(box).toEqual(id === 'framework' ? [0, 0, 2160, 1404] : [0, 0, 2400, 1400]);
  }
});

test('the opening contains the title and phrase without a separate introduction or centre header label', async ({ page }) => {
  await openSite(page);
  await expect(page.locator('#introduction')).toHaveCount(0);
  await expect(page.locator('#home #site-title')).toHaveText('synSPORT.');
  await expect(page.locator('#home #opening-identity')).toContainText('Synthetic data generation applied to sport');
  await expect(page.locator('#chapter-position')).toHaveCount(0);
});

test('the same opening scene transforms the phrase into the logo and reverses with scrolling', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'reduced-motion', 'Reduced motion presents the complete identity without animated typography.');
  await openSite(page);
  const artwork = await scrollOpening(page, .69);
  const identity = page.locator('#opening-identity');
  await expect(artwork).toHaveAttribute('data-phase', 'phrase');
  await expect(identity).toBeInViewport();
  for (const selector of ['.identity-tail', '.identity-data', '.identity-applied']) {
    await expect.poll(() => identity.locator(selector).evaluate(node => Number(getComputedStyle(node).opacity))).toBeGreaterThan(.98);
  }
  await scrollOpening(page, .81);
  await expect(artwork).toHaveAttribute('data-phase', 'transform');
  const middle = await identity.locator('.identity-syn,.identity-sport').evaluateAll(nodes => nodes.map(node => ({ transform: getComputedStyle(node).transform, size: getComputedStyle(node).fontSize })));
  await scrollOpening(page, .95);
  await expect(artwork).toHaveAttribute('data-phase', 'identity');
  await expect(identity).toBeInViewport();
  for (const selector of ['.identity-tail', '.identity-data', '.identity-applied']) {
    await expect.poll(() => identity.locator(selector).evaluate(node => Number(getComputedStyle(node).opacity))).toBeLessThan(.02);
  }
  await expect.poll(() => identity.locator('.identity-dot').evaluate(node => Number(getComputedStyle(node).opacity))).toBeGreaterThan(.98);
  await expect(identity.locator('.identity-syn .identity-target')).toHaveText('syn');
  await expect(identity.locator('.identity-sport .identity-target')).toHaveText('SPORT');
  for (const target of await identity.locator('.identity-target').all()) await expect(target).toHaveCSS('opacity', '1');
  await scrollOpening(page, .81);
  const reverse = await identity.locator('.identity-syn,.identity-sport').evaluateAll(nodes => nodes.map(node => ({ transform: getComputedStyle(node).transform, size: getComputedStyle(node).fontSize })));
  expect(reverse, 'Reversing should restore the same typographic composition').toEqual(middle);
  await scrollOpening(page, .69);
  await expect(artwork).toHaveAttribute('data-phase', 'phrase');
  const sizes = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: innerWidth }));
  expect(sizes.width).toBeLessThanOrEqual(sizes.viewport + 1);
});

test('the camera displays the published source SVG artwork', async ({ page, request, baseURL }) => {
  await openSite(page);
  for (const id of ['framework', 'objective']) {
    const section = page.locator(`#${id}`);
    await expect(section).toHaveAttribute('data-ready', 'true');
    const response = await request.get(new URL(`figures/${id}.svg`, baseURL).href);
    expect(response.ok()).toBeTruthy();
    const fidelity = await section.locator('.diagram-viewport > svg').evaluate((svg, source) => {
      const original = new DOMParser().parseFromString(source, 'image/svg+xml');
      const paths = element => [...element.querySelectorAll('path')].map(path => path.getAttribute('d'));
      const images = element => [...element.querySelectorAll('image')].map(image => image.getAttribute('href') || image.getAttributeNS('http://www.w3.org/1999/xlink', 'href'));
      const text = element => [...element.querySelectorAll('text')].map(node => node.textContent.trim());
      return {
        paths: paths(svg).length,
        samePaths: JSON.stringify(paths(svg)) === JSON.stringify(paths(original)),
        sameImages: JSON.stringify(images(svg)) === JSON.stringify(images(original)),
        sameText: JSON.stringify(text(svg)) === JSON.stringify(text(original)),
      };
    }, await response.text());
    expect(fidelity.paths).toBeGreaterThan(20);
    expect(fidelity.samePaths, 'Camera artwork must retain the scientific figure geometry').toBeTruthy();
    expect(fidelity.sameImages, 'Embedded source figures must remain in the camera').toBeTruthy();
    expect(fidelity.sameText, 'Original diagram labels must remain intact').toBeTruthy();
    await expect(section.locator('.diagram-source')).toHaveCount(1);
    const references = await section.locator('.diagram-layer use').evaluateAll(nodes => nodes.map(node => {
      const reference = node.getAttribute('href') || node.getAttributeNS('http://www.w3.org/1999/xlink', 'href');
      const target = reference?.startsWith('#') ? document.getElementById(reference.slice(1)) : null;
      return Boolean(target?.closest('.diagram-source'));
    }));
    expect(references.length, 'Separated components should reuse the source diagram geometry').toBeGreaterThan(3);
    expect(references.every(Boolean), 'Every separated component must refer to the intact source figure').toBeTruthy();
  }
});

test('scrolling pairs every diagram scene with its explanation and restores the overview', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'reduced-motion', 'Reduced motion uses complete static figures and all captions.');
  test.setTimeout(90_000);
  await openSite(page);
  for (const id of ['framework', 'objective']) {
    const section = await scrollDiagram(page, id, 0);
    const overview = await cameraBox(section);
    await expect(section).toHaveAttribute('data-layout', 'overview');
    const views = Number(await section.getAttribute('data-views'));
    expect(views).toBeGreaterThanOrEqual(6);
    for (let view = 0; view < views; view++) {
      await scrollDiagram(page, id, view / (views - 1));
      await expectCaptionMatches(section);
    }
    expect(await cameraBox(section), 'The chapter should end by reconnecting the complete diagram').toEqual(overview);
    await scrollDiagram(page, id, .42857);
    await expectCaptionMatches(section);
    await scrollDiagram(page, id, 0);
    expect(await cameraBox(section), 'Scrolling up should restore the original overview').toEqual(overview);
    await expect(section).toHaveAttribute('data-layout', 'overview');
  }
});

test('diagram components separate with their labels and return to the same arrangement', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'reduced-motion', 'Reduced motion retains the source diagram without separation.');
  await openSite(page);
  for (const id of ['framework', 'objective']) {
    const section = await scrollDiagram(page, id, 0);
    const overview = await layerTransforms(section);
    expect(overview.length, 'A chapter should contain multiple independently positioned components').toBeGreaterThan(3);
    await scrollDiagram(page, id, .4);
    await expectCaptionMatches(section);
    const focused = await layerTransforms(section);
    expect(focused, 'Focusing should move the components out of the full-figure arrangement').not.toEqual(overview);
    expect(new Set(focused.map(layer => layer.transform)).size, 'Components should occupy distinct positions').toBeGreaterThan(2);
    const active = section.locator('.diagram-layer[data-active="true"]');
    await expect(active).toHaveCount(1);
    await expect(active).toHaveAttribute('data-layer-key', await section.getAttribute('data-active-layer'));
    await scrollDiagram(page, id, .78);
    expect(await layerTransforms(section)).not.toEqual(focused);
    await scrollDiagram(page, id, .4);
    expect(await layerTransforms(section), 'Reverse scrolling should restore component positions and focus').toEqual(focused);
    await scrollDiagram(page, id, 1);
    await expect(section).toHaveAttribute('data-layout', 'overview');
    expect(await layerTransforms(section), 'The final view should reconnect the source composition').toEqual(overview);
  }
});

test('the complete figure opens and returns to the same camera position', async ({ page }, testInfo) => {
  await openSite(page);
  for (const id of ['framework', 'objective']) {
    const section = page.locator(`#${id}`);
    if (testInfo.project.name === 'reduced-motion') await section.locator('[data-figure]').scrollIntoViewIfNeeded();
    else await scrollDiagram(page, id, .4);
    await section.locator(`[data-figure="${id}"]`).click();
    const position = await page.evaluate(() => scrollY);
    await expect(page.locator('#reader')).toHaveAttribute('data-view', 'figure');
    const figure = page.locator('#reader-content img');
    await expect(figure).toHaveAttribute('src', new RegExp(`figures/${id}\\.svg$`));
    await expect.poll(() => figure.evaluate(image => image.complete && image.naturalWidth > 0)).toBeTruthy();
    await page.locator('#reader-close').click();
    await expect(page.locator('#reader')).toBeHidden();
    expect(await page.evaluate(() => scrollY)).toBeCloseTo(position, 0);
    await expect(section.locator(`[data-figure="${id}"]`)).toBeFocused();
  }
});

test('mobile enlarged text remains readable without clipping the narrative', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile', 'This check exercises narrow-screen text enlargement.');
  await openSite(page);
  await page.addStyleTag({ content: '.diagram-caption p { font-size: 32px !important; } .diagram-caption h3 { font-size: 56px !important; }' });
  for (const id of ['framework', 'objective']) {
    const section = page.locator(`#${id}`);
    await expect(section).toHaveAttribute('data-reduced', 'true');
    await expect(section).toHaveAttribute('data-static-reason', 'text-size');
    for (const caption of await section.locator('.diagram-caption').all()) {
      await caption.scrollIntoViewIfNeeded();
      await expect(caption).toBeVisible();
      const metrics = await caption.evaluate(element => {
        const paragraph = element.querySelector('p');
        return { font: parseFloat(getComputedStyle(paragraph).fontSize), height: element.clientHeight, content: element.scrollHeight };
      });
      expect(metrics.font).toBe(32);
      expect(metrics.content, 'Enlarged narrative text must not be clipped').toBeLessThanOrEqual(metrics.height + 1);
    }
    await section.locator('[data-read]').click();
    await expect(page.locator('#reader')).toBeVisible();
    await page.locator('#reader-close').click();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width + 1);
});

test('short-screen menus scroll to every chapter and close normally', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile', 'This check exercises short portrait and landscape menus.');
  await openSite(page);
  for (const viewport of [{ width: 320, height: 568 }, { width: 844, height: 390 }]) {
    await page.setViewportSize(viewport);
    await page.locator('#menu-toggle').click();
    const menu = page.locator('#site-menu');
    await expect(menu).toBeVisible();
    for (const id of ['home', 'framework', 'objective']) {
      const link = menu.locator(`a[href="#${id}"]`);
      await link.scrollIntoViewIfNeeded();
      await expect(link).toBeInViewport();
    }
    await menu.locator('.menu-footer').scrollIntoViewIfNeeded();
    await expect(menu.locator('.menu-footer')).toBeInViewport();
    await menu.locator('a[href="#objective"]').click();
    await expect(menu).toBeHidden();
    await expect(page.locator('#objective')).toBeInViewport();
    await page.locator('#menu-toggle').click();
    await page.keyboard.press('Escape');
    await expect(menu).toBeHidden();
  }
});

test('scrolling seeks decoded throw frames forward and back', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'reduced-motion', 'Reduced motion intentionally uses the static portrait.');
  await openSite(page);
  const artwork = page.locator('#opening-art');
  await expect(artwork).toHaveAttribute('data-renderer', 'webgl');
  const frames = [];
  for (const fraction of [0.4, 0.49, 0.4]) {
    await scrollOpening(page, fraction);
    await expect.poll(async () => artwork.evaluate(element => {
      const frame = Number(element.dataset.filmFrame);
      const target = Number(element.dataset.targetFrame);
      return Number.isFinite(frame) && frame > 0 && frame === target;
    })).toBeTruthy();
    frames.push(Number(await artwork.getAttribute('data-film-frame')));
  }
  expect(frames[1]).toBeGreaterThan(frames[0]);
  expect(Math.abs(frames[2] - frames[0])).toBeLessThanOrEqual(1);
});

test('a direct chapter link survives refresh', async ({ page }) => {
  await page.goto('./#objective', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#loader')).toBeHidden();
  await expectChapterEntry(page, 'objective');
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.locator('#loader')).toBeHidden();
  await expectChapterEntry(page, 'objective');
});

test('standalone chapters retain figures, citations and return links', async ({ page }) => {
  for (const chapter of ['framework', 'objective']) {
    await page.goto(`./chapters/${chapter}.html`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('h1')).toHaveText(new RegExp(chapter, 'i'));
    const citationTargets = await page.locator('a[role="doc-biblioref"]').evaluateAll(links =>
      links.map(link => Boolean(document.getElementById(link.hash.slice(1)))));
    expect(citationTargets.length, 'The full chapter must retain its source citations').toBeGreaterThan(0);
    expect(citationTargets.every(Boolean), 'Every citation should reach its bibliography entry').toBeTruthy();
    for (const image of await page.locator('article img').all()) {
      await image.scrollIntoViewIfNeeded();
      await expect.poll(() => image.evaluate(element => element.complete && element.naturalWidth > 0)).toBeTruthy();
    }
    await expect(page.locator(`a[href="../#${chapter}"]`).first()).toHaveAttribute('href', `../#${chapter}`);
  }
});
