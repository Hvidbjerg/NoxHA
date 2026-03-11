import asyncio
from collections import deque
import logging
import re
import time
from typing import Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    BULK_COOLDOWN_SECONDS,
    BULK_FLUSH_INTERVAL,
    BULK_FLUSH_MAX_ITEMS,
    BULK_MESSAGE_THRESHOLD,
    BULK_WINDOW_SECONDS,
    DOMAIN,
    PLATFORMS,
    PREFIX_AREA,
    PREFIX_INPUT,
    PREFIX_OUTPUT,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Sæt NOX integrationen op."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    _LOGGER.info("NoxHA runtime patch: threadsafe-statewrite-v2")

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
        self._output_states: dict[str, bool] = {}
        self._area_states: dict[str, tuple[str, str]] = {}
        self._recent_messages = deque()
        self._bulk_mode_until = 0.0
        self._queued_dispatches: dict[str, tuple[str, object]] = {}
        self._bulk_flush_task: asyncio.Task | None = None

    def _dispatch(self, signal: str, payload) -> None:
        """Send dispatcher-signal på Home Assistant loopet."""
        self.hass.loop.call_soon_threadsafe(
            async_dispatcher_send, self.hass, signal, payload
        )

    def _is_bulk_mode(self) -> bool:
        """Afgør om vi er i burst/bulk mode baseret på beskedfrekvens."""
        now = time.monotonic()
        self._recent_messages.append(now)
        cutoff = now - BULK_WINDOW_SECONDS
        while self._recent_messages and self._recent_messages[0] < cutoff:
            self._recent_messages.popleft()

        if len(self._recent_messages) >= BULK_MESSAGE_THRESHOLD:
            self._bulk_mode_until = now + BULK_COOLDOWN_SECONDS

        return now < self._bulk_mode_until

    def _schedule_dispatch(self, key: str, signal: str, payload, bulk_mode: bool) -> None:
        """Send straks ved single events; coalesce + throttle under bulk mode."""
        if not bulk_mode:
            self._dispatch(signal, payload)
            return

        self._queued_dispatches[key] = (signal, payload)
        if self._bulk_flush_task is None or self._bulk_flush_task.done():
            self._bulk_flush_task = self.entry.async_create_background_task(
                self.hass,
                self._async_flush_queued_dispatches(),
                "nox_bulk_dispatch_flush",
            )

    async def _async_flush_queued_dispatches(self) -> None:
        """Flusher queued updates i små batches for at skåne HA under brute force."""
        while self._queued_dispatches:
            keys = list(self._queued_dispatches.keys())[:BULK_FLUSH_MAX_ITEMS]
            for key in keys:
                signal, payload = self._queued_dispatches.pop(key)
                self._dispatch(signal, payload)

            await asyncio.sleep(BULK_FLUSH_INTERVAL)

    @staticmethod
    def _normalize_binary_state(raw_state: str) -> Optional[bool]:
        """Normaliser NOX state-tekst til bool, eller None ved ukendt værdi."""
        state = raw_state.strip().lower()
        on_values = {"1", "on", "open", "active", "aktiv", "true"}
        off_values = {
            "0",
            "off",
            "closed",
            "lukket",
            "ok",
            "hvil",
            "idle",
            "inactive",
            "inaktiv",
            "false",
            "normal",
        }

        if state in on_values:
            return True
        if state in off_values:
            return False
        return None

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
                    await self._drain_messages()

            except Exception as err:
                _LOGGER.error("Fejl i NOX-forbindelse: %s", err)

            _LOGGER.info("Venter 2 sekunder før reconnect")
            await asyncio.sleep(2)

    async def _drain_messages(self) -> None:
        """Split stream-buffer på både CR og LF og parse komplette beskeder."""
        parts = self._line_breaker.split(self._read_buffer)
        if not self._read_buffer.endswith("\n") and not self._read_buffer.endswith("\r"):
            self._read_buffer = parts.pop() if parts else self._read_buffer
        else:
            self._read_buffer = ""

        input_messages: list[str] = []
        other_messages: list[str] = []

        for raw in parts:
            message = raw.strip()
            if message:
                if message.startswith(PREFIX_INPUT):
                    input_messages.append(message)
                else:
                    other_messages.append(message)

        # Input events har realtime-prioritet over bulk-opdateringer.
        processed = 0
        for message in input_messages:
            _LOGGER.debug("NOX raw: %s", message)
            self._handle_nox_message(
                message,
                bulk_mode=False,
                received_monotonic=time.monotonic(),
            )
            processed += 1
            if processed % 100 == 0:
                await asyncio.sleep(0)

        for message in other_messages:
            _LOGGER.debug("NOX raw: %s", message)
            self._handle_nox_message(
                message,
                self._is_bulk_mode(),
                received_monotonic=time.monotonic(),
            )
            processed += 1
            if processed % 100 == 0:
                await asyncio.sleep(0)

    def _handle_nox_message(
        self,
        message: str,
        bulk_mode: bool,
        received_monotonic: float,
    ):
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
                normalized_state = self._normalize_binary_state(parts[3])
                if normalized_state is None:
                    _LOGGER.debug(
                        "Ukendt input state for %s: %s", uid, parts[3])
                    return

                is_on = normalized_state

                if uid not in self._known_uids:
                    _LOGGER.info("Opdaget nyt input: %s (%s)", name, uid)
                    self._input_states[uid] = is_on
                    self._dispatch(
                        f"{DOMAIN}_new_binary_sensor",
                        {"uid": uid, "name": name, "index": index, "is_on": is_on},
                    )
                    _LOGGER.debug(
                        "NOX input discovery uid=%s state=%s dispatch_latency_ms=%.1f",
                        uid,
                        is_on,
                        (time.monotonic() - received_monotonic) * 1000,
                    )
                    self._known_uids.add(uid)

                if self._input_states.get(uid) != is_on:
                    self._input_states[uid] = is_on
                    self._dispatch(f"{DOMAIN}_update_{uid}", is_on)
                    _LOGGER.debug(
                        "NOX input update uid=%s state=%s dispatch_latency_ms=%.1f",
                        uid,
                        is_on,
                        (time.monotonic() - received_monotonic) * 1000,
                    )

            # --- OUTPUT HÅNDTERING ---
            elif header.startswith(PREFIX_OUTPUT):
                if len(parts) < 3:
                    return

                index = header.replace(PREFIX_OUTPUT, "")
                name = parts[1]
                normalized_state = self._normalize_binary_state(parts[2])
                if normalized_state is None:
                    _LOGGER.debug(
                        "Ukendt output state for %s: %s", index, parts[2])
                    return

                is_on = normalized_state
                uid = f"out_{index}"

                if uid not in self._known_uids:
                    self._output_states[index] = is_on
                    self._schedule_dispatch(
                        f"new_output_{index}",
                        f"{DOMAIN}_new_output_sensor",
                        {"index": index, "name": name, "is_on": is_on},
                        bulk_mode,
                    )
                    self._known_uids.add(uid)

                if self._output_states.get(index) != is_on:
                    self._output_states[index] = is_on
                    self._schedule_dispatch(
                        f"output_state_{index}",
                        f"{DOMAIN}_output_update_{index}",
                        is_on,
                        bulk_mode,
                    )

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
                    self._schedule_dispatch(
                        f"new_area_{index}",
                        f"{DOMAIN}_new_area",
                        {"index": index, "name": name},
                        bulk_mode,
                    )
                    self._known_uids.add(uid)

                area_payload = (state, alarm_type)
                if self._area_states.get(index) != area_payload:
                    self._area_states[index] = area_payload
                    self._schedule_dispatch(
                        f"area_state_{index}",
                        f"{DOMAIN}_area_update_{index}",
                        {"state": state, "alarm_type": alarm_type},
                        bulk_mode,
                    )

        except Exception as e:
            _LOGGER.error("Kunne ikke parse besked '%s': %s", message, e)
