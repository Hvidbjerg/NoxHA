"""Binary sensor platform for NoxHA (Inputs & Outputs)."""
import logging
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _normalize_name(name: str, fallback: str) -> str:
    clean = (name or "").strip()
    if not clean or clean in {"-", "?"}:
        return fallback
    if clean.isdigit():
        return f"{fallback} {clean}"
    return clean


async def async_setup_entry(hass, entry, async_add_entities):
    """Sæt binary_sensor platformen op via discovery."""
    known_devices = set()

    @callback
    def async_discover_input(data):
        """Håndterer nye inputs fra NOX."""
        uid = data["uid"]
        if uid not in known_devices:
            _LOGGER.info("Opdaget NOX Input: %s (%s)", data["name"], uid)
            new_sensor = NoxInputSensor(
                hass,
                uid,
                data["name"],
                data["index"],
                data.get("is_on", False),
            )
            hass.add_job(async_add_entities, [new_sensor])
            known_devices.add(uid)

    @callback
    def async_discover_output(data):
        """Håndterer nye outputs fra NOX."""
        index = data["index"]
        uid = f"out_{index}"
        if uid not in known_devices:
            _LOGGER.info("Opdaget NOX Output: %s", data["name"])
            new_sensor = NoxOutputSensor(
                hass,
                index,
                data["name"],
                data.get("is_on", False),
            )
            hass.add_job(async_add_entities, [new_sensor])
            known_devices.add(uid)

    # Forbind til dispatcher
    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{DOMAIN}_new_binary_sensor", async_discover_input)
    )
    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{DOMAIN}_new_output_sensor", async_discover_output)
    )


class NoxBaseEntity(BinarySensorEntity):
    """Fælles egenskaber for alle NOX entiteter."""

    @property
    def device_info(self):
        """Samler alle sensorer på én 'enhed' i Home Assistant flisen."""
        return {
            "identifiers": {(DOMAIN, "nox_central_unit")},
            "name": "NOX Alarm Central",
            "manufacturer": "Nox Systems",
            "model": "TIO Protocol",
        }


class NoxInputSensor(NoxBaseEntity):
    """Repræsentation af et NOX Input (@I)."""

    def __init__(self, hass, uid, name, index, initial_state=False):
        self.hass = hass
        self._uid = uid
        self._attr_name = _normalize_name(name, f"Input {uid}")
        self._attr_unique_id = f"{DOMAIN}_inp_{uid}"
        self._index = index
        self._attr_is_on = initial_state

        name_lower = name.lower() if name else ""
        if any(x in name_lower for x in ["dør", "door", "port"]):
            self._attr_device_class = BinarySensorDeviceClass.DOOR
        elif any(x in name_lower for x in ["vindue", "window"]):
            self._attr_device_class = BinarySensorDeviceClass.WINDOW
        elif any(x in name_lower for x in ["pir", "bevægelse", "motion"]):
            self._attr_device_class = BinarySensorDeviceClass.MOTION
        else:
            self._attr_device_class = BinarySensorDeviceClass.SAFETY

    async def async_added_to_hass(self):
        """Forbind til statusopdateringer når sensoren lander i HA."""
        @callback
        def update_state(is_on):
            if self._attr_is_on == is_on:
                return

            self._attr_is_on = is_on
            self.hass.add_job(self.async_write_ha_state)

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_update_{self._uid}", update_state)
        )


class NoxOutputSensor(NoxBaseEntity):
    """Repræsentation af et NOX Output (#O)."""

    def __init__(self, hass, index, name, initial_state=False):
        self.hass = hass
        self._index = index
        self._attr_name = _normalize_name(name, f"Output {index}")
        self._attr_unique_id = f"{DOMAIN}_out_{index}"
        self._attr_is_on = initial_state

    @property
    def icon(self):
        """Brug et fast ikon for alle relæ outputs."""
        return "mdi:electric-switch"

    async def async_added_to_hass(self):
        """Forbind til statusopdateringer."""
        @callback
        def update_state(is_on):
            if self._attr_is_on == is_on:
                return

            self._attr_is_on = is_on
            self.hass.add_job(self.async_write_ha_state)

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_output_update_{self._index}", update_state)
        )
