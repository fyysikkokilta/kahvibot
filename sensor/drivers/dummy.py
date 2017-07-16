"""
A driver that returns dummy values ranging from zero to 1023 in a manner that
very crudely tries to imitate the dynamics of a coffee maker in use. Useful for
testing when no GPIO is available.
"""

import random
import time
from math import floor, exp

def create_dummy_generator():
    prev = 0
    t = time.time()
    tau = 2.5 * 60
    while True:
      prev =  int(floor(1023 * (1 - exp(-(time.time() - t) / tau))))
      prev += random.randrange(-3, 3)
      prev = max(min(prev, 1023), 0) # clip values

      # 'empty' the coffee maker.
      if prev > 900 and random.expovariate((time.time() - t) / (tau * 2)) > tau * 2:
        t = time.time()
      yield prev

dummy_generator = create_dummy_generator()

def read_adc(**kwargs):
  return dummy_generator.__next__()

# there's nothing to do when cleaning up the dummy driver.
def cleanup():
  return
