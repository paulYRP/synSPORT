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
  await expect(page.locator(`#${id}`)).toBeInViewport();
  await page.locator(`[data-read="${id}"]`).first().click();
  await expect(page.locator('#reader')).toBeVisible();
}
