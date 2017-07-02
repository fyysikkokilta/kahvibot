"""
A very simple script that creates an appropriate systemd service config.
Currently works only on debian and is pretty dirty overall.
"""

from os import path
import sys

exec_path_daemon = path.join(path.dirname(path.abspath(__file__)), "kahvid")
service_path_daemon = "/etc/systemd/system/kiltiskahvi.service"

exec_path_bot = path.join(path.dirname(path.abspath(__file__)), "kahvibot")
service_path_bot = "/etc/systemd/system/kahvibot.service"

# TODO: move these to separate files?
service_content_daemon = """# systemd configuration for kahvid
[Unit]
Description=Coffee measurement daemon

[Service]
ExecStart={}
ExecReload=/bin/kill -HUP $MAINPID
Type=simple
PIDFile=/var/run/kahvid.pid

[Install]
WantedBy=multi-user.target
""".format(exec_path_daemon)

service_content_bot = """# systemd configuration for kahvibot
[Unit]
Description=Telegram bot for reporting the amount of coffee

[Service]
ExecStart={}
ExecReload=/bin/kill -HUP $MAINPID
Type=simple
PIDFile=/var/run/kahvibot.pid

[Install]
WantedBy=multi-user.target
""".format(exec_path_bot)


"""
Check if the specified configuration file already exists. If it doesn't, create
it. If it does, ask if the user wants to overwrite it.
"""
def create_config_file(p, content, description):
  if path.exists(p):
    ans = input(
        "Found systemd configuration file for {}. Do you want to overwrite it?(y/n) ".format(description)
        ).lower()
    if not ans in ["y", "yes"]:
      print("Not writing configuration file for {}.".format(description))
      return

  with open(p, "w") as f:
    f.write(content)

  print("Created systemd configuration file {} for {}.".format(p, description))

"""
Call the above function for both the measurement daemon and Telegram bot.
"""
if __name__ == "__main__":

  # this is kinda hacky and not very thorough but oh well.
  if not sys.version_info >= (3,):
    sys.stderr.write(
        "Python 3 is required. Found: {}.\n".format(
          sys.version.split("\n")[0].rstrip()
          )
        )
    sys.exit(1)

  paths = [
      (service_path_daemon, service_content_daemon, "kiltiskahvi service"),
      (service_path_bot, service_content_bot, "kahvibot service"),
      ]

  for p, content, description in paths:
    create_config_file(p, content, description)
