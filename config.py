"""
This module is responsible for handling configuration and files related to it,
including calibration parameters.
"""

import configparser
from os import path
import syslog

"""
Default options
"""
_CONFIG_DEFAULTS = {
      "telegram" : {
        "bot_token" : "",
        "group_trigger_threshold" : 20,
      },

    }

"""
Initialize a configparser dictionary with given or default filename and
return it
"""
def get_config_dict(filename = None):

  if filename is None:
    cfg_path = path.dirname(__file__)
    filename = path.join(cfg_path, "config.ini")

  cp = configparser.ConfigParser()

  # read default values from dict if they are not given in the config file.
  cp.read_dict(_CONFIG_DEFAULTS)

  if not path.exists(filename):
    raise IOError("Configuration file {} does not exist.".format(filename))

  cp.read(filename)
  syslog.syslog(syslog.LOG_INFO, "config: Using configuration file " + filename)

  # check for placeholder telegram bot token
  if set(cp["telegram"]["bot_token"]) == set("X"):
    cp["telegram"]["bot_token"] = ""

  return cp


if __name__ == "__main__":
  import argparse
  from pprint import pprint

  ap = argparse.ArgumentParser()
  ap.add_argument("-c", "--config",
      dest = "config_file",
      help = "use CONFIG_FILE as the configuration file instead of the default")

  args = ap.parse_args()

  cfg = get_config_dict(args.config_file)

  for sec in cfg.sections():
    print("{}:".format(sec))
    pprint(list(cfg[sec].items()))
    print("")
