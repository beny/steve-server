# Firmware (LoLin NodeMCU V3, ESP8266, MicroPython)

Hall senzor je na D5/GPIO14, OLED SSD1306 na I2C (SCL D1/GPIO5,
SDA D2/GPIO4). Tlačítko FLASH je na GPIO0. Displej je normálně zhasnutý;
stisk FLASH jej rozsvítí na 5 sekund. Další stisk interval obnoví.
Otáčky se zaznamenávají stále, i při zhasnutém displeji.

## Nahrání přes Thonny

1. V `config.py` doplň `WIFI_PASSWORD` pro síť `aLAN`. Soubor je
   gitignorovaný. `SERVER_URL` už míří na `http://macmini.local:8000`.
2. Na ESP nahraj `main.py`, `transport.py`, `config.py` a knihovnu
   `ssd1306.py`.
3. Na Macu spusť server podle hlavního README. Ověř, že Mac a ESP jsou
   ve stejné síti a že port 8000 není blokovaný firewallem.

## Přenos dat

Impulzy se ukládají v RAM do kruhového bufferu (1024 míst) pomocí
přerušení. Každých 20 sekund ESP odešle dávky nejvýše 100 otáček na
`POST /pulses`, včetně prázdného heartbeatu. Opakovaná dávka se na
serveru pozná podle `boot_id` a `ticks` a neuloží se podruhé.

Při výpadku Wi-Fi nebo serveru se odesílání opakuje. Pokud buffer přeteče,
nejstarší neodeslané impulzy se ztratí. Při resetu ESP se buffer v RAM
vyprázdní. Server vrací součty posledního dne s otáčkami; firmware podle
nich po úspěšném přenosu opraví vzdálenost a aktivní čas na displeji.
Mezi přenosy přičítá nově zachycené otáčky lokálně. Den se na serveru
láme v poledne a ESP se při změně dne po odeslání bufferu restartuje,
aby získalo nový `boot_id` před obalením `ticks_ms()`.

Adresa `macmini.local` se překládá přes mDNS. Pokud v konkrétní síti
nefunguje, lze do `SERVER_URL` v `config.py` zadat IP Macu, například
`http://192.168.1.10:8000`.

FLASH nemaže firmware. Při zapnutí nebo resetu jej nedrž stisknuté,
protože tím ESP přejde do režimu nahrávání firmwaru.
