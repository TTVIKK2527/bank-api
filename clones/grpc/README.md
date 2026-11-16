# #336 — olemasoleva panga REST API gRPC-liides

See projekt lisab olemasolevale EST001 panga API-le tüübitud Protobuf/gRPC-liidese.
Äriloogika jääb algsesse REST-teenusesse: gRPC adapter edastab päringud avalikule
API gateway'le, mitte sisemistele teenustele. Nii säilivad autentimine, kontoomandi
kontroll, raha täpsus, valuutavahetus, korduvate maksete kontroll ja retry-töövoog.
Adapter vajab töötavat algset REST-teenust; see pole iseseisev panga uusimplementatsioon.

## Käivitamine

Vaja on Python 3.10+ ja töötavat kohalikku REST-arenduskeskkonda. IDE-d pole vaja.
Python 3.14, grpcio/grpcio-tools 1.84.0 ja protobuf 7.36.1 korral kontrollitud.

```sh
cd clones/grpc
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
REST_BASE_URL=http://127.0.0.1:3000/api/v1 ./run.sh
```

`run.sh` kompileerib `proto/bank.proto` faili ja käivitab serveri ühe käsuga.
Algse REST-panga seadistus on repositooriumi juurkausta README-s. Adapter ei käivita
automaatselt selle andmebaase, keskserverit ega väliseid panku.
Vaikimisi kuulab server ainult `127.0.0.1:50051`. Kõik katsetused tee enda
arenduspanga testandmetega; automaattestid ei pöördu avaliku panga poole.

## REST → RPC kaardistus

Kõik teed on suhtelised `REST_BASE_URL` väärtuse suhtes.

| REST | RPC | Sisend | Väljund |
|---|---|---|---|
| GET /health | Health | Empty | HealthResponse |
| GET /api-docs.json | GetApiDocs | Empty | ApiDocsResponse |
| POST /users | RegisterUser | fullName, optional email | User koos tokeniga |
| GET /users/{userId} | GetUser | userId | User |
| POST /users/{userId}/accounts | CreateAccount | userId, currency | Account |
| GET /accounts/{accountNumber} | LookupAccount | accountNumber | AccountLookup |
| POST /transfers | InitiateTransfer | transferId, sourceAccount, destinationAccount, amount | Transfer |
| POST /transfers/receive | ReceiveTransfer | jwt | Transfer |
| GET /transfers/{transferId} | GetTransfer | transferId | Transfer |

Gateway pakub tervise- ja OpenAPI-päringuid ka ilma `/api/v1` prefiksita; need on
samade operatsioonide aliasteed. Swagger UI ja staatilised HTML-failid on
dokumentatsiooni kasutajaliides, mitte täiendavad pangaoperatsioonid.
Sisemised `/internal/*` marsruudid ei kuulu avalikku lepingusse.

Protobuf-sõnumites on rahasummad ja kursid stringid, täpselt nagu REST-is.
Ajatemplid jäävad ISO 8601 stringideks, ID-d stringideks. Valikulistel väljadel on
`optional`, et eristada puuduvat väärtust tühjast stringist või nullist erinevast
loendurist. Valuutakood on string, et algne REST saaks otsustada kehtivuse üle.
OpenAPI dokument liigub JSON-stringina; panga domeeni vastused on tüübitud.

## Autentimine ja vead

REST-i `Authorization: Bearer ...` päis tuleb gRPC `authorization` metadata kaudu.
Tokenit ei salvestata serveris ega kirjutata logisse. Adapter ei lisa `x-user-id`
päist ega möödu gateway autentimisest. Kontonumbri avalik päring ja registreerimine
jäävad avalikuks; pankadevaheline vastuvõtt kasutab algse API allkirjastatud JWT-d.

| HTTP | gRPC status |
|---|---|
| 400 | INVALID_ARGUMENT |
| 401 | UNAUTHENTICATED |
| 403 | PERMISSION_DENIED |
| 404 | NOT_FOUND |
| 409 | ALREADY_EXISTS |
| 422, 423 | FAILED_PRECONDITION |
| 429 | RESOURCE_EXHAUSTED |
| 502, 503 | UNAVAILABLE |
| 504 / adapteri timeout | DEADLINE_EXCEEDED |
| muu viga, sh 500 | INTERNAL |

`details` sisaldab algset veateadet. Trailing metadata `bank-error-bin` sisaldab
`BankError` Protobuf-sõnumit: algne HTTP staatus, kood, teade ja kogu JSON-vastus.
See säilitab ka 503 pending-ülekande ID ning 423 timeout-ülekande lisaväljad.
Kliendi tähtaeg piirab REST-päringu kestust; adapter ei korda maksepäringut ise.

## Klient ja testid

```sh
./client/example.sh --fixture
./tests/test.sh
```

`--fixture` käivitab ajutise kohaliku HTTP-lepingufikstuuri ja gRPC-serveri, kutsub
kõiki üheksat RPC-d ning sulgeb mõlemad. Fikstuuris on ainult sünteetilised andmed;
see ei tõenda algse panga andmebaasi, JWT-allkirjastamise ega retry-loogika tööd.

Töötava enda arenduspanga adapteri vastu:

```sh
./client/example.sh --rpc Health
./client/example.sh --rpc RegisterUser --data '{"fullName":"Demo User"}'
./client/example.sh --rpc LookupAccount --data '{"accountNumber":"EST12345"}'
# Kaitstud RPC jaoks sea BANK_AUTHORIZATION oma testtokenile.
./client/example.sh --rpc GetUser --data '{"userId":"user-example"}'
```

Muud RPC-d kasutavad kaardistustabeli sisendvälju ja sama `--rpc` / `--data`
vormingut. RegisterUser klient peidab väljastatud tokeni konsooliväljundis.

Testikomplekt sisaldab päris HTTP/gRPC ühendusega võrdlust ja socket'ita kontrolle.
Need kontrollivad kõigi RPC-de päringuid/vastuseid, Protobuf serialiseerimist,
autentimise edastust, kümmet HTTP veastaatust, täpseid summasid, puuduvate
valikuliste väljade käsitlust ning ID-de URL-kodeerimist. Kohalikke socket'eid
keelavas keskkonnas märgitakse võrguintegratsiooni klass selgelt SKIP-iks.
Ära tõlgenda seda täidetud võrguintegratsiooni või pärispanga võrdlustestina.

## Kontrollitud seis ja kaitsmine

Vaata [VERIFICATION.md](VERIFICATION.md). Valmis kood ei asenda individuaalset kaitsmist.
Ole valmis selgitama metadata ja HTTP päise seost, `.proto` lepingut,
rahastringide põhjust, gRPC veastaatusi ning pending-vastuse lisaväljade säilitamist.
Harjutus: lisa kliendi soovil uus tüübitud valikuline väljundväli ning testi
seda nii Protobuf-serialiseerimise kui ka REST-vastuse teisenduse kaudu.

Algse lähtekoodi snapshot on GitHubi commit'ist
`71978824c030111bd0dc09d9036cfcdba3999eb7`. Kohalik algcommit tähistab snapshot'i
taastamist, mitte algse Git-ajaloo koopiat. gRPC lisand on tehtud Codexi poolt;
iseseisvat kaitsmist, Kriiti esitamist ega õpetaja kinnitust ei ole väidetud.
