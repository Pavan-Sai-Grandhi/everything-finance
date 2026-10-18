/* Offline browser integration for the actual report runtime. Called by
 * test_render.py when EF_REPORT_BROWSER_CHECK=1; requires Playwright. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

(async () => {
  const browser = await chromium.launch({executablePath: process.argv[3], headless: true});
  try {
    for (const name of ['deep-analysis', 'wealth-report', 'mf-analysis', 'sector-analysis', 'daily-brief']) {
      const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
      const errors = [];
      page.on('pageerror', error => errors.push(String(error)));
      await page.route(/^https?:/, route => route.abort());
      await page.goto(pathToFileURL(path.join(process.argv[2], name + '.html')).href);
      await page.evaluate(() => document.fonts.ready);
      if (name !== 'daily-brief') {
        await page.evaluate(() => customElements.whenDefined('deck-stage'));
        // Force a long section so this remains a regression even when samples shorten.
        await page.evaluate(() => {
          const stage = document.querySelector('deck-stage');
          stage.goTo(0);
          const block = document.createElement('p');
          block.style.cssText = 'flex:none;height:2000px';
          block.textContent = 'Long report evidence';
          stage.children[0].appendChild(block);
        });
        assert.equal(await page.evaluate(() => getComputedStyle(document.querySelector('[data-deck-active]')).overflowY), 'auto');
        await page.keyboard.press('End');
        assert.ok(await page.evaluate(() => document.querySelector('[data-deck-active]').scrollTop > 0));
        assert.equal(await page.evaluate(() => document.querySelector('deck-stage').index), 0);
        await page.keyboard.press('ArrowRight');
        assert.equal(await page.evaluate(() => document.querySelector('deck-stage').index), 1);
        const disclosure = await page.evaluate(() => {
          const stage = document.querySelector('deck-stage');
          const index = [...stage.children].findIndex(s => s.querySelector('summary'));
          if (index < 0) return null;
          stage.goTo(index);
          const summary = stage.children[index].querySelector('summary');
          summary.parentElement.open = false;
          summary.focus();
          return index;
        });
        if (disclosure !== null) {
          await page.keyboard.press('Space');
          assert.equal(await page.evaluate(() => document.querySelector('deck-stage').index), disclosure);
          assert.ok(await page.evaluate(() => document.activeElement.parentElement.open), 'Space opens disclosure');
          await page.evaluate(() => { document.activeElement.parentElement.open = false; });
        }
        await page.emulateMedia({media: 'print'});
        const sizes = await page.evaluate(() => [...document.querySelectorAll('deck-stage > section')].map(s => ({
          height: s.clientHeight, scroll: s.scrollHeight, overflow: getComputedStyle(s).overflowY,
        })));
        assert.ok(sizes.every(s => s.scroll <= s.height + 1 && s.overflow === 'visible'), JSON.stringify({name, sizes}));
      } else {
        await page.setViewportSize({width: 390, height: 844});
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'brief overflows phone viewport');
      }
      assert.deepEqual(errors, [], name);
      await page.close();
    }
    console.log('Five report templates: browser checks passed');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
