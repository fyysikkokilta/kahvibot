"""
A very simple script that creates an appropriate systemd service config.
Currently works only on raspbian/debian and is pretty spaghettyish overall.
"""

from os import path
import sys

kahvibot_root = path.dirname(path.abspath(__file__))

virtualenv_path = path.join(kahvibot_root, "venv")
if not path.exists(virtualenv_path):
    raise ValueError(f"Could not find virtual env at '{virtualenv_path}'.")

exec_path = path.join(kahvibot_root, "kahvibot")
service_path = "/etc/systemd/system/kahvibot.service"

service_content_fmt = """
# systemd configuration for kahvibot
[Unit]
Description=Telegram bot for checking the amount of coffee

# Only enable after network is online (after reboot)
# see https://unix.stackexchange.com/questions/379167/starting-systemd-service-after-network-online-target-but-dns-is-still-not-availa
# and https://www.freedesktop.org/wiki/Software/systemd/NetworkTarget/
After=systemd-resolved.service network-online.target
Wants=systemd-resolved.service network-online.target

# Even though we have the After and Wants options above, the first restart still fails.
# So we add these and the RstartSec and Restart options below.
StartLimitIntervalSec=1h
StartLimitBurst=5


[Service]
ExecStart={}
ExecReload=/bin/kill -HUP $MAINPID
Type=simple
PIDFile=/var/run/kahvibot.pid
WorkingDirectory={}
RestartSec=10
Restart=on-failure


[Install]
WantedBy=multi-user.target
""".strip()


"""
Check if the specified configuration file already exists. If it doesn't, create
it. If it does, ask if the user wants to overwrite it.
"""
def create_config_file(fname: str, content: str):
    if path.exists(fname):
        ans = input(f"Found existing systemd configuration file {fname}. "
                    "Do you want to overwrite it? (y/n) ")
        ans = ans.lower()
        if not ans in ["y", "yes"]:
            print("Not writing configuration file.")
            return

    with open(fname, "w") as f:
        f.write(content)

    print(f"Created systemd configuration file {fname}. You can check the status with 'sudo service kahvibot status' and use 'sudo systemctl enable kahvibot' to make it run on startup.")


if __name__ == "__main__":

    # prepend the python interpreter inside the virtualenv to use that, see
    # https://stackoverflow.com/a/37211676
    exec_start = f"{virtualenv_path}/bin/python {exec_path}"
    service_content = service_content_fmt.format(exec_start, kahvibot_root)
    create_config_file(service_path, service_content)
