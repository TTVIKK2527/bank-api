# Panga harukontori API liidestused (ÕV3)

Dokument kirjeldab repositooriumi `TTVIKK2527/bank-api` versiooni `3b3f1a0a79f6094dd888252ae83b28c3bd754553` lähtekoodi. Kontrollitud 1. oktoobril 2026. Kirjeldus põhineb teostusel, mitte ainult README näidetel. Käesoleva kontrolli käigus ei käivitatud teenuseid ega tehtud päris ülekandeid; avaliku serveri hetkeseis ei ole kinnitatud.

## 1. Liidestatud süsteemid

- **Kasutajarakendus ja API kliendid:** gateway sisaldab veebilehte (`services/api-gateway/src/public/index.html`); päringuid saab teha ka curl-i, Postmani ja Swagger UI kaudu. Veebileht kasutab suhtelist baasrada `/api/v1` ning salvestab kasutaja tokeni brauseri localStorage'i.
- **API gateway:** Expressi teenus autentib kasutaja, piirab päringuid ja suunab need kasutaja-, konto- või ülekandeteenusele. Docker Compose'i Nginx kasutab TCP stream-proksimist ja jagab ühendusi kolme gateway eksemplari vahel. Väline port on 3000.
- **user-service:** kasutaja registreerimine, juhusliku Bearer tokeni väljastamine ja kasutaja andmed (sisemine port 3001).
- **account-service:** konto loomine, avalik konto otsing ning sisemised saldo-, debiteerimis-, krediteerimis- ja pangasisese ülekande toimingud (3002).
- **transfer-service:** ülekannete algatamine, vastuvõtmine, olek ja korduskatsete töötleja (3003).
- **bank-sync-service:** Keskpanga registreerimine, heartbeat, pankade kataloog, kursid ja ES256 allkirjastamine (3004).
- **PostgreSQL 16:** SQL-liides Node.js `pg` ühenduspuulide kaudu. Skeemid `users`, `accounts`, `transfers` ja `bank_sync` hoiavad kasutajaid, tokeniräsisid, kontosid, ülekandeid, registreeringut ja pankade kataloogi. Rahasummad on `NUMERIC(18,2)`; konto toimingud kasutavad sentide aritmeetikat.
- **Redis 7 ja BullMQ:** pankade/kursi vahemälu, `transfer-retry` tööjärjekord ning korduskatsete ajutised lukud. See ei ole põhiline kontode andmebaas.
- **Keskpanga API:** baas-URL tuleb `CENTRAL_BANK_URL` muutujast; koodi vaikeväärtus on `https://test.diarainfra.com/central-bank`.
- **Teised harukontorid:** aadressid ja avalikud võtmed tulevad Keskpanga kataloogist. Konto esimesed kolm märki määravad panga; konto on kaheksa suurtähtedest/numbritest koosnevat märki.
- **Swagger UI:** gateway avaldab OpenAPI kirjeldusest interaktiivse testimise liidese. See on sama API klient, mitte eraldi andmebaas või autentimisteenus.

## 2. Avalikud integratsioonipunktid

Kohalik API baasrada on `http://localhost:3000/api/v1`. Allpool on täielikud rajad gateway suhtes. README serveriaadress on paigaldusnäide, mitte käesoleva dokumendi tõend serveri töötamise kohta.

| Liides | Teine süsteem | Meetod / vorming | Autentimine | Eesmärk ja oluline käitumine |
| --- | --- | --- | --- | --- |
| `/api/v1/users` | Veebirakendus / API klient → user-service | POST, JSON | Puudub | `fullName`, valikuline `email`; tagastab kasutaja ja toortokeni, 201 |
| `/api/v1/users/{userId}` | API klient → user-service | GET, JSON | Bearer | Kasutaja andmed; omanikukontroll puudub |
| `/api/v1/users/{userId}/accounts` | API klient → account-service | POST, JSON | Bearer + kasutaja vastavus | `currency`; loob nullsaldoga konto, 201 |
| `/api/v1/accounts/{accountNumber}` | API klient / teine pank → account-service | GET, JSON | Puudub | Konto number, omaniku nimi ja valuuta; **saldo ei kuulu vastusesse** |
| `/api/v1/transfers` | API klient → transfer-service | POST, JSON | Bearer + lähtekonto omanikukontroll | Sama endpoint pangasisesele ja pankadevahelisele ülekandele |
| `/api/v1/transfers/{transferId}` | API klient → transfer-service | GET, JSON | Bearer | Ülekande olek; omanikukontroll puudub |
| `/api/v1/transfers/receive` | Teine harukontor → transfer-service | POST, JSON `{jwt}` | Kehtiv panga ES256 JWT päringu kehas | Laekumise vastuvõtmine; ei kasuta kasutaja Bearer tokenit |
| `/health`, `/api/v1/health` | Jälgimine / API klient | GET, JSON | Puudub | Gateway PostgreSQL-ühenduse kontroll: 200 või 503; ei tõenda kõigi teenuste korrasolekut |
| `/api-docs` | Brauser | GET, HTML | Puudub | Swagger UI |
| `/api-docs.json`, `/api/v1/api-docs.json` | Swagger / API klient | GET, JSON | Puudub | OpenAPI kirjeldus |

Ülekande algatamise väljad on `transferId` (UUID), `sourceAccount`, `destinationAccount` ja positiivne kahe komakohaga kümnendstring `amount`. Tegelik valuuta võetakse lähtekontolt; kood ei kasuta kliendi saadetud `currency` välja. Oma pangas erinevate valuutade korral võetakse kurss Keskpangast ning rakendatakse `sihtkurss / lähtekurss`. Toetatud valuutad: EUR, USD, GBP, SEK, LVL ja EEK.

**Saldo küsimine:** avalikku saldoendpoint'i ei ole. Saldo tagastatakse konto loomisel ja sisemisel `GET /internal/accounts/{accountNumber}` liidesel. Avalikku konto otsingut ei tohi dokumenteerida saldo päringuna.

## 3. Keskpanga ja teiste pankade liidesed

Keskpanga rajad lisatakse `CENTRAL_BANK_URL` väärtusele. Nende päringute kood ei lisa Authorization päist ega API võtit.

| Liides | Suund | Meetod | Autentimine teostuses | Eesmärk |
| --- | --- | --- | --- | --- |
| `/api/v1/banks` | bank-sync → Keskpank | POST, JSON | Puudub | Saadab `name`, `address`, `publicKey`; saab `bankId` |
| `/api/v1/banks/{bankId}/heartbeat` | bank-sync → Keskpank | POST, JSON | Puudub | Saadab ajatembli; 410 korral registreerib panga uuesti |
| `/api/v1/banks` | bank-sync → Keskpank | GET, JSON | Puudub | Pankade aadressid ja avalikud võtmed |
| `/api/v1/banks/{bankId}` | bank-sync → Keskpank | GET, JSON | Puudub | Ühe panga värsked andmed, sh võtme uuendamisel |
| `/api/v1/exchange-rates` | bank-sync → Keskpank | GET, JSON | Puudub | Valuutakursid |
| `{bank.address}/accounts/{accountNumber}` | transfer → teine pank | GET, JSON | Puudub | Sihtkonto valuuta otsing; ebaõnnestumisel eeldatakse lähtekonto valuutat |
| `{bank.address}/api/v1/transfers/receive` | transfer → teine pank | POST, JSON `{jwt}` | ES256 JWT kehas | Allkirjastatud laekumise saatmine |

Viimased kaks URL-i on kirjeldatud **täpselt koodi koostatud kujul**. Konto otsing ja laekumine eeldavad erinevat `bank.address` baasraja kuju. Kui kataloogi aadress juba lõpeb `/api/v1`, võib laekumise URL sisaldada topelt `/api/v1`; kui aadress on serveri juur, puudub konto otsingus `/api/v1`. Koostalitlus sõltub teise panga aadressist ja marsruutidest; ühtset normaliseerimist ei ole.

Registreerimisel genereeritakse ES256 võtmepaar ja saadetakse ainult avalik võti. Olemasolev registreering loetakse PostgreSQL-ist. Heartbeat toimub cron-graafiku järgi iga 15 minuti järel ning esimest korda ligikaudu minut pärast heartbeat'i käivitamist. Kataloog sünkroonitakse käivitamisel ja iga viie minuti järel, Redis TTL on üks tund. Kursi vahemälu TTL on kümme minutit, eraldi varuvahemälul 24 tundi. Varuvahemälu kasutatakse erindi korral; Keskpanga mitte-2xx vastus tagastab kohe 503.

## 4. Sisemised integratsioonid ja ülekandevoog

Teenused kasutavad REST-laadseid HTTP GET/POST päringuid ja JSON-i. Gateway edastab kontrollitud identiteedi `x-user-id` päises, konto loomisel ka URL-i kasutaja `x-path-user-id` päises. Kasutaja toortokenit siseteenustele ei edastata. PUT/DELETE avalikke äriliideseid selles versioonis ei ole.

| Sisemine teenus | Liidesed | Kasutaja / eesmärk |
| --- | --- | --- |
| account-service | GET `/internal/accounts/{accountNumber}` | transfer-service: omanik, valuuta ja saldo |
| account-service | POST `/internal/accounts/transfer` | Pangasisene debiteerimine ja krediteerimine ühes SQL-tehingus |
| account-service | POST `/internal/accounts/{accountNumber}/debit`, `/credit` | Väljaminev ülekanne, laekumine ja tagastus |
| account-service | POST `/internal/set-bank-prefix` | bank-sync määrab konto prefiksi; konto teenus küsib seda ka jooksvalt |
| bank-sync-service | GET `/internal/bank-info` | Oma panga ID, prefiks, avalik võti ja aadress |
| bank-sync-service | GET `/internal/banks`, `/internal/banks/{bankId}` | Panga marsruut ja kontrollimise avalik võti; `?fresh=true` sunnib värskendamist |
| bank-sync-service | GET `/internal/exchange-rates`, `/internal/supported-currencies` | Kursid ja toetatud valuutad |
| bank-sync-service | POST `/internal/sign-jwt` | Allkirjastab antud `payload` objekti |
| user-service | GET `/users/{userId}`, `/internal/users/{userId}/name` | Kasutaja olemasolu / nimi; konto teenus kasutab esimest rada |

Pangasisene ülekanne kontrollib lähtekonto omanikku ning sihtkonto olemasolu, arvutab vajadusel teisenduse ja kutsub konto teenuse SQL-tehingut. Kontod lukustatakse `FOR UPDATE` abil ja mõlemad saldod muudetakse ühe tehinguga. Ülekande kirje lisatakse seejärel eraldi teenuse toiminguna.

Pankadevaheline ülekanne leiab kataloogist sihtpanga, proovib saada konto valuutat, debiteerib lähtekonto ja salvestab `pending` kirje neljatunnise aegumisajaga. bank-sync allkirjastab JWT; sihtpanka saadetakse `{jwt}`. Edu korral on olek `completed`. Sihtpanga 5xx või receive-raja 404 (ilma `ACCOUNT_NOT_FOUND` tekstita) liigitub ajutiseks tõrkeks ja vastus on 503 koos `pending` olekuga. Algne tavaline võrgu-erind ei ole selles koodis sama tõrkeklass ning võib minna püsiva vea/tagastuse harusse.

BullMQ korduskatse algab ühe minuti pärast; järgnevad viivitused on 2, 4, 8, 16, 32 ja kuni 60 minutit. Redis `NX` lukk kehtib 300 sekundit. Töötleja kontrollib aegumist; lisaks otsitakse aegunud pending-kirjeid iga minut. Aegumisel või kui järgmine katse ületaks aegumisaja, püütakse raha tagastada ja olekuks määrata `failed_timeout`. Seetõttu ei tähenda neljatunnine aken täpselt nelja tunni järel toimuvat garanteeritud tagastust.

## 5. Autentimine ja turvalisuse reeglid

### Kasutaja token ja ligipääs

Registreerimine loob UUID toortokeni ning salvestab selle SHA-256 räsi tabelisse `users.api_keys`. Gateway räsib `Authorization: Bearer <token>` väärtuse, otsib kasutaja ja kontrollib aegumist. Kood seab tähtajaks ühe aasta; kasutaja token **ei ole JWT**. Token väljastatakse registreerimisvastuses.

Konto loomisel peab URL-i kasutaja vastama tokeni kasutajale. Ülekande algatamisel peab lähtekonto kuuluma talle. Kasutaja andmete ja ülekande oleku lugemisel kontrollitakse ainult tokeni olemasolu/kehtivust, mitte päringu objekti omanikku. Konto avalik otsing avaldab omaniku nime ja valuuta, mitte saldo.

### Pankadevaheline allkiri ja võtme hoidmine

`jose` allkirjastab ES256 (ECDSA P-256) JWT, millel on `iat` ja viieminutiline `exp`. Allkirjastatud andmed on `transferId`, `sourceAccount`, `destinationAccount`, `amount` (teisendatud summa, kui olemas), `sourceBankId`, `destinationBankId` ja `timestamp`. Saatja ei lisa valuutavälja; vastuvõtja kasutab puuduva valuuta korral kirje jaoks EUR-i.

Vastuvõtja loeb algul kontrollimata `sourceBankId` välja ainult võtme leidmiseks, seejärel kontrollib allkirja ja JWT ajatingimusi ES256 algoritmiga. Ebaõnnestumisel proovib ta Keskpangast värsket võtit. Teostus ei kontrolli eraldi `destinationBankId` vastavust oma pangale, kõigi äriväljade skeemi, positiivset summat ega lähtekonto seost allkirjastanud pangaga. TypeScripti tüübiteisendus ei asenda sisendvalideerimist.

Privaatvõti salvestatakse PKCS#8 PEM tekstina PostgreSQL-i veergu `bank_sync.bank_registration.private_key` ning laaditakse bank-sync teenuse mällu. Koodis ei ole selle veeru krüpteerimist, võtmehoidlat ega automaatset võtmerotatsiooni. Privaatvõtit ei saadeta Keskpanka ega avalikku bank-info vastusesse. Andmebaasi ja varukoopiate ligipääs peab olema piiratud; võtmeid ei tohi kopeerida dokumentatsiooni ega logidesse.

### Topeltülekannete vältimine ja piirid

`transferId` on PostgreSQL-i primaarvõti. Algatamise eelkontroll tagastab olemasoleva ID korral 409; vastuvõtt tagastab olemasoleva kirje oleku uuesti ning korduskatseid piirab Redis lukk. Need mehhanismid on olemas, kuid **täielik täpselt-üks-kord garantii puudub**:

- Algatamise eelkontroll ning konto rahaliigutus ja ülekandekirje lisamine on eraldi toimingud; paralleelpäringud või katkestus nende vahel võivad liigutada raha enne ID konflikti avastamist.
- Laekumisel toimub konto krediteerimine enne ülekandekirje lisamist. Paralleelsed sama ID-ga päringud või katkestus võivad põhjustada korduva krediteerimise.
- Aegumise tagastus on eraldi HTTP-kutse. Tingimuslikku olekumuutust ei kontrollita muudetud ridade arvu järgi ning perioodiline aegumiskontroll ei kasuta korduskatse Redis lukku; paralleelne tagastus ei ole välistatud.

### Võrk ja logimine

Sisemistel endpoint'idel ei ole teenustevahelist tokeni-/JWT-/mTLS-kontrolli. Need usaldavad sisevõrku ja päiseid, seega peavad siseteenused jääma klientidele kättesaamatuks. Compose ei avalda nende teenuste porte otse, kuid avaldab PostgreSQL-i hostipordil 5433 ja Redis-e 6380. Failides ei ole tõendit tulemüüri või tootmiskeskkonna ligipääsupiirangute kohta. Gateway juures on HTTP, Nginx konfiguratsioonides TLS lõpetamist ei ole; JWT allkiri ei krüpteeri sisu. Bearer tokenite ja pangaandmete transpordiks on vajalik HTTPS.

Gateway piirang on 100 päringut minutis IP kohta **iga gateway protsessi mälus**, mitte kõigi eksemplaride ühine Redis piirang. `/health` ja `/api-docs` prefiksiga rajad on erandiks; `/api/v1/health` ja `/api/v1/api-docs.json` läbivad piirangu.

Logida ei tohi Authorization päist, toortokeneid, JWT täisteksti, privaatvõtit, ühenduse saladusi, täielikke päringu-/vastusekehi ega põhjendamatult isiku- või kontoandmeid. Kasutada võib sündmuse liiki, HTTP staatust ja vajalikku korrelatsiooni-ID-d. Kood logib ID-sid ja erindeid ning mõnel juhul välise teenuse veateksti; keskset redaktsiooni ei ole, seega pole tundlike andmete eemaldamine garanteeritud. Veebirakenduse localStorage token vajab kaitset brauseris käivituva pahatahtliku skripti eest.

## 6. Vastused ja veakoodid

Ärivead tagastatakse tavaliselt JSON kujul `{code, message}`, mõnel juhul koos ülekandeandmetega. Kõik raamistikutaseme või käsitlemata vead ei ole koodis ühtlustatud.

| HTTP staatus | Näide teostusest |
| --- | --- |
| 200 | Edukas lugemine, laekumine või korduva laekumise olemasolev olek |
| 201 | Kasutaja, konto või edukas algatatud ülekanne |
| 400 | `INVALID_REQUEST`, `SAME_ACCOUNT`, `UNSUPPORTED_CURRENCY`, puuduv JWT või `TRANSFER_FAILED` |
| 401 | Puuduv/vale Bearer token, `TOKEN_EXPIRED`, vigane panga JWT |
| 403 | Konto loomine teisele kasutajale või võõra lähtekonto debiteerimise katse |
| 404 | `USER_NOT_FOUND`, `ACCOUNT_NOT_FOUND`, `TRANSFER_NOT_FOUND` |
| 409 | `DUPLICATE_USER`, `DUPLICATE_TRANSFER`, `TRANSFER_ALREADY_PENDING` |
| 422 | `INSUFFICIENT_FUNDS` |
| 423 | Aegunud ülekande oleku lugemine: `TRANSFER_TIMEOUT` |
| 429 | `RATE_LIMITED` |
| 500 | Teenuse sisemine või autentimise andmebaasiviga |
| 503 | Teenus/Keskpank kättesaamatu, registreering puudub või järjekorda pandud pankadevaheline ülekanne |

Keskpanga heartbeat'i **410** on väljamineva integratsiooni vastus: bank-sync kustutab vana kohaliku registreeringu ning registreerib uuesti.

## 7. Puuduvad või kinnitamata omadused

- `init-db.sql` ei loo `users.api_keys.expires_at` veergu, mida registreerimine ja autentimine kasutavad. Repositooriumist ei leitud seda lisavat migratsiooni. Värske andmebaasi korral ei saa kirjeldatud tokenivoogu selle skeemiga edukalt kasutada; olemasoleva serveri skeem võib olla erinev.
- Avalik saldo lugemine, kontode nimekirja endpoint, eraldi sisselogimine ja tokeni uuendamine/tühistamine ei ole selles teostuses olemas.
- Kasutaja/ülekande lugemise omanikukontroll, täielik laekumise valideerimine, atomaarne idempotentsus, tagastuse korduskindlus, ühine päringupiirang, võtme krüpteerimine ja teenustevaheline autentimine ei ole teostatud eespool kirjeldatud ulatuses.
- Keskpanga 410 järel muutub registreering bank-sync teenuses; cross-bank mooduli puhverdatud oma bankId-d ei tühjendata. Panga ID muutumise korral võib allkirjastatud andmetesse jääda vana ID.
- Päris serveri TLS, tulemüür, andmebaasi migratsioonid, praegune Keskpanga registreering ja edukad pankadevahelised päringud vajavad eraldi käituskeskkonna kontrolli. README varasemad PASS-väited ei ole selle kontrolli uued testitulemused.

## 8. Kontrollitavad lähtefailid

- [Gateway rajad, Swagger ja päringupiirang](services/api-gateway/src/index.ts), [autentimine](services/api-gateway/src/middleware/auth.ts), [proksimine](services/api-gateway/src/proxy.ts), [OpenAPI](services/api-gateway/src/openapi.yaml).
- [Kasutajad ja tokeni väljastamine](services/user-service/src/index.ts), [kontod ja saldotehingud](services/account-service/src/index.ts).
- [Ülekannete rajad](services/transfer-service/src/index.ts), [pankadevaheline saatmine ja JWT kontroll](services/transfer-service/src/cross-bank.ts), [korduskatsed ja tagastus](services/transfer-service/src/retry-worker.ts).
- [Kataloog, kursid ja allkirjastamine](services/bank-sync-service/src/index.ts), [registreerimine](services/bank-sync-service/src/registration.ts), [heartbeat](services/bank-sync-service/src/heartbeat.ts).
- [Andmebaasi algskeem](init-db.sql), [Compose](docker-compose.yml), [Nginx gateway](nginx/api-gateway-lb.conf), [olemasolev API testiskript](test/api.test.sh).

Swagger UI kasutamiseks ava `/api-docs`, registreeri testkasutaja ja sisesta väljastatud token Authorize dialoogi. Seejärel saab proovida lubatud kasutajapäringuid. `transfers/receive` kasutab hoopis allkirjastatud JWT-d kehas. Testimine tuleb teha eraldatud testkeskkonnas, sest registreerimine, konto loomine ja ülekanded muudavad andmeid. Käesolev dokument neid päringuid ei käivitanud.
