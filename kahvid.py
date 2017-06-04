#!/usr/bin/env python3

"""
The main measurement program, responsible for polling the sensor periodically 
and inserting the results into a database. 

Must be run as root (to access the GPIO and to create a PID).
"""

#import db, sensor, config
import config
import sys

# TODO: see http://www.gavinj.net/2012/06/building-python-daemon-process.html
import daemon
import signal
import os
from daemon import pidfile
#from daemon import runner 

# python daemon example from https://gist.github.com/javisantana/339430 
class KahviDaemon(object):
  def __init__(self, config_dict = None):

    if config_dict is None:
      config_dict = config.get_config_dict()

    #db_path = config_dict["paths"]["db_path"]
    paths = config_dict["paths"]

    self.root = paths["root"]

    self.run_dir = self.root
    self.working_directory = self.root

    #TODO: replace these with actual logging ...
    self.stdin_path = paths["stdin"]
    self.stdout_path = paths["stdout"]
    self.stderr_path = paths["stderr"]
    self.pidfile_path = paths["kahvid_pidfile"]
    self.pidfile_timeout = 1

  def handle_sigterm(self, *kwargs):
    print("caught sigterm: " + str(kwargs))
    #os.kill(self.pidfile_path, signal.SIGTERM)
    raise Exception

  def run(self):
    import time
    signal.signal(signal.SIGTERM, self.handle_sigterm)
    i = 0
    #try:
    while True:
      with open("test.txt", "a") as f:
        #print(i)
        f.write(str(i) + "\n")
        i += 1
        time.sleep(1)
    #except KeyboardInterrupt:
    #  print("exiting.")

#TODO: see example on how to start / stop the daemon using commands ...
# https://pagure.io/python-daemon/blob/master/f/daemon/runner.py 

if __name__ == "__main__":
  #context = daemon.DaemonContext(
  #    stdout = sys.stdout,
  #    stderr = sys.stderr,
  #    #pidfile = lockfile.FileLock("/var/run/kahvid.pid"),
  #    pidfile = pidfile.TimeoutPIDLockFile("/var/run/kahvid.pid"),
  #    umask = 0o002,
  #    working_directory = ".",
  #    )

  #context.signal_map = {
  ##    signal.SIGHUP: "terminate",
  ##    signal.SIGTERM: "terminate",
  ##    signal.SIGUSR1 : "terminate",
  ##    signal.SIGUSR2 : "terminate",
  ##    #signal.SIGUSR0 : "terminate",
  ##    }

  from daemon.runner import DaemonRunner
  d = KahviDaemon()

  dr = DaemonRunner(d)
  dr.daemon_context.working_directory = "." #TODO
  #TODO: figure out how to respond to result of do_action ...
  dr.do_action()
