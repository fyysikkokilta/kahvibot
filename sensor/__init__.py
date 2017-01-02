"""
The package 'sensor' is responsible for handling
sensor input i.e. reading the FSR.

Needs to be run as root to access the GPIO pins.

Mostly copied from https://gist.github.com/ladyada/3151375
"""



import time, os, sys
import config
#TODO: put this under a try-except and fall back to a dummy poll function if 
# GPIO is not available
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)

# pin setup constants. see also: http://pinout.xyz
#TODO: should these be read from the config?
SPICLK = 18
SPIMISO = 23
SPIMOSI = 24
SPICS = 25
#mcp = Adafruit_MCP3008.MCP3008(clk = SPICLK, cs = SPICS, miso = SPIMISO, mosi = SPIMOSI)


class Sensor():
  # set up SPI interface pins and read configuration
  def __init__(self, config):

    self.calibration = config["calibration"]

    GPIO.setup(SPIMOSI, GPIO.OUT)
    GPIO.setup(SPIMISO, GPIO.IN)
    GPIO.setup(SPICLK, GPIO.OUT)
    GPIO.setup(SPICS, GPIO.OUT)
  
  # advance the ADC clock by one
  def _adc_tick(self, clk = SPICLK):
    GPIO.output(clk, True)
    GPIO.output(clk, False)
  
  # read from  the ADC
  def _read_adc(self, adc_num, 
      clockpin = SPICLK, mosipin = SPIMOSI, misopin = SPIMISO, cspin = SPICS): 
  
    if (adc_num > 7) or (adc_num < 0):
      return -1
  
    GPIO.output(cspin, True)
    GPIO.output(clockpin, False)
    GPIO.output(cspin, False)
  
    command_out = adc_num
    command_out |= 0x18 # start bit + single-ended bit (what does this mean?)
    command_out <<= 3
  
    for i in range(5):
      #print(str(bin(command_out & 0x80)) + " " + str(bool(command_out & 0x80)))
      if(command_out & 0x80):
        GPIO.output(mosipin, True)
      else:
        GPIO.output(mosipin, False)
      command_out <<=1
      self._adc_tick()
  
    adc_out = 0
    for i in range(12):
      self._adc_tick(clockpin)
  
      adc_out <<= 1
  
      if GPIO.input(misopin):
        adc_out |= 0x1
  
    GPIO.output(cspin, True)
    adc_out >>= 1
    return adc_out
  
  
  # a function that generates random numbers in the same range
  # as the real adc, for testing purposes.
  
  def _dummy_adc(self):
    import random
    import time
    from math import floor
    prev = 0
    t = time.time()
    while True:
      prev += (random.randrange(100) - 20) * int(floor(time.time() - t))
      prev %= 1024
      t = time.time()
      yield prev
  
  
  """
  The function that returns the sensor value after averaging,
  this is supposed to be called externally.
  """
  #TODO
  def poll(self, averaging_time = 10, avg_interval = 0.01):
    fun = self._read_adc
    #fun = self._dummy_adc
    start = time.time()
    res = 0
    n = 0
    while time.time() - start < averaging_time:
      res += fun()
      n += 1
      time.sleep(avg_interval)
    #res = fun()
    res /= 1.0 * n
    print("poll result: " + str(res) + " ({} averages)".format(n))
    return res

if __name__ == "__main__":
  #tol = 3

  fsr_adc = 0

  s = Sensor()

  try:

    x = 0
    epsilon = 2
    prev_value = 0

    while True:
      adc_out = s._read_adc(fsr_adc) #, SIPCLK, SPIMOSI, SPIMISO, SPICS)
      curr_value = prev_value if abs(prev_value - adc_out) < epsilon else adc_out
      #adc_out = mcp.read_adc(1)
      if False:
        fmt = "{:010b}"
      else:
        fmt = "{:0>4}"
      #sys.stdout.write((" " if x % 2 else "x") + fmt.format(adc_out) + "\r")
      sys.stdout.write(fmt.format(curr_value) + "\r")
      #sys.stdout.write((" " if x % 2 else "x") + "{:0>5}x".format(adc_out) + "\r")
      #sys.stdout.write("{:0>4}\n".format(adc_out))
      sys.stdout.flush()
      x += 1
      time.sleep(0.05)

  except KeyboardInterrupt:
    GPIO.cleanup()
    raise
