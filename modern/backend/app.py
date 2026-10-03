"""
Expense Tracker API -- legacy service (Python 2.7, Flask 1.x).

Serves the AngularJS frontend from ../frontend and a small JSON API under /api.
Data lives in memory and is seeded from data/expenses.json on startup.
"""
import json
import math
import os
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory
from functools import cmp_to_key

HERE = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(HERE, '..', 'frontend')
SEED_FILE = os.path.join(HERE, 'data', 'expenses.json')

CATEGORIES = ['Food', 'Travel', 'Bills', 'Shopping']

app = Flask(__name__, static_folder=None)

_expenses = []


def load_seed():
    with open(SEED_FILE) as f:
        return json.load(f)


def reset_store():
    global _expenses
    _expenses = load_seed()
    print("[expenses] store reset, %d expenses loaded" % len(_expenses))


def next_id():
    if not _expenses:
        return 1
    return max(e['id'] for e in _expenses) + 1


def validate_expense(payload):
    """Return (clean_expense, error_message)."""
    if not isinstance(payload, dict):
        return None, 'request body must be a JSON object'

    title = payload.get('title')
    if not isinstance(title, str) or not title.strip():
        return None, 'title is required'

    amount = payload.get('amount')
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
        return None, 'amount must be a positive whole number'

    category = payload.get('category')
    if category not in CATEGORIES:
        return None, 'category must be one of: %s' % ', '.join(CATEGORIES)

    date = payload.get('date')
    try:
        datetime.strptime(date or '', '%Y-%m-%d')
    except ValueError as e:
        return None, 'date must be YYYY-MM-DD'

    return {
        'title': title.strip(),
        'amount': amount,
        'category': category,
        'date': date,
    }, None


def py2_round(value):
    """round() as Python 2 did it: halves away from zero, result is a float."""
    return float(math.floor(value + 0.5)) if value >= 0 else float(math.ceil(value - 0.5))


def by_total_desc(a, b):
    # Python 3 has no cmp(); this returns the same -1 / 0 / 1.
    return (b['total'] > a['total']) - (b['total'] < a['total'])


def build_summary(expenses):
    totals = {}
    counts = {}
    for e in expenses:
        cat = e['category']
        if cat not in totals:
            totals[cat] = 0
            counts[cat] = 0
        totals[cat] += e['amount']
        counts[cat] += 1

    grand_total = sum(totals.values())
    count = len(expenses)

    rows = []
    for cat, total in totals.items():
        rows.append({
            'category': cat,
            'total': total,
            'count': counts[cat],
            # average spend per expense in this category
            # Kept legacy Python 2 behaviour on purpose: integer division (see migration/decisions.yaml).
            'average': total // counts[cat],
            # share of all spending, as a whole percentage
            # Kept legacy Python 2 behaviour on purpose: round half away from zero (see migration/decisions.yaml).
            'share_percent': py2_round(total * 100.0 / grand_total) if grand_total else 0,
        })

    return {
        'total': grand_total,
        'count': count,
        # Kept legacy Python 2 behaviour on purpose: integer division (see migration/decisions.yaml).
        'average': grand_total // count if count else 0,
        'by_category': sorted(rows, key=cmp_to_key(by_total_desc)),
    }


# ---------------------------------------------------------------- API routes

@app.route('/api/expenses', methods=['GET'])
def list_expenses():
    return jsonify(_expenses)


@app.route('/api/expenses', methods=['POST'])
def add_expense():
    payload = request.get_json(silent=True)
    clean, error = validate_expense(payload)
    if error:
        return jsonify({'error': error}), 400
    clean['id'] = next_id()
    _expenses.append(clean)
    print("[expenses] added #%d %s" % (clean['id'], clean['title']))
    return jsonify(clean), 201


@app.route('/api/expenses/<int:expense_id>', methods=['DELETE'])
def delete_expense(expense_id):
    for i in range(len(_expenses)):
        if _expenses[i]['id'] == expense_id:
            del _expenses[i]
            return '', 204
    return jsonify({'error': 'expense %d not found' % expense_id}), 404


@app.route('/api/summary', methods=['GET'])
def summary():
    return jsonify(build_summary(_expenses))


@app.route('/api/test/reset', methods=['POST'])
def test_reset():
    # Test hook used by the parity suites to get a known starting state.
    if os.environ.get('TEST_HOOKS') != '1':
        return jsonify({'error': 'test hooks disabled'}), 404
    reset_store()
    return '', 204


# ----------------------------------------------------------- static frontend

@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(FRONTEND_DIR, filename)


if __name__ == '__main__':
    reset_store()
    port = int(os.environ.get('PORT', '5001'))
    print("[expenses] legacy API listening on http://0.0.0.0:%d" % port)
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
