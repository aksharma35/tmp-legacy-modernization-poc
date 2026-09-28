// @ts-check
const { test, expect } = require('@playwright/test');
const { resetAndOpen, formRegion, expenseRows, tableRows, stat } = require('./helpers');

test.describe('ExpenseForm @ExpenseForm', () => {
  test.beforeEach(async ({ page, request }) => {
    await resetAndOpen(page, request);
  });

  test('keeps "Add expense" disabled until the form is valid', async ({ page }) => {
    const form = formRegion(page);
    const add = form.getByRole('button', { name: 'Add expense' });
    await expect(add).toBeDisabled();

    await form.getByLabel('Title').fill('Taxi home');
    await expect(add).toBeDisabled();

    await form.getByLabel('Amount (₹)').fill('350');
    await expect(add).toBeEnabled();
  });

  test('shows validation messages after the user leaves a field', async ({ page }) => {
    const form = formRegion(page);

    await form.getByLabel('Title').focus();
    await form.getByLabel('Title').blur();
    await expect(form.getByText('Title is required')).toBeVisible();

    await form.getByLabel('Amount (₹)').fill('0');
    await form.getByLabel('Amount (₹)').blur();
    await expect(form.getByText('Amount must be at least ₹1')).toBeVisible();
    await expect(form.getByRole('button', { name: 'Add expense' })).toBeDisabled();
  });

  test('adds an expense, resets the form and refreshes list and summary', async ({ page }) => {
    const form = formRegion(page);
    await form.getByLabel('Title').fill('Taxi home');
    await form.getByLabel('Amount (₹)').fill('350');
    await form.getByLabel('Category').selectOption('Travel');
    await form.getByLabel('Date').fill('2026-09-27');
    await form.getByRole('button', { name: 'Add expense' }).click();

    await expect(expenseRows(page)).toHaveCount(12);
    expect((await tableRows(page))[0]).toEqual(['27 Sep 2026', 'Taxi home', 'Travel', '₹350.00']);

    await expect(form.getByLabel('Title')).toHaveValue('');
    await expect(form.getByLabel('Amount (₹)')).toHaveValue('');
    await expect(form.getByLabel('Category')).toHaveValue(/Food/);
    await expect(form.getByText('Title is required')).toBeHidden();

    await expect(stat(page, 'Total spent')).toHaveText('₹8,350.00');
    await expect(stat(page, 'Expenses')).toHaveText('12');
  });
});
