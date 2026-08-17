# Steve Server

HTTP server pro křeččí počítadlo: přijímá dávky otáček z ESP8266 (Hall senzor
na kole), ukládá je do SQLite, seskupuje do aktivit (max jedna za křeččí den,
poledne–poledne) a uzavřené dny automaticky posílá jako FIT na Stravu.

## Spuštění

Nasazení na Mac mini (LaunchAgent s KeepAlive, start po přihlášení,
log v `logs/server.log`; opakované spuštění = reinstalace):

```sh
deploy/install.sh
sudo pmset -a sleep 0   # jednorázově: server nesmí v noci spát
```

Ruční spuštění pro vývoj:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Interaktivní dokumentace API: http://localhost:8000/docs

## API

### POST /pulses

ESP posílá dávky relativních časů otáček (`time.ticks_ms()`), server je
přepočte na absolutní čas podle okamžiku přijetí. Duplicitně poslaná dávka
se tiše ignoruje (idempotence přes `boot_id` + `ticks`).

Odpověď nese vše, co ESP potřebuje pro displej: `day` (aktuální křeččí
den) a `latest` — součty posledního dne, který má nějaké otáčky. DIST
a TIME na displeji jsou přímo hodnoty z `latest`; dokud Steve v novém
dni neběžel, ukazuje se tak celá minulá noc a první večerní otáčka
displej přirozeně přepne na nový den. ESP proto posílá dávky i prázdné
(heartbeat) a lokálně počítá jen okamžitou rychlost.

```json
{
  "received": 3,
  "stored": 3,
  "day": "2026-08-16",
  "latest": {
    "day": "2026-08-16",
    "start": "2026-08-16T21:03:11+00:00",
    "end": "2026-08-16T21:04:02+00:00",
    "revolutions": 87,
    "distance_m": 43.7,
    "elapsed_s": 51,
    "moving_time_s": 48,
    "avg_speed_kmh": 3.3,
    "max_speed_kmh": 4.1
  }
}
```

```json
{
  "boot_id": "a3f9",
  "sent_at_ticks": 123456789,
  "pulses_ticks": [123450100, 123450612, 123451098]
}
```

### GET /activities

Impulzy seskupené do aktivit — maximálně jedna za den. Den se láme
v poledne lokálního času, takže noční běhání přes půlnoc je jedna
aktivita. Vrací počet otáček, vzdálenost, elapsed/moving time a rychlosti.

## Strava

Jednorázové nastavení:

1. Založ účet pro křečka a na strava.com/settings/api vytvoř API aplikaci
   (Authorization Callback Domain: `localhost`).
2. Spusť `.venv/bin/python strava_auth.py`, zadej Client ID + Secret
   a v prohlížeči odklikni Authorize. Tokeny se uloží do
   `strava_tokens.json` (gitignorovaný, server si je obnovuje sám).

Server pak každých 10 minut kontroluje uzavřené dny. Den je uzavřený,
když už běží pozdější křeččí den (tvrdá pojistka — po poledni do něj
nemůže nic přibýt), nebo když je ráno (7:00–12:00) a od poslední otáčky
uplynuly aspoň 3 hodiny. Uzavřený neodeslaný den se vygeneruje jako FIT
(indoor ride, record každou sekundu) a nahraje na Stravu; odeslané dny
eviduje tabulka `uploads`, duplicitní upload Strava sama odmítne.

Dokud `strava_tokens.json` neexistuje, server jen sbírá data.

## Konfigurace (env)

- `STEVE_DB` — cesta k SQLite databázi (default `steve.db` v kořeni projektu)
- `STEVE_WHEEL_CIRCUMFERENCE_M` — obvod kola v metrech (default π × 0,16)
- `STEVE_STRAVA_TOKENS` — cesta k souboru s tokeny (default
  `strava_tokens.json` v kořeni projektu)

## Testy

```sh
.venv/bin/pytest
```
