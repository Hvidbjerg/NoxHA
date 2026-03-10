import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, PLATFORMS, PREFIX_INPUT, PREFIX_OUTPUT, PREFIX_AREA

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Sæt NOX integrationen op."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    _LOGGER.error("!!! async_setup_entry STARTER NU !!!")

    # Opret klient-instansen
    client = NoxTcpClient(hass, host, port, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client

    # Start TCP-klienten som en baggrundsopgave
    entry.async_create_background_task(
        hass, client.async_run(), "nox_tcp_client")

    # Registrer platforme (binary_sensor, sensor, etc.)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.error("!!! SETUP ER FÆRDIG - AFVENTER DATA FRA KLIENT !!!")
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
        """Hovedloop for TCP-forbindelsen."""
        _LOGGER.error("!!! NoxTcpClient.async_run LOOP STARTER !!!")

        while True:
            try:
                _LOGGER.error(
                    f"PRØVER AT FORBINDE TIL NOX: {self.host}:{self.port}")
                reader, writer = await asyncio.open_connection(self.host, self.port)
                _LOGGER.error(
                    "+++ SUCCES: FORBUNDET TIL NOX TELNET SERVER +++")

                while True:
                    line_bytes = await reader.readline()
                    if not line_bytes:
                        _LOGGER.error(
                            "--- ADVARSEL: FORBINDELSE LUKKET AF NOX (EOF) ---")
                        break

                    message = line_bytes.decode(
                        'utf-8', errors='ignore').strip()
                    if message:
                        # VI BRUGER ERROR HER FOR AT SE ALT RÅ DATA I LOGGEN
                        _LOGGER.error(f"MODTAGET FRA NOX: >>> {message} <<<")
                        self._handle_nox_message(message)

            except Exception as err:
                _LOGGER.error(f"!!! FEJL I NOX-FORBINDELSE: {err} !!!")

            _LOGGER.error("Venter 10 sekunder før næste forbindelsesforsøg...")
            await asyncio.sleep(10)

    def _handle_nox_message(self, message: str):
        """Parser TIO matrixen og sender signaler internt i HA."""
        # Vi lader denne være debug, da vi allerede logger 'message' ovenfor med ERROR
        _LOGGER.debug("Parser besked: %s", message)

        try:
            parts = message.split('|')
            if len(parts) < 2:
                return

            header = parts[0]

            # --- INPUT HÅNDTERING ---
            if header.startswith(PREFIX_INPUT):
                index = header.replace(PREFIX_INPUT, "")
                uid = parts[1]
                name = parts[2]
                state = parts[3]

                if uid not in self._known_uids:
                    _LOGGER.error(f"OPDAGER NY SENSOR: {name} ({uid})")
                    async_dispatcher_send(
                        self.hass,
                        f"{DOMAIN}_new_binary_sensor",
                        {"uid": uid, "name": name, "index": index}
                    )
                    self._known_uids.add(uid)

                is_on = state.lower() not in [
                    "closed", "lukket", "ok", "off", "hvil"]
                async_dispatcher_send(
                    self.hass, f"{DOMAIN}_update_{uid}", is_on)

            # (Resten af din output/area logik er fin...)

        except Exception as e:
            _LOGGER.error(
                f"!!! KUNNE IKKE PARSE BESKED: {message} | FEJL: {e} !!!")
