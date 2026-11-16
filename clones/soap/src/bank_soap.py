import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import quote
from lxml import etree as E
from contract import NS, XSD, WSDL, ENVELOPE, OPERATIONS, build_wsdl
from upstream import RestClient, UpstreamError


def segment(value):
    if not value or value in (".", ".."):
        raise UpstreamError(400, {"code": "INVALID_REQUEST", "message": "Path ID is required"})
    return quote(value, safe="")


def route(operation, args):
    if operation == "Health": return "GET", "/health", None
    if operation == "GetApiDocs": return "GET", "/api-docs.json", None
    if operation == "RegisterUser": return "POST", "/users", args
    if operation == "GetUser": return "GET", "/users/" + segment(args["userId"]), None
    if operation == "CreateAccount": return "POST", "/users/" + segment(args["userId"]) + "/accounts", {"currency": args["currency"]}
    if operation == "LookupAccount": return "GET", "/accounts/" + segment(args["accountNumber"]), None
    if operation == "InitiateTransfer": return "POST", "/transfers", args
    if operation == "ReceiveTransfer": return "POST", "/transfers/receive", args
    if operation == "GetTransfer": return "GET", "/transfers/" + segment(args["transferId"]), None
    raise ValueError("Unknown operation")


def envelope():
    root = E.Element("{" + ENVELOPE + "}Envelope", nsmap={"soap": ENVELOPE, "bank": NS})
    return root, E.SubElement(root, "{" + ENVELOPE + "}Body")


class Service:
    def __init__(self, rest):
        self.rest = rest
        self.schema = E.XMLSchema(build_wsdl().find("{" + WSDL + "}types/{" + XSD + "}schema"))

    def fault(self, status, data, client=True):
        root, body = envelope()
        fault = E.SubElement(body, "{" + ENVELOPE + "}Fault")
        E.SubElement(fault, "faultcode").text = "soap:Client" if client else "soap:Server"
        E.SubElement(fault, "faultstring").text = str(data.get("message", "Request failed"))
        detail = E.SubElement(E.SubElement(fault, "detail"), "{" + NS + "}BankError")
        for name, value in (("httpStatus", status), ("code", data.get("code", "UPSTREAM_ERROR")),
                            ("message", data.get("message", "Request failed")), ("responseJson", json.dumps(data, ensure_ascii=False))):
            E.SubElement(detail, "{" + NS + "}" + name).text = str(value)
        return 500, E.tostring(root, xml_declaration=True, encoding="utf-8")

    def handle(self, raw, authorization=None, soap_action=None):
        try:
            parser = E.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
            root = E.fromstring(raw, parser)
            if root.getroottree().docinfo.doctype:
                raise ValueError("DTD is not accepted")
            if root.tag != "{" + ENVELOPE + "}Envelope":
                raise ValueError("SOAP 1.1 Envelope required")
            bodies = root.findall("{" + ENVELOPE + "}Body")
            if len(bodies) != 1 or len(bodies[0]) != 1:
                raise ValueError("Exactly one Body and one operation required")
            headers = root.findall("{" + ENVELOPE + "}Header")
            if len(headers) > 1 or any(h.get("{" + ENVELOPE + "}mustUnderstand") == "1" for header in headers for h in header):
                raise ValueError("Unsupported mandatory SOAP header")
            request = bodies[0][0]
            self.schema.assertValid(request)
            operation = E.QName(request).localname
            if operation not in OPERATIONS:
                raise ValueError("Request operation required")
            if soap_action and soap_action.strip('"') != NS + "/" + operation:
                raise ValueError("SOAPAction does not match operation")
            args = {E.QName(child).localname: child.text or "" for child in request}
            method, path, data = route(operation, args)
            result = self.rest.request(method, path, data, authorization)
            if operation == "GetApiDocs": result = {"json": json.dumps(result, ensure_ascii=False)}
            root, body = envelope()
            response = E.SubElement(body, "{" + NS + "}" + operation + "Response")
            known = OPERATIONS[operation][1]
            if not isinstance(result, dict) or set(result) - set(known):
                raise RuntimeError("REST response does not match WSDL")
            for field in known:
                if field in result and result[field] is not None:
                    E.SubElement(response, "{" + NS + "}" + field).text = str(result[field])
            try:
                self.schema.assertValid(response)
            except E.DocumentInvalid as error:
                raise RuntimeError("REST response does not match WSDL") from error
            return 200, E.tostring(root, xml_declaration=True, encoding="utf-8")
        except UpstreamError as error:
            return self.fault(error.status, error.body, error.status < 500)
        except (E.XMLSyntaxError, E.DocumentInvalid, ValueError, KeyError):
            return self.fault(400, {"code": "INVALID_REQUEST", "message": "Invalid SOAP request"})
        except RuntimeError:
            return self.fault(502, {"code": "INVALID_UPSTREAM_RESPONSE", "message": "REST response does not match WSDL"}, False)


def make_handler(rest):
    service = Service(rest)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def do_GET(self):
            if self.path not in ("/soap?wsdl", "/?wsdl"):
                self.send_error(404)
                return
            self.reply(200, E.tostring(build_wsdl(), xml_declaration=True, encoding="utf-8"))

        def reply(self, status, data):
            self.send_response(status)
            self.send_header("Content-Type", "text/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != "/soap":
                self.send_error(404)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 65536 or len(self.headers.get_all("Authorization", [])) > 1:
                    raise ValueError()
                status, response = service.handle(self.rfile.read(size), self.headers.get("Authorization"), self.headers.get("SOAPAction"))
            except ValueError:
                status, response = service.fault(400, {"code": "INVALID_REQUEST", "message": "Invalid HTTP envelope"})
            self.reply(status, response)
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rest-url", default=os.getenv("REST_BASE_URL", "http://127.0.0.1:3000/api/v1"))
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", 50053), make_handler(RestClient(args.rest_url)))
    print("SOAP http://127.0.0.1:50053/soap?wsdl", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__": main()
