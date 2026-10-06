import { test, expect, openSite, openChapter } from './helpers.js';

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
    await page.locator(`#${id}`).scrollIntoViewIfNeeded();
    await expect(page.locator(`#${id}`)).toBeInViewport();
    await expect(page.locator(`#${id} h2`).first()).toBeVisible();
  }
});

test('scrolling seeks decoded throw frames forward and back', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'reduced-motion', 'Reduced motion intentionally uses the static portrait.');
  await openSite(page);
  const artwork = page.locator('#opening-art');
  await expect(artwork).toHaveAttribute('data-renderer', 'webgl');
  const frames = [];
  for (const fraction of [0.5, 0.85, 0.5]) {
    await page.evaluate(value => {
      const home = document.getElementById('home');
      scrollTo({ top: home.offsetTop + (home.offsetHeight - innerHeight) * value, behavior: 'instant' });
    }, fraction);
    await expect.poll(async () => Number(await artwork.getAttribute('data-progress'))).toBeCloseTo(fraction, 2);
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
  await expect(page.locator('#objective-title')).toBeInViewport();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.locator('#loader')).toBeHidden();
  await expect(page.locator('#objective-title')).toBeInViewport();
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
