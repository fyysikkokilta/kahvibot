"""
This module is responsible for handling web requests using Flask. 

Requests are of the form (start, end) in unix time and are passed on to the db
manager, which then returns the appropriate data to be sent back as JSON.
"""

#TODO: turn this into a daemon

from flask import Flask, request
import json
import db
import config

app = Flask(__name__)

dbm = db.DatabaseManager(config)

@app.route("/data")
def get_data():
  try:
    data_range = (request.args.get("s"), request.args.get("e"))
    query_result = dbm.query_range(data_range)
    return(str(data_range))
  except DBException:
    #TODO
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

