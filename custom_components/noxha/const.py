from homeassistant.const import Platform

DOMAIN = "noxha"
PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

# Traffic shaping: single events sendes straks, burst-opdateringer throttles.
BULK_WINDOW_SECONDS = 1.0
BULK_MESSAGE_THRESHOLD = 25
BULK_COOLDOWN_SECONDS = 2.0
BULK_FLUSH_INTERVAL = 0.2
BULK_FLUSH_MAX_ITEMS = 20

PREFIX_INPUT = "INP"
PREFIX_OUTPUT = "OUT"
PREFIX_AREA = "AREA"

# Mapping af Alarm Typer ($T)
ALARM_TYPES = {
    "0": "Ingen",
    "1": "Indbrud",
    "2": "Brand",
    "3": "Overfald"
}
