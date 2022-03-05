# kiltiskahvi - minimal edition

Kiltiskahvi is a simple Python program for checking the amount of coffee at the
[Guild of Physics](http://www.fyysikkokilta.fi/) guild room via a Telegram bot.
The script runs on a Raspberry Pi at the guild room, with a webcamera taking a
picture of the coffee pan when a user enters a command or says something with
the keyword "kahvi" in it.

Interfacing with the Telegram API is done using the
[python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
library, and the pictures are taken using ??. Optionally, a watermark can be added to the photos using [PIL](https://pillow.readthedocs.io/en/stable/).


## Usage
### Setup

1. `git clone` the repo on to your device
1. Create a virtualenv. You have to install `sudo apt install python3-virtualenv` on raspbian, then `python3 -m virtualenv virtualenvname`. Activate the virtualenv with `source virtualenvname/bin/activate` and  `pip install python-telegram-bot` (tested with `python-telegram-bot` version 13.11).
1. Install webcam software: `sudo apt install fswebcam`
1. Copy the example config file to an actual config file: `cp config-example.py config.py` and add your bot token to the config file.
1. Make the script file excutable: `chmod +x kahvibot`

You then have two options for running the bot, either manually (using `screen` or `tmux`), or with a systemd service (recommended).

#### Running as a systemd service
This makes restarting and automatically running the script on startup easier.
Note that in this case the script is run as sudo, although it shouldn't be a
problem.

1. Run `sudo python3 setup.py` (this just creates a systemd script in `/etc/systemd/system/`). If you want custom arguments for running the program, you can pass them to `setup.py` or edit the line `ExecStart` in the file `/etc/systemd/system/kahvibot.service` after the setup has been run.
1. Run `sudo service kahvibot start` to start the telegram bot. Check the syslog to see that it's working (or if it's not).
1. Run `sudo systemctl enable kahvibot` to make it also start on boot, and you should be good to go.

#### Running manually
This is useful for debugging, or if you don't like systemd or something.

1. Add the user who will be running the script to the `video` group, so they can access the webcam: `sudo usermod -a -G video $USER`. You will need to log out and log back in to reflect the changes.
1. Run the bot: `./kahvibot`
1. You can also set up the Pi to run your script at startup if it is rebooted or something.


## Hacking

While developing, you can run the script `bot-offline.py`, which just responds with a simple "the bot is offline" message to all queries. It also uses the bot token from the config file. It's easiest to run this script on e.g. kosh inside `tmux` or something.

### Configuration
#### Configuration file
**TODO**


#### Adding a watermark
**TODO**


## History

Originally, in 2016, the idea of this project was to _measure_ the amount of
coffee at the guild room, by hacking a cheap digital kitchen scale. The
measured coffee data could then be stored and plotted and analyzed for detailed
coffee statistics, as physics students do. This didn't pan out so well, since
the load cell of the scale gave very unreliable results (I don't know what I
was expecting for a 5€ scale bought from Aliexpress).

Around January 2018 came the great innovation of just attaching a webcam to the
Pi and letting the users judge for themselves how much coffee there is. But
this wasn't enough, I thought that maybe the webcamera could be used for
measuring the coffee amount.  Initially, I attempted to use OpenCV and
classical computer vision algorithms, with some very minimal success (this was
before OpenCV was available in pip for Raspbian, it had to be compiled
manually). The results of this attempt are available in the branch `cv`, for
what they are worth.

After fiddling with OpenCV, the next idea was of course to use the webcamera
images with this new cool thing called _machine learning_. After dreaming about
it for several months, me and my friend turned it into a project for the Deep
Learning course at Aalto. In the end, we threw together a version using both
`sklearn` and `pytorch` in a few days before the deadline, as is customary for
course projects. We had decent success - with four different labels for images
("no coffee", "a little bit of coffee", "a lot of coffee" and "unknown"), we
got around 85% correct labeling if I recall correctly. It wasn't good enough to
put into production, though. The code for that is sitting somewhere in my
school Gitlab. Something useful that came out of that project was a small html
site for labeling images so that the work can be distributed among many people,
that's available in the folder `compvis/label_data_web/` in the `cv` branch.

In the beginning of 2020, I re-wrote the script from scratch and removed all of
the old stuff related to the scale and the computer vision and everything,
leaving just the very simple core of taking pictures with the webcam. As my
graduation is nearing, I wanted to leave relatively clean code that might be
picked up by somebody else to maintain.
