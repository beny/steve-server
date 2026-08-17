# Firmware křeččího čidla — ESP8266 + Hall senzor (D5/GPIO14) + OLED SSD1306 (I2C).
#
# ESP je jen hloupé čidlo: chytá otáčky do kruhového bufferu (IRQ),
# dávkově je posílá serveru a zobrazuje, co mu server vrátí. Lokálně
# počítá jedině okamžitou rychlost. Nemá hodiny ani vlastní denní
# čítače — DIST/TIME jsou součty "latest" dne z odpovědi serveru,
# takže restart ESP o nic nepřijde a den se láme na serveru.

import array
import json
import os
import time

import machine
import network
import ssd1306
import ubinascii
import urequests
from machine import I2C, Pin, disable_irq, enable_irq

import config

OBVOD = 0.50265  # m; jen pro lokální rychlost, vzdálenost počítá server
DEBOUNCE_MS = 100
STOP_GAP_MS = 3000  # bez impulzu → rychlost 0
BUF_SIZE = 1024  # 4 B na otáčku; při přetečení se zahazují nejstarší
CHUNK = 200  # max otáček v jednom POSTu (velký JSON = riziko MemoryError)
HTTP_TIMEOUT_S = 10
DISPLAY_INTERVAL_MS = 500

BOOT_ID = ubinascii.hexlify(os.urandom(3)).decode()

i2c = I2C(scl=Pin(5), sda=Pin(4))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)
hall = Pin(14, Pin.IN, Pin.PULL_UP)

# --- sběr otáček (IRQ) -------------------------------------------------
# V handleru se nesmí alokovat: jen zápis do předalokovaného pole.

buf = array.array("l", (0 for _ in range(BUF_SIZE)))
write_i = 0  # celkem zachycených otáček
read_i = 0  # kolik už bylo odesláno
prev_pulse = 0  # předposlední otáčka (pro rychlost)
last_pulse = -STOP_GAP_MS


def on_pulse(_pin):
    global write_i, prev_pulse, last_pulse
    t = time.ticks_ms()
    if time.ticks_diff(t, last_pulse) < DEBOUNCE_MS:
        return
    prev_pulse = last_pulse
    last_pulse = t
    buf[write_i % BUF_SIZE] = t
    write_i += 1


hall.irq(trigger=Pin.IRQ_FALLING, handler=on_pulse)

# --- stav displeje (plní se z odpovědí serveru) ------------------------

latest_distance_m = 0.0
latest_elapsed_s = 0
latest_received = time.ticks_ms()
server_day = None


def current_speed_kmh():
    if time.ticks_diff(time.ticks_ms(), last_pulse) > STOP_GAP_MS:
        return 0.0
    gap = time.ticks_diff(last_pulse, prev_pulse)
    if gap <= 0:
        return 0.0
    return OBVOD / (gap / 1000) * 3.6


def displayed_time_s():
    # mezi odpověďmi serveru čas dotikává lokálně, ale jen když Steve
    # běží (server počítá elapsed jen po poslední otáčku dne)
    extra = 0
    if current_speed_kmh() > 0:
        extra = time.ticks_diff(time.ticks_ms(), latest_received) // 1000
    return latest_elapsed_s + extra


# --- odesílání ---------------------------------------------------------


def _post(body):
    data = json.dumps(body)
    headers = {"Content-Type": "application/json"}
    url = config.SERVER_URL + "/pulses"
    try:
        return urequests.post(url, data=data, headers=headers, timeout=HTTP_TIMEOUT_S)
    except TypeError:  # starší urequests bez podpory timeoutu
        return urequests.post(url, data=data, headers=headers)


def _send_chunk():
    """Pošle jednu dávku (max CHUNK otáček). Vrací (úspěch, zbývá_něco)."""
    global read_i, latest_distance_m, latest_elapsed_s, latest_received, server_day

    state = disable_irq()
    n = write_i
    enable_irq(state)

    if n - read_i > BUF_SIZE:  # přetečení: nejstarší už jsou přepsané
        read_i = n - BUF_SIZE

    count = min(n - read_i, CHUNK)
    ticks_list = [buf[i % BUF_SIZE] for i in range(read_i, read_i + count)]

    resp = None
    try:
        resp = _post({
            "boot_id": BOOT_ID,
            "sent_at_ticks": time.ticks_ms(),
            "pulses_ticks": ticks_list,
        })
        if resp.status_code != 200:
            return False, True
        read_i += count
        data = resp.json()
    except OSError:
        return False, True  # server/WiFi nedostupné — buffer drží
    finally:
        if resp:
            resp.close()

    latest = data.get("latest")
    if latest:
        latest_distance_m = latest["distance_m"]
        latest_elapsed_s = latest["elapsed_s"]
    else:
        latest_distance_m = 0.0
        latest_elapsed_s = 0
    latest_received = time.ticks_ms()

    if server_day is None:
        server_day = data.get("day")
    elif data.get("day") != server_day and read_i == write_i:
        # Nový křeččí den a všechno odesláno → jednou denně restart.
        # ticks_ms() wrapuje po ~12 dnech a hodnoty by kolidovaly
        # s dedup klíčem (boot_id, ticks) na serveru; denní reboot
        # (v poledne, kdy Steve spí) dá čerstvý boot_id i ticks.
        machine.reset()

    return True, read_i < write_i


def send_batch():
    """Odešle vše nasbírané, po chunkách. Končí při chybě nebo prázdnu."""
    while True:
        ok, remaining = _send_chunk()
        if not ok or not remaining:
            return ok


# --- WiFi --------------------------------------------------------------


def wifi_connect():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return
    oled.fill(0)
    oled.text("WiFi...", 0, 28)
    oled.show()
    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
    while not wlan.isconnected():
        time.sleep_ms(200)


# --- displej (layout z prototypu: DIST | TIME nahoře, SPEED velkym) ----


def velky_text(text, x, y, scale=3):
    import framebuf

    width = len(text) * 8
    buffer = bytearray(width * 8 // 8)
    fb = framebuf.FrameBuffer(buffer, width, 8, framebuf.MONO_HLSB)
    fb.fill(0)
    fb.text(text, 0, 0, 1)
    for py in range(8):
        for px in range(width):
            if fb.pixel(px, py):
                oled.fill_rect(x + px * scale, y + py * scale, scale, scale, 1)


def format_cas(sekundy):
    hodiny = sekundy // 3600
    minuty = (sekundy % 3600) // 60
    sekundy = sekundy % 60
    if hodiny > 0:
        return "{}:{:02d}:{:02d}".format(hodiny, minuty, sekundy)
    return "{:02d}:{:02d}".format(minuty, sekundy)


def zobraz():
    oled.fill(0)

    if latest_distance_m < 1000:
        vzdalenost = "{:.1f}m".format(latest_distance_m)
    else:
        vzdalenost = "{:.2f}km".format(latest_distance_m / 1000)

    oled.text("DIST", 0, 0)
    oled.text(vzdalenost, 0, 10)
    oled.vline(63, 0, 22, 1)

    cas_text = format_cas(displayed_time_s())
    oled.text("TIME", 128 - 4 * 8, 0)
    oled.text(cas_text, 128 - len(cas_text) * 8, 10)

    oled.hline(0, 22, 128, 1)
    oled.text("SPEED", 0, 27)

    speed_text = "{:.1f}".format(current_speed_kmh())
    sirka_speed = len(speed_text) * 8 * 3
    x = (128 - (sirka_speed + 4 + 4 * 8)) // 2
    if x < 0:
        x = 0
    velky_text(speed_text, x, 38)
    oled.text("km/h", x + sirka_speed + 4, 54)

    oled.show()


# --- hlavní smyčka -----------------------------------------------------

wifi_connect()
send_batch()  # hned po startu si vyžádat "latest" pro displej
zobraz()

posledni_zobrazeni = 0
posledni_odeslani = time.ticks_ms()

while True:
    ted = time.ticks_ms()

    if time.ticks_diff(ted, posledni_odeslani) >= config.SEND_INTERVAL_MS:
        posledni_odeslani = ted
        wifi_connect()
        send_batch()

    if time.ticks_diff(ted, posledni_zobrazeni) >= DISPLAY_INTERVAL_MS:
        posledni_zobrazeni = ted
        zobraz()

    time.sleep_ms(50)
