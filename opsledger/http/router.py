"""HTTP transport adapter for OpsLedger: router over stdlib http.server.

This adapter is thin on purpose: exact-path routing, bounded request-body
reads, JSON content negotiation, and canonical error mapping. Business
transactions never live here.

Routing rules:

- Routes are registered per exact path with the allowed method set.
- A known path with a disallowed method returns 405 with an ``Allow`` header.
- An unknown path returns 404 (canonical error envelope).

Bounded input rules:

- Bodies larger than ``body_limit_bytes`` (default 1 MiB) return 413 with
  code ``body_too_large``.
- Malformed JSON on a JSON route returns 400 with code ``malformed_json``.
- A non-JSON content type on a JSON route returns 415 with code
  ``unsupported_media_type``.

The server binds 127.0.0.1 by default; callers must explicitly pass another
host to bind anything else.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opsledger.core.errors import ApplicationError

from .envelope import InputError, build_error_body, error_response_for, new_request_id

__all__ = [
    "DEFAULT_BODY_LIMIT_BYTES",
    "DEFAULT_HOST",
    "Request",
    "Router",
    "RouterError",
    "RouterServer",
]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_BODY_LIMIT_BYTES = 1024 * 1024
_READ_CHUNK_BYTES = 65536

_MEDIA_TYPE_JSON = "application/json"
_MEDIA_TYPE_JSON_SUFFIX = "+json"


class RouterError(Exception):
    """Raised for router misuse (duplicate route registration)."""


@dataclass(frozen=True)
class Request:
    """Parsed view of one request, handed to route handlers.

    Attributes:
        method: HTTP method as upper-case text.
        path: Request target path (no query string).
        headers: Message headers of the parsed request.
        body: Raw request body bytes (empty when there is no body).
        content_type: Media type from the Content-Type header, or ``""``.
        json: Parsed JSON payload. ``None`` when absent or not parseable;
            use :attr:`json_error` to tell a JSON ``null`` payload apart
            from a parse failure.
        json_error: ``None`` when the body parsed (or was absent); an
            :class:`InputError` describing the parse failure otherwise.
    """

    method: str
    path: str
    headers: object
    body: bytes
    content_type: str
    json: object
    json_error: InputError | None

    def json_or_error(self) -> object:
        """Return the parsed JSON payload or raise the parse :class:`InputError`."""
        if self.json_error is not None:
            raise self.json_error
        return self.json


class _Route:
    __slots__ = ("handler", "methods")

    def __init__(self, handler, methods: frozenset[str]) -> None:
        self.handler = handler
        self.methods = methods


class Router:
    """Exact-path router with allowed-method sets per route."""

    def __init__(self, *, body_limit_bytes: int = DEFAULT_BODY_LIMIT_BYTES) -> None:
        self._routes: dict[str, _Route] = {}
        self._body_limit_bytes = int(body_limit_bytes)
        self._lock = threading.Lock()

    def add(self, path: str, methods: str | list[str], handler) -> None:
        """Register ``handler`` for an exact ``path`` and allowed methods.

        ``methods`` accepts a single method or a list. Registering the same
        path twice raises :class:`RouterError`.
        """
        if not path.startswith("/"):
            raise RouterError("route path must start with '/'")
        normalized = [str(m).upper() for m in ([methods] if isinstance(methods, str) else methods)]
        if not normalized:
            raise RouterError("route must allow at least one method")
        with self._lock:
            if path in self._routes:
                raise RouterError(f"duplicate route registered for {path}")
            self._routes[path] = _Route(handler, frozenset(normalized))

    def _allow_header_for(self, path: str) -> str | None:
        route = self._routes.get(path)
        if route is None:
            return None
        return ", ".join(sorted(route.methods))

    def _parse_request(self, handler: BaseHTTPRequestHandler, body: bytes) -> Request:
        content_type = ""
        raw_type = handler.headers.get("Content-Type")
        if raw_type:
            content_type = str(raw_type).split(";", 1)[0].strip().lower()
        parsed: object = None
        parse_error: InputError | None = None
        if (content_type == _MEDIA_TYPE_JSON
                or content_type.endswith(_MEDIA_TYPE_JSON_SUFFIX)):
            if body:
                try:
                    parsed = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    parse_error = InputError(
                        400, "malformed_json", "request body is not valid JSON"
                    )
                    parsed = None
        elif content_type and handler.command not in ("GET", "HEAD", "OPTIONS"):
            parse_error = InputError(
                415,
                "unsupported_media_type",
                "content type must be application/json",
            )
        return Request(
            method=handler.command,
            path=handler.path,
            headers=handler.headers,
            body=body,
            content_type=content_type,
            json=None if parse_error is not None else parsed,
            json_error=parse_error,
        )

    def dispatch(self, method: str, path: str) -> tuple[str | None, _Route | None]:
        """Return (allow header or None, matching route or None)."""
        route = self._routes.get(path)
        if route is None:
            return None, None
        upper = str(method).upper()
        if upper in route.methods:
            return None, route
        return self._allow_header_for(path), route


class _BodyTooLarge(Exception):
    """Internal signal: declared body length exceeds the configured limit."""


class _AdapterHandler(BaseHTTPRequestHandler):
    """Transport adapter: parse one request, run the route, map errors."""

    protocol_version = "HTTP/1.1"
    server_version = "OpsLedger"
    sys_version = ""

    router: Router

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        """Silence per-request stderr logging; the adapter never logs bodies."""
        pass

    def _read_body(self) -> bytes:
        length_header = self.headers.get("Content-Length")
        if not length_header:
            return b""
        try:
            declared = int(str(length_header).strip())
        except ValueError:
            return b""
        if declared <= 0:
            return b""
        if declared > self.router._body_limit_bytes:
            raise _BodyTooLarge()
        remaining = declared
        chunks: list[bytes] = []
        while remaining > 0:
            block = self.rfile.read(min(_READ_CHUNK_BYTES, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        return b"".join(chunks)

    def _send_json(
        self,
        status: int,
        payload: dict[str, object],
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _handle_one(self) -> None:
        try:
            body = self._read_body()
            allow_header, route = self.router.dispatch(self.command, self.path)
            extra_headers = None
            if route is None:
                status = 404
                body_dict = build_error_body(
                    "not_found", "route not found", new_request_id()
                )
            elif allow_header is not None:
                status = 405
                body_dict = build_error_body(
                    "method_not_allowed",
                    "method is not allowed for this route",
                    new_request_id(),
                )
                extra_headers = {"Allow": allow_header}
            else:
                try:
                    request = self.router._parse_request(self, body)
                    request.json_or_error()
                except InputError as exc:
                    status = exc.status
                    body_dict = build_error_body(exc.code, exc.message, new_request_id())
                else:
                    try:
                        status, body_dict = route.handler(request)
                        body_dict = dict(body_dict)
                    except ApplicationError as error:
                        status, body_dict = error_response_for(error, new_request_id())
                    except Exception as error:
                        status, body_dict = error_response_for(error, new_request_id())
            self._send_json(status, body_dict, extra_headers)
        except _BodyTooLarge:
            self._send_json(
                413,
                build_error_body(
                    "body_too_large", "request body is too large", new_request_id()
                ),
            )
        except Exception:
            try:
                self._send_json(
                    500,
                    build_error_body(
                        "internal_error",
                        "internal server error",
                        new_request_id(),
                    ),
                )
            except Exception:
                pass

    def do_GET(self):
        self._handle_one()

    def do_POST(self):
        self._handle_one()

    def do_PUT(self):
        self._handle_one()

    def do_PATCH(self):
        self._handle_one()

    def do_DELETE(self):
        self._handle_one()

    def do_HEAD(self):
        self._handle_one()

    def do_OPTIONS(self):
        self._handle_one()


class RouterServer(ThreadingHTTPServer):
    """Threading HTTP server bound to the given host (127.0.0.1 default).

    ``daemon_threads`` is enabled so a shutdown does not wait on hung client
    connections. Route dispatch is handled entirely by :class:`Router` and
    :class:`_AdapterHandler`.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        router: Router,
        *,
        host: str = DEFAULT_HOST,
        port: int = 0,
        timeout: float = 10,
    ) -> None:
        if host != DEFAULT_HOST and not _explicit_host_allowed(host):
            raise ValueError(
                "binding a non-loopback host requires an explicit host argument"
            )
        self.router = router
        handler_class = type(
            "_BoundAdapterHandler", (_AdapterHandler,), {"router": router}
        )
        super().__init__((host, int(port)), handler_class)
