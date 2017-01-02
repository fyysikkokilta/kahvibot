"""
A small script for calibration. Creates a csv file specified by FILENAME
in the same folder as the script and stores sensor values in it at a 
high frequency while displaying the current sensor value in real time.
After pressing ctrl+C, it attempts to plot the collected data using numpy and
matplotlib, but does nothing if these are not available.
"""

import sensor
import os, sys
import time

if __name__ == "__main__":
  os.chdir(os.path.dirname(__file__))
  FILENAME = "calibration.csv"
  SEP = "," # separator used for csv

  try:
    answer = None
    if os.path.exists(FILENAME):
      answer = raw_input("Warning: overwrite file '{}' (y/n)? ".format(FILENAME))
    if answer is not None and "n" in answer:
      print("Quitting. Not overwriting '{}'.".format(FILENAME))
      sys.exit()

    elif answer is not None and "y" in answer:
      print("Overwriting '{}'".format(FILENAME))

    s = sensor.Sensor()

    with open(FILENAME, "w") as f:
      while True:
        sensor_value = s.poll()

  except KeyboardInterrupt:
    pass

  print("Plotting data if possible...")
  try:
    import numpy as np
    import matplotlib.pyplot as plt

    data = np.loadtxt(FILENAME, delimiter = SEP)

    plt.plot(data[:, 0], data[:, 1])

    plt.show()

  except ImportError as e:
    print("{} not found, not plotting.".format(e.name))


