// Replaces the AngularJS ExpenseService ($http). Not migrated yet.
const notMigrated = () => Promise.reject(new Error('ExpenseService has not been migrated yet'));

export const listExpenses = notMigrated;
export const addExpense = notMigrated;
export const deleteExpense = notMigrated;
export const getSummary = notMigrated;
