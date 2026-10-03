import { useState } from 'react';
import { addExpense } from '../api.js';

// Migrated from the AngularJS directive `expenseForm`.
// ng-model -> controlled inputs; $touched/$error -> `touched` + derived errors;
// $rootScope.$broadcast('expenses:changed') -> props.onChanged().

const CATEGORIES = ['Food', 'Travel', 'Bills', 'Shopping'];

function today() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function blank() {
  return { title: '', amount: '', category: 'Food', date: today() };
}

export default function ExpenseForm({ onChanged = () => {} }) {
  const [draft, setDraft] = useState(blank);
  const [touched, setTouched] = useState({ title: false, amount: false });
  const [saving, setSaving] = useState(false);
  const [serverError, setServerError] = useState(null);

  // Same rules as the AngularJS validators (ng-trim, required, min="1", step="1").
  const title = draft.title.trim();
  const amount = draft.amount === '' ? null : Number(draft.amount);
  const errors = {
    titleRequired: title === '',
    amountRequired: amount === null,
    amountMin: amount !== null && amount < 1,
    amountStep: amount !== null && !Number.isInteger(amount),
    dateRequired: draft.date === '',
  };
  const invalid = Object.values(errors).some(Boolean);

  const set = (field) => (event) => setDraft((d) => ({ ...d, [field]: event.target.value }));
  const touch = (field) => () => setTouched((t) => ({ ...t, [field]: true }));

  async function submit(event) {
    event.preventDefault();
    if (invalid) return;
    setSaving(true);
    setServerError(null);
    try {
      await addExpense({ title, amount, category: draft.category, date: draft.date });
      setDraft(blank());
      setTouched({ title: false, amount: false });
      onChanged();
    } catch (error) {
      setServerError((error.data && error.data.error) || 'Could not save expense');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card" aria-label="Add expense">
      <h2>Add expense</h2>
      <form name="form" noValidate onSubmit={submit}>
        <div className="field">
          <label htmlFor="title">Title</label>
          <input id="title" name="title" type="text" value={draft.title} onChange={set('title')} onBlur={touch('title')} required maxLength={60} />
          {touched.title && errors.titleRequired && <p className="error">Title is required</p>}
        </div>

        <div className="field-row">
          <div className="field">
            <label htmlFor="amount">Amount (₹)</label>
            <input id="amount" name="amount" type="number" value={draft.amount} onChange={set('amount')} onBlur={touch('amount')} required min="1" step="1" />
            {touched.amount && errors.amountRequired && <p className="error">Amount is required</p>}
            {touched.amount && errors.amountMin && <p className="error">Amount must be at least ₹1</p>}
          </div>

          <div className="field">
            <label htmlFor="category">Category</label>
            <select id="category" name="category" value={draft.category} onChange={set('category')}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="date">Date</label>
            <input id="date" name="date" type="date" value={draft.date} onChange={set('date')} required />
          </div>
        </div>

        {serverError && <p className="error" role="alert">{serverError}</p>}
        <button type="submit" className="primary" disabled={invalid || saving}>Add expense</button>
      </form>
    </section>
  );
}
