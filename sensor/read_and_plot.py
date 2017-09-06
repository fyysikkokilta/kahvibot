"""
A small script that creates a csv file specified by FILENAME in the same folder
as the script and stores sensor values in it at a high frequency while
displaying the current sensor value in real time. After pressing ctrl+C, it
attempts to plot the collected data using numpy and matplotlib, but does
nothing if these are not available. Might be useful for cailbration.
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
      answer = input("Warning: overwrite file '{}' (y/n)? ".format(FILENAME))
    if answer is not None and "n" in answer:
      print("Quitting. Not overwriting '{}'.".format(FILENAME))
      sys.exit()

    elif answer is not None and "y" in answer:
      print("Overwriting '{}'".format(FILENAME))

    s = sensor.Sensor()

    with open(FILENAME, "w") as f:
      while True:
        #TODO: make this less of a hack (currently copied from __name__ == __main__ section of sensor/__init)
        poll_result = s.poll(averaging_time = 0.01, avg_interval = 0.001) #TODO: adjust these timings
        rawValue = poll_result["rawValue"]
        timestamp = time.time()
        txt = SEP.join([str(rawValue), str(timestamp)]) + "\n"
        f.write(txt)
        fmt = "{:0=10} {:>12.1f}"
        sys.stdout.write(fmt.format(rawValue, timestamp) + "\r")
        sys.stdout.flush()
        time.sleep(0.05)

  except KeyboardInterrupt:
    sensor.driver.cleanup()

  except Exception:
    sensor.driver.cleanup()
    raise

  print("\n\nPlotting data if possible...")
  try:
    import numpy as np
    import matplotlib.pyplot as plt

    data = np.loadtxt(FILENAME, delimiter = SEP)

    plt.plot(data[:, 0], data[:, 1])

    plt.show()

  except ImportError as e:
    print("{} not found, not plotting.".format(e.name))


