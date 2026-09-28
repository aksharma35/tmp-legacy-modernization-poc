// @ts-check
const { test, expect } = require('@playwright/test');
const { resetAndOpen, expensesRegion, expenseRows, rowByTitle, tableRows } = require('./helpers');

test.describe('ExpenseList @ExpenseList', () => {
  test.beforeEach(async ({ page, request }) => {
    await resetAndOpen(page, request);
    await expect(expenseRows(page)).toHaveCount(11);
  });

  test('lists every expense, newest first, with formatted dates and rupee amounts', async ({ page }) => {
    await expect(expensesRegion(page).getByRole('status')).toHaveText('Showing 11 of 11');
    const rows = await tableRows(page);
    expect(rows[0]).toEqual(['24 Sep 2026', 'Phone case', 'Shopping', '₹601.00']);
    expect(rows[10]).toEqual(['01 Sep 2026', 'Electricity bill', 'Bills', '₹1,500.00']);
    await expect(rowByTitle(page, 'Running shoes').locator('td').nth(3)).toHaveText('₹1,400.00');
  });

  test('search ignores case and matches every field, not just the title', async ({ page }) => {
    const search = page.getByLabel('Search');

    await search.fill('TRAVEL');
    await expect(expenseRows(page)).toHaveCount(3);
    expect((await tableRows(page)).map((r) => r[1]).sort()).toEqual(['Cab to airport', 'Metro card top-up', 'Train tickets']);
    await expect(expensesRegion(page).getByRole('status')).toHaveText('Showing 3 of 11');

    await search.fill('999');
    await expect(expenseRows(page)).toHaveCount(1);
    await expect(expenseRows(page).first()).toContainText('Mobile recharge');

    await search.fill('coffee');
    await expect(expenseRows(page)).toHaveCount(1);
    await expect(expenseRows(page).first()).toContainText('Coffee beans');
  });

  test('shows an empty message and a Clear button that resets the search', async ({ page }) => {
    const clear = expensesRegion(page).getByRole('button', { name: 'Clear' });
    await expect(clear).toBeHidden();

    await page.getByLabel('Search').fill('zzz');
    await expect(expenseRows(page)).toHaveCount(0);
    await expect(expensesRegion(page)).toContainText('No expenses match "zzz".');
    await expect(clear).toBeVisible();

    await clear.click();
    await expect(expenseRows(page)).toHaveCount(11);
    await expect(page.getByLabel('Search')).toHaveValue('');
    await expect(clear).toBeHidden();
  });

  test('sorts by the chosen option', async ({ page }) => {
    const sort = page.getByLabel('Sort by');

    await sort.selectOption({ label: 'Highest amount' });
    expect((await tableRows(page))[0][1]).toBe('Electricity bill');

    await sort.selectOption({ label: 'Lowest amount' });
    expect((await tableRows(page))[0][1]).toBe('Street food');

    await sort.selectOption({ label: 'Oldest first' });
    expect((await tableRows(page))[0][1]).toBe('Electricity bill');

    await sort.selectOption({ label: 'Newest first' });
    expect((await tableRows(page))[0][1]).toBe('Phone case');
  });

  test('asks before deleting, and keeps the row when the user cancels', async ({ page }) => {
    page.once('dialog', async (dialog) => {
      expect(dialog.type()).toBe('confirm');
      expect(dialog.message()).toBe('Delete "Team lunch"?');
      await dialog.dismiss();
    });
    await page.getByRole('button', { name: 'Delete Team lunch' }).click();
    await expect(expenseRows(page)).toHaveCount(11);
  });

  test('deletes a row after confirmation', async ({ page, request }) => {
    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: 'Delete Team lunch' }).click();
    await expect(expenseRows(page)).toHaveCount(10);
    await expect(rowByTitle(page, 'Team lunch')).toHaveCount(0);
    await expect(expensesRegion(page).getByRole('status')).toHaveText('Showing 10 of 10');
    const titles = (await (await request.get('/api/expenses')).json()).map((e) => e.title);
    expect(titles).not.toContain('Team lunch');
  });
});
