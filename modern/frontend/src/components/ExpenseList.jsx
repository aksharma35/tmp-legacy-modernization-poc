import { useEffect, useState } from 'react';
import { deleteExpense, listExpenses } from '../api.js';
import { currency, filterByQuery, formatDate, lowercase, orderBy } from '../lib/filters.js';

// Migrated from the AngularJS controller `ExpenseListCtrl` (ng-controller block in index.html).
// $scope state -> useState; $scope.$watch('query') -> derived `searching`;
// $scope.$on('expenses:changed', load) -> reload when `version` changes.

const SORT_OPTIONS = [
  { value: '-date', label: 'Newest first' },
  { value: 'date', label: 'Oldest first' },
  { value: '-amount', label: 'Highest amount' },
  { value: 'amount', label: 'Lowest amount' },
];

export default function ExpenseList({ version = 0, onChanged = () => {} }) {
  const [expenses, setExpenses] = useState([]);
  const [query, setQuery] = useState('');
  const [sortField, setSortField] = useState('-date');

  useEffect(() => {
    let cancelled = false;
    listExpenses().then((data) => {
      if (!cancelled) setExpenses(data);
    });
    return () => {
      cancelled = true;
    };
  }, [version]);

  const filtered = orderBy(filterByQuery(expenses, query), sortField);
  const searching = !!query;

  async function remove(expense) {
    if (!window.confirm(`Delete "${expense.title}"?`)) return;
    await deleteExpense(expense.id);
    onChanged();
  }

  return (
    <section className="card" aria-label="Expenses">
      <div className="card-header">
        <h2>Expenses</h2>
        <p className="muted" role="status">Showing {filtered.length} of {expenses.length}</p>
      </div>

      <div className="toolbar">
        <label htmlFor="search">Search</label>
        <input id="search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Title, category, amount" />
        {searching && (
          <button type="button" className="link" onClick={() => setQuery('')}>Clear</button>
        )}
        <label htmlFor="sort">Sort by</label>
        <select id="sort" value={sortField} onChange={(e) => setSortField(e.target.value)}>
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      <table>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Title</th>
            <th scope="col">Category</th>
            <th scope="col" className="num">Amount</th>
            <th scope="col"><span className="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((e) => (
            <tr key={e.id}>
              <td>{formatDate(e.date)}</td>
              <td>{e.title}</td>
              <td><span className={`tag tag-${lowercase(e.category)}`}>{e.category}</span></td>
              <td className="num">{currency(e.amount)}</td>
              <td className="num">
                <button type="button" className="link danger" aria-label={`Delete ${e.title}`} onClick={() => remove(e)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {filtered.length === 0 && <p className="empty">No expenses match "{query}".</p>}
    </section>
  );
}
