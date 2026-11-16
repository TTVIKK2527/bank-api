"""Typed gRPC facade for the existing public REST gateway."""
import argparse
from concurrent import futures
import json
import os
from urllib.parse import quote

import grpc
from google.protobuf.json_format import MessageToDict, ParseDict, ParseError
import bank_pb2 as pb
import bank_pb2_grpc as rpc
from upstream import RestClient, UpstreamError

STATUS = {
    400: grpc.StatusCode.INVALID_ARGUMENT, 401: grpc.StatusCode.UNAUTHENTICATED,
    403: grpc.StatusCode.PERMISSION_DENIED, 404: grpc.StatusCode.NOT_FOUND,
    409: grpc.StatusCode.ALREADY_EXISTS, 422: grpc.StatusCode.FAILED_PRECONDITION,
    423: grpc.StatusCode.FAILED_PRECONDITION, 429: grpc.StatusCode.RESOURCE_EXHAUSTED,
    502: grpc.StatusCode.UNAVAILABLE, 503: grpc.StatusCode.UNAVAILABLE,
    504: grpc.StatusCode.DEADLINE_EXCEEDED,
}


def segment(value):
    # Do not let an empty path ID accidentally select another public endpoint.
    if not value or value in (".", ".."):
        raise UpstreamError(400, {"code": "INVALID_REQUEST", "message": "Path ID is required"})
    return quote(value, safe="")


class Bank(rpc.BankServicer):
    def __init__(self, rest):
        self.rest = rest

    def call(self, context, response_type, method, path, body=None):
        try:
            # Path builders are evaluated here so validation becomes an RPC error.
            path = path() if callable(path) else path
            auth = [m.value for m in context.invocation_metadata() if m.key == "authorization"]
            if len(auth) > 1:
                raise UpstreamError(400, {"code": "INVALID_REQUEST", "message": "Multiple authorization values"})
            remaining = context.time_remaining()
            result = self.rest.request(method, path, body, auth[0] if auth else None,
                                       min(5, remaining) if remaining is not None else 5)
            if response_type is pb.ApiDocsResponse:
                return pb.ApiDocsResponse(json=json.dumps(result, ensure_ascii=False))
            return ParseDict(result, response_type())
        except UpstreamError as error:
            details = pb.BankError(httpStatus=error.status,
                code=str(error.body.get("code", "UPSTREAM_ERROR")),
                message=str(error.body.get("message", "REST request failed")),
                responseJson=json.dumps(error.body, ensure_ascii=False))
            context.set_trailing_metadata((("bank-error-bin", details.SerializeToString()),))
            context.abort(STATUS.get(error.status, grpc.StatusCode.INTERNAL), details.message)
        except (ValueError, TypeError, ParseError):
            context.abort(grpc.StatusCode.INTERNAL, "REST response does not match the protobuf contract")

    def Health(self, request, context):
        return self.call(context, pb.HealthResponse, "GET", "/health")

    def GetApiDocs(self, request, context):
        return self.call(context, pb.ApiDocsResponse, "GET", "/api-docs.json")

    def RegisterUser(self, request, context):
        return self.call(context, pb.User, "POST", "/users", MessageToDict(request))

    def GetUser(self, request, context):
        return self.call(context, pb.User, "GET", lambda: "/users/" + segment(request.userId))

    def CreateAccount(self, request, context):
        return self.call(context, pb.Account, "POST", lambda: "/users/" + segment(request.userId) + "/accounts",
                         {"currency": request.currency})

    def LookupAccount(self, request, context):
        return self.call(context, pb.AccountLookup, "GET", lambda: "/accounts/" + segment(request.accountNumber))

    def InitiateTransfer(self, request, context):
        return self.call(context, pb.Transfer, "POST", "/transfers", MessageToDict(request))

    def ReceiveTransfer(self, request, context):
        return self.call(context, pb.Transfer, "POST", "/transfers/receive", {"jwt": request.jwt})

    def GetTransfer(self, request, context):
        return self.call(context, pb.Transfer, "GET", lambda: "/transfers/" + segment(request.transferId))


def create_server(base_url, address="127.0.0.1:50051"):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    rpc.add_BankServicer_to_server(Bank(RestClient(base_url)), server)
    port = server.add_insecure_port(address)
    if not port:
        raise RuntimeError("Cannot bind gRPC address")
    return server, port


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rest-url", default=os.getenv("REST_BASE_URL", "http://127.0.0.1:3000/api/v1"))
    parser.add_argument("--listen", default="127.0.0.1:50051")
    args = parser.parse_args()
    server, _ = create_server(args.rest_url, args.listen)
    server.start()
    print("gRPC listening on " + args.listen, flush=True)
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(2).wait()


if __name__ == "__main__":
    main()
