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
  import argparse, config

  ap = argparse.ArgumentParser()
  ap.add_argument("-c", "--config",
      dest = "config_file",
      help = "use CONFIG_FILE as the configuration file instead of the default")

  args = ap.parse_args()

  cfg = config.get_config_dict(args.config_file)

  print("Starting calibration.")

  # how many seconds to average each measurement for
  AVG_TIME = 10.

  s = sensor.Sensor(cfg)

  instructions = [
      #("coffee_empty_value", "Remove the decanter from the coffee machine and press enter."),
      ("coffee_empty_decanter_value", "Place an empty decanter on to the decanter tray and press enter."),
      ("coffee_full_value", "Now fill up the decanter completely, place it on the tray and press enter."),
      #("coffee_start_value", "Fill the water tank and press enter."),
      ]

  calibration = {}


  try:
    for param, msg in instructions:
      input(msg + "\n")
      print("Calibrating (averaging for {} seconds)...".format(AVG_TIME))
      poll_result = s.poll(averaging_time = AVG_TIME, avg_interval = 0.001) #TODO: adjust these timings
      rawValue = poll_result["rawValue"]
      std = poll_result["std"]

      #sys.stdout.write(fmt.format(rawValue, timestamp) + "\r")
      #sys.stdout.flush()

      calibration[param] = (rawValue, std)
  except KeyboardInterrupt:
    pass

  finally:
    sensor.driver.cleanup()

  print("Finished. Your calibration parameters are:")
  for k, v in calibration.items():
    print("{}: {} (std: {} ({} %))".format(k, v[0], v[1], v[1] /v[0] * 100))
