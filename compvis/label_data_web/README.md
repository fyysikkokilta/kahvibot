# Crowdsource labeling

This folder contains a simple [flask](http://flask.pocoo.org/) app that allows
easily labeling pictures of coffee pans in a web browser. By running it on a
server, the task of labeling pictures can be easily crowd-sourced. The labels
are stored in a MongoDB database and can be exported as JSON, see below.

## Usage
1. Place images to be labeled in the folder `img/data/`
1. Place examples of full and empty coffee pans in `img/example_full.jpg` and `img/example_empty.jpg` (or if you don't want this, remove the `examples-container` div from `label-data.html`).
1. `$ sudo python3 app.py` --  This runs the Flask server on port 80. This definitely against the [recommended ways](http://flask.pocoo.org/docs/1.0/deploying/) of running a Flask app, but should suffice for a simple thing like this.
1. You should be now able to label pictures at `http://your-domain.com/kahvi`.
1. Labels are stored in mongodb database determined by `DATABASE_NAME` in `app.py`, the default name is `coffeedata-labels`.

The database can be exported as JSON by running
`python3 utils.py --export` (**TODO**)
