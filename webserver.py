"""
This module is responsible for handling web requests using Flask. 

Requests are of the form (start, end) in unix time and are passed on to the db
manager, which then returns the appropriate data to be sent back as JSON.
"""

#TODO: turn this into a daemon

from flask import Flask, request, current_app, jsonify, make_response
from functools import update_wrapper
import db
import config

app = Flask(__name__)

cfg = config.get_config_dict()
dbm = db.DatabaseManager(cfg)

# Allow cross domain requests, see http://flask.pocoo.org/snippets/56/
# Stripped down version, not general at all but gets the job done
#TODO: configure allowed origins etc. in this via config file...
def crossdomain(origin = None):

  if not isinstance(origin, str):
    origin = ", ".join(origin)

  def decorator(f):
    def wrapped_function(*args, **kwargs):
      resp = make_response(f(*args, **kwargs))
      #resp = current_app.make_default_options_response()
      #print(resp)
      h = resp.headers
      h["Access-Control-Allow-Origin"] = origin
      h["Access-Control-Allow-Methods"] = "GET" # TODO make this configurable
      return resp
    return update_wrapper(wrapped_function, f)
  return decorator

@app.route("/data", methods=["GET", "OPTIONS"])
@crossdomain(origin="*")
def get_data():
  #print("getting data: {}".format(request))
  try:

    data_range = (int(float(request.args["s"])), int(float(request.args.get("e"))))

    datapoints = dbm.query_range(data_range)

    #return jsonify([[i * 100 + data_range[0], x] for i, x in enumerate(datapoints)])
    return jsonify(datapoints)


  #TODO
  except db.DBException:
    raise

def main():
  pass

# Testing
#TODO: move these to main function...
if __name__ == "__main__":
  import argparse

  ap = argparse.ArgumentParser()
  ap.add_argument("--public", 
      dest="public", action = "store_true", 
      help = "make the flask app publicly visible to the network.")


  args = ap.parse_args()

  # initialize a dummy database, which returns random values.
  #TODO
  dbm = db.DatabaseManager("dummy")
  

  app.run('0.0.0.0' if args.public else None)

