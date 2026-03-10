import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, PLATFORMS, PREFIX_INPUT, PREFIX_OUTPUT, PREFIX_AREA

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Sæt NOX integrationen op fra en config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    # Opret klient-instansen
    client = NoxTcpClient(hass, host, port, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client

    # Start TCP-klienten som en baggrundsopgave
    entry.async_create_background_task(
        hass, client.async_run(), "nox_tcp_client")

    # Registrer platforme (binary_sensor, sensor, etc.)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Fjern integrationen igen."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class NoxTcpClient:
    """Håndterer den vedvarende TCP-forbindelse til NOX."""

    def __init__(self, hass, host, port, entry):
        self.hass = hass
        self.host = host
        self.port = port
        self.entry = entry
        self._known_uids = set()

    async def async_run(self):
        """Hovedloop for TCP-forbindelsen med automatisk genforbindelse."""
        while True:
            try:
                _LOGGER.info("Forsøger at forbinde til NOX på %s:%s",
                             self.host, self.port)
                reader, writer = await asyncio.open_connection(self.host, self.port)
                _LOGGER.info("Forbundet til NOX Telnet server")

                while True:
                    # Vi læser en linje ad gangen (kræver delimiter i NOX)
                    line = await reader.readline()
                    if not line:
                        _LOGGER.warning("Forbindelse lukket af NOX (EOF)")
                        break

                    message = line.decode().strip()
                    if message:
                        self._handle_nox_message(message)

            except Exception as err:
                _LOGGER.error("Fejl i NOX-forbindelse: %s", err)

            # Vent 10 sekunder før vi prøver at forbinde igen ved fejl
            await asyncio.sleep(10)

    def _handle_nox_message(self, message: str):
        """Parser TIO matrixen og sender signaler internt i HA."""
        _LOGGER.debug("Modtaget fra NOX: %s", message)

        try:
            parts = message.split('|')
            header = parts[0]

            # --- INPUT HÅNDTERING ---
            if header.startswith(PREFIX_INPUT):
                # Format: INP4|3002-2|DET Stue|closed
                index = header.replace(PREFIX_INPUT, "")
                uid = parts[1]      # @I
                name = parts[2]     # $I
                state = parts[3]    # %I

                # Hvis vi aldrig har set dette ID før, trigger vi 'discovery'
                if uid not in self._known_uids:
                    async_dispatcher_send(
                        self.hass,
                        f"{DOMAIN}_new_binary_sensor",
                        {"uid": uid, "name": name, "index": index}
                    )
                    self._known_uids.add(uid)

                # Send statusopdatering (On hvis ikke closed)
                is_on = state.lower() not in [
                    "closed", "lukket", "ok", "off", "hvil"]
                async_dispatcher_send(
                    self.hass, f"{DOMAIN}_update_{uid}", is_on)

            # --- OUTPUT HÅNDTERING ---
            elif header.startswith(PREFIX_OUTPUT):
                # Format: OUT1|Gårdlys|off
                index = header.replace(PREFIX_OUTPUT, "")
                name = parts[1]
                state = parts[2]

                # VI SKAL HAVE DISCOVERY HER:
                if f"out_{index}" not in self._known_uids:
                    async_dispatcher_send(
                        self.hass,
                        # Dette matcher binary_sensor.py
                        f"{DOMAIN}_new_output_sensor",
                        {"index": index, "name": name}
                    )
                    self._known_uids.add(f"out_{index}")

                # Send selve statusopdateringen
                async_dispatcher_send(
                    self.hass, f"{DOMAIN}_output_update_{index}", state)

            # --- AREA HÅNDTERING ---
            elif header.startswith(PREFIX_AREA):
                # Format: AREA1|Stueetage|Tilkoblet|0
                index = header.replace(PREFIX_AREA, "")
                name = parts[1]       # $A
                state = parts[2]      # %A
                alarm_type = parts[3] if len(parts) > 3 else "0"  # $T

                # Hvis vi aldrig har set dette Område-index før, trigger vi 'discovery'
                if f"area_{index}" not in self._known_uids:
                    async_dispatcher_send(
                        self.hass,
                        f"{DOMAIN}_new_area",
                        {"index": index, "name": name}
                    )
                    self._known_uids.add(f"area_{index}")

                # Send selve dataen til den sensor, der lytter på dette index
                async_dispatcher_send(
                    self.hass,
                    f"{DOMAIN}_area_update_{index}",
                    {"state": state, "alarm_type": alarm_type}
                )

        except Exception as e:
            _LOGGER.error("Kunne ikke parse NOX besked '%s': %s", message, e)
