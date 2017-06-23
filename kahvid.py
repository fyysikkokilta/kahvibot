#!/usr/bin/env python3

"""
The main measurement program, responsible for polling the sensor periodically 
and inserting the results into a database. 

Must be run as root (to access the GPIO and to create a PID file).
"""

#import db, sensor, config
import config
import sys
import threading

# TODO: see http://www.gavinj.net/2012/06/building-python-daemon-process.html
import daemon
import signal
import os, time
from daemon import pidfile
#import logging, logging.handlers
import syslog
#from daemon import runner 

# python daemon example from https://gist.github.com/javisantana/339430 
class KahviDaemon(object):
  def __init__(self, config_dict = None):

    if config_dict is None:
      config_dict = config.get_config_dict()

    self.config_dict = config_dict

    #db_path = config_dict["paths"]["db_path"]
    paths = config_dict["paths"]

    self.root = paths["root"]

    self.run_dir = self.root
    self.working_directory = self.root

    #TODO: replace these with actual logging ...
    #NOTE: these redirect print() to these files ...
    # see also: https://stackoverflow.com/questions/13180720/maintaining-logging-and-or-stdout-stderr-in-python-daemon

    #TODO: figure out how to set these to None (without fiddling with the library...)
    # - use a custom daemonContext instead of using the runner thing?
    #   - how to pass paths then?
    #   - also, how to catch signals?
    #self.stdin_path = paths["stdin"]
    #self.stdout_path = paths["stdout"]
    #self.stderr_path = paths["stderr"]
    self.stdin_path = ""
    self.stdout_path = None
    self.stderr_path = None
    self.pidfile_path = paths["kahvid_pidfile"]
    self.pidfile_timeout = 1

    self.poll_interval = int(config_dict["general"]["poll_interval"])


  def handle_sigterm(self, *kwargs):
    syslog.syslog(syslog.LOG_INFO, "Exiting.")
    #print("caught sigterm: " + str(kwargs))
    #TODO: close all files and disconnect db etc.
    #os.kill(self.pidfile_path, signal.SIGTERM)
    #raise Exception
    sys.exit(0)

  def run(self):
    # good idea to import here?
    import sensor as sensorModule

    signal.signal(signal.SIGTERM, self.handle_sigterm)
    start_time = int(time.time())

    sensor = sensorModule.Sensor(self.config_dict)

    # the time it took to start the measurement thread, to minimize clock error.
    delta_t = 0

    # the thread handling sensor polling and database writing.
    # its value is set below.
    thread = None

    with open("test.txt", "a") as f:
      while True:

        # if the previous measurement is in progress, skip a measurement
        # shouldn't be a problem if self.poll_interval and averaging_time 
        # aren't close to each other.
        if thread is not None and thread.is_alive():
          #print("WARNING: the sensor was still busy, skipping poll.")
          syslog.syslog(syslog.LOG_WARNING, "Sensor was busy, skipping poll.")
          pass
        else:
          delta_t = -1 * time.time()
          thread = threading.Thread(
                target = self.write_record,
                args = [sensor, f] # TODO: db instead of f
              )
          thread.start()
          delta_t += time.time()

          #poll_result = sensor.poll(averaging_time = 1)
          #f.write("{} {}\n".format(time.time(), poll_result))
          time.sleep(self.poll_interval - delta_t)


  """
  This function polls the sensor and writes the result to the database using 
  the given db_conection. The function is supposed to be called in its own 
  thread so the timing of poll intervals doesn't get messed up.
  """
  # TODO: better name
  # TODO: change handling of db_connection to an actual database connection instead of file...
  def write_record(self, sensor, db_connection):
    #poll_result = sensor.poll(averaging_time = self.poll_interval)
    poll_result = sensor.poll(averaging_time = 1)
    t = time.time()
    #TODO: replace with actual db stuff...
    db_connection.write("{} {}\n".format(t, poll_result))



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

  # set up logging
  #TODO
  #TODO: formatting
  #logger = logging.getLogger() #name = "???")
  #logger.setLevel = logging.INFO # ???
  #see e.g. https://stackoverflow.com/questions/3968669/how-to-configure-logging-to-syslog-in-python for explanation of /dev/log
  #handler = logger.handlers.SysLogHandler(address = "/dev/log")  
  #logger.addHandler(handler)


  from daemon.runner import DaemonRunner
  d = KahviDaemon()

  dr = DaemonRunner(d)
  dr.daemon_context.working_directory = "." #TODO
  #dr.daemon_context.stdin = sys.stdin

  #TODO: figure out how to respond to result of do_action ...
  dr.do_action()
