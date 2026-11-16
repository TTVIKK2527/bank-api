import argparse
import json
import os
import urllib.request
from lxml import etree as E
from contract import NS, ENVELOPE, OPERATIONS
from bank_soap import Service
from fixture import CASES
from test_soap import request, Rest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--operation", choices=list(OPERATIONS), default="Health")
    parser.add_argument("--data", default="{}")
    args = parser.parse_args()
    cases = [(name, inputs, expected) for name, inputs, _, _, _, expected in CASES] if args.fixture else [(args.operation, json.loads(args.data), None)]
    for name, inputs, expected in cases:
        raw = request(name, inputs)
        if args.fixture:
            status, response = Service(Rest(expected)).handle(raw)
        else:
            headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '"'+NS+"/"+name+'"'}
            if os.getenv("BANK_AUTHORIZATION"): headers["Authorization"] = os.environ["BANK_AUTHORIZATION"]
            with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:50053/soap", raw, headers), timeout=10) as reply:
                status, response = reply.status, reply.read()
        if status != 200: raise RuntimeError(response.decode())
        root = E.fromstring(response)
        for element in root.findall(".//{"+NS+"}token"): element.text = "[redacted]"
        print(name, E.tostring(root, encoding="unicode"))


if __name__ == "__main__": main()
