import json
import unittest
from lxml import etree as E
from contract import NS, WSDL, ENVELOPE, OPERATIONS, build_wsdl
from bank_soap import Service, envelope
from fixture import CASES, TRANSFER
from upstream import UpstreamError


def request(name, inputs):
    root, body = envelope()
    operation = E.SubElement(body, "{" + NS + "}" + name)
    for key, value in inputs.items():
        E.SubElement(operation, "{" + NS + "}" + key).text = str(value)
    return E.tostring(root)


class Rest:
    def __init__(self, result=None, error=None): self.result, self.error, self.calls = result, error, []
    def request(self, *args):
        self.calls.append(args)
        if self.error: raise self.error
        return self.result


class SoapTests(unittest.TestCase):
    def test_nine_operations_roundtrip_and_match_rest(self):
        for name, inputs, method, path, body, expected in CASES:
            with self.subTest(operation=name):
                rest = Rest(expected)
                service = Service(rest)
                status, response = service.handle(request(name, inputs), "Bearer test", NS + "/" + name)
                self.assertEqual(status, 200)
                wrapper = E.fromstring(response).find("{" + ENVELOPE + "}Body")[0]
                service.schema.assertValid(wrapper)
                result = {E.QName(e).localname: e.text or "" for e in wrapper}
                self.assertEqual(json.loads(result["json"]) if name == "GetApiDocs" else result, expected)
                self.assertEqual(rest.calls, [(method, path, body, "Bearer test")])

    def test_faults_retain_all_rest_details(self):
        for status in (400, 401, 403, 404, 409, 422, 423, 429, 500, 503):
            with self.subTest(status=status):
                body = {"code": "TEST", "message": "Example", **TRANSFER}
                service = Service(Rest(error=UpstreamError(status, body)))
                http_status, raw = service.handle(request("Health", {}))
                self.assertEqual(http_status, 500)
                detail = E.fromstring(raw).find(".//{" + NS + "}BankError")
                service.schema.assertValid(detail)
                values = {E.QName(e).localname: e.text for e in detail}
                self.assertEqual(int(values["httpStatus"]), status)
                self.assertEqual(json.loads(values["responseJson"]), body)

    def test_wsdl_references_cover_all_operations(self):
        root = build_wsdl()
        self.assertEqual({e.get("name") for e in root.findall("{"+WSDL+"}portType/{"+WSDL+"}operation")}, set(OPERATIONS))
        self.assertEqual({e.get("name") for e in root.findall("{"+WSDL+"}binding/{"+WSDL+"}operation")}, set(OPERATIONS))
        names = {e.get("name") for e in root.findall("{"+WSDL+"}message")}
        for e in root.findall(".//{"+WSDL+"}input") + root.findall(".//{"+WSDL+"}output"):
            if e.get("message"): self.assertIn(e.get("message").split(":")[1], names)

    def test_invalid_xml_missing_input_and_wrong_action_are_faults(self):
        for raw, action in ((b"broken", None), (request("GetUser", {}), None),
                            (request("Health", {}), NS + "/GetUser"),
                            (b'<!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]><x>&a;</x>', None)):
            with self.subTest(raw=raw):
                rest = Rest()
                code, response = Service(rest).handle(raw, soap_action=action)
                self.assertEqual(code, 500)
                self.assertEqual(rest.calls, [])
                self.assertIsNotNone(E.fromstring(response).find(".//{"+ENVELOPE+"}Fault"))

    def test_duplicate_fields_rejected(self):
        raw = request("GetUser", {"userId": "x"})
        root = E.fromstring(raw)
        E.SubElement(root.find("{"+ENVELOPE+"}Body")[0], "{"+NS+"}userId").text = "y"
        rest = Rest()
        self.assertEqual(Service(rest).handle(E.tostring(root))[0], 500)
        self.assertEqual(rest.calls, [])

    def test_retry_count_and_decimal_precision(self):
        expected = {**TRANSFER, "retryCount": 0, "amount": "9999999999999.99"}
        service = Service(Rest(expected))
        code, raw = service.handle(request("GetTransfer", {"transferId": "x"}))
        self.assertEqual(code, 200)
        root = E.fromstring(raw)
        self.assertEqual(root.find(".//{"+NS+"}amount").text, expected["amount"])
        self.assertEqual(root.find(".//{"+NS+"}retryCount").text, "0")


if __name__ == "__main__": unittest.main()
