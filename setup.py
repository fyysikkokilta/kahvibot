"""
A very simple script that creates an appropriate systemd service config.
Currently works only on raspbian/debian and is pretty dirty overall.
"""

from os import path
import sys

exec_path = path.join(path.dirname(path.abspath(__file__)), "kahvibot")
service_path = "/etc/systemd/system/kahvibot.service"

service_content_fmt = """# systemd configuration for kahvibot
[Unit]
Description=Telegram bot for checking the amount of coffee

[Service]
ExecStart={}
ExecReload=/bin/kill -HUP $MAINPID
Type=simple
PIDFile=/var/run/kahvibot.pid

[Install]
WantedBy=multi-user.target
"""


"""
Check if the specified configuration file already exists. If it doesn't, create
it. If it does, ask if the user wants to overwrite it.
"""
def create_config_file(p, content, description):
    if path.exists(p):
        ans = input("Found existing systemd configuration file for {}. "
                    "Do you want to overwrite it?(y/n) ".format(description))
        ans = ans.lower()
        if not ans in ["y", "yes"]:
            print("Not writing configuration file for {}.".format(description))
            return

    with open(p, "w") as f:
        f.write(content)

    print("Created systemd configuration file {} for {}.".format(p, description))


if __name__ == "__main__":

    # this is kinda hacky and not very thorough but oh well.
    if not sys.version_info >= (3,):
        ver = sys.version.split("\n")[0].strip()
        msg = "Python 3 is required. Found: {}.\n".format(ver)
        sys.stderr.write(msg)
        sys.exit(1)

    args = " ".join(sys.argv[1:])
    if args:
        exec_path += " " + args

    service_content = service_content_fmt.format(exec_path)
    create_config_file(service_path, service_content, "kiltiskahvi service")
