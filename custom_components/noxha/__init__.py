import asyncio
import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, PLATFORMS, PREFIX_INPUT, PREFIX_OUTPUT, PREFIX_AREA

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Sæt NOX integrationen op."""
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
        self._line_breaker = re.compile(r"[\r\n]+")
        self._read_buffer = ""
        self._known_uids = set()
        self._input_states: dict[str, bool] = {}
        self._output_states: dict[str, str] = {}
        self._area_states: dict[str, tuple[str, str]] = {}

    def _dispatch(self, signal: str, payload) -> None:
        """Send dispatcher-signal på Home Assistant loopet."""
        self.hass.add_job(async_dispatcher_send, self.hass, signal, payload)

    async def async_run(self):
        """Hovedloop for TCP-forbindelsen."""
        while True:
            try:
                _LOGGER.info("Forbinder til NOX %s:%s", self.host, self.port)
                reader, _writer = await asyncio.open_connection(self.host, self.port)
                _LOGGER.info("Forbundet til NOX")
                self._read_buffer = ""

                while True:
                    chunk = await reader.read(4096)
                    if not chunk:
                        _LOGGER.warning("Forbindelse lukket af NOX (EOF)")
                        break

                    self._read_buffer += chunk.decode("utf-8", errors="ignore")
                    self._drain_messages()

            except Exception as err:
                _LOGGER.error("Fejl i NOX-forbindelse: %s", err)

            _LOGGER.info("Venter 10 sekunder før reconnect")
            await asyncio.sleep(10)

    def _drain_messages(self) -> None:
        """Split stream-buffer på både CR og LF og parse komplette beskeder."""
        parts = self._line_breaker.split(self._read_buffer)
        if not self._read_buffer.endswith("\n") and not self._read_buffer.endswith("\r"):
            self._read_buffer = parts.pop() if parts else self._read_buffer
        else:
            self._read_buffer = ""

        for raw in parts:
            message = raw.strip()
            if message:
                _LOGGER.debug("NOX raw: %s", message)
                self._handle_nox_message(message)

    def _handle_nox_message(self, message: str):
        """Parser TIO matrixen og sender signaler internt i HA."""
        _LOGGER.debug("Parser besked: %s", message)

        try:
            parts = message.split('|')
            if len(parts) < 2:
                return

            header = parts[0]

            # --- INPUT HÅNDTERING ---
            if header.startswith(PREFIX_INPUT):
                if len(parts) < 4:
                    return

                index = header.replace(PREFIX_INPUT, "")
                uid = parts[1]
                name = parts[2]
                state = parts[3]

                if uid not in self._known_uids:
                    _LOGGER.info("Opdaget nyt input: %s (%s)", name, uid)
                    self._dispatch(
                        f"{DOMAIN}_new_binary_sensor",
                        {"uid": uid, "name": name, "index": index},
                    )
                    self._known_uids.add(uid)

                is_on = state.lower() not in [
                    "closed", "lukket", "ok", "off", "hvil"]
                if self._input_states.get(uid) != is_on:
                    self._input_states[uid] = is_on
                    self._dispatch(f"{DOMAIN}_update_{uid}", is_on)

            # --- OUTPUT HÅNDTERING ---
            elif header.startswith(PREFIX_OUTPUT):
                if len(parts) < 3:
                    return

                index = header.replace(PREFIX_OUTPUT, "")
                name = parts[1]
                state = parts[2].strip().lower()
                uid = f"out_{index}"

                if uid not in self._known_uids:
                    self._dispatch(
                        f"{DOMAIN}_new_output_sensor",
                        {"index": index, "name": name},
                    )
                    self._known_uids.add(uid)

                if self._output_states.get(index) != state:
                    self._output_states[index] = state
                    self._dispatch(f"{DOMAIN}_output_update_{index}", state)

            # --- AREA HÅNDTERING ---
            elif header.startswith(PREFIX_AREA):
                if len(parts) < 3:
                    return

                index = header.replace(PREFIX_AREA, "")
                name = parts[1]
                state = parts[2].strip()
                alarm_type = parts[3].strip() if len(parts) > 3 else "0"

                uid = f"area_{index}"
                if uid not in self._known_uids:
                    self._dispatch(
                        f"{DOMAIN}_new_area",
                        {"index": index, "name": name},
                    )
                    self._known_uids.add(uid)

                area_payload = (state, alarm_type)
                if self._area_states.get(index) != area_payload:
                    self._area_states[index] = area_payload
                    self._dispatch(
                        f"{DOMAIN}_area_update_{index}",
                        {"state": state, "alarm_type": alarm_type},
                    )

        except Exception as e:
            _LOGGER.error("Kunne ikke parse besked '%s': %s", message, e)
