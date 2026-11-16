"""Exercise every query/mutation with synthetic data or a local development endpoint."""
import argparse
import json
import os
import urllib.request
from bank_graphql import create_schema, execute
from fixture import CASES
from test_graphql import QUERIES, FIELDS, Rest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", action="store_true", help="No network; execute all operations on deterministic REST fixtures")
    parser.add_argument("--endpoint", default="http://127.0.0.1:50052/graphql")
    parser.add_argument("--query", default="{ health { status database timestamp } }")
    parser.add_argument("--variables", default="{}")
    args = parser.parse_args()
    if args.fixture:
        schema = create_schema()
        for index, (_, inputs, _, _, _, expected) in enumerate(CASES):
            variables = {"x": inputs} if index in (2, 6) else inputs
            output = execute(schema, {"query": QUERIES[index], "variables": variables}, Rest(expected))
            if "errors" in output:
                raise RuntimeError(output["errors"])
            if FIELDS[index] == "registerUser":
                output["data"]["registerUser"]["token"] = "[redacted]"
            print(FIELDS[index], json.dumps(output, ensure_ascii=False))
    else:
        headers = {"Content-Type": "application/json"}
        if os.getenv("BANK_AUTHORIZATION"):
            headers["Authorization"] = os.environ["BANK_AUTHORIZATION"]
        payload = json.dumps({"query": args.query, "variables": json.loads(args.variables)}).encode()
        with urllib.request.urlopen(urllib.request.Request(args.endpoint, payload, headers), timeout=10) as response:
            result = json.load(response)
        if result.get("data", {}).get("registerUser"):
            result["data"]["registerUser"].pop("token", None)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
