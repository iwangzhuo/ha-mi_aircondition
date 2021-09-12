"""
Support for Xiaomi Air Conditioning C1
"""
import logging
import asyncio

from miio.device import Device, DeviceException

from datetime import timedelta
from .ac_c1 import XiaomiAirConditionC1
from .ac_m1 import XiaomiAirConditionM1
import voluptuous as vol

from homeassistant.components.climate import (
    ClimateDevice, PLATFORM_SCHEMA, )
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE, DOMAIN, HVAC_MODES, HVAC_MODE_OFF, HVAC_MODE_HEAT,
    HVAC_MODE_COOL, HVAC_MODE_AUTO, HVAC_MODE_DRY, HVAC_MODE_FAN_ONLY,
    SUPPORT_SWING_MODE, SUPPORT_FAN_MODE, SUPPORT_TARGET_TEMPERATURE, )
from homeassistant.const import (
    ATTR_ENTITY_ID, ATTR_TEMPERATURE, ATTR_UNIT_OF_MEASUREMENT, CONF_NAME,
    CONF_HOST, CONF_TOKEN, CONF_TIMEOUT, TEMP_CELSIUS, )
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.event import async_track_state_change
import homeassistant.helpers.config_validation as cv
from homeassistant.util.dt import utcnow

_LOGGER = logging.getLogger(__name__)

SUCCESS = ['ok']

MODEL_AIRCONDITION_MA2 = 'xiaomi.aircondition.ma2'
MODEL_SA1 = "zhimi.aircondition.sa1"
MODEL_MA1 = "zhimi.aircondition.ma1"
MODEL_MA2 = "zhimi.aircondition.ma2"
MODEL_MA3 = "zhimi.aircondition.ma3"
MODEL_MA4 = "zhimi.aircondition.ma4"
MODEL_VA1 = "zhimi.aircondition.va1"
MODEL_ZA1 = "zhimi.aircondition.za1"
MODEL_ZA2 = "zhimi.aircondition.za2"

MODELS_SUPPORTED = [MODEL_AIRCONDITION_MA2,
                    MODEL_SA1,
                    MODEL_MA1,
                    MODEL_MA2,
                    MODEL_MA3,
                    MODEL_MA4,
                    MODEL_VA1,
                    MODEL_ZA1,
                    MODEL_ZA2,
                    ]


SCAN_INTERVAL = timedelta(seconds=15)

SUPPORT_FLAGS = (SUPPORT_TARGET_TEMPERATURE |
                 SUPPORT_FAN_MODE |
                 SUPPORT_SWING_MODE)

CONF_MIN_TEMP = 'min_temp'
CONF_MAX_TEMP = 'max_temp'
DEFAULT_NAME = 'Xiaomi Air Conditioning'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_TOKEN): vol.All(cv.string, vol.Length(min=32, max=32)),
    vol.Optional(CONF_MIN_TEMP, default=16): vol.Coerce(int),
    vol.Optional(CONF_MAX_TEMP, default=30): vol.Coerce(int),
})

# pylint: disable=unused-argument
@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up the air condition companion from config."""

    host = config.get(CONF_HOST)
    token = config.get(CONF_TOKEN)
    name = config.get(CONF_NAME)
    min_temp = config.get(CONF_MIN_TEMP)
    max_temp = config.get(CONF_MAX_TEMP)

    _LOGGER.info("Initializing with host %s (token %s...)", host, token[:5])

    try:
        device = Device(host, token)
        device_info = device.info()
        model = device_info.model
        if model not in MODELS_SUPPORTED:
            _LOGGER.error("no support model found: %s", model)
            raise PlatformNotReady
        unique_id = "{}-{}".format(model, device_info.mac_address)
        if model == MODEL_AIRCONDITION_MA2:
            air_condition_companion = XiaomiAirConditionC1(
                hass, name, host, token, unique_id, min_temp, max_temp)
        else:
            air_condition_companion = XiaomiAirConditionM1(
                hass, name, host, token, unique_id, min_temp, max_temp)

        _LOGGER.info("model[ %s ] firmware_ver[ %s ] hardware_ver[ %s ] detected",
                     model,
                     device_info.firmware_version,
                     device_info.hardware_version)
        async_add_devices([air_condition_companion], update_before_add=True)

    except DeviceException as ex:
        _LOGGER.error("Device unavailable or token incorrect: %s", ex)
        raise PlatformNotReady


class AirConditionException(DeviceException):
    pass


