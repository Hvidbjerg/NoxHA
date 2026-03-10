from homeassistant.const import Platform

DOMAIN = "noxha"
PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

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
