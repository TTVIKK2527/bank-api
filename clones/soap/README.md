# #337 Panga SOAP teenus

SOAP 1.1 document/literal teenus kasutab olemasolevat REST gateway'd ja säilitab
selle äriloogika ning autentimise. WSDL sisaldab üheksat operatsiooni, tüübistatud
XSD sisendeid/väljundeid ja BankFault vealepingut. See ei ole iseseisev pank:
REST gateway peab eraldi töötama. SOAP ei pääse otse sisemiste panga teenuste juurde.

## Käivitamine

Vaja Python 3.10+, lxml ja olemasolevat REST-arenduspanka. IDE-d pole vaja.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r clones/soap/requirements.txt
REST_BASE_URL=http://127.0.0.1:3000/api/v1 ./clones/soap/run.sh
```

`run.sh` genereerib WSDL-i ja käivitab serveri ühe käsuga. WSDL on ka
repositooriumis `wsdl/bank.wsdl`; sama kirjelduse loob `src/contract.py`.
Server kuulab localhost'il `http://127.0.0.1:50053/soap`; WSDL asub `/soap?wsdl`.

| REST | SOAP operation | Sisend |
|---|---|---|
| GET /health | Health | tühi |
| GET /api-docs.json | GetApiDocs | tühi |
| POST /users | RegisterUser | fullName, optional email |
| GET /users/{userId} | GetUser | userId |
| POST /users/{userId}/accounts | CreateAccount | userId, currency |
| GET /accounts/{accountNumber} | LookupAccount | accountNumber |
| POST /transfers | InitiateTransfer | transferId, sourceAccount, destinationAccount, amount |
| POST /transfers/receive | ReceiveTransfer | jwt |
| GET /transfers/{transferId} | GetTransfer | transferId |

Sisendid ja väljundid on nimeruumis `urn:est001:bank:v1`. Näiteks `<bank:Health/>`
asub SOAP Envelope'i Body sees; vastus on `<bank:HealthResponse>`, mille lapsed
on `bank:status`, `bank:database` ja `bank:timestamp`. Raha ning ajatempli tüübid
on `xsd:string`; `retryCount` on `xsd:int`. OpenAPI dokument on JSON-string väljas
`json`. Sisendi kohustuslikkus ja väljundväljade järjekord tulevad XSD-st.

## Veahaldus ja autentimine

Authorization HTTP päis edastatakse muutmata REST gateway'le. SOAP päisesse
tokenit dubleerida pole vaja. ReceiveTransfer võtab vastu algse ES256 JWT stringi;
allkirja kontrollib algne pangateenus. Tokenit ei logita ega salvestata.

SOAP Fault annab HTTP 500. `faultcode` on Client sisendi/REST 4xx korral ja Server
REST 5xx korral. `detail/BankError` sisaldab algset `httpStatus`, `code`, `message`
ja `responseJson`. Viimane säilitab ka pending/timeout ülekande lisaväljad.
XML parser ei laadi DTD-sid ega lahenda väliseid üksusi. Puuduvad ja korduvad
sisendväljad ning vale SOAPAction lükatakse tagasi enne REST-päringut.

## Näited ja kontrollid

```sh
./clones/soap/client/example.sh --fixture
./clones/soap/tests/test.sh
./clones/soap/client/example.sh --operation Health
./clones/soap/client/example.sh --operation LookupAccount --data '{"accountNumber":"EST12345"}'
```

`--fixture` kutsub kõiki üheksat operatsiooni sünteetiliste REST vastustega.
Muude operatsioonide sisend on tabelis; kaitstud päringute jaoks määra
`BANK_AUTHORIZATION` enda arenduspanga testtokenile. Testifailid ja REST-klient
on jagatud naaberprojektiga `clones/grpc`, seega hoia repositoorium tervikuna.

16.11.2026: kuus testi PASS, sh üheksa operatsiooni vastavus REST-fikstuurile,
kümme veastaatust, XML/XSD valideerimine, WSDL sõnumiviidete kontroll,
vigase XML-i/DTD/korduvate väljade tõrjumine ning rahastringi täpsus.
WSDL-i pole siin kontrollitud välise WSDL-tööriistaga. Päris HTTP käivitus ja
arenduspanga smoke-test on endiselt tegemata: sandbox keelab socket'id.
Ühik- ja lepingutestid ei asenda neid ega individuaalset kaitsmist.


## Jätkukontroll 16.11.2026 (varasemad socket-piirangud lahendatud)

Lisand on kantud päris upstream Git-ajaloole, algne snapshot-root ei ole avaldamise alus.
`python -m unittest discover -s clones/tests -v` kontrollis kõiki üheksat
GraphQL ja SOAP operatsiooni tegelike kohalike HTTP ühendustega, sh Authorization
päise edastus, XSD valideerimine ning WSDL-i HTTP päring. Mõlemad testid PASS.
Ühiktestid: GraphQL 8 PASS, SOAP 6 PASS; gRPC 23 PASS koos päris võrgutranspordiga.
Sünteetiline REST-fikstuur ei tõenda PostgreSQL/Redis-panga ega väliste pankade
äriloogika tööd. Arenduspanga smoke-test ja individuaalne kaitsmine jäävad eraldi.

WSDL-i sõltumatu kontroll: Zeep 4.3.3 laadis lepingu ning koostas kõigi üheksa
operatsiooni sisendsõnumid edukalt. See kontroll ei saatnud päringuid pärispangale.
