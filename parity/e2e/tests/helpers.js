// Shared helpers. Everything is located by what a user sees: region labels,
// form labels, table rows and text. No framework-specific selectors.
const { expect } = require('@playwright/test');

async function resetAndOpen(page, request) {
  const res = await request.post('/api/test/reset');
  expect(res.status(), 'test reset hook').toBe(204);
  await page.goto('/');
  await expect(expenseRows(page)).toHaveCount(11);
}

function expensesRegion(page) {
  return page.getByRole('region', { name: 'Expenses' });
}

function formRegion(page) {
  return page.getByRole('region', { name: 'Add expense' });
}

function summaryRegion(page) {
  return page.getByRole('region', { name: 'Summary' });
}

function expenseRows(page) {
  return expensesRegion(page).locator('tbody tr');
}

function rowByTitle(page, title) {
  return expenseRows(page).filter({ has: page.locator('td:nth-child(2)', { hasText: new RegExp(`^${title}$`) }) });
}

/** Cell texts of the expense table, as [date, title, category, amount]. */
async function tableRows(page) {
  const rows = await expenseRows(page).all();
  const out = [];
  for (const row of rows) {
    const cells = row.locator('td');
    out.push([
      (await cells.nth(0).innerText()).trim(),
      (await cells.nth(1).innerText()).trim(),
      (await cells.nth(2).innerText()).trim(),
      (await cells.nth(3).innerText()).trim(),
    ]);
  }
  return out;
}

/** The value (<dd>) that follows a summary label (<dt>). */
function stat(page, label) {
  return summaryRegion(page)
    .getByRole('term')
    .filter({ hasText: new RegExp(`^${label}$`) })
    .locator('xpath=following-sibling::dd[1]');
}

module.exports = { resetAndOpen, expensesRegion, formRegion, summaryRegion, expenseRows, rowByTitle, tableRows, stat };
