"""Real local HTTP round trips against a synthetic REST contract, never a live bank."""
import json
from pathlib import Path
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
for part in ('grpc/src', 'grpc/tests', 'graphql/src', 'graphql/tests', 'soap/src', 'soap/tests'):
    sys.path.insert(0, str(ROOT / part))
from fixture import Fixture, CASES
from upstream import RestClient
from bank_graphql import make_handler as graphql_handler
from bank_soap import make_handler as soap_handler, Service
from contract import NS, ENVELOPE, WSDL
from test_graphql import QUERIES, FIELDS
from test_soap import request as soap_request
from lxml import etree as E


class HTTPTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = Fixture().start()
        cls.servers = []
        cls.threads = []
        for handler in (graphql_handler, soap_handler):
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler(RestClient(cls.fixture.url)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            cls.servers.append(server)
            cls.threads.append(thread)

    @classmethod
    def tearDownClass(cls):
        for server, thread in zip(cls.servers, cls.threads):
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
        cls.fixture.close()

    def test_graphql_nine_operations_over_http(self):
        port = self.servers[0].server_port
        for index, (_, inputs, method, path, body, expected) in enumerate(CASES):
            with self.subTest(field=FIELDS[index]):
                variables = {'x': inputs} if index in (2, 6) else inputs
                payload = json.dumps({'query': QUERIES[index], 'variables': variables}).encode()
                req = Request(f'http://127.0.0.1:{port}/graphql', payload,
                              {'Content-Type': 'application/json', 'Authorization': 'Bearer fixture-token'})
                with urlopen(req, timeout=3) as response:
                    result = json.load(response)
                self.assertNotIn('errors', result)
                actual = result['data'][FIELDS[index]]
                self.assertEqual(json.loads(actual) if index == 1 else actual, expected)
                self.assertEqual(self.fixture.calls[-1], (method, '/api/v1' + path, body, 'Bearer fixture-token'))

    def test_soap_nine_operations_and_wsdl_over_http(self):
        port = self.servers[1].server_port
        with urlopen(f'http://127.0.0.1:{port}/soap?wsdl', timeout=3) as response:
            self.assertEqual(E.fromstring(response.read()).tag, '{' + WSDL + '}definitions')
        schema = Service(RestClient(self.fixture.url)).schema
        for name, inputs, method, path, body, expected in CASES:
            with self.subTest(operation=name):
                req = Request(f'http://127.0.0.1:{port}/soap', soap_request(name, inputs),
                              {'Content-Type': 'text/xml', 'SOAPAction': '"' + NS + '/' + name + '"',
                               'Authorization': 'Bearer fixture-token'})
                with urlopen(req, timeout=3) as response:
                    wrapper = E.fromstring(response.read()).find('{' + ENVELOPE + '}Body')[0]
                schema.assertValid(wrapper)
                result = {E.QName(e).localname: e.text or '' for e in wrapper}
                self.assertEqual(json.loads(result['json']) if name == 'GetApiDocs' else result, expected)
                self.assertEqual(self.fixture.calls[-1], (method, '/api/v1' + path, body, 'Bearer fixture-token'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
