"""
The main measurement program, responsible for polling the sensor periodically 
and inserting the results into a database. 

Must be run as root (to access the GPIO and to create a PID).
"""

#import db, sensor, config
import sys

# TODO: see http://www.gavinj.net/2012/06/building-python-daemon-process.html
import daemon
import lockfile
import signal
from daemon import pidfile
#from daemon import runner 

def main():
  import time
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

# python daemon example from https://gist.github.com/javisantana/339430 
class MyApp(object):
  def __init__(self):
    import os
    self.root = os.path.abspath(os.path.dirname(__file__))
    self.run_dir = self.root
    self.working_directory = self.root
    #TODO: replace these with actual logging ...
    self.stdin_path = "/dev/null"
    self.stdout_path = "./stdout.txt"
    self.stderr_path = "./stderr.txt"
    self.pidfile_path = "/var/run/kahvid.pid"
    self.pidfile_timeout = 1

  def run(self):
    main()

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
  dr = DaemonRunner(MyApp())
  dr.daemon_context.working_directory = "." #TODO
  #TODO: figure out how to respond to result of do_action ...
  dr.do_action()
