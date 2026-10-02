# -*- coding: utf-8 -*-
"""Test harness: run a Flask app.py unchanged and record which of its lines run.

    python linetrace.py path/to/app.py

Runs on Python 2.7 and 3.x with no extra packages. It loads app.py as a module,
traces line events in that one file, and adds two test-only endpoints:

    GET    /api/test/lines   -> {"file": "app.py", "lines": [12, 13, ...]}
    DELETE /api/test/lines   -> forget what was recorded so far

`modernize lock` uses them to prove every risky line found by discover is
executed by at least one recorded API call. The app's own code is not touched.
"""
import json
import os
import sys
import threading

APP_PATH = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "app.py")
LINES = set()


def _tracer(frame, event, arg):
    if frame.f_code.co_filename != APP_PATH:
        return None
    if event == "line":
        LINES.add(frame.f_lineno)
    return _tracer


def _load(path):
    sys.path.insert(0, os.path.dirname(path))
    if sys.version_info[0] == 2:
        import imp
        return imp.load_source("legacy_app", path)
    import importlib.util
    spec = importlib.util.spec_from_file_location("legacy_app", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    os.chdir(os.path.dirname(APP_PATH))
    module = _load(APP_PATH)
    app = module.app
    from flask import request

    def lines():
        if request.method == "DELETE":
            LINES.clear()
            return "", 204
        body = json.dumps({"file": os.path.basename(APP_PATH), "lines": sorted(LINES)})
        return app.response_class(body, mimetype="application/json")

    if os.environ.get("TEST_HOOKS") == "1":
        app.add_url_rule("/api/test/lines", "test_lines", lines, methods=["GET", "DELETE"])

    # Same start-up as app.py's __main__ block.
    module.reset_store()
    sys.settrace(_tracer)
    threading.settrace(_tracer)
    port = int(os.environ.get("PORT", "5001"))
    print("[linetrace] tracing %s on port %d" % (os.path.basename(APP_PATH), port))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
