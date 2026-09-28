"""Tiny static file server that forwards /api/* to a backend. Serves the hybrid page.

    python -m modernize.static_proxy --root out/hybrid --api http://localhost:5002 --port 8081
"""
from __future__ import annotations

import argparse
import functools
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class Handler(SimpleHTTPRequestHandler):
    api = "http://localhost:5002"

    def log_message(self, fmt, *args):  # quieter logs
        pass

    def _proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(self.api.rstrip("/") + self.path, data=body, method=self.command)
        for h in ("Content-Type", "Accept"):
            if self.headers.get(h):
                req.add_header(h, self.headers[h])
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                status, headers, payload = res.status, res.headers, res.read()
        except urllib.error.HTTPError as err:
            status, headers, payload = err.code, err.headers, err.read()
        self.send_response(status)
        for h in ("Content-Type",):
            if headers.get(h):
                self.send_header(h, headers[h])
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        return super().do_GET()

    def do_POST(self):
        return self._proxy()

    def do_DELETE(self):
        return self._proxy()

    def do_PUT(self):
        return self._proxy()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--api", required=True)
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args()
    Handler.api = args.api
    handler = functools.partial(Handler, directory=args.root)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Hybrid page on http://localhost:{args.port} (API → {args.api})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
