import math
import os

# Průměr kola 16 cm → obvod ≈ 0,50265 m (viz poznámky k prototypu).
# Přepsat lze env proměnnou, až proběhne kalibrace skutečné dráhy.
WHEEL_CIRCUMFERENCE_M = float(
    os.environ.get("STEVE_WHEEL_CIRCUMFERENCE_M", math.pi * 0.16)
)

DB_PATH = os.environ.get(
    "STEVE_DB", os.path.join(os.path.dirname(__file__), "..", "steve.db")
)

# MicroPython time.ticks_ms() wrapuje na 2^30.
TICKS_PERIOD = 2**30

# Strava OAuth tokeny (vytvoří strava_auth.py). Dokud soubor neexistuje,
# upload se přeskakuje a server jede jen jako sběrač dat.
STRAVA_TOKENS_PATH = os.environ.get(
    "STEVE_STRAVA_TOKENS",
    os.path.join(os.path.dirname(__file__), "..", "strava_tokens.json"),
)

# Detekce konce křeččího dne: ticho aspoň QUIET_HOURS a je ráno
# (MORNING_HOUR–poledne). Poledne je tvrdá pojistka — po něm už den
# nemůže dostat další otáčky.
QUIET_HOURS = 3
MORNING_HOUR = 7

# Jak často background task kontroluje uzavřené dny (sekundy).
UPLOAD_CHECK_S = 600
