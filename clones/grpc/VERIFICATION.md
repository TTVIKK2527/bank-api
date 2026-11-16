# Kontroll — 16.11.2026

## Teostatud

- Kriidi #335, #336 ja #337 täiskirjeldused loetud. Rakendatud on kõik kolm protokolliadapterit.
- Algse bank-api snapshot'i 55 faili taastatud GitHubi commit'ist
  `71978824c030111bd0dc09d9036cfcdba3999eb7`; kõigi failide Git blob SHA-1
  kontrollitud. `.claude/settings.local.json` jäeti teadlikult taastamata.
- `.proto` kompileerimine: `./generate.sh` — PASS.
- `./tests/test.sh` — 13 socket'ita testi PASS; võrguintegratsiooni testiklass SKIP.
  Testid sisaldavad üheksa operatsiooni ja kümne HTTP veastaatuse alamkontrolle.
- Kõik üheksa OpenAPI operatsiooni on kaetud RPC ja kliendi fikstuurinäitega.
- Serveri ja kliendi `--help` ning Python lähtekoodi kompileerimine kontrollitud.

## Kontrollimata

Selle sessiooni sandbox keelab kohalike socket'ite loomise (`PermissionError`).
Seetõttu ei ole serveri päris käivitust, gRPC/HTTP transporti ega kõigi RPC-de
fikstuuridemo käivitust siin õnnestunuks märgitud. Võrgutestid on olemas ja
käivituvad sama testikäsuga keskkonnas, kus socket'id on lubatud.

Päris PostgreSQL/Redis-panga, väliste pankade ja keskserveriga võrdväärsus pole
siin kontrollitud. Fikstuuritestid tõendavad protokolli teisendust, mitte algse
panga äriloogika korrektsust. Adapter kasutab seda loogikat REST gateway kaudu.
Vähemalt päris kohalik käivitus ja arenduspanga smoke-test tuleb enne esitamist teha.

GraphQL #335 ja SOAP #337 on samuti rakendatud; nende eraldi testid ja piirangud on vastavates README failides. Kriidi
kriteeriume ei muudetud, midagi ei esitatud ja individuaalset kaitsmist ei tehtud.

Kohalik Git on taastatud snapshot koos uue lisandiga, mitte GitHubi ajaloo kloon.
Enne PR-i tuleb lisand kanda päris upstream-ajalooga feature-harusse.


## Jätkukontroll kohalikus piiranguteta ülesandes

- Kloonitud päris upstream-ajalugu commit'ini 7197882 ja kantud ainult adapterite
  lisandid feature/protocol-adapters harusse. Taastatud snapshot-rooti ei pushita.
- gRPC: 23 testi PASS, sh kõik 10 varem socket-piirangu tõttu vahele jäetud võrgutesti.
- GraphQL: 8 ühiktesti PASS; SOAP: 6 ühiktesti PASS.
- Ühine HTTP integratsioon: 2 testi PASS, kummaski kõik 9 operatsiooni läbi
  päris kohaliku HTTP-serveri ja sünteetilise REST-fikstuuri; SOAP vastused XSD-ga valideeritud.
- CI workflow lisatud; selle päris tulemus on repositooriumi Actions vaates.
- Need tulemused asendavad ülaltoodud socket-piirangu ja kohaliku Git-ajaloo takistuse.
  Pärispanga PostgreSQL/Redis, keskserveri ja teiste pankadega test ning õppija
  iseseisev kaitsmine jäävad kontrollimata; sünteetilist testmakset ei esitata päris ülekandena.
