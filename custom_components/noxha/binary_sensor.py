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

    _LOGGER.error("!!! NOX BINARY_SENSOR PLATFORM ER AKTIV !!!")

    def async_discover_input(data):
        """Håndterer nye inputs fra NOX."""
        uid = data["uid"]
        if uid not in known_devices:
            _LOGGER.info("Opdaget NOX Input: %s (%s)", data["name"], uid)
            new_sensor = NoxInputSensor(hass, uid, data["name"], data["index"])
            hass.add_job(async_add_entities, [new_sensor])
            known_devices.add(uid)

    def async_discover_output(data):
        """Håndterer nye outputs fra NOX."""
        index = data["index"]
        uid = f"out_{index}"
        if uid not in known_devices:
            _LOGGER.info("Opdaget NOX Output: %s", data["name"])
            new_sensor = NoxOutputSensor(hass, index, data["name"])
            hass.add_job(async_add_entities, [new_sensor])
            known_devices.add(uid)

    # Forbind til dispatcher
    async_dispatcher_connect(
        hass, f"{DOMAIN}_new_binary_sensor", async_discover_input)
    async_dispatcher_connect(
        hass, f"{DOMAIN}_new_output_sensor", async_discover_output)


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

    def __init__(self, hass, uid, name, index):
        self.hass = hass
        self._uid = uid
        self._attr_name = name if name else f"Input {uid}"
        self._attr_unique_id = f"{DOMAIN}_inp_{uid}"
        self._index = index
        self._attr_is_on = False

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
        def update_state(is_on):
            self._attr_is_on = is_on
            # RETTELSE: Vi bruger schedule_update i stedet for write_ha_state
            # Det gør det sikkert at opdatere fra TCP-tråden
            self.async_schedule_update_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_update_{self._uid}", update_state)
        )


class NoxOutputSensor(NoxBaseEntity):
    """Repræsentation af et NOX Output (#O)."""

    def __init__(self, hass, index, name):
        self.hass = hass
        self._index = index
        self._attr_name = name if name else f"Output {index}"
        self._attr_unique_id = f"{DOMAIN}_out_{index}"
        self._attr_is_on = False
        self._attr_icon = "mdi:relay"

    async def async_added_to_hass(self):
        """Forbind til statusopdateringer."""
        def update_state(state_text):
            self._attr_is_on = str(state_text).lower() in [
                "on", "1", "active", "aktiv", "open"]
            # RETTELSE: Samme her for outputs
            self.async_schedule_update_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_output_update_{self._index}", update_state)
        )
