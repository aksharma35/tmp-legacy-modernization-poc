// @ts-check
const { test, expect } = require('@playwright/test');
const { resetAndOpen, summaryRegion, stat } = require('./helpers');

test.describe('SummaryPanel @SummaryPanel', () => {
  test.beforeEach(async ({ page, request }) => {
    await resetAndOpen(page, request);
  });

  test('shows total, count and average expense', async ({ page }) => {
    await expect(stat(page, 'Total spent')).toHaveText('₹8,000.00');
    await expect(stat(page, 'Expenses')).toHaveText('11');
    await expect(stat(page, 'Average expense')).toHaveText('₹727.00');
  });

  test('breaks spending down by category, largest first', async ({ page }) => {
    const table = summaryRegion(page).getByRole('table', { name: 'Spending by category' });
    const rows = table.locator('tbody tr');
    await expect(rows).toHaveCount(4);

    const expected = [
      ['Travel', '₹2,500.00', '₹833.00', '31%'],
      ['Bills', '₹2,499.00', '₹1,249.00', '31%'],
      ['Shopping', '₹2,001.00', '₹1,000.00', '25%'],
      ['Food', '₹1,000.00', '₹250.00', '13%'],
    ];
    for (let i = 0; i < expected.length; i++) {
      await expect(rows.nth(i).locator('td')).toHaveText(expected[i]);
    }
  });
});
