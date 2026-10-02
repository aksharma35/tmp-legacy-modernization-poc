// @ts-check
// Cross-unit behaviour: one unit changes data and the others refresh. In the
// legacy app this is $rootScope.$broadcast('expenses:changed'); in React it is
// the onChanged/version props; on the hybrid page it crosses the bridge.
const { test, expect } = require('@playwright/test');
const { resetAndOpen, formRegion, expenseRows, tableRows, stat } = require('./helpers');

test.describe('Whole page @integration', () => {
  test.beforeEach(async ({ page, request }) => {
    await resetAndOpen(page, request);
    await expect(expenseRows(page)).toHaveCount(11);
    await expect(stat(page, 'Total spent')).toHaveText('₹8,000.00');
  });

  test('adding an expense refreshes the list and the summary', { tag: '@B15' }, async ({ page }) => {
    const form = formRegion(page);
    await form.getByLabel('Title').fill('Taxi home');
    await form.getByLabel('Amount (₹)').fill('350');
    await form.getByLabel('Category').selectOption('Travel');
    await form.getByLabel('Date').fill('2026-09-27');
    await form.getByRole('button', { name: 'Add expense' }).click();

    await expect(expenseRows(page)).toHaveCount(12);
    expect((await tableRows(page))[0]).toEqual(['27 Sep 2026', 'Taxi home', 'Travel', '₹350.00']);
    await expect(stat(page, 'Total spent')).toHaveText('₹8,350.00');
    await expect(stat(page, 'Expenses')).toHaveText('12');
  });

  test('deleting an expense refreshes the summary', { tag: '@B15' }, async ({ page }) => {
    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: 'Delete Team lunch' }).click();
    await expect(expenseRows(page)).toHaveCount(10);
    await expect(stat(page, 'Total spent')).toHaveText('₹7,700.00');
    await expect(stat(page, 'Expenses')).toHaveText('10');
  });
});
