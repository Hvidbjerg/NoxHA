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

    _LOGGER.error("!!! BINARY_SENSOR PLATFORM ER NU AKTIV OG LYTTER !!!")

    def async_discover_input(data):
        """Håndterer opdagelse af nye input (sensorer) fra NOX."""
        uid = data["uid"]
        if uid not in known_devices:
            _LOGGER.info("Opdaget nyt NOX Input: %s (%s)", data["name"], uid)
            new_sensor = NoxInputSensor(hass, uid, data["name"], data["index"])

            # Vi bruger add_job for at sikre, at entiteten oprettes i det korrekte loop
            hass.add_job(async_add_entities([new_sensor]))
            known_devices.add(uid)

    def async_discover_output(data):
        """Håndterer opdagelse af nye outputs fra NOX."""
        index = data["index"]
        uid = f"out_{index}"
        if uid not in known_devices:
            _LOGGER.info("Opdaget nyt NOX Output: %s (Index: %s)",
                         data["name"], index)
            new_sensor = NoxOutputSensor(hass, index, data["name"])

            # Samme her: add_job sikrer trådsikkerhed
            hass.add_job(async_add_entities([new_sensor]))
            known_devices.add(uid)

    # Forbind til dispatcher-signalerne fra __init__.py
    async_dispatcher_connect(
        hass, f"{DOMAIN}_new_binary_sensor", async_discover_input)
    async_dispatcher_connect(
        hass, f"{DOMAIN}_new_output_sensor", async_discover_output)


class NoxBaseEntity(BinarySensorEntity):
    """Base klasse for NOX entiteter for at dele enheds-info."""

    @property
    def device_info(self):
        """Samler alle sensorer under én NOX Central enhed i HA."""
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
        self._attr_name = f"Nox {name}" if name else f"Nox Input {uid}"
        self._attr_unique_id = f"{DOMAIN}_inp_{uid}"
        self._index = index
        self._attr_is_on = False

        # Intelligent gæt af device_class baseret på navnet
        name_lower = name.lower() if name else ""
        if any(x in name_lower for x in ["dør", "door", "port"]):
            self._attr_device_class = BinarySensorDeviceClass.DOOR
        elif any(x in name_lower for x in ["vindue", "window"]):
            self._attr_device_class = BinarySensorDeviceClass.WINDOW
        elif any(x in name_lower for x in ["pir", "bevægelse", "motion"]):
            self._attr_device_class = BinarySensorDeviceClass.MOTION

    async def async_added_to_hass(self):
        """Tilmeld statusopdateringer når sensoren er klar."""
        def update_state(is_on):
            self._attr_is_on = is_on
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_update_{self._uid}", update_state)
        )


class NoxOutputSensor(NoxBaseEntity):
    """Repræsentation af et NOX Output (#O)."""

    def __init__(self, hass, index, name):
        self.hass = hass
        self._index = index
        self._attr_name = f"Nox Output {name}" if name else f"Nox Output {index}"
        self._attr_unique_id = f"{DOMAIN}_out_{index}"
        self._attr_is_on = False
        self._attr_icon = "mdi:relay"

    async def async_added_to_hass(self):
        """Tilmeld statusopdateringer."""
        def update_state(state_text):
            # Konverter tekst-status til True/False
            self._attr_is_on = str(state_text).lower() in [
                "on", "1", "active", "aktiv", "open"]
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_output_update_{self._index}", update_state)
        )
