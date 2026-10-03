// Replaces the AngularJS ExpenseService ($http): same URLs, same payloads.

async function request(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    // Like a rejected $http promise: the caller can read error.data.error.
    const error = new Error((data && data.error) || `HTTP ${res.status}`);
    error.status = res.status;
    error.data = data;
    throw error;
  }
  return data;
}

export const listExpenses = () => request('GET', '/api/expenses');
export const addExpense = (expense) => request('POST', '/api/expenses', expense);
export const deleteExpense = (id) => request('DELETE', `/api/expenses/${id}`);
export const getSummary = () => request('GET', '/api/summary');
