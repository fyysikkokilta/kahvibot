# kiltiskahvi
## What?
Software for tracking the amount of coffee at the [Guild of Physics](http://www.fyysikkokilta.fi/) guild room, mostly written in Python.
The system consists of essentially three parts:
* A script that continuously measures the amount of coffee via a GPIO connected scale and stores the measurements in a database
* A Telegram bot that tells how much coffee there is when asked
* Web software for displaying how the amount of coffee varies over time on a website

The first two of these are run on a Raspberry Pi, while the web software is hosted elsewhere and then whitelisted on said Pi to allow database queries.


## How?
The telegram bot will most likely be based on [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) or possibly [telepot](https://github.com/nickoala/telepot).
Data will be served in JSON by [Flask](http://flask.pocoo.org/) to a whitelisted server. The graphing will most likely be done using [Highstock](http://www.highcharts.com/products/highstock).

## Why?
Because.

## When?
Soon(TM)

## Usage
Mostly as a reminder for myself how the system is set up.

### Setup

1. `git clone` the repo on to your device
1. Run `sudo ???` to start the coffee measurement daemon
1. Clone the repo or download the contents of the folder `web/front/` to your desired location on your webserver.
1. Download [highstock](http://www.highcharts.com/download), navigate to the folder `js` and copy the files `highstock.js` and `modules/exporting.js` to `front/lib/`
1. Set up the `config` file in said folder according to the instructions in `config.default`
1. Expose the folder `front` on your webserver and you're good to go, assuming your firewall settings are correct.

### Running
**TODO**


### Configuration, calibration
**TODO**


