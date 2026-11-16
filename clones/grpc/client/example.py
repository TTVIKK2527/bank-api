"""Call every RPC against a local contract fixture, or one RPC on your own dev bank."""
import argparse
import json
import os
import grpc
from google.protobuf.json_format import MessageToDict, ParseDict
import bank_pb2 as pb
import bank_pb2_grpc as rpc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", action="store_true", help="Run all nine RPCs against synthetic local data")
    parser.add_argument("--target", default="127.0.0.1:50051")
    parser.add_argument("--rpc", choices=list(pb.DESCRIPTOR.services_by_name["Bank"].methods_by_name), default="Health")
    parser.add_argument("--data", default="{}", help="Request message as JSON")
    args = parser.parse_args()
    fixture = server = None
    try:
        if args.fixture:
            from fixture import Fixture, CASES
            from server import create_server
            fixture = Fixture().start()
            server, port = create_server(fixture.url, "127.0.0.1:0")
            server.start()
            args.target = "127.0.0.1:" + str(port)
            cases = [(name, inputs) for name, inputs, *_ in CASES]
        else:
            cases = [(args.rpc, json.loads(args.data))]
        with grpc.insecure_channel(args.target) as channel:
            stub = rpc.BankStub(channel)
            metadata = (("authorization", os.environ["BANK_AUTHORIZATION"]),) if os.getenv("BANK_AUTHORIZATION") else ()
            for name, data in cases:
                descriptor = pb.DESCRIPTOR.services_by_name["Bank"].methods_by_name[name]
                request = ParseDict(data, getattr(pb, descriptor.input_type.name)())
                try:
                    response = getattr(stub, name)(request, timeout=5, metadata=metadata)
                    # Do not echo a newly issued bearer token to console logs.
                    output = MessageToDict(response)
                    if "token" in output:
                        output["token"] = "[redacted]"
                    print(name, json.dumps(output, ensure_ascii=False))
                except grpc.RpcError as error:
                    print(name, error.code().name, error.details())
                    raise
    finally:
        if server:
            server.stop(0).wait()
        if fixture:
            fixture.close()


if __name__ == "__main__":
    main()
