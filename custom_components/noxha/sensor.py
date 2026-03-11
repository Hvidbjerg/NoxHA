from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, ALARM_TYPES


def _normalize_name(name: str, fallback: str) -> str:
    clean = (name or "").strip()
    if not clean or clean in {"-", "?"}:
        return fallback
    if clean.isdigit():
        return f"{fallback} {clean}"
    return clean


async def async_setup_entry(hass, entry, async_add_entities):
    """Sætter sensor platformen op."""

    known_areas = set()

    @callback
    def async_discover_area(data):
        """Denne kaldes når en ny AREA pakke modtages fra __init__.py."""
        area_index = data["index"]
        if area_index not in known_areas:
            # Opret det nye område i HA
            new_area = NoxAreaSensor(area_index, data["name"])
            hass.add_job(async_add_entities, [new_area])
            known_areas.add(area_index)

    # Lyt efter 'new_area' signalet fra din __init__.py
    # Husk at tilføje dette signal i din __init__.py handle_message logik!
    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{DOMAIN}_new_area", async_discover_area)
    )


class NoxAreaSensor(SensorEntity):
    """Repræsentation af et NOX Område (Area)."""

    def __init__(self, index, name):
        self._index = index
        self._attr_name = _normalize_name(name, f"Area {index}")
        self._attr_unique_id = f"{DOMAIN}_area_{index}"
        self._attr_native_value = "Ukendt"
        self._alarm_type = "0"
        self._attr_icon = "mdi:shield-home"

    @property
    def extra_state_attributes(self):
        """Tilføj alarmtype og område-nummer som attributter."""
        alarm_desc = ALARM_TYPES.get(
            self._alarm_type, f"Ukendt kode: {self._alarm_type}")
        return {
            "nox_area_index": self._index,
            "alarm_type_code": self._alarm_type,
            "alarm_status": alarm_desc
        }

    async def async_added_to_hass(self):
        """Når sensoren er tilføjet, lyt efter AREA-opdateringer."""
        @callback
        def update_area(data):
            # data indeholder {"state": %A, "alarm_type": $T}
            new_state = data["state"]
            new_alarm_type = data["alarm_type"]

            if self._attr_native_value == new_state and self._alarm_type == new_alarm_type:
                return

            self._attr_native_value = new_state
            self._alarm_type = new_alarm_type

            # Skift ikon baseret på tilstand (valgfrit)
            if "tilkoblet" in new_state.lower():
                self._attr_icon = "mdi:shield-lock"
            else:
                self._attr_icon = "mdi:shield-off"

            self.hass.add_job(self.async_write_ha_state)

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_area_update_{self._index}", update_area)
        )
