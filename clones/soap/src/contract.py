"""Single contract definition used to emit a static WSDL and validate XML."""
from pathlib import Path
from lxml import etree as E

NS = "urn:est001:bank:v1"
WSDL = "http://schemas.xmlsoap.org/wsdl/"
XSD = "http://www.w3.org/2001/XMLSchema"
BINDING = "http://schemas.xmlsoap.org/wsdl/soap/"
ENVELOPE = "http://schemas.xmlsoap.org/soap/envelope/"

OPERATIONS = {
    "Health": ([], ["status", "database", "timestamp"]),
    "GetApiDocs": ([], ["json"]),
    "RegisterUser": (["fullName", "email?"], ["userId", "fullName", "email", "createdAt", "token"]),
    "GetUser": (["userId"], ["userId", "fullName", "email", "createdAt"]),
    "CreateAccount": (["userId", "currency"], ["accountNumber", "ownerId", "currency", "balance", "createdAt"]),
    "LookupAccount": (["accountNumber"], ["accountNumber", "ownerName", "currency"]),
    "InitiateTransfer": (["transferId", "sourceAccount", "destinationAccount", "amount"],
                         ["transferId", "status", "sourceAccount", "destinationAccount", "amount", "convertedAmount", "exchangeRate", "rateCapturedAt", "timestamp"]),
    "ReceiveTransfer": (["jwt"], ["transferId", "status", "destinationAccount", "amount", "timestamp"]),
    "GetTransfer": (["transferId"], ["transferId", "status", "sourceAccount", "destinationAccount", "amount", "convertedAmount", "exchangeRate", "rateCapturedAt", "timestamp", "pendingSince", "nextRetryAt", "retryCount", "errorMessage"]),
}


def node(parent, namespace, tag, **attrs):
    return E.SubElement(parent, "{" + namespace + "}" + tag, **attrs)


def build_wsdl():
    root = E.Element("{" + WSDL + "}definitions", nsmap={"wsdl": WSDL, "xsd": XSD, "soap": BINDING, "tns": NS},
                     targetNamespace=NS, name="Bank")
    types = node(root, WSDL, "types")
    schema = node(types, XSD, "schema", targetNamespace=NS, elementFormDefault="qualified")
    for operation, (inputs, outputs) in OPERATIONS.items():
        for name, fields, required in ((operation, inputs, True), (operation + "Response", outputs, False)):
            element = node(schema, XSD, "element", name=name)
            sequence = node(node(element, XSD, "complexType"), XSD, "sequence")
            for field in fields:
                name = field.rstrip("?")
                node(sequence, XSD, "element", name=name, type="xsd:int" if name == "retryCount" else "xsd:string",
                     minOccurs="1" if required and not field.endswith("?") else "0", maxOccurs="1")
    sequence = node(node(node(schema, XSD, "element", name="BankError"), XSD, "complexType"), XSD, "sequence")
    for name, kind in (("httpStatus", "int"), ("code", "string"), ("message", "string"), ("responseJson", "string")):
        node(sequence, XSD, "element", name=name, type="xsd:" + kind)
    for operation in OPERATIONS:
        for suffix, element in (("Request", operation), ("Response", operation + "Response")):
            node(node(root, WSDL, "message", name=operation + suffix), WSDL, "part", name="parameters", element="tns:" + element)
    node(node(root, WSDL, "message", name="BankFault"), WSDL, "part", name="fault", element="tns:BankError")
    port = node(root, WSDL, "portType", name="BankPortType")
    for operation in OPERATIONS:
        op = node(port, WSDL, "operation", name=operation)
        node(op, WSDL, "input", message="tns:" + operation + "Request")
        node(op, WSDL, "output", message="tns:" + operation + "Response")
        node(op, WSDL, "fault", name="BankFault", message="tns:BankFault")
    binding = node(root, WSDL, "binding", name="BankSoapBinding", type="tns:BankPortType")
    node(binding, BINDING, "binding", style="document", transport="http://schemas.xmlsoap.org/soap/http")
    for operation in OPERATIONS:
        op = node(binding, WSDL, "operation", name=operation)
        node(op, BINDING, "operation", soapAction=NS + "/" + operation)
        for direction in ("input", "output"):
            node(node(op, WSDL, direction), BINDING, "body", use="literal")
        node(node(op, WSDL, "fault", name="BankFault"), BINDING, "fault", name="BankFault", use="literal")
    service = node(root, WSDL, "service", name="BankService")
    node(node(service, WSDL, "port", name="BankSoapPort", binding="tns:BankSoapBinding"),
         BINDING, "address", location="http://127.0.0.1:50053/soap")
    return root


def write_wsdl():
    path = Path(__file__).resolve().parents[1] / "wsdl/bank.wsdl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(E.tostring(build_wsdl(), pretty_print=True, xml_declaration=True, encoding="utf-8"))


if __name__ == "__main__":
    write_wsdl()
