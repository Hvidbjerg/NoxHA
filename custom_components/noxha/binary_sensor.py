"""Binary sensor platform for NoxHA (Inputs & Outputs)."""
import logging
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Sæt binary_sensor platformen op via discovery."""
    known_devices = set()

    # --- DISCOVERY LOGIK FOR INPUTS (INP) ---
    def async_discover_input(data):
        uid = data["uid"]
        if uid not in known_devices:
            _LOGGER.info("Opdaget nyt NOX Input: %s (%s)", data["name"], uid)
            new_sensor = NoxInputSensor(uid, data["name"], data["index"])
            async_add_entities([new_sensor])
            known_devices.add(uid)

    # --- DISCOVERY LOGIK FOR OUTPUTS (OUT) ---
    def async_discover_output(data):
        index = data["index"]
        uid = f"out_{index}"
        if uid not in known_devices:
            _LOGGER.info("Opdaget nyt NOX Output: %s (Index: %s)",
                         data["name"], index)
            new_sensor = NoxOutputSensor(index, data["name"])
            async_add_entities([new_sensor])
            known_devices.add(uid)

    # Forbind discovery-funktionerne til dispatcher-signalerne fra __init__.py
    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{DOMAIN}_new_binary_sensor", async_discover_input)
    )
    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{DOMAIN}_new_output_sensor", async_discover_output)
    )


class NoxInputSensor(BinarySensorEntity):
    """Repræsentation af et NOX Input (@I)."""

    def __init__(self, uid, name, index):
        self._uid = uid
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_inp_{uid}"
        self._index = index
        self._attr_is_on = False

        # Gæt device_class
        name_lower = name.lower()
        if any(x in name_lower for x in ["dør", "door", "port"]):
            self._attr_device_class = BinarySensorDeviceClass.DOOR
        elif any(x in name_lower for x in ["vindue", "window"]):
            self._attr_device_class = BinarySensorDeviceClass.WINDOW
        elif any(x in name_lower for x in ["pir", "bevægelse", "motion"]):
            self._attr_device_class = BinarySensorDeviceClass.MOTION
        else:
            self._attr_device_class = None

    async def async_added_to_hass(self):
        def update_state(is_on):
            self._attr_is_on = is_on
            self.async_write_ha_state()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_update_{self._uid}", update_state)
        )


class NoxOutputSensor(BinarySensorEntity):
    """Repræsentation af et passivt NOX Output (#O)."""

    def __init__(self, index, name):
        self._index = index
        self._attr_name = f"Output {name}"
        self._attr_unique_id = f"{DOMAIN}_out_{index}"
        self._attr_is_on = False
        self._attr_icon = "mdi:relays"

    async def async_added_to_hass(self):
        def update_state(state_text):
            # Antager at NOX sender 'on', '1', 'active' eller lignende
            self._attr_is_on = state_text.lower(
            ) in ["on", "1", "active", "aktiv"]
            self.async_write_ha_state()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_output_update_{self._index}", update_state)
        )
