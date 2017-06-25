"""
A very simple script that creates an appropriate systemd service config.
Currently works only on debian and is pretty dirty overall.
"""

from os import path
import sys

exec_path = path.join(path.dirname(path.abspath(__file__)), "kahvid")
service_path = "/etc/systemd/system/kiltiskahvi.service"

service_content = """# systemd configuration for kahvid
[Unit]
Description=Coffee measurement daemon

[Service]
ExecStart={}
ExecReload=/bin/kill -HUP $MAINPID
Type=simple
PIDFile=/var/run/kahvid.pid

[Install]
WantedBy=multi-user.target
""".format(exec_path)

if __name__ == "__main__":

  # this is kinda hacky and not very thorough but oh well.
  if not sys.version_info >= (3,):
    sys.stderr.write(
        "Python 3 is required. Found: {}.\n".format(
          sys.version.split("\n")[0].rstrip()
          )
        )
    sys.exit(1)

  if path.exists(service_path):
    ans = input(
        "Found systemd configuration file. Do you want to overwrite it? (y/n) "
        ).lower()
    if not ans in ["y", "yes"]:
      print("Aborting.")
      sys.exit(1)

  with open(service_path, "w") as f:
    f.write(service_content)

  print("Created systemd configuration file {}.".format(service_path))
