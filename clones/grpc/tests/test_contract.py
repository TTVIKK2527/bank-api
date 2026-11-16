import json
import unittest
import urllib.request

import grpc
from google.protobuf.json_format import MessageToDict, ParseDict
import bank_pb2 as pb
import bank_pb2_grpc as rpc
from fixture import Fixture, CASES, TRANSFER
from server import create_server, STATUS
from upstream import RestClient


def request_message(name, data):
    method = pb.DESCRIPTOR.services_by_name["Bank"].methods_by_name[name]
    return ParseDict(data, getattr(pb, method.input_type.name)())


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.fixture = Fixture().start()
        except PermissionError:
            raise unittest.SkipTest("This sandbox does not permit local sockets; run on the host")
        cls.server, port = create_server(cls.fixture.url, "127.0.0.1:0")
        cls.server.start()
        cls.channel = grpc.insecure_channel("127.0.0.1:" + str(port))
        grpc.channel_ready_future(cls.channel).result(timeout=3)
        cls.stub = rpc.BankStub(cls.channel)

    @classmethod
    def tearDownClass(cls):
        cls.channel.close()
        cls.server.stop(0).wait()
        cls.fixture.close()

    def setUp(self):
        self.fixture.override = None
        self.fixture.calls.clear()

    def test_all_nine_operations_match_direct_http_and_exact_request(self):
        for name, inputs, method, path, body, _ in CASES:
            with self.subTest(rpc=name):
                direct = RestClient(self.fixture.url).request(method, path, body, "Bearer fixture-token")
                response = getattr(self.stub, name)(request_message(name, inputs), timeout=3,
                                                  metadata=(("authorization", "Bearer fixture-token"),))
                result = json.loads(response.json) if name == "GetApiDocs" else MessageToDict(response)
                self.assertEqual(direct, result)
                self.assertEqual(self.fixture.calls[-1], (method, "/api/v1" + path, body, "Bearer fixture-token"))

    def test_all_documented_error_statuses_retain_original_payload(self):
        for status in (400, 401, 403, 404, 409, 422, 423, 429, 500, 503):
            with self.subTest(http_status=status):
                original = {"code": "TEST_ERROR", "message": "Example error", **TRANSFER}
                self.fixture.override = status, original
                with self.assertRaises(grpc.RpcError) as raised:
                    self.stub.GetTransfer(pb.TransferLookup(transferId=TRANSFER["transferId"]), timeout=3)
                error = raised.exception
                self.assertEqual(error.code(), STATUS.get(status, grpc.StatusCode.INTERNAL))
                details = pb.BankError.FromString(dict(error.trailing_metadata())["bank-error-bin"])
                self.assertEqual(details.httpStatus, status)
                self.assertEqual(json.loads(details.responseJson), original)
                self.assertEqual(error.details(), original["message"])

    def test_optional_zero_retry_count_and_decimal_strings_are_preserved(self):
        expected = {**TRANSFER, "status": "pending", "retryCount": 0, "amount": "9999999999999.99",
                    "exchangeRate": "1.234567", "convertedAmount": "12345678901234.56"}
        self.fixture.override = 200, expected
        response = self.stub.GetTransfer(pb.TransferLookup(transferId=TRANSFER["transferId"]), timeout=3)
        self.assertEqual(MessageToDict(response), expected)

    def test_empty_id_does_not_reach_upstream(self):
        with self.assertRaises(grpc.RpcError) as raised:
            self.stub.GetUser(pb.UserRequest(), timeout=3)
        self.assertEqual(raised.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)
        self.assertEqual(self.fixture.calls, [])

    def test_path_parameter_cannot_inject_a_query_or_path(self):
        with self.assertRaises(grpc.RpcError):
            self.stub.GetUser(pb.UserRequest(userId="a/b?admin=true#x"), timeout=3)
        self.assertEqual(self.fixture.calls[-1][1], "/api/v1/users/a%2Fb%3Fadmin%3Dtrue%23x")

    def test_no_authorization_header_is_invented(self):
        self.stub.Health(pb.Empty(), timeout=3)
        self.assertIsNone(self.fixture.calls[-1][3])

    def test_duplicate_authorization_is_rejected(self):
        with self.assertRaises(grpc.RpcError) as raised:
            self.stub.Health(pb.Empty(), timeout=3, metadata=(("authorization", "a"), ("authorization", "b")))
        self.assertEqual(raised.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)
        self.assertEqual(self.fixture.calls, [])

    def test_omitted_optional_email_is_not_sent_as_empty_string(self):
        self.stub.RegisterUser(pb.RegisterUserRequest(fullName="Demo User"), timeout=3)
        self.assertEqual(self.fixture.calls[-1][2], {"fullName": "Demo User"})

    def test_unknown_upstream_fields_fail_instead_of_silently_disappearing(self):
        self.fixture.override = 200, {"status": "ok", "unexpected": "new field"}
        with self.assertRaises(grpc.RpcError) as raised:
            self.stub.Health(pb.Empty(), timeout=3)
        self.assertEqual(raised.exception.code(), grpc.StatusCode.INTERNAL)

    def test_rest_base_url_validation(self):
        for url in ("file:///etc/passwd", "http://name:password@localhost", "http://localhost/?x=y"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                RestClient(url)


if __name__ == "__main__":
    unittest.main()
