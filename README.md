# kiltiskahvi - computer vision edition
## What?
Software for tracking the amount of coffee at the [Guild of Physics](http://www.fyysikkokilta.fi/) guild room, mostly written in Python.
The system consists of essentially three parts:
* A script that continuously measures the amount of coffee with a webcamera and stores the measurements in a database
* A Telegram bot that tells how much coffee there is when asked
* Web software for displaying how the amount of coffee varies over time on a website

The first two of these are run on a Raspberry Pi, while the web software is hosted elsewhere and then whitelisted on said Pi to allow database queries.


## How?
The telegram bot will most likely be based on [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) or possibly [telepot](https://github.com/nickoala/telepot).
Instead of storing full images, the amount of coffee is determined from a picture using [OpenCV](https://opencv.org/).
Data will be served in JSON by [Flask](http://flask.pocoo.org/) to a whitelisted server. The graphing will most likely be done using [Highstock](http://www.highcharts.com/products/highstock).
The database is handled by MongoDB using [PyMongo](https://api.mongodb.com/python/current/).

## Why?
Because.

## When?
Soon™

## Usage
Mostly as a reminder for myself how the system is set up.

### Setup

1. `git clone` the repo on to your device
1. Install dependencies: `sudo apt install mongodb`, `sudo pip3 install flask pymongo telepot numpy matplotlib`.
1. Run `sudo systemctl enable mongodb && sudo service mongodb start` to start the mongodb server and make it start on boot. Check `/etc/mongodb.conf` to make sure that mongodb is bound to localhost.
1. Set up OpenCV. Instructions can be found [here](sensor/README.md).
1. Run `sudo python3 setup.py` (this just creates a systemd script in `/etc/systemd/system/`).
1. Set up your hardware, calibration and configs (see below)
1. Run `sudo service kiltiskahvi start` to start the coffee measurement daemon. Check the syslog to see that it's working (or if it's not).
1. Run `sudo systemctl enable kiltiskahvi` to make it also start on boot
1. Insert your telegram [bot token](https://core.telegram.org/bots#generating-an-authorization-token) in the configuration file in `config/config.ini`
1. Start the telegram bot service: `sudo systemctl enable kahvibot && sudo service kahvibot start`
1. Clone the repo or download the contents of the folder `web/` to your desired location on your webserver.
1. Download [highstock](http://www.highcharts.com/download), navigate to the folder `js` and copy the files `highstock.js` and `modules/exporting.js` to `web/lib/` or wherever you copied the contents of `web` to
1. Set up the `config` file in said folder according to the instructions in `config.default`
1. Expose the `web` folder on your server and you're good to go, assuming your firewall settings are correct.

### Running
**TODO**


### Configuration, calibration
**TODO**

# Hardware setup
If you're using an MCP3008 ADC to read out your sensor, adjust your wiring and the pinouts in `sensor/drivers/adafruit_mcp3008` to match. Otherwise, you can write your own driver for ADC readout, see the README in `sensor/drivers/` for instructions.
