"""Smoke-test adapters against disposable PostgreSQL and the actual upstream services.
Requires built user/account/gateway services and PostgreSQL tools on PATH.
No central bank, external bank, real credentials or real money is used.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
for part in ('grpc/src', 'grpc/tests', 'grpc/generated', 'graphql/src', 'soap/src', 'soap/tests'):
    sys.path.insert(0, str(ROOT / 'clones' / part))
import grpc
import bank_pb2 as pb
import bank_pb2_grpc as rpc
from server import create_server
from bank_graphql import make_handler as graphql_handler
from bank_soap import make_handler as soap_handler
from contract import NS, ENVELOPE
from test_soap import request as soap_request
from upstream import RestClient
from lxml import etree as E


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait_port(port):
    for _ in range(100):
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=.1):
                return
        except OSError:
            time.sleep(.1)
    raise RuntimeError(f'Local service failed to start on {port}')


def main():
    processes, servers, threads = [], [], []
    pg_running = False
    with tempfile.TemporaryDirectory(prefix='bank-smoke-') as folder:
        temp = Path(folder)
        log = (temp / 'services.log').open('w')
        def run(args, **kwargs):
            return subprocess.run(args, check=True, stdout=log, stderr=log, **kwargs)
        try:
            pg_port, user_port, account_port, gateway_port = [free_port() for _ in range(4)]
            pg = temp / 'pg'
            run(['initdb', '-D', str(pg), '-A', 'trust', '-U', 'bank', '--no-locale'])
            run(['pg_ctl', '-D', str(pg), '-l', str(temp / 'pg.log'), '-o',
                 f'-h 127.0.0.1 -p {pg_port} -k {temp}', '-w', 'start'])
            pg_running = True
            db_url = f'postgresql://bank@127.0.0.1:{pg_port}/postgres'
            run(['psql', db_url, '-v', 'ON_ERROR_STOP=1', '-f', str(ROOT / 'init-db.sql')])
            # Exercise the existing-schema upgrade, retaining a pre-existing user.
            run(['psql', db_url, '-v', 'ON_ERROR_STOP=1', '-c',
                 "ALTER TABLE users.api_keys DROP COLUMN expires_at; "
                 "INSERT INTO users.users(id,full_name) VALUES('legacy-check','Legacy Test');"])
            run(['psql', db_url, '-v', 'ON_ERROR_STOP=1', '-f', str(ROOT / 'init-db.sql')])
            check = subprocess.check_output(['psql', db_url, '-Atc',
                "SELECT COUNT(*) FROM users.users WHERE id='legacy-check'"], text=True).strip()
            assert check == '1', 'Schema upgrade must preserve existing users'
            preload = temp / 'loopback.cjs' 
            preload.write_text("const net=require('node:net'); const listen=net.Server.prototype.listen; "
                               "net.Server.prototype.listen=function(...a){if(typeof a[0]==='number' && typeof a[1]!=='string')"
                               "a.splice(1,0,'127.0.0.1'); return listen.apply(this,a);};")
            env = dict(os.environ, DATABASE_URL=db_url,
                       USER_SERVICE_URL=f'http://127.0.0.1:{user_port}',
                       ACCOUNT_SERVICE_URL=f'http://127.0.0.1:{account_port}',
                       BANK_SYNC_SERVICE_URL='http://127.0.0.1:1',
                       TRANSFER_SERVICE_URL='http://127.0.0.1:1')
            for service, port in [('user-service', user_port), ('account-service', account_port),
                                  ('api-gateway', gateway_port)]:
                process = subprocess.Popen(['node', '--require', str(preload), 'dist/index.js'],
                                           cwd=ROOT / 'services' / service,
                                           env=dict(env, PORT=str(port)), stdout=log, stderr=log)
                processes.append(process)
                wait_port(port)
            rest_url = f'http://127.0.0.1:{gateway_port}/api/v1'
            rest = RestClient(rest_url)
            assert rest.request('GET', '/health')['status'] == 'ok'
            grpc_server, port = create_server(rest_url, '127.0.0.1:0')
            grpc_server.start()
            channel = grpc.insecure_channel(f'127.0.0.1:{port}')
            grpc.channel_ready_future(channel).result(timeout=3)
            stub = rpc.BankStub(channel)
            try:
                assert stub.Health(pb.Empty(), timeout=3).database == 'connected'
                json.loads(stub.GetApiDocs(pb.Empty(), timeout=3).json)
                user = stub.RegisterUser(pb.RegisterUserRequest(fullName='Local gRPC Smoke'), timeout=3)
                auth = (('authorization', 'Bearer ' + user.token),)
                assert stub.GetUser(pb.UserRequest(userId=user.userId), metadata=auth, timeout=3).fullName == user.fullName
                account = stub.CreateAccount(pb.CreateAccountRequest(userId=user.userId, currency='EUR'), metadata=auth, timeout=3)
                assert account.balance == '0.00'
                assert stub.LookupAccount(pb.AccountRequest(accountNumber=account.accountNumber), timeout=3).currency == 'EUR'
                print('PASS gRPC: PostgreSQL health, OpenAPI, register, authenticated user/account, public lookup')
            finally:
                channel.close()
                grpc_server.stop(0).wait()
            for handler in (graphql_handler, soap_handler):
                server = ThreadingHTTPServer(('127.0.0.1', 0), handler(rest))
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start(); servers.append(server); threads.append(thread)
            def graphql(query, authorization=None):
                headers = {'Content-Type': 'application/json'}
                if authorization: headers['Authorization'] = authorization
                req = Request(f'http://127.0.0.1:{servers[0].server_port}/graphql',
                              json.dumps({'query': query}).encode(), headers)
                with urlopen(req, timeout=3) as response: result = json.load(response)
                assert 'errors' not in result, 'GraphQL upstream smoke returned errors'
                return result['data']
            assert graphql('{health{database}}')['health']['database'] == 'connected'
            user = graphql('mutation{registerUser(input:{fullName:"Local GraphQL Smoke"}){userId token}}')['registerUser']
            auth = 'Bearer ' + user['token']
            assert graphql('{user(userId:' + json.dumps(user['userId']) + '){userId}}', auth)['user']['userId'] == user['userId']
            account = graphql('mutation{createAccount(userId:' + json.dumps(user['userId']) + ',currency:"EUR"){accountNumber balance}}', auth)['createAccount']
            assert account['balance'] == '0.00'
            assert graphql('{account(accountNumber:' + json.dumps(account['accountNumber']) + '){currency}}')['account']['currency'] == 'EUR'
            print('PASS GraphQL HTTP: PostgreSQL health, register, authenticated user/account, public lookup')
            def soap(name, inputs, authorization=None):
                headers = {'Content-Type': 'text/xml', 'SOAPAction': '"' + NS + '/' + name + '"'}
                if authorization: headers['Authorization'] = authorization
                req = Request(f'http://127.0.0.1:{servers[1].server_port}/soap', soap_request(name, inputs), headers)
                with urlopen(req, timeout=3) as response: wrapper = E.fromstring(response.read()).find('{' + ENVELOPE + '}Body')[0]
                return {E.QName(e).localname: e.text for e in wrapper}
            assert soap('Health', {})['database'] == 'connected'
            user = soap('RegisterUser', {'fullName': 'Local SOAP Smoke'})
            auth = 'Bearer ' + user['token']
            assert soap('GetUser', {'userId': user['userId']}, auth)['userId'] == user['userId']
            account = soap('CreateAccount', {'userId': user['userId'], 'currency': 'EUR'}, auth)
            assert account['balance'] == '0.00'
            assert soap('LookupAccount', {'accountNumber': account['accountNumber']})['currency'] == 'EUR'
            print('PASS SOAP HTTP: PostgreSQL health, register, authenticated user/account, public lookup')
            print('Transfers, Redis retry, central-bank registration and external banks are outside this smoke test.')
        finally:
            for server, thread in zip(servers, threads):
                server.shutdown(); server.server_close(); thread.join(timeout=3)
            for process in reversed(processes):
                process.terminate()
                try: process.wait(timeout=12)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
            if pg_running:
                run(['pg_ctl', '-D', str(temp / 'pg'), '-m', 'immediate', '-w', 'stop'])
            log.close()


if __name__ == '__main__':
    main()
