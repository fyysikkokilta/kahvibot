# kahvibot

This repo contains `kahvibot`, a simple Python program for checking the amount of coffee at the
[Guild of Physics](http://www.fyysikkokilta.fi/) guild room via a Telegram bot.
The script runs on a Raspberry Pi at the guild room, and when a user sends a
command or a message with the keyword "kahvi" in it, the bot takes a picture
with a webcamera and sends it.

Interfacing with the Telegram API is done using the
[python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
library, and the pictures are taken using the `fswebcam` command. Optionally, a
watermark can be added to the photos using
[PIL](https://pillow.readthedocs.io/en/stable/).


## Usage
### Setup

1. `git clone` the repo on to your device
1. Create a virtualenv. You have to install `sudo apt install python3-virtualenv` on raspbian, then create the environment with `python3 -m virtualenv venv`, where `venv` is the environment name. Activate the env with `source venv/bin/activate`.
1. Inside the virtualenv, install the dependencies: `pip install python-telegram-bot pillow`. The script is tested with `python-telegram-bot` version 13.11 and `pillow` version 9.0.1.
1. Install the command to take pictures with the USB webcamera: `sudo apt install fswebcam`. The script is tested with `fswebcam` version 20140113.
1. Get a bot token from @BotFather if you haven't already. Also, disable privacy mode for the bot, if you want it to respond to any message that contains some specific words.
1. Copy the example config file to an actual config file: `cp config-example.py config.py` and add your bot token to the config file. Check also the other options in the config.
1. Make the script file excutable: `chmod +x kahvibot`

You then have two options for running the bot, either with a systemd service (recommended) or manually (using `screen` or `tmux`).

#### Running as a systemd service
This makes it easier to restart and automatically run the script on startup.
Note that in this case the script is run as sudo, although it shouldn't be a
problem.

1. Check that `virtualenv_path` in `setup.py` matches the name of the virtualenv you created above.
1. Run `sudo python3 setup.py`. This just creates a systemd script in `/etc/systemd/system/`.
1. Run `sudo service kahvibot start` to start the telegram bot. Check the syslog to see that it's working (or if it's not). You can do so using e.g. the command `sudo tail -f /var/log/syslog`.
1. Run `sudo systemctl enable kahvibot` to make it also start on boot, and you should be good to go. You can check the status of the bot using `sudo service kahvibot status`.
1. If the bot doesn't respond, you can check the syslog, and/or just reboot it by re-plugging the power socket of the raspi.

#### Running manually
This is useful for debugging, or if you don't like systemd or something.

1. Add the user who will be running the script to the `video` group, so they can access the webcam: `sudo usermod -a -G video $USER`. You will need to log out and log back in to reflect the changes.
1. Run the bot: `./kahvibot`
1. You can also set up the Pi to run your script at startup if it is rebooted I guess. I don't really know a good way to do it without systemd.

### Configuration

The bot is configured by just `import`ing values from the `config.py` file. See the comments in the example config for further details.


## Hacking

While developing, you can run the script `bot-offline.py`, which just responds with a simple "the bot is offline" message to all queries. It also uses the bot token from the config file. It's easiest to run this script on e.g. kosh inside `tmux` or something.


## History

Kahvibot was originally written by Márton Gunyhó in 2016. Initially, the idea
of this project was to _measure_ the amount of coffee at the guild room, by
hacking a cheap digital kitchen scale. The measured coffee data could then be
stored and plotted and analyzed for interesting statistics, like coffee
consumption during the day or to see if the coffee in the pan is stale and so
on. This didn't _pan_ out so well, since the load cell of the scale gave very
unreliable results (I don't know what I was expecting for a 5€ scale bought
from Aliexpress).

Around January 2018 came the great innovation of just attaching a webcam to the
Pi and letting the users judge for themselves how much coffee there is. But
this wasn't enough, I thought that maybe the webcamera could be used for
measuring the coffee amount. Initially, I tried to use OpenCV and traditional
computer vision algorithms and feature engineering, with some very minimal
success (this was before OpenCV was available in pip for Raspbian, it had to be
compiled manually). The results of this attempt are available in the branch
`cv`, for what they are worth.

After fiddling with OpenCV, the next idea was of course to use the webcamera
images with this new cool thing called _machine learning_. After dreaming about
it for several months, me and my friend turned it into a project for the Deep
Learning course at Aalto. In the end, we threw together a version using both
`sklearn` and `pytorch` in a few days before the deadline, as is customary for
course projects. We had decent success - with four different labels for images
("no coffee", "a little bit of coffee", "a lot of coffee" and "unknown"), we
got around 85% correct labeling if I recall correctly. In the end, I decided
that this accuracy was not good enough, and the idea was not put into
production. The code for that is sitting somewhere in my Aalto Gitlab.
Something useful that came out of this project was a small website where people
can label pictures of pans with the amount of coffee. This is available in the
folder `compvis/label_data_web/` in the `cv` branch.

After the machine learning project, I got the idea to rewrite the whole script
from scratch and remove all of the old stuff related to the scale and computer
vision and such. I first started this in 2020, but then ended up finishing it
only in the spring of 2022 during a weekend hackathon at the guild room. With
the rewrite, I reduced the code to just the simple core of taking pictures with
the webcam, and improved the documentation. I also switched from the
unmaintained telepot library to python-telegram-bot. This way, the project
could be picked up by soneone else now that I have basically graduated.

With the rewrite, the bot actually became a bit slower to send pictures,
because the `fswebcam` command always has to open a new session to the
webcamera. But I think this is an ok tradeoff for not having to install OpenCV.
I also considered rewriting it in Rust, but that is left as an exercises for
the reader.
