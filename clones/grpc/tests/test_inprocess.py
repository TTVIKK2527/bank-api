"""No sockets: real HTTP request encoding, protobuf wire format and RPC handlers."""
import io
import json
import socket
import unittest
from pathlib import Path
import re
from urllib.error import HTTPError, URLError

import grpc
from google.protobuf.json_format import MessageToDict, ParseDict
import bank_pb2 as pb
from fixture import CASES, TRANSFER
from server import Bank, STATUS
from upstream import RestClient, UpstreamError


class Aborted(Exception):
    def __init__(self, code, details):
        self.code, self.details = code, details


class Context:
    def __init__(self, auth=()):
        self.auth, self.trailing = auth, ()

    def invocation_metadata(self):
        from collections import namedtuple
        Metadata = namedtuple("Metadata", "key value")
        return [Metadata("authorization", value) for value in self.auth]

    def time_remaining(self):
        return 2

    def set_trailing_metadata(self, metadata):
        self.trailing = metadata

    def abort(self, code, details):
        raise Aborted(code, details)


class RecordingOpener:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error:
            raise self.error
        return io.BytesIO(json.dumps(self.response).encode())


class InProcessTests(unittest.TestCase):
    def test_all_openapi_public_operations_have_a_fixture_and_rpc(self):
        spec = (Path(__file__).resolve().parents[3] / "services/api-gateway/src/openapi.yaml").read_text()
        paths = set()
        current = None
        for line in spec.splitlines():
            match = re.match(r"^  (/[^:]+):$", line)
            if match:
                current = match[1]
            method = re.match(r"^    (get|post|put|delete|patch):$", line)
            if current and method:
                paths.add((method[1].upper(), current))
        mapped = {
            ("GET", "/health"), ("GET", "/api-docs.json"), ("POST", "/users"),
            ("GET", "/users/{userId}"), ("POST", "/users/{userId}/accounts"),
            ("GET", "/accounts/{accountNumber}"), ("POST", "/transfers"),
            ("POST", "/transfers/receive"), ("GET", "/transfers/{transferId}"),
        }
        self.assertEqual(paths, mapped)
        self.assertEqual({case[0] for case in CASES},
                         set(pb.DESCRIPTOR.services_by_name["Bank"].methods_by_name))

    def setup_bank(self, response=None, error=None):
        rest = RestClient("http://127.0.0.1:3000/api/v1")
        opener = RecordingOpener(response, error)
        rest.opener = opener
        return Bank(rest), opener

    def request(self, name, data):
        descriptor = pb.DESCRIPTOR.services_by_name["Bank"].methods_by_name[name]
        cls = getattr(pb, descriptor.input_type.name)
        message = ParseDict(data, cls())
        return cls.FromString(message.SerializeToString())

    def test_nine_operations_roundtrip_protobuf_and_http_contract(self):
        for name, inputs, method, path, body, expected in CASES:
            with self.subTest(rpc=name):
                bank, opener = self.setup_bank(expected)
                response = getattr(bank, name)(self.request(name, inputs), Context(("Bearer demo",)))
                response = type(response).FromString(response.SerializeToString())
                actual = json.loads(response.json) if name == "GetApiDocs" else MessageToDict(response)
                self.assertEqual(actual, expected)
                req, timeout = opener.calls[0]
                self.assertEqual(req.full_url, "http://127.0.0.1:3000/api/v1" + path)
                self.assertEqual(req.method, method)
                self.assertEqual(json.loads(req.data) if req.data else None, body)
                self.assertEqual(req.get_header("Authorization"), "Bearer demo")
                self.assertEqual(timeout, 2)

    def test_ten_error_statuses_and_structured_details(self):
        for status in (400, 401, 403, 404, 409, 422, 423, 429, 500, 503):
            with self.subTest(status=status):
                body = {"code": "TEST_ERROR", "message": "Example error", **TRANSFER}
                error = HTTPError("http://localhost", status, "error", {}, io.BytesIO(json.dumps(body).encode()))
                bank, _ = self.setup_bank(error=error)
                context = Context()
                with self.assertRaises(Aborted) as raised:
                    bank.GetTransfer(pb.TransferLookup(transferId=TRANSFER["transferId"]), context)
                self.assertEqual(raised.exception.code, STATUS.get(status, grpc.StatusCode.INTERNAL))
                details = pb.BankError.FromString(dict(context.trailing)["bank-error-bin"])
                self.assertEqual(details.httpStatus, status)
                self.assertEqual(details.code, "TEST_ERROR")
                self.assertEqual(details.message, "Example error")
                self.assertEqual(json.loads(details.responseJson), body)

    def test_optional_zero_and_precise_decimal_values(self):
        expected = {**TRANSFER, "retryCount": 0, "amount": "9999999999999.99", "exchangeRate": "1.234567"}
        bank, _ = self.setup_bank(expected)
        result = bank.GetTransfer(pb.TransferLookup(transferId="id"), Context())
        self.assertEqual(MessageToDict(result), expected)

    def test_missing_and_dot_ids_do_not_contact_rest(self):
        for value in ("", ".", ".."):
            with self.subTest(id=value):
                bank, opener = self.setup_bank()
                with self.assertRaises(Aborted) as raised:
                    bank.GetUser(pb.UserRequest(userId=value), Context())
                self.assertEqual(raised.exception.code, grpc.StatusCode.INVALID_ARGUMENT)
                self.assertEqual(opener.calls, [])

    def test_encoded_path_ids(self):
        bank, opener = self.setup_bank({"userId": "a/b?x#y"})
        bank.GetUser(pb.UserRequest(userId="a/b?x#y"), Context())
        self.assertTrue(opener.calls[0][0].full_url.endswith("/users/a%2Fb%3Fx%23y"))

    def test_duplicate_auth_rejected_before_request(self):
        bank, opener = self.setup_bank()
        with self.assertRaises(Aborted) as raised:
            bank.Health(pb.Empty(), Context(("a", "b")))
        self.assertEqual(raised.exception.code, grpc.StatusCode.INVALID_ARGUMENT)
        self.assertEqual(opener.calls, [])

    def test_public_request_does_not_invent_auth(self):
        bank, opener = self.setup_bank({"status": "ok"})
        bank.Health(pb.Empty(), Context())
        self.assertIsNone(opener.calls[0][0].get_header("Authorization"))

    def test_unknown_response_field_is_not_discarded(self):
        bank, _ = self.setup_bank({"status": "ok", "newField": True})
        with self.assertRaises(Aborted) as raised:
            bank.Health(pb.Empty(), Context())
        self.assertEqual(raised.exception.code, grpc.StatusCode.INTERNAL)

    def test_omitted_email_vs_explicit_empty_email(self):
        for inputs in ({"fullName": "Demo"}, {"fullName": "Demo", "email": ""}):
            with self.subTest(inputs=inputs):
                bank, opener = self.setup_bank({"userId": "id"})
                bank.RegisterUser(self.request("RegisterUser", inputs), Context())
                self.assertEqual(json.loads(opener.calls[0][0].data), inputs)

    def test_timeout_and_connection_failure(self):
        for error, status in ((TimeoutError(), 504), (URLError(socket.timeout()), 504), (URLError("connection refused"), 503)):
            with self.subTest(status=status):
                bank, _ = self.setup_bank(error=error)
                with self.assertRaises(Aborted) as raised:
                    bank.Health(pb.Empty(), Context())
                self.assertEqual(raised.exception.code, STATUS[status])

    def test_non_json_error_retains_http_status(self):
        error = HTTPError("http://localhost", 429, "error", {}, io.BytesIO(b"<html>busy</html>"))
        bank, _ = self.setup_bank(error=error)
        context = Context()
        with self.assertRaises(Aborted) as raised:
            bank.Health(pb.Empty(), context)
        self.assertEqual(raised.exception.code, grpc.StatusCode.RESOURCE_EXHAUSTED)
        details = pb.BankError.FromString(dict(context.trailing)["bank-error-bin"])
        self.assertEqual(details.httpStatus, 429)

    def test_bad_upstream_url_rejected(self):
        for url in ("file:///etc/passwd", "http://user:pass@host", "http://host/?x=y"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                RestClient(url)


if __name__ == "__main__":
    unittest.main()
