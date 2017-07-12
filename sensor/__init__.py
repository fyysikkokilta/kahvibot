"""
The package 'sensor' is responsible for handling
sensor input i.e. reading the FSR.

Needs to be run as root to access the GPIO pins.

Mostly copied from https://gist.github.com/ladyada/3151375
"""



import time, os, sys, syslog
try:
  import config
except ImportError:
  print("Could not import config, try adding the kiltiskahvi folder to your PYTHONPATH. Exiting.")
  sys.exit(1)

# fall back to randomly generated sensor values if GPIO is not available
try:
  import RPi.GPIO as GPIO
except ImportError:
  syslog.syslog(syslog.LOG_WARNING, "sensor: WARNING: no RPi module available, falling back to dummy GPIO")

  import random

  class GPIO_dummy():

    # this is quite dirty
    def input(self, foo):
      return random.randint(0,1)

    # override all other methods to return 0
    def __getattr__(self, *a):
      return lambda *x: 0


  GPIO = GPIO_dummy()

GPIO.setmode(GPIO.BCM)

# pin setup constants. BCM numbers. see also: http://pinout.xyz
#TODO: should these be read from the config?
SPICLK = 12
SPIMISO = 5
SPIMOSI = 6
SPICS = 26
#mcp = Adafruit_MCP3008.MCP3008(clk = SPICLK, cs = SPICS, miso = SPIMISO, mosi = SPIMOSI)


class Sensor():
  # set up SPI interface pins and read configuration
  def __init__(self, cfg_dict = None):

    if cfg_dict is None:
      # use default configuration
      cfg_dict = config.get_config_dict()

    self.calibration = cfg_dict["calibration"]

    self.averaging_time = float(cfg_dict["general"]["averaging_time"])

    # this attribute can be used to check if the GPIO module is working
    self.is_dummy = not GPIO.__name__ == "RPi.GPIO"

    GPIO.setup(SPIMOSI, GPIO.OUT)
    GPIO.setup(SPIMISO, GPIO.IN)
    GPIO.setup(SPICLK, GPIO.OUT)
    GPIO.setup(SPICS, GPIO.OUT)
  
  
  # read from  the ADC
  def _read_adc(self, adc_num = 0, 
      clockpin = SPICLK, mosipin = SPIMOSI, misopin = SPIMISO, cspin = SPICS): 

    # helper function for advancing the ADC clock by one
    def adc_tick(clk = SPICLK):
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
      adc_tick(clockpin)
  
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
  Returns: a dictionary containing the averaged raw sensor value and the no. of
  cups we have determined to be in the coffee machine.
  """
  def poll(self, averaging_time = None, avg_interval = 0.01):
    if not averaging_time:
      averaging_time = self.averaging_time

    fun = self._read_adc
    #fun = self._dummy_adc
    start = time.time()
    raw_value = 0
    n = 0
    while time.time() - start < averaging_time:
      raw_value += fun()
      n += 1
      time.sleep(avg_interval)

    raw_value /= 1.0 * n

    nCups = self.compute_nCups(raw_value)

    # is there coffee?
    isCoffee = nCups > 0.

    result = {}

    result["rawValue"] = raw_value
    result["nCups"] = nCups
    result["isCoffee"] = isCoffee

    # TODO: compute standard deviation also.
    #result["std"] = ???
    #print("poll result: {} ({} averages)".format(res, n))
    return result

  """
  Compute the number of cups a given raw sensor value corresponds to, using the
  calibration parameters.
  """
  def compute_nCups(self, raw_value):
    #import warnings
    #raise NotImplementedError("No. of cups computation not implemented yet.")
    return raw_value / 1024. * 10

if __name__ == "__main__":

  cfg = config.get_config_dict()

  s = Sensor(cfg)

  try:

    # threshold value for debouncing
    epsilon = 2

    nCups = 0.
    rawValue = 0

    while True:
      res = s.poll(averaging_time = 0.01, avg_interval = 0.001)
      rawValue_new = int(res["rawValue"])
      nCups_new = res["nCups"]
      if abs(rawValue_new - rawValue) > epsilon:
        rawValue = rawValue_new
        nCups = nCups_new

      fmt = "{:0>4} {:>7.1f} {:>12.1f}"
      sys.stdout.write(fmt.format(rawValue, nCups, time.time()) + "\r")
      sys.stdout.flush()
      time.sleep(0.05)

  except KeyboardInterrupt:
    GPIO.cleanup()
    raise
