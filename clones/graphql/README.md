# #335 Panga GraphQL teenus

GraphQL SDL ja resolverid katavad olemasoleva REST gateway kõik üheksa avalikku
operatsiooni. Äriloogika ja autentimine jäävad REST gateway sisse. See on olemasoleva
teenuse protokolliadapter; REST-pank peab eraldi töötama. Raha ja ajatempleid
ei teisendata: mõlemad jäävad REST-is kasutatud stringideks. Subscription'eid pole,
sest algne avalik REST-leping ei sisalda reaalaja tellimusi.

## Paigaldamine ja kasutamine

Vaja Python 3.10+ ja olemasolevat REST-panga arenduskeskkonda. IDE-d pole vaja.
Käsud repositooriumi juurkaustast:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r clones/graphql/requirements.txt
REST_BASE_URL=http://127.0.0.1:3000/api/v1 ./clones/graphql/run.sh
```

SDL laaditakse ja valideeritakse käivitamisel. Server kuulab ainult localhost'il,
vaikimisi `http://127.0.0.1:50052/graphql`. Autentimine tuleb HTTP Authorization
päises ja edastatakse muutmata REST gateway'le. Server ei logi tokeneid.

| REST | GraphQL |
|---|---|
| GET /health | Query.health |
| GET /api-docs.json | Query.apiDocs |
| GET /users/{userId} | Query.user(userId) |
| GET /accounts/{accountNumber} | Query.account(accountNumber) |
| GET /transfers/{transferId} | Query.transfer(transferId) |
| POST /users | Mutation.registerUser(input) |
| POST /users/{userId}/accounts | Mutation.createAccount(userId, currency) |
| POST /transfers | Mutation.initiateTransfer(input) |
| POST /transfers/receive | Mutation.receiveTransfer(jwt) |

Kõik objektid ja sisendtüübid on failis `schema/bank.graphql`. OpenAPI dokument
tagastatakse JSON-stringina; ülejäänud vastused on tüübitud objektid. Valikulised
väljundväljad võivad olla null, nagu GraphQL-i leping ette näeb. Vigane päring
annab `errors`; REST-vea korral sisaldab `extensions` algset `code`, `httpStatus`
ja kogu `response` objekti, kaasa arvatud pending-ülekande lisaväljad.

## Näited ja kontrollid

```sh
./clones/graphql/client/example.sh --fixture
./clones/graphql/tests/test.sh
./clones/graphql/client/example.sh --query '{ health { status database timestamp } }'
./clones/graphql/client/example.sh --query 'mutation { registerUser(input:{fullName:"Demo User"}) { userId fullName } }'
```

`--fixture` kutsub kõiki query/mutation välju sünteetilise REST-fikstuuri vastu.
Näidisskript ja testid jagavad naaberprojekti `clones/grpc` lepingufikstuuri ning
REST-kliendi moodulit; hoia kogu repositoorium koos. Kliendinäites on ka
`--variables` tugi. Kaitstud operatsioonide jaoks määra `BANK_AUTHORIZATION` oma
arenduspanga testtokenile; ära lisa tokenit Git-i ega esitatavasse ekraanipilti.

16.11.2026: kaheksa testi PASS, sh üheksa operatsiooni alamkontrollid, kümme
veastaatust, skeemi valideerimine ja introspektsioon. Kontrollid kasutavad
graphql-core 3.2.6 ametlikku lähtekoodi commit'ist
`b7935f75511dde280325631541f4a8a24b245709`; teek ei ole projekti vendordatud.
Testid ei tõenda päris HTTP-serveri käivitust ega ühendust pärispangaga:
käesolev sandbox keelab socket'id. Need kontrollid on enne esitamist veel vajalikud.
Kaitsmine ja Kriiti esitamine on eraldi tegevused.


## Jätkukontroll 16.11.2026 (varasemad socket-piirangud lahendatud)

Lisand on kantud päris upstream Git-ajaloole, algne snapshot-root ei ole avaldamise alus.
`python -m unittest discover -s clones/tests -v` kontrollis kõiki üheksat
GraphQL ja SOAP operatsiooni tegelike kohalike HTTP ühendustega, sh Authorization
päise edastus, XSD valideerimine ning WSDL-i HTTP päring. Mõlemad testid PASS.
Ühiktestid: GraphQL 8 PASS, SOAP 6 PASS; gRPC 23 PASS koos päris võrgutranspordiga.
Sünteetiline REST-fikstuur ei tõenda PostgreSQL/Redis-panga ega väliste pankade
äriloogika tööd. Arenduspanga smoke-test ja individuaalne kaitsmine jäävad eraldi.
