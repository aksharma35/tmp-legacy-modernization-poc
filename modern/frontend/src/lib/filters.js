// Replacements for the AngularJS filters used by the legacy templates.
// Each one reproduces the AngularJS 1.8 output exactly, because the parity
// tests compare what the user sees.

const SHORT_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// {{ value | currency:'₹' }}  ->  "₹1,400.00" (en-US grouping, always two decimals)
export function currency(value, symbol = '₹') {
  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) return '';
  const n = Number(value);
  const digits = Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return (n < 0 ? '-' : '') + symbol + digits;
}

// {{ '2026-09-02' | date:'dd MMM yyyy' }}  ->  "02 Sep 2026"
// AngularJS reads a YYYY-MM-DD string as a LOCAL date. new Date('2026-09-02')
// would be UTC midnight and show the previous day west of UTC, so parse by hand.
export function formatDate(isoDate) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate || '');
  if (!m) return isoDate || '';
  return `${m[3]} ${SHORT_MONTHS[Number(m[2]) - 1]} ${m[1]}`;
}

// {{ value | lowercase }}
export function lowercase(value) {
  return value === null || value === undefined ? '' : String(value).toLowerCase();
}

// ng-repeat="e in list | filter:query"
// A string query matches, case-insensitively, any property value (numbers too).
export function filterByQuery(items, query) {
  if (query === null || query === undefined || query === '') return items;
  const needle = String(query).toLowerCase();
  return items.filter((item) =>
    Object.entries(item).some(([key, value]) =>
      !key.startsWith('$') && value !== null && typeof value !== 'object' && String(value).toLowerCase().includes(needle),
    ),
  );
}

// ng-repeat="e in list | orderBy:'-field'"
// '-' means descending. Strings compare case-insensitively. Ties keep their
// original order (AngularJS orderBy is stable).
export function orderBy(items, expression) {
  const descending = expression.startsWith('-');
  const field = expression.replace(/^[-+]/, '');
  const key = (v) => (typeof v === 'string' ? v.toLowerCase() : v);
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => {
      const av = key(a.item[field]);
      const bv = key(b.item[field]);
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return (descending ? -cmp : cmp) || a.index - b.index;
    })
    .map(({ item }) => item);
}
