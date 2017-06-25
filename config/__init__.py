"""
This module is responsible for handling configuration and files related to it,
including calibration parameters.
"""

import configparser
import os, syslog


"""
Default options
"""
#TODO: more default options...
_CONFIG_DEFAULTS = {
      "general": {
          "poll_interval": 10,
          "averaging_time": 9,
      },

      "paths": {
        "root": os.getcwd(),

        "stdin": "/dev/null",

        "stdout": os.path.join(
          os.path.dirname(os.path.dirname(__file__)),
          "log/stdout.log"),

        "stderr" : os.path.join(
          os.path.dirname(os.path.dirname(__file__)),
          "log/stderr.log"),

        # default database path is ../db/test.db relative to this file
        "db_path": os.path.join(
          os.path.dirname(os.path.dirname(__file__)),
          "db/test.db"),

        "kahvid_pidfile": "/var/run/kahvid.pid",

      },

      "calibration" : {
        "sensor_min_value" : 0,
        "sensor_max_value" : 1024,
      },

    }

"""
Initialize a configparser dictionary with given or default filename and
return it
"""
def get_config_dict(filename = None):

  if filename is None:
    cfg_path = os.path.dirname(__file__)
    filename = os.path.join(cfg_path, "config.ini")

  cp = configparser.ConfigParser() #_CONFIG_DEFAULTS)

  # read default values from dict if they are not given in the config file.
  cp.read_dict(_CONFIG_DEFAULTS)

  syslog.syslog(syslog.LOG_INFO, "config: Using configuration file " + filename)
  cp.read(filename)

  return cp

  #def __getitem__(self, i): self.configparser.


if __name__ == "__main__":
  import argparse

  ap = argparse.ArgumentParser()
  ap.add_argument("-c", "--config",
      dest = "config_file",
      help = "use CONFIG_FILE as the configuration file instead of the default")

  args = ap.parse_args()

  cfg = get_config_dict(args.config_file)
  print(str(cfg))
