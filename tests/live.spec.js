import { test, expect, openSite, openChapter, scrollDiagram, cameraBox, expectCaptionMatches } from './helpers.js';

test('the deployed site serves its media and both chapters', async ({ page, request, baseURL }) => {
  test.setTimeout(150_000);
  if (process.env.CI && process.env.GITHUB_SHA) {
    await page.goto(`./?revision=${encodeURIComponent(process.env.GITHUB_SHA)}`, { waitUntil: 'domcontentloaded' });
    await expect(async () => {
      const revision = await page.evaluate(() => window.synsportRevision);
      if (revision !== process.env.GITHUB_SHA) await page.reload({ waitUntil: 'domcontentloaded' });
      expect(await page.evaluate(() => window.synsportRevision)).toBe(process.env.GITHUB_SHA);
    }).toPass({ timeout: 90_000, intervals: [2000, 5000, 10000] });
    await expect(page.locator('#loader')).toBeHidden();
    await expect(page).toHaveTitle(/synSPORT|QUT|Judo/i);
  } else await openSite(page);
  await expect.poll(() => page.evaluate(() => window.synsportRevision)).toBeTruthy();
  await expect(page.locator('#introduction p')).toHaveText('Synthetic data generation applied to sport');
  await expect(page.locator('#chapter-position')).toHaveCount(0);
  for (const asset of ['media/motion.json', 'media/judoka.png', 'media/throw.mp4', 'fonts/roboto.css', 'figures/framework.svg', 'figures/objective.svg']) {
    const response = await request.get(new URL(asset, baseURL).href, { headers: { Range: 'bytes=0-1023' } });
    expect(response.ok(), `${asset} should be available on the deployed site`).toBeTruthy();
    expect(response.headers()['content-type'] ?? '').not.toContain('text/html');
  }
  for (const id of ['framework', 'objective']) {
    const section = await scrollDiagram(page, id, 0);
    const overview = await cameraBox(section);
    expect(await section.locator('.diagram-viewport > svg path').count()).toBeGreaterThan(20);
    await scrollDiagram(page, id, .4);
    await expectCaptionMatches(section);
    const focused = await cameraBox(section);
    expect(focused[2] * focused[3]).toBeLessThan(overview[2] * overview[3]);
    await scrollDiagram(page, id, 1);
    expect(await cameraBox(section)).toEqual(overview);
    await scrollDiagram(page, id, 0);
    expect(await cameraBox(section)).toEqual(overview);
    await openChapter(page, id);
    await expect(page.locator('#reader')).toContainText(id === 'framework' ? /synthetic/i : /regain/i);
    await page.locator('#reader-close').click();
  }
});
