#!/usr/bin/env python3
"""Networkless container Ollama bridge; protocol traffic uses docker -i stdio only.

The guest has --network none. This process is the sole route to model inference:
HTTP on guest loopback becomes framed requests on stdout, with replies on stdin.
No shell, filesystem or Docker API endpoint is exposed by the bridge.
"""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import queue
import sys
import threading
import uuid

LIMIT = 2 * 1024 * 1024
META_LIMIT = 8 * 1024 * 1024
META_PATHS = {"/api/tags", "/api/show"}
_out = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
_write_lock = threading.Lock()
_pending = {}
_pending_lock = threading.Lock()
_timeout = 450


def emit(frame):
    with _write_lock:
        _out.write(json.dumps(frame, separators=(",", ":")) + "\n")
        _out.flush()


def receive():
    for line in sys.stdin:
        try:
            frame = json.loads(line)
            with _pending_lock:
                inbox = _pending.get(frame.get("id"))
            if inbox:
                inbox.put(frame)
        except (ValueError, TypeError):
            continue
    with _pending_lock:
        all_queues = list(_pending.values())
    for inbox in all_queues:
        inbox.put({"kind": "error", "status": 502, "message": "BROKER_PIPE_CLOSED"})


class Bridge(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        return

    def do_GET(self):
        self.bridge()

    def do_POST(self):
        self.bridge()

    def do_DELETE(self):
        self.send_error(403, "METHOD_NOT_ALLOWED")

    def metadata(self, inbox):
        """Buffer small fixed metadata replies before sending HTTP 200.

        The pinned Cloi isReachable() intentionally checks headers without
        consuming the first /api/tags body. Sending an upstream 200 before
        the bridge has received all chunks exposes an incomplete chunked body
        to Undici while it starts listModels() on another connection.

        Metadata is finite and bounded: use Content-Length and only commit a
        success response after a complete upstream end frame. Generation
        endpoints are NOT routed here and retain their original streaming.
        """
        payload = bytearray()
        status = None
        failure_status = None
        failure_message = "BROKER_ERROR"
        while True:
            try:
                frame = inbox.get(timeout=_timeout)
            except queue.Empty:
                frame = {"kind": "error", "status": 504, "message": "BROKER_TIMEOUT"}
            kind = frame.get("kind")
            if kind == "error":
                failure_status = int(frame.get("status", 502))
                failure_message = str(frame.get("message", "BROKER_ERROR"))[:180]
                break
            if kind == "start" and status is None:
                status = int(frame.get("status", 200))
            elif kind == "chunk" and status is not None:
                raw = base64.b64decode(frame["body"], validate=True)
                if len(payload) + len(raw) > META_LIMIT:
                    failure_status = 502
                    failure_message = "METADATA_RESPONSE_TOO_LARGE"
                    break
                payload.extend(raw)
            elif kind == "end" and status is not None:
                break
            else:
                failure_status = 502
                failure_message = "BROKER_METADATA_FRAME_INVALID"
                break
        if failure_status is not None:
            # Never emit a half-successful HTTP 200 with an incomplete body.
            body = json.dumps({"error": failure_message}).encode("utf-8")
            status = failure_status if 400 <= failure_status <= 599 else 502
        else:
            body = bytes(payload)
            if status is None or not 100 <= status <= 599:
                body = b'{"error":"BROKER_METADATA_STATUS_INVALID"}'
                status = 502
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def bridge(self):
        try:
            raw_length = self.headers.get("Content-Length", "0")
            length = int(raw_length)
            if length < 0 or length > LIMIT:
                return self.send_error(413, "REQUEST_TOO_LARGE")
            body = self.rfile.read(length)
            if len(body) != length:
                return self.send_error(400, "BODY_INCOMPLETE")
            request_id = uuid.uuid4().hex
            inbox = queue.Queue()
            with _pending_lock:
                _pending[request_id] = inbox
            try:
                emit({"kind": "request", "id": request_id,
                      "method": self.command, "path": self.path,
                      "body": base64.b64encode(body).decode("ascii")})
                if self.path in META_PATHS:
                    self.metadata(inbox)
                    return
                headers_sent = False
                while True:
                    try:
                        frame = inbox.get(timeout=_timeout)
                    except queue.Empty:
                        frame = {"kind": "error", "status": 504, "message": "BROKER_TIMEOUT"}
                    kind = frame.get("kind")
                    if kind == "error":
                        if not headers_sent:
                            msg = json.dumps({"error": frame.get("message", "BROKER_ERROR")}).encode()
                            self.send_response(int(frame.get("status", 502)))
                            self.send_header("Content-Type", "application/json")
                            self.send_header("Content-Length", str(len(msg)))
                            self.send_header("Connection", "close")
                            self.close_connection = True
                            self.end_headers()
                            self.wfile.write(msg)
                        else:
                            self.close_connection = True
                        break
                    if kind == "start":
                        self.send_response(int(frame.get("status", 200)))
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Transfer-Encoding", "chunked")
                        # Cloi's reachability check reads only response headers.
                        # Explicitly end this response's TCP lifetime to prevent
                        # reusing a socket with a body the client never consumed.
                        self.send_header("Connection", "close")
                        self.close_connection = True
                        self.end_headers()
                        headers_sent = True
                    elif kind == "chunk" and headers_sent:
                        raw = base64.b64decode(frame["body"], validate=True)
                        if raw:
                            self.wfile.write(("%X\r\n" % len(raw)).encode("ascii"))
                            self.wfile.write(raw)
                            self.wfile.write(b"\r\n")
                            self.wfile.flush()
                    elif kind == "end" and headers_sent:
                        self.wfile.write(b"0\r\n\r\n")
                        self.wfile.flush()
                        break
                    else:
                        self.close_connection = True
                        break
            finally:
                with _pending_lock:
                    _pending.pop(request_id, None)
        except (OSError, ValueError, KeyError) as exc:
            self.close_connection = True
            print("GUEST_BRIDGE_ERROR: " + type(exc).__name__, file=sys.stderr)


def main():
    global _timeout
    from compare import main as compare_main
    _timeout = 700
    threading.Thread(target=receive, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", 11434), Bridge)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # All benchmark progress goes to stderr. stdout is exclusively framed JSON.
    sys.stdout = sys.stderr
    try:
        return compare_main()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED", "error": type(exc).__name__,
                          "reason": str(exc)}), file=sys.stderr)
        sys.exit(2)
