// @ts-check
const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const FIXTURE_PATH = path.join(__dirname, 'fixtures', 'sample.srt');
const SRT_CONTENT = fs.readFileSync(FIXTURE_PATH, 'utf-8');

// ---------------------------------------------------------------------------
// Helper: upload the sample SRT fixture via the file input
// ---------------------------------------------------------------------------
async function uploadSrt(page) {
  const [fileChooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    page.locator('#fileInput').click(),
  ]);
  await fileChooser.setFiles(FIXTURE_PATH);
  // Wait until at least one subtitle block is rendered
  await expect(page.locator('#editor article')).not.toHaveCount(0);
}

// ---------------------------------------------------------------------------
// Page load & basic structure
// ---------------------------------------------------------------------------
test.describe('Page structure', () => {
  test('loads the page with correct title', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle('SRT Fix PWA');
  });

  test('shows all required UI controls', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#fileInput')).toBeVisible();
    await expect(page.locator('#applyCorrections')).toBeVisible();
    await expect(page.locator('#exportSRT')).toBeVisible();
    await expect(page.locator('#savePatched')).toBeVisible();
    await expect(page.locator('#loadHistory')).toBeVisible();
    await expect(page.locator('#clearHistory')).toBeVisible();
    await expect(page.locator('#speechToggle')).toBeVisible();
  });

  test('editor section is empty before any file is loaded', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#editor article')).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// SRT parsing – verified through the rendered output
// ---------------------------------------------------------------------------
test.describe('SRT parsing', () => {
  test('parses all 95 subtitle blocks from the fixture', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    await expect(page.locator('#editor article')).toHaveCount(95);
  });

  test('first subtitle has the correct timecode and text', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    const firstBlock = page.locator('#editor article').first();
    await expect(firstBlock.locator('.meta')).toContainText('00:00:05,897 --> 00:00:08,748');
    await expect(firstBlock.locator('textarea')).toHaveValue('SUPERSTAR');
  });

  test('last subtitle has the correct timecode and text', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    const lastBlock = page.locator('#editor article').last();
    await expect(lastBlock.locator('.meta')).toContainText('00:06:24,490 --> 00:06:26,038');
    const lastValue = await lastBlock.locator('textarea').inputValue();
    expect(lastValue.trim()).toBe('A jsme tady i včas.');
  });

  test('subtitle index is shown in the meta section', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    const firstMeta = page.locator('#editor article').first().locator('.meta');
    await expect(firstMeta).toContainText('#1');
  });

  test('multi-line subtitle content is preserved', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    // Entry #2: "První, čeho si na\ntéhle dámě všimnete,"
    const secondBlock = page.locator('#editor article').nth(1);
    const value = await secondBlock.locator('textarea').inputValue();
    expect(value).toContain('První, čeho si na');
    expect(value).toContain('téhle dámě všimnete,');
  });

  test('subtitle with special Czech characters is parsed correctly', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    // Entry #6 contains Czech diacritics and multi-line
    const block6 = page.locator('#editor article').nth(5);
    const value = await block6.locator('textarea').inputValue();
    expect(value).toContain('brýle');
  });

  test('subtitle containing colon in text is parsed correctly', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    // Entry #28: "Glen: je jejím manažerem už 7 let."
    const block28 = page.locator('#editor article').nth(27);
    await expect(block28.locator('textarea')).toHaveValue('Glen: je jejím manažerem už 7 let.');
  });

  test('subtitle with ellipsis is parsed correctly', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    // Entry #17: "A je to naprostá pí..."
    const block17 = page.locator('#editor article').nth(16);
    await expect(block17.locator('textarea')).toHaveValue('A je to naprostá pí...');
  });
});

// ---------------------------------------------------------------------------
// Text editing
// ---------------------------------------------------------------------------
test.describe('Text editing', () => {
  test('editing a subtitle marks it as modified', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    const firstBlock = page.locator('#editor article').first();
    await expect(firstBlock).not.toHaveClass(/modified/);
    await firstBlock.locator('textarea').fill('SUPERSTAR edited');
    await expect(firstBlock).toHaveClass(/modified/);
  });

  test('edited text is retained in the textarea', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    const firstTextarea = page.locator('#editor article').first().locator('textarea');
    await firstTextarea.fill('New subtitle text');
    await expect(firstTextarea).toHaveValue('New subtitle text');
  });

  test('editing one subtitle does not affect others', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    const firstTextarea = page.locator('#editor article').first().locator('textarea');
    await firstTextarea.fill('Changed first');
    const secondTextarea = page.locator('#editor article').nth(1).locator('textarea');
    const secondValue = await secondTextarea.inputValue();
    expect(secondValue).toContain('První, čeho si na');
  });

  test('unmodified subtitles do not have the modified class', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    // Edit only the first block
    await page.locator('#editor article').first().locator('textarea').fill('edited');
    // Second block should remain unmodified
    await expect(page.locator('#editor article').nth(1)).not.toHaveClass(/modified/);
  });
});

// ---------------------------------------------------------------------------
// LocalStorage history – save, load, clear
// ---------------------------------------------------------------------------
test.describe('History operations', () => {
  test('saving corrections shows an alert', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    await page.locator('#editor article').first().locator('textarea').fill('Saved text');
    const dialogPromise = page.waitForEvent('dialog');
    page.locator('#savePatched').click();
    const d = await dialogPromise;
    expect(d.message()).toContain('Uloženo');
    await d.accept();
  });

  test('loading history shows an alert with count', async ({ page }) => {
    await page.goto('/');
    // Pre-populate localStorage
    await page.evaluate((key) => {
      localStorage.setItem(key, JSON.stringify({ '1': 'cached text' }));
    }, 'srt-fix-history-v1');
    const dialogPromise = page.waitForEvent('dialog');
    page.locator('#loadHistory').click();
    const d = await dialogPromise;
    expect(d.message()).toContain('1');
    await d.accept();
  });

  test('clearing history shows an alert and removes data', async ({ page }) => {
    await page.goto('/');
    await page.evaluate((key) => {
      localStorage.setItem(key, JSON.stringify({ '1': 'cached', '2': 'data' }));
    }, 'srt-fix-history-v1');
    const dialogPromise = page.waitForEvent('dialog');
    page.locator('#clearHistory').click();
    const d = await dialogPromise;
    expect(d.message()).toContain('smazána');
    await d.accept();
    const stored = await page.evaluate((key) => localStorage.getItem(key), 'srt-fix-history-v1');
    expect(stored).toBeNull();
  });

  test('editing a subtitle stores it in localStorage automatically', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    await page.locator('#editor article').first().locator('textarea').fill('Auto saved');
    const stored = await page.evaluate((key) => {
      return JSON.parse(localStorage.getItem(key) || '{}');
    }, 'srt-fix-history-v1');
    expect(stored['1']).toBe('Auto saved');
  });
});

// ---------------------------------------------------------------------------
// Apply corrections
// ---------------------------------------------------------------------------
test.describe('Apply corrections', () => {
  test('apply corrections updates subtitle text from history and shows alert', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    // Pre-populate history with a change for entry id "1"
    await page.evaluate((key) => {
      localStorage.setItem(key, JSON.stringify({ '1': 'From history' }));
    }, 'srt-fix-history-v1');

    const dialogPromise = page.waitForEvent('dialog');
    page.locator('#applyCorrections').click();
    const d = await dialogPromise;
    // Should report 1 applied change
    expect(d.message()).toContain('1');
    await d.accept();

    await expect(page.locator('#editor article').first().locator('textarea')).toHaveValue('From history');
  });

  test('apply corrections marks updated subtitle as modified', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    await page.evaluate((key) => {
      localStorage.setItem(key, JSON.stringify({ '3': 'Opraveno' }));
    }, 'srt-fix-history-v1');

    const dialogPromise = page.waitForEvent('dialog');
    page.locator('#applyCorrections').click();
    await (await dialogPromise).accept();

    // Entry #3 (index 2) should be marked modified
    await expect(page.locator('#editor article').nth(2)).toHaveClass(/modified/);
  });

  test('apply corrections with empty history reports 0 changes', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    await page.evaluate((key) => localStorage.removeItem(key), 'srt-fix-history-v1');

    const dialogPromise = page.waitForEvent('dialog');
    page.locator('#applyCorrections').click();
    const d = await dialogPromise;
    expect(d.message()).toContain('0');
    await d.accept();
  });

  test('apply corrections does not change subtitles already matching history', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    // Set history to the same value as the existing subtitle
    await page.evaluate((key) => {
      localStorage.setItem(key, JSON.stringify({ '13': 'Je to legenda.' }));
    }, 'srt-fix-history-v1');

    const dialogPromise = page.waitForEvent('dialog');
    page.locator('#applyCorrections').click();
    const d = await dialogPromise;
    expect(d.message()).toContain('0');
    await d.accept();
  });
});

// ---------------------------------------------------------------------------
// Export SRT
// ---------------------------------------------------------------------------
test.describe('Export SRT', () => {
  test('clicking export triggers a file download', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('#exportSRT').click(),
    ]);
    expect(download.suggestedFilename()).toBe('patched.srt');
  });

  test('exported file contains all subtitle entries', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('#exportSRT').click(),
    ]);
    const filePath = await download.path();
    const content = fs.readFileSync(filePath, 'utf-8');
    // Check a few representative lines
    expect(content).toContain('SUPERSTAR');
    expect(content).toContain('00:00:05,897 --> 00:00:08,748');
    expect(content).toContain('A jsme tady i včas.');
    expect(content).toContain('00:06:24,490 --> 00:06:26,038');
  });

  test('exported file reflects edited subtitles', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    await page.locator('#editor article').first().locator('textarea').fill('SUPERSTAR EDITED');
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('#exportSRT').click(),
    ]);
    const filePath = await download.path();
    const content = fs.readFileSync(filePath, 'utf-8');
    expect(content).toContain('SUPERSTAR EDITED');
    expect(content).not.toContain('SUPERSTAR\n');
  });

  test('exported file preserves timecodes', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('#exportSRT').click(),
    ]);
    const filePath = await download.path();
    const content = fs.readFileSync(filePath, 'utf-8');
    expect(content).toContain('00:01:27,618 --> 00:01:29,909');
    expect(content).toContain('00:06:22,035 --> 00:06:23,843');
  });

  test('exported file preserves multi-line subtitle text', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('#exportSRT').click(),
    ]);
    const filePath = await download.path();
    const content = fs.readFileSync(filePath, 'utf-8');
    expect(content).toContain('První, čeho si na');
    expect(content).toContain('téhle dámě všimnete,');
  });
});

// ---------------------------------------------------------------------------
// SRT formatting – round-trip test
// ---------------------------------------------------------------------------
test.describe('SRT round-trip (format after parse)', () => {
  test('exported content contains all 95 block separators', async ({ page }) => {
    await page.goto('/');
    await uploadSrt(page);
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('#exportSRT').click(),
    ]);
    const filePath = await download.path();
    const content = fs.readFileSync(filePath, 'utf-8');
    // Count timecode lines as a proxy for block count
    const timecodePattern = /\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}/g;
    const matches = content.match(timecodePattern);
    expect(matches).not.toBeNull();
    expect(matches.length).toBe(95);
  });
});
