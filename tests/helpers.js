import { test as base, expect } from '@playwright/test';

// Browser failures and broken same-origin resources must fail the interaction test.
export const test = base.extend({
  browserHealth: [async ({ page, baseURL }, use) => {
    const errors = [];
    const origin = new URL(baseURL).origin;
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => {
      if (message.type() === 'error') errors.push(message.text());
    });
    page.on('response', response => {
      if (new URL(response.url()).origin === origin && response.status() >= 400) {
        errors.push(`${response.status()} ${response.url()}`);
      }
    });
    await use();
    expect(errors, 'The page should have no browser errors or failed local resources').toEqual([]);
  }, { auto: true }],
});

export { expect };

export async function openSite(page) {
  const response = await page.goto('./', { waitUntil: 'domcontentloaded' });
  expect(response?.ok(), 'The production entry point should respond successfully').toBeTruthy();
  await expect(page).toHaveTitle(/synSPORT|QUT|Judo/i);
  await expect(page.locator('#menu-toggle')).toBeVisible();
  await expect(page.locator('#loader')).toBeHidden();
}

export async function openChapter(page, id) {
  await page.locator('#menu-toggle').click();
  const menu = page.locator('#site-menu');
  await expect(menu).toBeVisible();
  await menu.locator(`a[href="#${id}"]`).click();
  await expectChapterEntry(page, id);
  await page.locator(`[data-read="${id}"]`).first().click();
  await expect(page.locator('#reader')).toBeVisible();
}

export async function expectChapterEntry(page, id) {
  const section = page.locator(`#${id}`);
  await expect(section).toHaveAttribute('data-ready', 'true');
  await expect(page.locator(`#${id}-title`)).toBeInViewport();
  if (await section.getAttribute('data-reduced') === 'false') {
    for (const button of await section.locator('.diagram-actions button').all()) {
      await expect(button, 'Chapter entry should show the complete-diagram and full-text actions').toBeInViewport({ ratio: 1 });
    }
  }
}

export async function scrollDiagram(page, id, fraction) {
  const section = page.locator(`#${id}`);
  await expect(section).toHaveAttribute('data-ready', 'true');
  await section.evaluate((element, progress) => {
    const rect = element.getBoundingClientRect();
    scrollTo({ top: scrollY + rect.top + (rect.height - innerHeight) * progress, behavior: 'instant' });
  }, fraction);
  await expect.poll(async () => Number(await section.getAttribute('data-progress'))).toBeCloseTo(fraction, 3);
  return section;
}

export async function cameraBox(section) {
  return section.locator('.diagram-viewport > svg').evaluate(svg => {
    const { x, y, width, height } = svg.viewBox.baseVal;
    return [x, y, width, height];
  });
}

export async function expectCaptionMatches(section) {
  const index = await section.getAttribute('data-scene-index');
  const current = section.locator('.diagram-caption.is-current');
  await expect(current).toHaveCount(1);
  await expect(current).toHaveAttribute('data-scene-index', index);
  await expect(current).toHaveCSS('opacity', '1');
  await expect(current.locator('h3')).toBeVisible();
  await expect(current.locator('p')).toBeVisible();
  await expect(section.locator('.diagram-viewport')).toHaveAttribute('data-scene-index', index);
}
