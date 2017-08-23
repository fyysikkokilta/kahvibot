"""
Driver for the HX711N load cell amplifier.
Based mostly on
https://gist.github.com/Richard-Major/64e94338c2d08eb1221c2eca9e014362
"""

import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)

# TODO: read these from the config?
CLKPIN = 6
DATAPIN = 26
