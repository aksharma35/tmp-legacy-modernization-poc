# Migration conventions

Aider reads this file on every run. Humans should read it too: it is the
contract the AI works under.

## Ground rules (both migrations)

1. **Behaviour must not change.** The parity tests recorded from the legacy app
   are the specification. Do not "improve" behaviour, fix bugs, change text,
   rename fields or reorder things unless a test requires it.
2. **Never decide a behaviour change yourself.** If you notice that the new
   runtime or library behaves differently from the legacy one (for example
   Python 3 division, rounding, sorting, date parsing), do not silently
   reproduce or change it. Leave the code as the codemod produced it and add a
   comment starting with `MODERNIZE-REVIEW:` that explains the difference. The
   pipeline's verify step shows the difference to a human, who decides.
3. **Only fix what the task asks.** Keep edits small and focused on the files
   you were given. Do not reformat untouched code.
4. **Keep test hooks.** `POST /api/test/reset` (enabled by `TEST_HOOKS=1`) must
   keep working. The parity suites depend on it.

## Backend: Python 2.7 → Python 3.12

- 2to3 and ruff have already rewritten the syntax. Your job is what they could
  not do: code that still crashes or cannot run on Python 3.12.
- Replace `cmp`-style sorting with `key=` functions that produce the same order.
- Log lines must print text, not `b'...'` bytes.
- Keep the same routes, status codes, JSON field names and error messages.
- Keep Flask. Target Flask 3.1.

## Frontend: AngularJS 1.8 → React 19

The React app lives in `modern/frontend` (Vite, plain JavaScript + JSX, no
TypeScript, no extra libraries). `src/App.jsx` is already wired: it owns a
`version` counter and an `onChanged` callback that replace
`$rootScope.$broadcast('expenses:changed')`. Do not change `App.jsx`.

| AngularJS | React |
|---|---|
| `$scope.x = ...` | `const [x, setX] = useState(...)` |
| `$scope.$watch('x', fn)` | a value derived during render (preferred) or `useEffect` |
| `$rootScope.$broadcast('expenses:changed')` | call the `onChanged` prop |
| `$scope.$on('expenses:changed', load)` | reload in `useEffect` when the `version` prop changes |
| `ExpenseService` (`$http`) | functions in `src/api.js` using `fetch`, same URLs and payloads |
| `ng-model` | controlled input: `value` + `onChange` |
| `ng-repeat="x in list track by x.id"` | `list.map(x => <tr key={x.id}>…)` |
| `ng-show` / `ng-if` | conditional rendering |
| `ng-submit` / `ng-click` | `onSubmit` (with `preventDefault`) / `onClick` |
| AngularJS filters (`currency`, `date`, `filter`, `orderBy`, `lowercase`) | pure functions in `src/lib/filters.js`, reused by every component |
| `$window.confirm(msg)` | `window.confirm(msg)` with the exact same text |

Rules for components:

- **Same markup contract.** Keep the same visible text, headings, labels,
  `aria-label`s, roles, table structure and CSS class names. The shared
  stylesheet (`src/styles.css`) is a copy of the legacy one. The parity tests
  find elements by label, role and text, exactly like a user would.
- **Same formatting.** Copy AngularJS filter behaviour exactly:
  - `currency:'₹'` → `₹` + en-US grouping + exactly two decimals, e.g. `₹1,400.00`.
  - `date:'dd MMM yyyy'` on a `YYYY-MM-DD` string → parse it as a LOCAL date,
    e.g. `02 Sep 2026`. Never `new Date('YYYY-MM-DD')`, which is UTC.
  - `filter:query` with a string → case-insensitive substring match against
    every property value of the object (numbers included).
  - `orderBy:'-field'` → descending, stable for ties.
- **Same validation UX.** Error messages appear only after a field is touched
  (blurred); the submit button stays disabled while the form is invalid; the
  form resets and clears touched state after a successful save.
- One component per file in `src/components/`, default export, function
  components and hooks only.
