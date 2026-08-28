"""Local REST API for the Python Tweet Viewer client."""

from __future__ import annotations

import argparse
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

from .client import TweetViewerClient, TweetViewerError

MAX_BODY_BYTES = 16 * 1024


def create_server(
    host: str = "127.0.0.1",
    port: int = 3001,
    *,
    client: Optional[TweetViewerClient] = None,
    cors_origin: Optional[str] = "*",
) -> ThreadingHTTPServer:
    api_client = client or TweetViewerClient()

    class Handler(BaseHTTPRequestHandler):
        def _cors(self) -> None:
            if cors_origin is not None:
                self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Access-Control-Allow-Headers", "content-type, range")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def _json(self, status: int, data: Any) -> None:
            body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _error(self, error: Exception) -> None:
            if isinstance(error, TweetViewerError):
                code_status = {
                    "ABORTED": 504,
                    "NETWORK_ERROR": 502,
                    "INVALID_JSON": 502,
                    "INVALID_LIVE_JSON": 502,
                    "LIVE_API_ERROR": 502,
                    "UNEXPECTED_RESPONSE": 502,
                }
                status = error.status if error.status and error.status >= 400 else code_status.get(error.code, 400)
                self._json(status, {"ok": False, "code": error.code, "error": str(error)})
            elif isinstance(error, (json.JSONDecodeError, ValueError)):
                self._json(400, {"ok": False, "code": "INVALID_JSON", "error": str(error)})
            else:
                self.log_error("Unhandled error: %r", error)
                self._json(500, {"ok": False, "error": "Internal server error"})

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                if parsed.path == "/health":
                    self._json(200, {"ok": True})
                    return

                if parsed.path == "/v1/media/file":
                    self._stream_media(query.get("url", [""])[0])
                    return
                if parsed.path == "/v1/media/resolve":
                    target = query.get("url", query.get("id", [""]))[0]
                    result = api_client.resolve_media(target, language=query.get("lang", ["en"])[0])
                    self._json(200, result)
                    return

                match = re.fullmatch(r"/v1/profiles/([^/]+)/timeline", parsed.path)
                if match:
                    result = api_client.get_timeline(
                        unquote(match.group(1)), cursor=query.get("cursor", [None])[0]
                    )
                    self._json(200, result)
                    return
                match = re.fullmatch(r"/v1/profiles/([^/]+)/latest", parsed.path)
                if match:
                    tweet = api_client.get_latest_tweet(
                        unquote(match.group(1)),
                        include_replies=query.get("includeReplies", ["1"])[0] != "0",
                        include_retweets=query.get("includeRetweets", ["1"])[0] != "0",
                    )
                    self._json(200, {"ok": True, "source": "fxtwitter-v2-live", "tweet": tweet})
                    return
                match = re.fullmatch(r"/v1/profiles/([^/]+)", parsed.path)
                if match:
                    self._json(200, api_client.get_profile(unquote(match.group(1))))
                    return
                match = re.fullmatch(r"/v1/tweets/([^/]+)", parsed.path)
                if match:
                    self._json(200, api_client.get_tweet(unquote(match.group(1))))
                    return
                self._json(404, {"ok": False, "error": "Not found"})
            except Exception as error:  # Route boundary
                self._error(error)

        def do_POST(self) -> None:  # noqa: N802
            try:
                if urlparse(self.path).path != "/v1/view":
                    self._json(404, {"ok": False, "error": "Not found"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    raise ValueError("JSON body is required")
                if length > MAX_BODY_BYTES:
                    raise ValueError("Request body is too large")
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(body, dict):
                    raise ValueError("JSON body must be an object")
                self._json(200, api_client.view(body.get("q")))
            except Exception as error:  # Route boundary
                self._error(error)

        def _stream_media(self, media_url: str) -> None:
            upstream = api_client.fetch_media(media_url, byte_range=self.headers.get("Range"))
            try:
                status = getattr(upstream, "status", None) or upstream.getcode()
                self.send_response(status)
                self._cors()
                for name in (
                    "Accept-Ranges",
                    "Content-Disposition",
                    "Content-Length",
                    "Content-Range",
                    "Content-Type",
                    "Last-Modified",
                ):
                    value = upstream.headers.get(name)
                    if value:
                        self.send_header(name, value)
                self.end_headers()
                while True:
                    chunk = upstream.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            finally:
                upstream.close()

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Tweet Viewer Python REST wrapper")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "3001")))
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    server = create_server(args.host, args.port)
    print(f"Tweet Viewer Python wrapper: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
