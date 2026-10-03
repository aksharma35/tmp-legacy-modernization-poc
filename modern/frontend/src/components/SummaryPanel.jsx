import { useEffect, useState } from 'react';
import { getSummary } from '../api.js';
import { currency } from '../lib/filters.js';

// Migrated from the AngularJS component `summaryPanel`.
// $scope.$on('expenses:changed', load)  ->  reload whenever `version` changes.
export default function SummaryPanel({ version = 0 }) {
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getSummary().then((data) => {
      if (!cancelled) setSummary(data);
    });
    return () => {
      cancelled = true;
    };
  }, [version]);

  return (
    <section className="card" aria-label="Summary">
      <h2>Summary</h2>
      {!summary && <p className="muted">Loading…</p>}

      {summary && (
        <div>
          <dl className="stats">
            <div className="stat">
              <dt>Total spent</dt>
              <dd>{currency(summary.total)}</dd>
            </div>
            <div className="stat">
              <dt>Expenses</dt>
              <dd>{summary.count}</dd>
            </div>
            <div className="stat">
              <dt>Average expense</dt>
              <dd>{currency(summary.average)}</dd>
            </div>
          </dl>

          <table>
            <caption>Spending by category</caption>
            <thead>
              <tr>
                <th scope="col">Category</th>
                <th scope="col" className="num">Total</th>
                <th scope="col" className="num">Average</th>
                <th scope="col" className="num">Share</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_category.map((row) => (
                <tr key={row.category}>
                  <td>{row.category}</td>
                  <td className="num">{currency(row.total)}</td>
                  <td className="num">{currency(row.average)}</td>
                  <td className="num">{row.share_percent}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
