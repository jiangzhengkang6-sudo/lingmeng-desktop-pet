"""只向公网隧道暴露 RTC RTS 回调路径的本地反向代理。"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ALLOWED_PATH = "/api/identity/rtc/rts/messages"
MAX_BODY_BYTES = 1_000_000


class RtsProxyHandler(BaseHTTPRequestHandler):
    upstream_url = "http://127.0.0.1:8000"

    def _reject(self, status_code: int, message: bytes) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(message)))
        self.end_headers()
        self.wfile.write(message)

    def _forward(self) -> None:
        parsed_path = self.path.split("?", 1)[0]
        if parsed_path != ALLOWED_PATH or self.command not in {"GET", "POST"}:
            self._reject(404, b"not found")
            return
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length > MAX_BODY_BYTES:
            self._reject(413, b"payload too large")
            return
        body = self.rfile.read(content_length) if content_length else b""
        target = self.upstream_url.rstrip("/") + ALLOWED_PATH
        headers = {}
        content_type = self.headers.get("Content-Type")
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(target, data=body if self.command == "POST" else None, headers=headers, method=self.command)
        try:
            with urlopen(request, timeout=20) as response:
                payload = response.read(MAX_BODY_BYTES + 1)
                status = response.status
                response_headers = response.headers
        except HTTPError as exc:
            payload = exc.read(MAX_BODY_BYTES + 1)
            status = exc.code
            response_headers = exc.headers
        except URLError as exc:
            self._reject(502, b"bad gateway")
            return
        self.send_response(status)
        content_type_out = response_headers.get("Content-Type", "application/json")
        self.send_header("Content-Type", content_type_out)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        self._forward()

    def do_POST(self) -> None:
        self._forward()

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="仅代理火山 RTC RTS 回调路径的本地 HTTP 代理")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--upstream-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    RtsProxyHandler.upstream_url = args.upstream_url
    server = ThreadingHTTPServer((args.listen_host, args.port), RtsProxyHandler)
    print(f"RTS public proxy listening on http://{args.listen_host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
