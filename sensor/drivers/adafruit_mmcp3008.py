"""
Driver for reading the Adafruit FSR using the MCP3008 ADC. Based on 
https://acaird.github.io/computers/2015/01/07/raspberry-pi-fsr and
https://gist.github.com/ladyada/3151375
"""

def read_adc(self, adc_num = 0, 
    clockpin = SPICLK, mosipin = SPIMOSI, misopin = SPIMISO, cspin = SPICS): 
  raise NotImplementedError
