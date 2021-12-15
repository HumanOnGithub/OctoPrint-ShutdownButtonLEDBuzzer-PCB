# coding=utf-8

"""
Copyright (C) 2021 Daniele Borgo

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from __future__ import absolute_import
import json
import octoprint.plugin
import os
import subprocess
from time import sleep
from gpiozero import Button, Buzzer, LED

__plugin_pythoncompat__ = ">=3,<4"  # only python 3

DEFAULT_BUTTON_PIN = 26
DEFAULT_LED_PIN = 6
DEFAULT_BUZZER_PIN = 13
DEFAULT_BEEP_MS = 50
DEFAULT_BEEPS_ON_STARTUP = 2
DEFAULT_BEEPS_ON_SHUTDOWN = 3
DEFAULT_BEEPS_ON_PRESSED = 1
DEFAULT_EN = True
OP_SHUTDOWN_COMMAND = "sudo service octoprint stop"
PI_SHUTDOWN_COMMAND = "sudo shutdown -h now"
I2C_STATUS_COMMAND = "raspi-config nonint get_i2c"
SPI_STATUS_COMMAND = "raspi-config nonint get_spi"
SERVICE_ENABLE_OUT = "0"


class ShutdownButtonLEDBuzzerPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ShutdownPlugin,
    octoprint.plugin.SimpleApiPlugin
):

    def __init__(self):
        super().__init__()
        self.__button_pin = None
        self.__led_pin = None
        self.__buzzer_pin = None
        self.__beep_ms = None
        self.__beeps_on_startup = None
        self.__beeps_on_shutdown = None
        self.__beeps_on_pressed = None
        self.__is_button_en = None,
        self.__is_led_en = None,
        self.__is_buzzer_en = None

        self.__button = None
        self.__led = None
        self.__buzzer = None

    def on_after_startup(self):
        self.__load_settings()
        self.__setup()
        self._logger.info('ShutdownButtonLEDBuzzerPlugin ready')

    def __load_settings(self):
        # Avoid errors in case of memory saved data corruption
        self.__button_pin = self.__pick_not_none_int("button_pin", DEFAULT_BUTTON_PIN)
        self.__led_pin = self.__pick_not_none_int("led_pin", DEFAULT_LED_PIN)
        self.__buzzer_pin = self.__pick_not_none_int("buzzer_pin", DEFAULT_BUZZER_PIN)
        self.__beep_ms = self.__pick_not_none_int("beep_ms", DEFAULT_BEEP_MS)
        self.__beeps_on_startup = self.__pick_not_none_int("beeps_on_startup", DEFAULT_BEEPS_ON_STARTUP)
        self.__beeps_on_shutdown = self.__pick_not_none_int("beeps_on_shutdown", DEFAULT_BEEPS_ON_SHUTDOWN)
        self.__beeps_on_pressed = self.__pick_not_none_bool("beeps_on_pressed", DEFAULT_BEEPS_ON_PRESSED)
        self.__is_button_en = self.__pick_not_none_bool("is_button_en", DEFAULT_EN)
        self.__is_led_en = self.__pick_not_none_bool("is_led_en", DEFAULT_EN)
        self.__is_buzzer_en = self.__pick_not_none_bool("is_buzzer_en", DEFAULT_EN)

    def __pick_not_none_int(self, name, default):
        value = self._settings.get_int([name])
        return value if value is not None else default

    def __pick_not_none_bool(self, name, default):
        value = self._settings.get_boolean([name])
        return value if value is not None else default

    def __setup(self):
        #  Set the button with a pull-up resistor, so it's measurable through a tester
        self.__close_component(self.__button)
        if self.__is_button_en:
            self.__button = Button(self.__button_pin, pull_up=True, bounce_time=1)
            self.__button.when_pressed = lambda shutdown: self.__shutdown()
        else:
            self.__button = None

        #  Set the status LED
        self.__close_component(self.__led)
        if self.__is_led_en:
            self.__led = LED(self.__led_pin)
            self.__led.on()
        else:
            self.__led = None

        #  Set the buzzer
        self.__close_component(self.__buzzer)
        if self.__is_buzzer_en:
            self.__buzzer = Buzzer(self.__buzzer_pin)
            self.__emit_beep(self.__beeps_on_startup)
        else:
            self.__buzzer = None

    def __shutdown(self):
        self._logger.info("Shutdown command received")
        sleep(1)
        self.__emit_beep(self.__beeps_on_pressed)
        os.system(OP_SHUTDOWN_COMMAND)
        os.system(PI_SHUTDOWN_COMMAND)

    def __emit_beep(self, n: int):
        for i in range(n):
            self.__buzzer.on()
            sleep(self.__beep_ms / 1000.0)
            self.__buzzer.off()
            sleep(self.__beep_ms / 1000.0)

    @staticmethod
    def __close_component(component):
        if component is not None:
            component.close()

    def on_shutdown(self):
        self.__close_component(self.__button)
        self.__emit_beep(self.__beeps_on_shutdown)
        self.__close_component(self.__buzzer)
        # LED is not turned off since it has to indicate the Raspberry GPIO shutdown
        self._logger.info("Plugin closed")

    def get_settings_defaults(self):
        return dict(
            button_pin=DEFAULT_BUTTON_PIN,
            buzzer_pin=DEFAULT_BUZZER_PIN,
            led_pin=DEFAULT_LED_PIN,
            beep_ms=DEFAULT_BEEP_MS,
            beeps_on_startup=DEFAULT_BEEPS_ON_STARTUP,
            beeps_on_shutdown=DEFAULT_BEEPS_ON_SHUTDOWN,
            beeps_on_pressed=DEFAULT_BEEPS_ON_PRESSED,
            is_button_en=DEFAULT_EN,
            is_led_en=DEFAULT_EN,
            is_buzzer_en=DEFAULT_EN
        )

    def on_settings_save(self, data):
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self.__load_settings()
        self.__setup()

    def on_api_get(self, request):
        self._logger.info("Refresh request received")
        return json.dumps({
            'i2c_status': ShutdownButtonLEDBuzzerPlugin.__get_i2c_status(),
            'spi_status': ShutdownButtonLEDBuzzerPlugin.__get_spi_status()
        })

    @staticmethod
    def __get_i2c_status():
        return ShutdownButtonLEDBuzzerPlugin.__get_service_status(I2C_STATUS_COMMAND)

    @staticmethod
    def __get_spi_status():
        return ShutdownButtonLEDBuzzerPlugin.__get_service_status(SPI_STATUS_COMMAND)

    @staticmethod
    def __get_service_status(command: str):
        try:
            out = subprocess.run(command.split(), capture_output=True).stdout.decode("utf-8").strip()
            return "enabled" if (out == SERVICE_ENABLE_OUT) else "disabled"
        except FileNotFoundError:
            return "undefined"

    def get_template_configs(self):
        return [
            #  dict(type="settings", custom_bindings=False)
        ]

    def get_assets(self):
        # Define your plugin's asset files to automatically include in the
        # core UI here.
        return {
            "js": ["js/ShutdownButtonLEDBuzzer.js"],
            "less": ["less/ShutdownButtonLEDBuzzer.less"],
            "css": ["css/ShutdownButtonLEDBuzzer.css"]
        }

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
        # for details.
        return {
            "ShutdownButtonLEDBuzzer": {
                "displayName": "Shutdownbuttonledbuzzer Plugin",
                "displayVersion": self._plugin_version,

                # version check: github repository
                "type": "github_release",
                "user": "danieleborgo",
                "repo": "OctoPrint-ShutdownButtonLEDBuzzer",
                "current": self._plugin_version,

                # update method: pip
                "pip": "https://github.com/danieleborgo/OctoPrint-ShutdownButtonLEDBuzzer/archive/{target_version}.zip",
            }
        }


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = ShutdownButtonLEDBuzzerPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }