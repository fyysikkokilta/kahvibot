## Crowdsource labeling

This folder contains a simple [flask](http://flask.pocoo.org/) app that allows
easily labeling pictures of coffee pans in a web browser. By running it on a
server, the task of labeling pictures can be easily crowd-sourced. The labels
are stored in a MongoDB database and can be exported as JSON, see below.

## Usage
1. Place images to be labeled in the folder `img/data/`
1. Place examples of empty coffee pan and full coffee pan in `img/example_full.jpg` and `img/example_empty.jpg` (or if you don't want this, remove the examples-container div from label-data.html).
1. `$ export FLASK_APP=app.py`
1. `$ flask run`
1. Labels are stored in mongodb database determined by `DATABASE_NAME` in `app.py`, the default name is `coffeedata-labels`.

The database can be exported as JSON by running
`python3 utils.py --export` (**TODO**)
