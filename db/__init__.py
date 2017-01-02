"""
This module handles inserting to and reading from the database, the location of
which is specified in the configuration. 

Possibly in the future, the database may be split into multiple parts each
corresponding to different amounts of aggregation. In this case the db manager
handles aggregation and querying the appropriate database if the request is a
range.
"""
import sqlite3


"""
The database schema used.
"""
#TODO: add some way to identify calibration parameters
#TODO: figure out if this should be defined in the configuration instead...
TABLES = {
    "data": [("timestamp", "integer primary key"), ("sensor_value", "integer"), ("calibrated_value", "real")],
    "calibration_parameters": [("timestamp", "integer primary key"), ("values", "text")], #TODO: something like 'parameters_json' ?
    }

"""
A class to handle database queries. Opens a database connection upon creation,
which needs to be closed manually.
"""
class DatabaseManager(object):

  def __init__(self, config):
    #TODO
    
    # override query function with dummy function
    # this if-else is pretty stupid...
    if config == "dummy":
      self.query_range = self.query_dummy_range
      self.query = self.query_dummy

    else:
      self.db_path = config["paths"]["db_path"]
      self._conn = sqlite3.connect(self.db_path)

  def query_range(self, r):
    try:
      (start, end) = r
      c = self._conn.cursor()
      c.execute("SELECT * FROM ???")
      query_result = c.fetchall()
      return query_result
    except (ValueError, TypeError) as e:
      #TODO: do this properly...
      raise DBException("Invalid database range: {}.".format(e))

  def query_dummy_range(self, r):
    import random
    max_num_points = 100
    lo, hi = r
    num_points = min(max(hi - lo, 0), max_num_points)
    y = random.sample(range(1024), num_points)
    x = [int(lo + 1.0 * x * (hi - lo) / num_points) for x in range(num_points)]
    return zip(x, y)

  def query_dummy(self):
    import random
    return random.randint(0, 1024)

  #TODO
  # this function queries the latest calibration parameters from the appropriate table 
  # should be used only on startup 
  def query_latest_calibration(self):
    # see https://stackoverflow.com/questions/22200587/get-records-for-the-latest-timestamp-in-sqlite
    c = self._conn.cursor()
    c.execute("SELECT * FROM ??? ORDER BY timestamp DESC LIMIT 1")
    query_result = c.fetchall()
    return query_result

  # TODO
  # store updated calibration settings in to the appropriate table
  def update_calibration(self, timestamp, calibration_dict):
    c = self._conn.cursor()
    c.execute("INSERT (?, ?) INTO TABLE ... ??? ", timestamp, calibration_dict)
    c.commit()


  # initialize the tables to the database using self._conn
  def initialize(self):
    import json
    c = self._conn.cursor()
    try:
      #schema_string = "{}".format(", ".join(", ".join()))
      c.execute("""CREATE TABLE ? (?)""", table, schema_string)
    except sqlite3.OperationalError as e:
      print("Abort: error when creating table {} in database {}: {}".format(t, self.db_path, e))
      sefl._conn.rollback()
      break

    self._conn.commit()


  def close_connection(self):
    self._conn.close()

# necessary?
class DBException(Exception):
  #TODO
  pass



# for testing and manual database management

if __name__ == "__main__":
  import argparse
  import config

  ap = argparse.ArgumentParser()
  ap.add_argument("-c", "--config",
      dest = "config_file",
      help = "use CONFIG_FILE as the configuration file instead of the default")

  ap.add_argument("--initialize",
      dest = "init",
      help = "Initialize the database specified in the configuration according to the schema. Don't do anything if the database already exists.")

  #TODO: options for resetting, initializing etc.

  args = ap.parse_args()

  cfg = config.get_config_dict(args.config_file)

  dbm = DatabaseManager(cfg)

  if args.init:
    dbm.initialize()

  #TODO: tests...
  #dbm.query_range((0, 100))
  #dbm.query_range((50, 0)) # should raise an exception
  #...


  dbm.close_connection()
