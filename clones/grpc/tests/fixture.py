"""Deterministic HTTP contract fixture, NOT a replacement bank implementation."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

NOW = "2026-11-16T08:00:00Z"
USER = {"userId": "user-example", "fullName": "Demo User", "createdAt": NOW}
TRANSFER = {"transferId": "550e8400-e29b-41d4-a716-446655440000", "status": "completed",
            "sourceAccount": "EST12345", "destinationAccount": "EST54321",
            "amount": "1.00", "timestamp": NOW}
CASES = [
    ("Health", {}, "GET", "/health", None,
     {"status": "ok", "database": "connected", "timestamp": NOW}),
    ("GetApiDocs", {}, "GET", "/api-docs.json", None, {"openapi": "3.0.3", "paths": {}}),
    ("RegisterUser", {"fullName": "Demo User"}, "POST", "/users", {"fullName": "Demo User"},
     {**USER, "token": "fixture-token"}),
    ("GetUser", {"userId": "user-example"}, "GET", "/users/user-example", None, USER),
    ("CreateAccount", {"userId": "user-example", "currency": "EUR"}, "POST", "/users/user-example/accounts",
     {"currency": "EUR"}, {"accountNumber": "EST12345", "ownerId": "user-example", "currency": "EUR",
                           "balance": "0.00", "createdAt": NOW}),
    ("LookupAccount", {"accountNumber": "EST12345"}, "GET", "/accounts/EST12345", None,
     {"accountNumber": "EST12345", "ownerName": "Demo User", "currency": "EUR"}),
    ("InitiateTransfer", {k: TRANSFER[k] for k in ("transferId", "sourceAccount", "destinationAccount", "amount")},
     "POST", "/transfers", {k: TRANSFER[k] for k in ("transferId", "sourceAccount", "destinationAccount", "amount")}, TRANSFER),
    ("ReceiveTransfer", {"jwt": "fixture-signed-token"}, "POST", "/transfers/receive", {"jwt": "fixture-signed-token"},
     {k: TRANSFER[k] for k in ("transferId", "status", "destinationAccount", "amount", "timestamp")}),
    ("GetTransfer", {"transferId": TRANSFER["transferId"]}, "GET", "/transfers/" + TRANSFER["transferId"], None, TRANSFER),
]


class Fixture:
    def __init__(self):
        self.calls = []
        self.override = None
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_request(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"]))) if self.headers.get("Content-Length") else None
                fixture.calls.append((self.command, self.path, body, self.headers.get("Authorization")))
                status, response = 404, {"code": "NOT_FOUND", "message": "Fixture route not found"}
                for _, _, method, path, expected, output in CASES:
                    if method == self.command and "/api/v1" + path == self.path:
                        status, response = (200 if method == "GET" or path.endswith("/receive") else 201), output
                        if body != expected:
                            status, response = 400, {"code": "INVALID_REQUEST", "message": "Unexpected fixture payload"}
                        break
                if fixture.override is not None:
                    status, response = fixture.override
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())

            do_GET = do_POST = handle_request

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.http.serve_forever, daemon=True)
        self.url = "http://127.0.0.1:" + str(self.http.server_port) + "/api/v1"

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
