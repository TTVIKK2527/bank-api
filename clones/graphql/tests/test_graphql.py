import json
import unittest
from graphql import get_introspection_query
from fixture import CASES
from bank_graphql import create_schema, execute
from upstream import UpstreamError

QUERIES = [
    '{ health { status database timestamp } }',
    '{ apiDocs }',
    'mutation($x:UserInput!){ registerUser(input:$x){ userId fullName createdAt token } }',
    'query($userId:String!){ user(userId:$userId){ userId fullName createdAt } }',
    'mutation($userId:String!,$currency:String!){ createAccount(userId:$userId,currency:$currency){ accountNumber ownerId currency balance createdAt } }',
    'query($accountNumber:String!){ account(accountNumber:$accountNumber){ accountNumber ownerName currency } }',
    'mutation($x:TransferInput!){ initiateTransfer(input:$x){ transferId status sourceAccount destinationAccount amount timestamp } }',
    'mutation($jwt:String!){ receiveTransfer(jwt:$jwt){ transferId status destinationAccount amount timestamp } }',
    'query($transferId:String!){ transfer(transferId:$transferId){ transferId status sourceAccount destinationAccount amount timestamp } }',
]
FIELDS = ["health", "apiDocs", "registerUser", "user", "createAccount", "account", "initiateTransfer", "receiveTransfer", "transfer"]


class Rest:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def request(self, *args):
        self.calls.append(args)
        if self.error:
            raise self.error
        return self.result


class GraphQLTests(unittest.TestCase):
    def setUp(self):
        self.schema = create_schema()

    def test_all_nine_operations_match_rest_contract(self):
        for index, (_, inputs, method, path, body, expected) in enumerate(CASES):
            with self.subTest(field=FIELDS[index]):
                rest = Rest(expected)
                variables = {"x": inputs} if index in (2, 6) else inputs
                result = execute(self.schema, {"query": QUERIES[index], "variables": variables}, rest, "Bearer test")
                self.assertNotIn("errors", result)
                output = result["data"][FIELDS[index]]
                self.assertEqual(json.loads(output) if index == 1 else output, expected)
                self.assertEqual(rest.calls, [(method, path, body, "Bearer test")])

    def test_introspection_and_schema_validation(self):
        result = execute(self.schema, {"query": get_introspection_query()}, Rest())
        self.assertNotIn("errors", result)
        self.assertEqual(result["data"]["__schema"]["queryType"]["name"], "Query")

    def test_missing_required_input_does_not_contact_rest(self):
        rest = Rest()
        result = execute(self.schema, {"query": 'mutation { registerUser(input:{}) { userId } }'}, rest)
        self.assertIn("errors", result)
        self.assertEqual(rest.calls, [])

    def test_error_payloads_preserve_pending_and_timeout_data(self):
        for status in (400, 401, 403, 404, 409, 422, 423, 429, 500, 503):
            with self.subTest(status=status):
                body = {"code": "TEST_ERROR", "message": "Not ready", "transferId": "demo", "status": "pending"}
                result = execute(self.schema, {"query": '{ health { status } }'}, Rest(error=UpstreamError(status, body)))
                self.assertEqual(result["errors"][0]["extensions"], {"code": "TEST_ERROR", "httpStatus": status, "response": body})

    def test_money_is_never_converted_to_float(self):
        rest = Rest({"amount": "9999999999999.99"})
        result = execute(self.schema, {"query": '{ transfer(transferId:"x") { amount } }'}, rest)
        self.assertEqual(result["data"]["transfer"]["amount"], "9999999999999.99")

    def test_path_injection_encoded_and_empty_id_rejected(self):
        rest = Rest({"userId": "x"})
        execute(self.schema, {"query": '{ user(userId:"x/y?q=1") { userId } }'}, rest)
        self.assertEqual(rest.calls[0][1], "/users/x%2Fy%3Fq%3D1")
        rest.calls.clear()
        result = execute(self.schema, {"query": '{ user(userId:"") { userId } }'}, rest)
        self.assertEqual(result["errors"][0]["extensions"]["code"], "INVALID_REQUEST")
        self.assertEqual(rest.calls, [])

    def test_invalid_transport_envelopes(self):
        for payload in (None, [], {}, {"query": 2}, {"query": "{ health { status } }", "variables": []}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                execute(self.schema, payload, Rest())

    def test_invalid_query_is_not_sent_to_rest(self):
        rest = Rest()
        result = execute(self.schema, {"query": '{ unknownField }'}, rest)
        self.assertIn("errors", result)
        self.assertEqual(rest.calls, [])


if __name__ == "__main__":
    unittest.main()
