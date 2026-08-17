# Firmware (ESP8266, MicroPython)

Čidlo otáček křeččího kola: Hall senzor na D5/GPIO14, OLED SSD1306 na
I2C (SCL D1/GPIO5, SDA D2/GPIO4). Otáčky chytá interrupt do kruhového
bufferu v RAM a každých 20 s je dávkou posílá serveru (i prázdnou —
heartbeat). DIST/TIME na displeji jsou součty ze serverové odpovědi
(`latest`), lokálně se počítá jen okamžitá rychlost.

## Nahrání (Thonny)

1. `cp config.example.py config.py` a doplň WiFi + adresu serveru.
2. Do ESP nahraj `main.py`, `config.py` a knihovnu `ssd1306.py`.
3. Ověř, že firmware MicroPythonu obsahuje `urequests` (novější buildy
   pro ESP8266 ano); případně doinstaluj přes mip/Thonny.

## Chování

- Reset displeje neřídí ESP: čísla se přepnou, jakmile server po první
  otáčce nového křeččího dne (láme se v poledne) vrátí nové součty.
  Do té doby displej ukazuje celou minulou noc.
- Výpadek serveru/WiFi: otáčky se hromadí v bufferu (1024 míst,
  při přetečení se zahazují nejstarší) a doručí se, až spojení naskočí.
  Odesílá se po chunkách max 200 otáček (velký JSON by na fragmentované
  haldě ESP8266 mohl spadnout na MemoryError).
- Restart ESP: buffer je v RAM, pár neodeslaných sekund se ztratí;
  displej se obnoví z první odpovědi serveru.
- ESP se jednou denně samo restartuje (při změně křeččího dne, když je
  buffer odeslaný — tedy v poledne, kdy Steve spí). Důvod: ticks_ms()
  wrapuje po ~12 dnech a hodnoty by kolidovaly s dedup klíčem
  (boot_id, ticks) na serveru; denní reboot dá čerstvý boot_id.
- HTTP požadavky mají 10s timeout (pokud ho build urequests umí),
  aby viset server neblokoval smyčku donekonečna.
