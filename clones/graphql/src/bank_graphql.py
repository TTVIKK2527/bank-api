"""GraphQL schema backed by the original public REST gateway."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import quote

from graphql import build_schema, graphql_sync, GraphQLError, assert_valid_schema
from upstream import RestClient, UpstreamError


def segment(value):
    if not value or value in (".", ".."):
        raise GraphQLError("Path ID is required", extensions={"code": "INVALID_REQUEST", "httpStatus": 400})
    return quote(value, safe="")


def create_schema():
    schema = build_schema((Path(__file__).resolve().parents[1] / "schema/bank.graphql").read_text())
    routes = {
        "health": ("GET", lambda a: "/health", lambda a: None),
        "apiDocs": ("GET", lambda a: "/api-docs.json", lambda a: None),
        "user": ("GET", lambda a: "/users/" + segment(a["userId"]), lambda a: None),
        "account": ("GET", lambda a: "/accounts/" + segment(a["accountNumber"]), lambda a: None),
        "transfer": ("GET", lambda a: "/transfers/" + segment(a["transferId"]), lambda a: None),
        "registerUser": ("POST", lambda a: "/users", lambda a: a["input"]),
        "createAccount": ("POST", lambda a: "/users/" + segment(a["userId"]) + "/accounts", lambda a: {"currency": a["currency"]}),
        "initiateTransfer": ("POST", lambda a: "/transfers", lambda a: a["input"]),
        "receiveTransfer": ("POST", lambda a: "/transfers/receive", lambda a: {"jwt": a["jwt"]}),
    }

    def resolver(name):
        method, path, body = routes[name]

        def resolve(root, info, **args):
            try:
                result = info.context["rest"].request(method, path(args), body(args), info.context.get("authorization"))
                return json.dumps(result, ensure_ascii=False) if name == "apiDocs" else result
            except UpstreamError as error:
                raise GraphQLError(str(error), extensions={
                    "code": error.body.get("code", "UPSTREAM_ERROR"), "httpStatus": error.status,
                    "response": error.body,
                }) from error
        return resolve

    for type_name in ("Query", "Mutation"):
        for name, field in schema.get_type(type_name).fields.items():
            field.resolve = resolver(name)
    assert_valid_schema(schema)
    return schema


def execute(schema, payload, rest, authorization=None):
    if not isinstance(payload, dict) or not isinstance(payload.get("query"), str):
        raise ValueError("query must be a string")
    variables = payload.get("variables")
    if variables is not None and not isinstance(variables, dict):
        raise ValueError("variables must be an object")
    operation = payload.get("operationName")
    if operation is not None and not isinstance(operation, str):
        raise ValueError("operationName must be a string")
    return graphql_sync(schema, payload["query"], variable_values=variables, operation_name=operation,
                        context_value={"rest": rest, "authorization": authorization}).formatted


def make_handler(rest):
    schema = create_schema()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.path != "/graphql":
                self.send_error(404)
                return
            try:
                if len(self.headers.get_all("Authorization", [])) > 1:
                    raise ValueError("Multiple authorization headers")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 65536:
                    raise ValueError("Request must be between 1 and 65536 bytes")
                payload = json.loads(self.rfile.read(size))
                result = execute(schema, payload, rest, self.headers.get("Authorization"))
                status = 200
            except (ValueError, UnicodeError) as error:
                status, result = 400, {"errors": [{"message": str(error)}]}
            data = json.dumps(result, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rest-url", default=os.getenv("REST_BASE_URL", "http://127.0.0.1:3000/api/v1"))
    parser.add_argument("--port", type=int, default=50052)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(RestClient(args.rest_url)))
    print(f"GraphQL http://127.0.0.1:{args.port}/graphql", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
