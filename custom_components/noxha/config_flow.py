import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from .const import DOMAIN


class NoxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Håndterer opsætning af NOX via UI."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # Her kunne vi indsætte et tjek for at se om IP'en svarer
            return self.async_create_entry(title="NOX Alarm", data=user_input)

        # Felter som brugeren skal udfylde i HA
        data_schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PORT, default=23): int,
        })

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )
