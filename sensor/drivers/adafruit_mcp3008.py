"""
Driver for reading the Adafruit FSR using the MCP3008 ADC. Based on 
https://acaird.github.io/computers/2015/01/07/raspberry-pi-fsr and
https://gist.github.com/ladyada/3151375
"""

import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)

# pin setup constants. BCM numbers. see also: http://pinout.xyz
#TODO: should these be read from the config?
SPICLK = 12
SPIMISO = 5
SPIMOSI = 6
SPICS = 26

GPIO.setup(SPIMOSI, GPIO.OUT)
GPIO.setup(SPIMISO, GPIO.IN)
GPIO.setup(SPICLK, GPIO.OUT)
GPIO.setup(SPICS, GPIO.OUT)

def read_adc(adc_num = 0,
    clockpin = SPICLK, mosipin = SPIMOSI, misopin = SPIMISO, cspin = SPICS):

    # helper function for advancing the ADC clock by one
    def adc_tick(clk = clockpin):
      GPIO.output(clk, True)
      GPIO.output(clk, False)

    if (adc_num > 7) or (adc_num < 0):
      return -1

    GPIO.output(cspin, True)
    GPIO.output(clockpin, False)
    GPIO.output(cspin, False)

    command_out = adc_num
    command_out |= 0x18 # start bit + single-ended bit (what does this mean?)
    command_out <<= 3

    for i in range(5):
      if(command_out & 0x80):
        GPIO.output(mosipin, True)
      else:
        GPIO.output(mosipin, False)
      command_out <<=1
      adc_tick()

    adc_out = 0
    for i in range(12):
      adc_tick()

      adc_out <<= 1

      if GPIO.input(misopin):
        adc_out |= 0x1

    GPIO.output(cspin, True)
    adc_out >>= 1
    return adc_out


def cleanup():
  GPIO.cleanup()
