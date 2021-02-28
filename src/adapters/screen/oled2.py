# -*- coding:utf-8 -*-

from luma.core.interface.serial import i2c, spi
from luma.core.render import canvas
from luma.oled.device import sh1106
import RPi.GPIO as GPIO
from time import sleep
from collections import deque
import time
import subprocess
import os
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from enum import Enum
from pymemcache import serde
from pymemcache.client.base import Client as MemCclient
import configparser
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class PIN(Enum):
    RST_PIN = 25
    CS_PIN = 8
    DC_PIN = 24
    JS_U_PIN = 6
    JS_D_PIN = 19
    JS_L_PIN = 5
    JS_R_PIN = 26
    JS_P_PIN = 13
    BTN1_PIN = 21
    BTN2_PIN = 20
    BTN3_PIN = 16

SCREEN_LINES = 4
SCREEN_SAVER = 30.0
CHAR_WIDTH = 19
font = ImageFont.load_default()
#font = ImageFont.truetype(globalParameters.font_text, size=10)
fontawesome = ImageFont.truetype(f"{os.path.dirname(os.path.realpath(__file__))}/fonts/fontawesome-webfont.ttf", size=10)
width, height = 128, 64
x0, y0 = 0, -2

class OLED():

    def __init__(self, config):
        # init GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PIN.JS_U_PIN.value, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PIN.JS_D_PIN.value, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PIN.JS_L_PIN.value, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PIN.JS_R_PIN.value, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PIN.JS_P_PIN.value, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PIN.BTN1_PIN.value, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PIN.BTN2_PIN.value, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PIN.BTN3_PIN.value, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.config = config
        self.currentUser = 'DEFAULT'
        self.turn_on_oled()
        self.screen_state = 1
        self.stamp = time.time()
        self.start = time.time()
        self.currentPage = 0
        self.WRValues = None
        self.pirowflocmd = ""
        self.status = ""
        try:
            self.mcclient = MemCclient('127.0.0.1:11211', serde=serde.pickle_serde, key_prefix=b'pirowflo_')
            self.mcclient.version()
        except Exception:
            self.mcclient = None
            logger.info("memcached not listening on 127.0.0.1:11211. No recording going to happen")
        self.currentSelection = type('XY', (object,), {"x": 1, "y": 1})()  # WARN: we select starting at 1 in this case
        self.Menu = {
            0: {"id": 0, "title": "-----PiRowFlo-----", "JS_U_PIN": ["SELECT_DEC_Y", 1], "JS_D_PIN": ["SELECT_INC_Y", 3],
                "JS_P_PIN": ["SELECT", self.func_action_MAIN],
                "TYPE": "MENU", "CONTENT": self.func_draw_UpDownMenu, "ITEMS": ["Rowing", "System", "Power"]},
            10: {"id": 10, "title": "Rowing", "JS_U_PIN": ["SELECT_DEC_Y", 1], "JS_D_PIN": ["SELECT_INC_Y", 5],
                 "JS_P_PIN": ["SELECT", self.func_action_RowingMenu], "JS_L_PIN": ["LINK", 0],
                 "TYPE": "MENU", "CONTENT": self.func_draw_RowingMenu,
                 "ITEMS": ["Start Rowing", "Stop Rowing", "Show Stats", "Settings", "Select User"]},
            100: {"id": 100, "title": "-----Rowing Stats 1----", "JS_L_PIN": ["LINK", 10], "JS_R_PIN": ["LINK", 101],
                 "TYPE": "PAGE", "CONTENT": self.func_draw_RowingStats12},
            101: {"id": 101, "title": "-----Rowing Stats 2----", "JS_L_PIN": ["LINK", 100], "TYPE": "PAGE",
                 "CONTENT": self.func_draw_RowingStats12},
            110: {"id": 110, "title": "--Rowing Settings--", "JS_L_PIN": ["LINK", 10],
                "JS_U_PIN": ["SELECT_DEC_Y", 1], "JS_D_PIN": ["SELECT_INC_Y", 5],
                "JS_P_PIN": ["SELECT", self.func_action_RowingSettings],
                "TYPE": "MENU", "CONTENT": self.func_draw_RowingSettings,
                "ITEMS": ["SmartRow", "S4 Monitor", "Bluetooth LE", "Ant+", "FIT+GC"]},
            20: {"id": 20, "title": "System Stats", "JS_L_PIN": ["LINK", 0], "JS_R_PIN": ["LINK", 21],
                 "TYPE": "PAGE", "CONTENT": self.func_draw_STATS},
            21: {"id": 21, "title": "System Stats", "JS_L_PIN": ["LINK", 20],
                 "TYPE": "PAGE", "CONTENT": self.func_draw_STATS},
            30: {"id": 30, "title": "Power", "JS_L_PIN": ["LINK", 0],
                 "JS_U_PIN": ["SELECT_DEC_Y", 1], "JS_D_PIN": ["SELECT_INC_Y", 3],
                 "JS_P_PIN": ["SELECT", self.func_action_POWER],
                 "TYPE": "MENU", "CONTENT": self.func_draw_POWER, "ITEMS": ["Shutdown", "Reboot", "Refresh"]},
        }

        GPIO.add_event_detect(PIN.BTN1_PIN.value, GPIO.RISING, callback=self.main_fun, bouncetime=200)
        GPIO.add_event_detect(PIN.BTN2_PIN.value, GPIO.RISING, callback=self.main_fun, bouncetime=200)
        GPIO.add_event_detect(PIN.BTN3_PIN.value, GPIO.RISING, callback=self.main_fun, bouncetime=200)
        GPIO.add_event_detect(PIN.JS_L_PIN.value, GPIO.RISING, callback=self.main_fun, bouncetime=200)
        GPIO.add_event_detect(PIN.JS_R_PIN.value, GPIO.RISING, callback=self.main_fun, bouncetime=200)
        GPIO.add_event_detect(PIN.JS_U_PIN.value, GPIO.RISING, callback=self.main_fun, bouncetime=200)
        GPIO.add_event_detect(PIN.JS_D_PIN.value, GPIO.RISING, callback=self.main_fun, bouncetime=200)
        GPIO.add_event_detect(PIN.JS_P_PIN.value, GPIO.RISING, callback=self.main_fun, bouncetime=200)

    # HELPER
    def func_draw_UpDownMenu(self, currentMenuItem, back=False):
        with canvas(self.device) as draw:
            draw.text((x0, y0), currentMenuItem.get("title"), font=font, fill=255)
            LINES = currentMenuItem.get("ITEMS").copy()
            LINES = [''.join(['> ', line]) if idx == self.currentSelection.y else ''.join(['  ', line])
                     for idx, line in enumerate(LINES, start=1)]
            if self.currentSelection.y > 4:
                del(LINES[:self.currentSelection.y-4])
            for i, line in enumerate(LINES[:4], start=1):
                self.draw_line(draw, i, line)
            arrow_pointer = self.currentSelection.y if self.currentSelection.y <= 4 else 4
            self.draw_arrow(draw, row=arrow_pointer, fill=True)
            if back:
                self.draw_back(draw)

    # MAIN screen actions
    def func_action_MAIN(self):
        if self.currentSelection.y == 1:
            self.currentPage = 10
        elif self.currentSelection.y == 2:
            self.currentPage = 20
        elif self.currentSelection.y == 3:
            self.currentPage = 30
        self.currentSelection.x, self.currentSelection.y = 1, 1

    def func_draw_RowingMenu(self, currentMenuItem, back=True):
        self.func_draw_UpDownMenu(currentMenuItem, back=back)

    def func_action_RowingMenu(self):  # ["Start Rowing", "Stop Rowing", "Show Stats", "Settings", "Select User"]},
        if self.currentSelection.y == 1 and self.pirowflocmd == "":
            self.createPiRowFlocmd()
            command = ["supervisorctl", "start", self.pirowflocmd]
            self.status = str(subprocess.run(command,capture_output=True).stdout)[2:-3].strip().split(' ')[1]
            self.Menu[10]['title'] = "Rowing ("+self.status+")"
        elif self.currentSelection.y == 2 and self.pirowflocmd != "":
            command = ['supervisorctl', 'stop', self.pirowflocmd]
            self.status = str(subprocess.run(command,capture_output=True).stdout)[2:-3].strip().split(' ')[1]
            self.pirowflocmd = ""
            self.Menu[10]['title'] = "Rowing ("+self.status+")"
        elif self.currentSelection.y == 3:
            self.currentPage = 100
            self.currentSelection.x, self.currentSelection.y = 1, 1
        elif self.currentSelection.y == 4:
            self.currentPage = 110
            self.currentSelection.x, self.currentSelection.y = 1, 1
        elif self.currentSelection.y == 5:
            self.currentPage = 10  # not yet implemented

    def func_draw_RowingStats12(self, currentMenuItem):
        with canvas(self.device) as draw:
            TITLE = currentMenuItem.get("title")
            if self.WRValues and currentMenuItem.get("id") == 100:
                LINE1 = "Stroke rate: " + str(self.WRValues['stroke_rate'])
                LINE2 = "Total strokes: " + str(self.WRValues['total_strokes'])
                LINE3 = "Distance: " + str(self.WRValues['total_distance_m'])
                LINE4 = "Pace: " + str(self.WRValues['instantaneous_pace'])
            elif self.WRValues and currentMenuItem.get("id") == 101:
                LINE1 = "HRM: " + str(self.WRValues['heart_rate'])
                LINE2 = "Elapsed time: " + str(self.WRValues['elapsedtime'])
                LINE3 = "Power: " + str(self.WRValues['watts_avg'])
                LINE4 = "stroke length: " + str(self.WRValues['stroke_length'])
            else:
                LINE1, LINE2, LINE3, LINE4 = "", "", "", ""
            if currentMenuItem.get("id") == 100:
                draw.rectangle((35, 61, 74, 63), outline=255, fill=1)
                draw.rectangle((75, 61, 92, 63), outline=255, fill=0)
                self.draw_back(draw)
                self.draw_pagearrow(draw, direction="right", text="page 2")
            else:
                draw.rectangle((35, 61, 52, 63), outline=255, fill=0)
                draw.rectangle((53, 61, 92, 63), outline=255, fill=1)
                self.draw_pagearrow(draw, direction="left", text="page 1")
            draw.text((x0, y0), TITLE, font=font, fill=255)
            self.draw_line(draw, 1, LINE1)
            self.draw_line(draw, 2, LINE2)
            self.draw_line(draw, 3, LINE3)
            self.draw_line(draw, 4, LINE4)

    # RowingSettings screen actions and drawings
    def func_action_RowingSettings(self):
        if self.currentSelection.y == 1:  # SR
            config.set(self.currentUser, 'interface', 'sr')
        elif self.currentSelection.y == 2:  # S4
            config.set(self.currentUser, 'interface', 's4')
        elif self.currentSelection.y == 3:  # BLE
            ble_state = 'False' if config[self.currentUser].getboolean('ble', fallback=False) else 'True'
            config.set(self.currentUser, 'ble', ble_state)
        elif self.currentSelection.y == 4:  # Ant
            ant_state = 'False' if config[self.currentUser].getboolean('ant', fallback=False) else 'True'
            config.set(self.currentUser, 'ant', ant_state)
        elif self.currentSelection.y == 5:  # FIT
            fit_state = 'False' if config[self.currentUser].getboolean('fit', fallback=False) else 'True'
            config.set(self.currentUser, 'fit', fit_state)

    def get_rower_config_state(self,i):
        interface = config[self.currentUser].get('interface', 'sr')
        if (i == 1 and interface == 'sr') \
        or (i == 2 and interface == 's4') \
        or (i == 3 and config[self.currentUser].getboolean('ble', fallback=False)) \
        or (i == 4 and config[self.currentUser].getboolean('ant', fallback=False)) \
        or (i == 5 and config[self.currentUser].getboolean('fit', fallback=False)):
            return 1
        else:
            return 0

    def func_draw_RowingSettings(self, currentMenuItem):
        with canvas(self.device) as draw:
            draw.text((x0, y0), currentMenuItem.get("title"), font=font, fill=255)
            LINES = currentMenuItem.get("ITEMS").copy()
            removed_lines = 0
            if self.currentSelection.y > 4:
                removed_lines = self.currentSelection.y-4
                del(LINES[:removed_lines])
            for i, line in enumerate(LINES[:4], start=1):
                self.draw_line(draw, i, line, option=self.get_rower_config_state(i + removed_lines))
            arrow_pointer = self.currentSelection.y if self.currentSelection.y <= 4 else 4
            self.draw_arrow(draw, row=arrow_pointer, fill=True, x=95)
            self.draw_back(draw)

    # STATS screen drawing
    def func_draw_STATS(self, currentMenuItem):
        with canvas(self.device) as draw:
            draw.text((x0, y0), currentMenuItem.get("title"), font=font, fill=255)
            if currentMenuItem.get("id") == 20:
                ssid = subprocess.check_output("iwgetid --raw", shell=True)
                freq = subprocess.check_output("iwgetid --freq|sed 's/.*://g'", shell=True)
                LINE1 = subprocess.check_output("hostname -I | awk '{printf \"IP: %s\", $1}'", shell=True)
                LINE2 = subprocess.check_output("df -h / | awk '$NF==\"/\"{printf \"Disk: %s\", $5}'", shell=True)
                LINE3 = f"WiFi: {ssid} {freq}"
                LINE4 = subprocess.check_output(
                    "cat /sys/class/thermal/thermal_zone0/temp | awk '{printf \"Temp:%.1fC\", $1/1000}'",shell=True)
            else:
                LINE1 = subprocess.check_output("top -bn1 | awk 'NR==3{printf \"CPU:%.1f%% idle\", $8}'",shell=True)
                LINE2 = subprocess.check_output("free -mh | awk 'NR==2{printf \"Mem:%s/%s\", $3,$2}'", shell=True)
                LINE3 = subprocess.check_output("ifstat -bT 0.1 1 | awk 'NR==3{printf \"%9.2fKbps %9.2fKbps\",$3,$4}'",
                                                shell=True)
                LINE4 = ""
            if currentMenuItem.get("id") == 20:
                draw.rectangle((35, 61, 74, 63), outline=255, fill=1)
                draw.rectangle((75, 61, 92, 63), outline=255, fill=0)
                self.draw_back(draw)
                self.draw_pagearrow(draw, direction="right", text="page 2")
            else:
                draw.rectangle((35, 61, 52, 63), outline=255, fill=0)
                draw.rectangle((53, 61, 92, 63), outline=255, fill=1)
                self.draw_pagearrow(draw, direction="left", text="page 1")
            self.draw_line(draw, 1, LINE1)
            self.draw_line(draw, 2, LINE2)
            self.draw_line(draw, 3, LINE3)
            self.draw_line(draw, 4, LINE4)

    # POWER screen actions
    def func_action_POWER(self):
        if self.currentSelection.y == 1:
            os.system("sudo shutdown -h now")
        elif self.currentSelection.y == 2:
            os.system("sudo shutdown -r now")
        elif self.currentSelection.y == 3:
            os.system("sudo systemctl restart screen")
        self.currentSelection.x, self.currentSelection.y = 1, 1

    def func_draw_POWER(self, currentMenuItem, back=True):
        self.func_draw_UpDownMenu(currentMenuItem, back=back)

    def trigger_action_and_draw_scn(self, channel):
        currentMenuItem = self.Menu[self.currentPage]
        # Button reactions here...
        if channel > 0 and PIN(channel).name in currentMenuItem:
            # a PIN has triggered and current Menu has an action for it
            action = currentMenuItem[PIN(channel).name]
            if action[0] == "LINK":
                self.currentPage = action[1]
                self.currentSelection.x, self.currentSelection.y = 1, 1  # page has changed, reset selection
            elif action[0] == "SELECT_DEC_X":
                self.currentSelection.x = self.currentSelection.x - 1 \
                    if self.currentSelection.x > action[1] else action[1]
            elif action[0] == "SELECT_INC_X":
                self.currentSelection.x = self.currentSelection.x + 1 \
                    if self.currentSelection.x < action[1] else action[1]
            elif action[0] == "SELECT_DEC_Y":
                self.currentSelection.y = self.currentSelection.y - 1 \
                    if self.currentSelection.y > action[1] else action[1]
            elif action[0] == "SELECT_INC_Y":
                self.currentSelection.y = self.currentSelection.y + 1 \
                    if self.currentSelection.y < action[1] else action[1]
            elif action[0] == "SELECT":  # Item has extra function for select action
                if callable(action[1]):
                    action[1]()  # will run the function stored.. works...
        # now drawing the screens...
        if currentMenuItem.get("CONTENT") and callable(currentMenuItem.get("CONTENT")):
            currentMenuItem.get("CONTENT")(currentMenuItem)  # it is callable...

    def draw_line(self, draw, index, text, option=None):
        text = text[:CHAR_WIDTH] if len(text) > CHAR_WIDTH else text
        x0 = 20
        if option == 1:
            draw.text((2, 11 * index), text="\uf205", font=fontawesome, fill="white")
        elif option == 0:
            draw.text((2, 11 * index), text="\uf204", font=fontawesome, fill="white")
        else:
            x0 = 0
        draw.text((x0, 11 * index), text, font=font, fill=255)

    def draw_arrow(self, draw, row=1, fill=True, x=95, y=11): #x84
        y = y * row
        fill = 1 if fill == True else 0
        draw.polygon([(x, y + 6), (x + 7, y - 1), (x + 7, y + 4), (x + 14, y + 4), (x + 14, y + 8), (x + 7, y + 8),
                      (x + 7, y + 13)], outline=255, fill=fill)

    def draw_back(self,draw):
        self.draw_pagearrow(draw, direction="left", text="back")

    def draw_pagearrow(self, draw, direction="left", text="back"):
        x = 0
        if direction == "left":
            text = "<"+text
        elif direction == "right":
            x = 100
            text += ">"
        draw.text((x, 55), text=text, font=ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSans.ttf', 9),
                  fill=255)

    def main_fun(self, channel):
        self.stamp = time.time()
        if self.mcclient:
            self.WRValues = self.mcclient.get_many((
                'message_time', 'stroke_rate', 'total_strokes', 'total_distance_m',
                'instantaneous_pace', 'speed', 'watts', 'total_kcal', 'total_kcal_hour',
                'total_kcal_min', 'heart_rate', 'elapsedtime', 'work', 'stroke_length',
                'force', 'watts_avg', 'pace_avg'))
            if len(self.WRValues.keys()) > 0:
                HRMValue = self.mcclient.get('HRM_Rate', default=None)
                if HRMValue and HRMValue > 0:
                    self.WRValues['heart_rate'] = HRMValue
        if self.screen_state <= 0:  # Display is off
            if channel > 0:  # A button is pressed, turn on display
                self.turn_on_oled()
                self.screen_state = 1
                self.start = time.time()
        else:  # Display is on
            if (channel == PIN.BTN3_PIN.value) or (
                    (self.stamp - self.start) > SCREEN_SAVER):  # A button is pressed or timed out, turn off display
                self.turn_off_oled()
                self.screen_state = 0
            elif channel > 0:
                self.start = time.time()
                self.trigger_action_and_draw_scn(channel)
            else:  # just refresh screen
                self.trigger_action_and_draw_scn(channel)

    def turn_on_oled(self):
        # Initialize the display...
        self.serial = spi(device=0, port=0, bus_speed_hz=8000000, transfer_size=4096, gpio_DC=PIN.DC_PIN.value,
                          gpio_RST=PIN.RST_PIN.value)
        self.device = sh1106(self.serial, rotate=2)
        self.draw = ImageDraw.Draw(Image.new('1', (width, height)))
        self.draw.rectangle((0, 0, width, height), outline=0, fill=0)

    def turn_off_oled(self):
        GPIO.output(PIN.RST_PIN.value, GPIO.LOW)

    def createPiRowFlocmd(self):
        interface = config[self.currentUser]['interface']
        ble = config[self.currentUser].getboolean('ble', fallback=False)
        ant = config[self.currentUser].getboolean('ant', fallback=False)
        fit = config[self.currentUser].getboolean('fit', fallback=False)
        string = ""
        if interface == 'sr':
            string += "pirowflo_SR_Smartrow_"
        else:
            string += "pirowflo_S4_Monitor_"
        if ble and ant:
            string += "Bluetooth_AntPlus"
        elif ble and not ant:
            string += "Bluetooth_only"
        elif not ble and ant:
            string += "AntPlus_only"
        if fit:
            string += "_Fit"
        self.pirowflocmd = string



config = configparser.ConfigParser()
logger.info(f"looking for rowers.conf in {os.path.join(os.path.dirname(__file__), 'rowers.conf')} " +
            f"and {str(Path.home())}/rowers.conf")
config.read([os.path.join(os.path.dirname(__file__), 'rowers.conf'), str(Path.home()) + '/rowers.conf'])
deque(maxlen=1)
oled = None
loop = True

while True:
    try:
        if not oled:
            oled = OLED(config)
        oled.main_fun(0)
        sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Exiting...")
        break
GPIO.cleanup()

