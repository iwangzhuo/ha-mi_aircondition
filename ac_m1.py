import enum
import asyncio
import logging
from collections import defaultdict
from typing import Optional
import click
from miio.device import Device, DeviceException
from miio.click_common import command, format_output, EnumType

from typing import Optional, List
from functools import partial
from datetime import timedelta

from homeassistant.components.climate import (
    ClimateDevice, PLATFORM_SCHEMA, )
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE, DOMAIN, HVAC_MODES, HVAC_MODE_OFF, HVAC_MODE_HEAT,
    HVAC_MODE_COOL, HVAC_MODE_AUTO, HVAC_MODE_DRY, HVAC_MODE_FAN_ONLY,
    SUPPORT_SWING_MODE, SUPPORT_FAN_MODE, SUPPORT_TARGET_TEMPERATURE,SUPPORT_PRESET_MODE, SUPPORT_AUX_HEAT)
from homeassistant.const import (
    ATTR_ENTITY_ID, ATTR_TEMPERATURE, ATTR_UNIT_OF_MEASUREMENT, CONF_NAME,
    CONF_HOST, CONF_TOKEN, CONF_TIMEOUT, TEMP_CELSIUS, )

_LOGGER = logging.getLogger(__name__)
SUCCESS = ['ok']
DEFAULT_NAME = 'Xiaomi Mijia Air Conditioning m1'
DATA_KEY = 'climate.xiaomi_airconditioning_m1'

SUPPORT_FLAGS = (SUPPORT_TARGET_TEMPERATURE |
                 SUPPORT_FAN_MODE |
                 # SUPPORT_PRESET_MODE |
                 SUPPORT_AUX_HEAT |
                 SUPPORT_SWING_MODE)

ATTR_SWING_MODE = 'swing_mode'
ATTR_FAN_MODE = 'fan_mode'
ATTR_WIND_LEVEL = 'wind_level'


class HVACMode(enum.Enum):
    Off = HVAC_MODE_OFF
    Cool = HVAC_MODE_COOL
    Dry = HVAC_MODE_DRY
    Fan_Only = HVAC_MODE_FAN_ONLY
    Heat = HVAC_MODE_HEAT



class OperationMode(enum.Enum):
    Cool = "cooling"
    Dry = "arefaction"
    Fan_Only = "wind"
    Heat = HVAC_MODE_HEAT



class FanSpeed(enum.Enum):
    Level_1 = 0
    Level_2 = 1
    Level_3 = 2
    Level_4 = 3
    Level_5 = 4
    Auto = 5


class SwingMode(enum.Enum):
    On = "on"
    Off = "off"


class AirConditionStatus:
    """Container for status reports of the Xiaomi Air Condition."""

    def __init__(self, data):
        """
        Device model: zhimi.aircondition.ma4
        {'power': "on",
         'is_on': True,
         'mode': 2,
         'st_temp_dec': 220 : 22.0°
         'temp_dec': 200, 20.0°
         'vertical_swing': True,
         'speed_level': 0}
        """
        self.data = data

    @property
    def power(self) -> str:
        """Current power state."""
        return self.data['power']

    @property
    def is_on(self) -> bool:
        """True if the device is turned on."""
        return self.power == "on"

    @property
    def mode(self) -> Optional[OperationMode]:
        """Current operation mode."""
        try:
            return OperationMode(self.data['mode'])
        except TypeError:
            return None

    @property
    def target_temp(self) -> float:
        """Target temperature."""
        return self.data['st_temp_dec'] / 10

    @property
    def temperature(self) -> float:
        """Current temperature."""
        return self.data['temp_dec'] / 10

    @property
    def swing(self) -> int:
        """Vertical swing."""
        return self.data['vertical_swing']

    @property
    def wind_level(self) -> int:
        """Wind level."""
        return self.data['speed_level']

    @property
    def is_aux_heat(self) -> Optional[bool]:
        return self.data['ptc'] == "on"

    def __repr__(self) -> str:
        s = "<AirConditionStatus " \
            "power=%s, " \
            "is_on=%s, " \
            "mode=%s, " \
            "st_temp_dec=%s, " \
            "temp_dec=%s, " \
            "vertical_swing=%s, " \
            "aux heat=%s," \
            "speed_level=%s>" % \
            (self.power,
             self.is_on,
             self.mode,
             self.target_temp,
             self.temperature,
             self.swing,
             self.is_aux_heat,
             self.wind_level)
        return s

    def __json__(self):
        return self.data


class AirConditionM1(Device):

    def __init__(self, ip: str = None, token: str = None, model: str = None,
                 start_id: int = 0, debug: int = 0, lazy_discover: bool = True) -> None:
        super().__init__(ip, token, start_id, debug, lazy_discover)
        self.model = model

    @command(
        default_output=format_output(
            "",
            "Power: {result.power}\n"
            "Mode: {result.mode}\n"
            "Target Temp: {result.target_temp} °C\n"
            "Temperature: {result.temperature} °C\n"
            "Wind Level: {result.wind_level}\n"
        )
    )
    def status(self) -> AirConditionStatus:
        """
        Retrieve properties.
        'power': 1          => 0 means off, 1 means on
        'mode': 2           => 2 means cool, 3 means dry, 4 means fan only, 5 means heat
        'settemp': 26.5     => target temperature
        'temperature': 27   => current temperature
        'swing': 0          => 0 means off, 1 means on
        'wind_level': 0     => 0~7 mean auto,level 1 ~ level 7
        'dry': 0            => 0 means off, 1 means on
        'energysave': 0     => 0 means off, 1 means on
        'sleep': 0          => 0 means off, 1 means on
        'auxheat': 0        => 0 means off, 1 means on
        'light': 1          => 0 means off, 1 means on
        'beep': 1           => 0 means off, 1 means on
        'timer': '0,0,0,0'
        'clean': '0,0,0,1'
        'examine': '0,0,"none"'
        """

        properties = [
            'power',
            'mode',
            'st_temp_dec',
            'temp_dec',
            'vertical_swing',
            'speed_level',
            'ptc',
            'silence',
            'comfort'
        ]

        # Something weird. A single request is limited to 1 property.
        # Therefore the properties are divided into multiple requests
        _props = properties.copy()
        values = []
        while _props:
            values.extend(self.send("get_prop", _props[:1]))
            _props[:] = _props[1:]

        properties_count = len(properties)
        values_count = len(values)
        if properties_count != values_count:
            _LOGGER.debug(
                "Count (%s) of requested properties does not match the "
                "count (%s) of received values.",
                properties_count, values_count)

        return AirConditionStatus(
            defaultdict(lambda: None, zip(properties, values)))

    @command(
        default_output=format_output("Powering the air condition on"),
    )
    def on(self):
        """Turn the air condition on."""
        return self.send("set_power", "on")

    @command(
        default_output=format_output("Powering the air condition off"),
    )
    def off(self):
        """Turn the air condition off."""
        return self.send("set_power", "off")

    @command(
        click.argument("temperature", type=float),
        default_output=format_output(
            "Setting target temperature to {temperature} degrees")
    )
    def set_temperature(self, temperature: float):
        """Set target temperature."""
        t = int(temperature * 10);
        return self.send("set_temperature", [t])

    def set_preset_mode(self, presetmode) -> None:
        if presetmode == PRESET_COMFORT:
            self.send("set_comfort", "on")
        elif presetmode == PRESET_SLEEP:
            self.send("set_silence", "on")
        else:
            self.send("set_comfort", "off")
            self.send("set_silence", "off")

    @command(                                                          
        default_output=format_output("turn aux heat on"),
    )   
    def turn_aux_heat_on(self) -> None:
        self.send("set_ptc", "on")

    @command(                                                     
        default_output=format_output("turn aux heat onff"),         
    ) 
    def turn_aux_heat_off(self) -> None:
        self.send("set_ptc", "off")

    @command(
        click.argument("wind_level", type=int),
        default_output=format_output(
            "Setting wind level to {wind_level}")
    )
    def set_wind_level(self, wind_level: int):
        """Set wind level."""
        if wind_level < 0 or wind_level > 7:
            raise AirConditionException("Invalid wind level level: %s", wind_level)

        return self.send("set_spd_level", [wind_level])

    @command(
        click.argument("swing", type=bool),
        default_output=format_output(
            lambda swing: "Turning on swing mode"
            if swing else "Turning off swing mode"
        )
    )
    def set_swing(self, swing: bool):
        """Set swing on/off."""
        if swing:
            return self.send("set_vertical", "on")
        else:
            return self.send("set_vertical", "off")

    @command(
        click.argument("dry", type=bool),
        default_output=format_output(
            lambda dry: "Turning on dry mode"
            if dry else "Turning off dry mode"
        )
    )
    def set_dry(self, dry: bool):
        """Set dry on/off."""
        if dry:
            return self.send("set_dry", "on")
        else:
            return self.send("set_dry", "off")

    @command(
        click.argument("energysave", type=bool),
        default_output=format_output(
            lambda energysave: "Turning on energysave mode"
            if energysave else "Turning off energysave mode"
        )
    )

    @command(
        click.argument("sleep", type=bool),
        default_output=format_output(
            lambda sleep: "Turning on sleep mode"
            if sleep else "Turning off sleep mode"
        )
    )
    def set_sleep(self, sleep: bool):
        """Set sleep on/off."""
        if sleep:
            return self.send("set_silent", "on")
        else:
            return self.send("set_silent", "off")

    @command(
        click.argument("mode", type=EnumType(OperationMode, False)),
        default_output=format_output("Setting operation mode to '{mode.value}'")
    )
    def set_mode(self, mode: OperationMode):
        """Set operation mode."""
        return self.send("set_mode", mode.value)


class XiaomiAirConditionM1(ClimateDevice):
    """Representation of a Xiaomi Air Condition Companion."""

    def __init__(self, hass, name, host, token, unique_id,
                 min_temp, max_temp):

        """Initialize the climate device."""
        self.hass = hass
        self._name = name
        self._device = AirConditionM1(host, token)
        self._unique_id = unique_id

        self._available = False
        self._state = None
        self._state_attrs = {
            ATTR_TEMPERATURE: None,
            ATTR_SWING_MODE: None,
            ATTR_HVAC_MODE: None,
        }
        self._aux_heat = None
        self._max_temp = max_temp
        self._min_temp = min_temp
        self._current_temperature = None
        self._swing_mode = None
        self._wind_level = None
        self._hvac_mode = None
        self._target_temperature = None

    @asyncio.coroutine
    def _try_command(self, mask_error, func, *args, **kwargs):
        """Call a command handling error messages."""
        try:
            result = yield from self.hass.async_add_job(
                partial(func, *args, **kwargs))

            _LOGGER.debug("Response received: %s", result)
            self.schedule_update_ha_state()

            return result == SUCCESS
        except DeviceException as exc:
            _LOGGER.error(mask_error, exc)
            self._available = False
            return False

    @asyncio.coroutine
    def async_turn_on(self, speed: str = None, **kwargs) -> None:
        """Turn the miio device on."""
        result = yield from self._try_command(
            "Turning the miio device on failed.", self._device.on)

        if result:
            self._state = True

    @asyncio.coroutine
    def async_turn_off(self, **kwargs) -> None:
        """Turn the miio device off."""
        result = yield from self._try_command(
            "Turning the miio device off failed.", self._device.off)

        if result:
            self._state = False

    @asyncio.coroutine
    def async_update(self):
        """Update the state of this climate device."""
        try:
            state = yield from self.hass.async_add_job(self._device.status)
            _LOGGER.debug("new state: %s", state)

            self._available = True
            self._last_on_operation = HVACMode[state.mode.name].value
            if state.power == "off":
                self._hvac_mode = HVAC_MODE_OFF
                self._state = False
            else:
                self._hvac_mode = self._last_on_operation
                self._state = True
            self._target_temperature = state.target_temp
            self._current_temperature = state.temperature
            self._fan_mode = FanSpeed(state.wind_level).name
            self._aux_heat = state.is_aux_heat
            self._swing_mode = SwingMode(state.swing).name
            self._state_attrs.update({
                ATTR_TEMPERATURE: state.target_temp,
                ATTR_SWING_MODE: state.swing,
                ATTR_FAN_MODE: state.wind_level,
                ATTR_HVAC_MODE: state.mode.name.lower() if self._state else "off"
            })
        except DeviceException as ex:
            self._available = False
            _LOGGER.error("Got exception while fetching the state: %s", ex)

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_FLAGS

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self._min_temp

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self._max_temp

    @property
    def should_poll(self):
        """Return the polling state."""
        return True

    @property
    def unique_id(self):
        """Return an unique ID."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the climate device."""
        return self._name

    @property
    def available(self):
        """Return true when state is known."""
        return self._available

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temperature

    @property
    def last_on_operation(self):
        """Return the last operation when the AC is on (ie heat, cool, fan only)"""
        return self._last_on_operation

    @property
    def hvac_mode(self):
        """Return new hvac mode ie. heat, cool, fan only."""
        return self._hvac_mode

    @property
    def hvac_modes(self):
        """Return the list of available hvac modes."""
        return [mode.value for mode in HVACMode]

    @property
    def swing_mode(self):
        """Return the current swing setting."""
        return self._swing_mode

    @property
    def swing_modes(self):
        """List of available swing modes."""
        return [mode.name for mode in SwingMode]

    @property
    def fan_mode(self):
        """Return fan mode."""
        return self._fan_mode

    @property
    def fan_modes(self):
        """Return the list of available fan modes."""
        return [speed.name for speed in FanSpeed]

    @property
    def preset_modes(self) -> Optional[List[str]]:
        return ["none", "silence", "comfort"]

    @property                                                         
    def is_aux_heat(self) -> Optional[bool]:                                                               
        return self._aux_heat  

    @asyncio.coroutine
    def async_set_temperature(self, **kwargs):
        """Set target temperature."""
        if self._hvac_mode == HVAC_MODE_OFF or self._hvac_mode == HVAC_MODE_FAN_ONLY:
            return;

        if kwargs.get(ATTR_TEMPERATURE) is not None:
            self._target_temperature = kwargs.get(ATTR_TEMPERATURE)
        if kwargs.get(ATTR_HVAC_MODE) is not None:
            self._hvac_mode = OperationMode(kwargs.get(ATTR_HVAC_MODE))

        yield from self._try_command(
            "Setting temperature of the miio device failed.",
            self._device.set_temperature, self._target_temperature)

    @asyncio.coroutine
    def async_set_preset_mode(self, preset_mode: str) -> None:
        yield from self._try_command(
            "Setting temperature of the miio device failed.",
            self._device.set_preset_mode, preset_mode)

    @asyncio.coroutine
    def async_turn_aux_heat_on(self) -> None:
        yield from self._try_command(
            "turn_aux_heat_on of the miio device failed.",
            self._device.turn_aux_heat_on)

    @asyncio.coroutine
    def async_turn_aux_heat_off(self) -> None:
        yield from self._try_command(
            "turn_aux_heat_off of the miio device failed.",
            self._device.turn_aux_heat_off)

    @asyncio.coroutine
    def async_set_swing_mode(self, swing_mode):
        """Set the swing mode."""
        if self.supported_features & SUPPORT_SWING_MODE == 0:
            return

        self._swing_mode = SwingMode[swing_mode.title()].name

        yield from self._try_command(
            "Setting swing mode of the miio device failed.",
            self._device.set_swing, self._swing_mode == SwingMode.On.name)

    @asyncio.coroutine
    def async_set_fan_mode(self, fan_mode):
        """Set the fan mode."""
        if self.supported_features & SUPPORT_FAN_MODE == 0:
            return

        if self._hvac_mode == HVAC_MODE_DRY:
            return

        self._fan_mode = FanSpeed[fan_mode.title()].name
        fan_mode_value = FanSpeed[fan_mode.title()].value

        yield from self._try_command(
            "Setting fan mode of the miio device failed.",
            self._device.set_wind_level, fan_mode_value)

    @asyncio.coroutine
    def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        if hvac_mode == HVAC_MODE_OFF:
            result = yield from self._try_command(
                "Turning the miio device off failed.", self._device.off)
            if result:
                self._state = False
                self._hvac_mode = HVAC_MODE_OFF
        else:
            if self._hvac_mode == HVAC_MODE_OFF:
                result = yield from self._try_command(
                    "Turning the miio device on failed.", self._device.on)
                if not result:
                    return
            self._hvac_mode = HVACMode(hvac_mode).value
            self._state = True
            result = yield from self._try_command(
                "Setting hvac mode of the miio device failed.",
                self._device.set_mode, OperationMode[self._hvac_mode.title()])
            if result:
                self.async_update();

