import { useCallback, useState } from 'react';
import ExpenseForm from './components/ExpenseForm.jsx';
import ExpenseList from './components/ExpenseList.jsx';
import SummaryPanel from './components/SummaryPanel.jsx';

// Page layout, same markup as legacy/frontend/index.html.
// `version` + `onChanged` replace $rootScope.$broadcast('expenses:changed'):
// any component that changes data calls onChanged, and every panel that shows
// data reloads when `version` changes.
export default function App() {
  const [version, setVersion] = useState(0);
  const onChanged = useCallback(() => setVersion((v) => v + 1), []);

  return (
    <>
      <header className="app-header">
        <h1>Expense Tracker</h1>
        <p className="subtitle">
          Team spending &middot; September 2026 <span className="badge">React 19</span>
        </p>
      </header>

      <main className="layout">
        <div className="column">
          <ExpenseForm onChanged={onChanged} />
          <ExpenseList version={version} onChanged={onChanged} />
        </div>
        <div className="column narrow">
          <SummaryPanel version={version} />
        </div>
      </main>
    </>
  );
}
