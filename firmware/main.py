import array
import os
import ubinascii
import machine
from machine import Pin, I2C, disable_irq, enable_irq
import ssd1306
import framebuf
import time
import math
import config
import transport


# ============================================================
# HARDWARE
# ============================================================

# OLED:
# D1 = GPIO5 = SCL
# D2 = GPIO4 = SDA

i2c = I2C(
    scl=Pin(5),
    sda=Pin(4)
)

oled = ssd1306.SSD1306_I2C(128, 64, i2c)


# Hall senzor:
# D5 = GPIO14

hall = Pin(14, Pin.IN, Pin.PULL_UP)

# Tlačítko FLASH na LoLin NodeMCU V3 (stisk = 0).
tlacitko = Pin(0, Pin.IN, Pin.PULL_UP)
DOBA_DISPLEJE_MS = 5000

# IRQ sbírá impulzy i během čekání na Wi-Fi/server.
DEBOUNCE_MS = 100
BUF_SIZE = 1024
CHUNK_SIZE = 100
boot_id = ubinascii.hexlify(os.urandom(6)).decode()
buf = array.array("I", (0 for _ in range(BUF_SIZE)))
write_i = 0
read_i = 0
processed_i = 0
last_irq_pulse = time.ticks_add(time.ticks_ms(), -DEBOUNCE_MS)


def on_pulse(_pin):
    global write_i, last_irq_pulse
    pulse_at = time.ticks_ms()
    if time.ticks_diff(pulse_at, last_irq_pulse) < DEBOUNCE_MS:
        return
    last_irq_pulse = pulse_at
    buf[write_i % BUF_SIZE] = pulse_at
    write_i += 1


hall.irq(trigger=Pin.IRQ_FALLING, handler=on_pulse)


# ============================================================
# KOLO
# ============================================================

# Prumer kola = 16 cm
PRUMER = 0.16

# Obvod kola v metrech
OBVOD = math.pi * PRUMER


# ============================================================
# PROMENNE
# ============================================================

pocet_otacek = 0

# Cas posledniho prujezdu magnetu
posledni_otacka = None

# Cas zacatku aktualniho useku behu
start_behu = None

# Celkovy aktivni cas v ms
aktivni_cas = 0

# Bezi kresek prave ted?
bezi = False

# Aktualni rychlost v km/h
rychlost = 0.0

# Cas posledniho prekresleni displeje
posledni_update_displeje = 0
predchozi_stav_tlacitka = tlacitko.value()
displej_sviti = False
zhasnout_v = 0
posledni_stisk = time.ticks_add(time.ticks_ms(), -50)
posledni_odeslani = time.ticks_ms()
server_day = None


# ============================================================
# VELKY TEXT
# ============================================================

def velky_text(text, x, y, scale=2):

    width = len(text) * 8
    height = 8

    buffer = bytearray(width * height // 8)

    fb = framebuf.FrameBuffer(
        buffer,
        width,
        height,
        framebuf.MONO_HLSB
    )

    fb.fill(0)
    fb.text(text, 0, 0, 1)

    for py in range(height):

        for px in range(width):

            if fb.pixel(px, py):

                oled.fill_rect(
                    x + px * scale,
                    y + py * scale,
                    scale,
                    scale,
                    1
                )


# ============================================================
# FORMAT CASU
# ============================================================

def format_cas(ms):

    celkem_sekund = ms // 1000

    hodiny = celkem_sekund // 3600
    minuty = (celkem_sekund % 3600) // 60
    sekundy = celkem_sekund % 60

    if hodiny > 0:

        return "{}:{:02d}:{:02d}".format(
            hodiny,
            minuty,
            sekundy
        )

    else:

        return "{:02d}:{:02d}".format(
            minuty,
            sekundy
        )


# ============================================================
# AKTUALNI AKTIVNI CAS
# ============================================================

def ziskej_aktivni_cas():

    if bezi and start_behu is not None:

        return aktivni_cas + time.ticks_diff(posledni_otacka, start_behu)

    return aktivni_cas


def registruj_otacku(pulse_at):
    global pocet_otacek, posledni_otacka, start_behu
    global aktivni_cas, bezi, rychlost

    if posledni_otacka is not None:
        gap = time.ticks_diff(pulse_at, posledni_otacka)
        if gap > 3000:
            if bezi:
                aktivni_cas += time.ticks_diff(posledni_otacka, start_behu)
            bezi = False
            rychlost = 0.0
        elif gap > 0:
            rychlost = OBVOD / (gap / 1000) * 3.6

    if not bezi:
        bezi = True
        start_behu = pulse_at

    pocet_otacek += 1
    posledni_otacka = pulse_at


def odesli_davky():
    global read_i, processed_i, pocet_otacek, aktivni_cas, start_behu, server_day

    reply = None
    while True:
        state = disable_irq()
        available = write_i
        enable_irq(state)

        if available - read_i > BUF_SIZE:
            read_i = available - BUF_SIZE

        count = min(available - read_i, CHUNK_SIZE)
        pulses = [buf[i % BUF_SIZE] for i in range(read_i, read_i + count)]
        reply = transport.post_pulses({
            "boot_id": boot_id,
            "sent_at_ticks": time.ticks_ms(),
            "pulses_ticks": pulses,
        })
        if reply is None:
            return

        read_i += count
        if read_i >= write_i:
            break

    # Impulzy zachycené během HTTP dosud nebyly promítnuty do lokálního
    # stavu. Zpracujeme je před synchronizací se součty serveru.
    if read_i - processed_i > BUF_SIZE:
        processed_i = read_i - BUF_SIZE
    while processed_i < read_i:
        registruj_otacku(buf[processed_i % BUF_SIZE])
        processed_i += 1

    latest = reply.get("latest")
    if latest:
        pocet_otacek = latest["revolutions"]
        aktivni_cas = latest["moving_time_s"] * 1000
        if bezi:
            start_behu = posledni_otacka

    day = reply.get("day")
    if server_day is None:
        server_day = day
    elif day != server_day and read_i == write_i:
        # Nový den: reset dá nové boot_id před obalením ticks_ms.
        machine.reset()


# ============================================================
# ZOBRAZENI DISPLEJE
# ============================================================

def zobraz():

    oled.fill(0)


    # ========================================================
    # VZDALENOST
    # ========================================================

    metry = pocet_otacek * OBVOD

    if metry < 1000:

        vzdalenost = "{:.1f}m".format(
            metry
        )

    else:

        vzdalenost = "{:.2f}km".format(
            metry / 1000
        )


    # ========================================================
    # CAS
    # ========================================================

    cas_text = format_cas(
        ziskej_aktivni_cas()
    )


    # ========================================================
    # LEVE HORNI POLE - SPEED
    # ========================================================

    oled.text(
        "SPEED",
        0,
        0
    )

    speed_small = "{:.1f}".format(
        rychlost
    )

    oled.text(
        speed_small,
        0,
        10
    )


    # ========================================================
    # VERTIKALNI CARA
    # ========================================================

    oled.vline(
        63,
        0,
        22,
        1
    )


    # ========================================================
    # PRAVE HORNI POLE - TIME
    # ========================================================

    time_label = "TIME"

    sirka_time = len(time_label) * 8

    oled.text(
        time_label,
        128 - sirka_time,
        0
    )

    sirka_casu = len(cas_text) * 8

    oled.text(
        cas_text,
        128 - sirka_casu,
        10
    )


    # ========================================================
    # HORIZONTALNI CARA
    # ========================================================

    oled.hline(
        0,
        22,
        128,
        1
    )


    # ========================================================
    # DIST
    # ========================================================

    oled.text(
        "DIST",
        0,
        27
    )


    # ========================================================
    # VELKA VZDALENOST
    # ========================================================

    scale = 3

    sirka_dist = (
        len(vzdalenost)
        * 8
        * scale
    )

    x = (
        128 - sirka_dist
    ) // 2

    # Pokud je text moc dlouhy, zmensime ho
    if x < 0:

        scale = 2

        sirka_dist = (
            len(vzdalenost)
            * 8
            * scale
        )

        x = (
            128 - sirka_dist
        ) // 2

    if x < 0:
        x = 0

    velky_text(
        vzdalenost,
        x,
        38,
        scale
    )


    oled.show()


# ============================================================
# START
# ============================================================

print("Start programu")

print(
    "Obvod kola:",
    OBVOD,
    "m"
)

print(
    "I2C:",
    i2c.scan()
)

oled.poweroff()
odesli_davky()  # prázdný heartbeat načte součty po restartu


# ============================================================
# HLAVNI SMYCKA
# ============================================================

while True:

    ted = time.ticks_ms()

    stav_tlacitka = tlacitko.value()

    if (predchozi_stav_tlacitka == 1 and stav_tlacitka == 0
            and time.ticks_diff(ted, posledni_stisk) >= 50):
        posledni_stisk = ted
        zhasnout_v = time.ticks_add(ted, DOBA_DISPLEJE_MS)
        if not displej_sviti:
            oled.poweron()
            displej_sviti = True
        zobraz()

    predchozi_stav_tlacitka = stav_tlacitka

    if displej_sviti and time.ticks_diff(ted, zhasnout_v) >= 0:
        oled.poweroff()
        displej_sviti = False


    # Zpracování otáček nasbíraných přerušením, včetně času během HTTP.
    state = disable_irq()
    available = write_i
    enable_irq(state)
    if available - processed_i > BUF_SIZE:
        processed_i = available - BUF_SIZE
    while processed_i < available:
        registruj_otacku(buf[processed_i % BUF_SIZE])
        processed_i += 1


    # ========================================================
    # DETEKCE ZASTAVENI
    # ============================================================

    if bezi and posledni_otacka is not None:

        bez_impulsu = time.ticks_diff(
            ted,
            posledni_otacka
        )

        # 3 sekundy bez otacky = kresek prestal bezet

        if bez_impulsu > 3000:

            rychlost = 0.0

            # Zapocitame cas pouze do POSLEDNI otacky.
            # Tedy nezapocitame 3 sekundy cekani.

            aktivni_cas += time.ticks_diff(
                posledni_otacka,
                start_behu
            )

            bezi = False
            start_behu = None

    # Během pěti sekund svícení se neblokujeme síťovým požadavkem.
    if (not displej_sviti
            and time.ticks_diff(ted, posledni_odeslani) >= config.SEND_INTERVAL_MS):
        posledni_odeslani = ted
        odesli_davky()


    # ========================================================
    # AKTUALIZACE DISPLEJE
    # ========================================================

    if displej_sviti and time.ticks_diff(
        ted,
        posledni_update_displeje
    ) >= 500:

        posledni_update_displeje = ted

        zobraz()


    time.sleep_ms(5)
