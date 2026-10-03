// Strangler-fig bridge: lets the legacy AngularJS page mount migrated React
// components one at a time, so the app keeps shipping during the migration.
// Built with `npm run build:bridge` into dist-bridge/react-bridge.js.
import { createRoot } from 'react-dom/client';
import ExpenseForm from './components/ExpenseForm.jsx';
import ExpenseList from './components/ExpenseList.jsx';
import SummaryPanel from './components/SummaryPanel.jsx';

const registry = { ExpenseForm, ExpenseList, SummaryPanel };

window.ReactBridge = {
  mount(element, name, props) {
    const Component = registry[name];
    if (!Component) throw new Error(`ReactBridge: unknown component "${name}"`);
    const root = createRoot(element);
    root.render(<Component {...props} />);
    return {
      update(nextProps) { root.render(<Component {...nextProps} />); },
      unmount() { root.unmount(); },
    };
  },
};
