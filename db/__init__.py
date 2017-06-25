"""
This module handles inserting to and reading from a mongodb database.

Possibly in the future, different collections (~tables, see mongodb reference) 
may be used corresponding to different levels of aggregation. In this case the 
db manager handles aggregation and querying the appropriate database if the 
query is a range.
"""
from pymongo import MongoClient

#TODO: does the connection need to be closd manually w/ mongodb?
"""
A class to handle database queries. 
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
      #TODO: remove this from configs, db location is determined by mongodb.conf ...
      #self.db_path = config["paths"]["db_path"]
      #self._conn = sqlite3.connect(self.db_path)
      client = MongoClient()
      # TODO: change this to an actual database
      db = client["kahvidb-test"]
      datacollection = db["test-data"]
      

      self.client = client
      self.db = db
      self.datacollection = datacollection
      #TODO: a collection holding a single entry which is the latest calibration parameters
      #self.calibrationParams = db["calibration-last"]
      # this contains a history of calibration dictionaries.
      #self.calibrationDicts = db["calibrationDicts"]

  #############
  # INSERTING #
  #############

  """
  Insert a data point into the database.
  """
  #TODO: inserting multiple data points?
  def insert_data(self, timestamp, raw_value, nCups):

    # multiple datapoints #TODO
    if hasattr(timestamp, "__iter__"):
      #TODO
      pass

    # as of now, 
    self.datacollection.insert_one(
        {
      "timestamp": 
      }) 

  #TODO: calibration parameters
  #def update_calibration(self, calibrationDict):

    #self.db["calibration-last"].update_one(
    #  {"_id": 0},  # this ensures that calibrationParams will only have one value.
    #  {"calibrationDict" : calibrationDict},
    #  upsert = True
    #)
    #self.db["calibrationDicts"].insert_one({"timestamp" : time.time(), "calibrationDict": calibrationDict})


  ############
  # QUERYING #
  ############

  """
  Query all datapoints within the given tuple range.
  """
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

  #TODO: option to reset/dump database

  args = ap.parse_args()

  cfg = config.get_config_dict(args.config_file)

  dbm = DatabaseManager(cfg)


  #TODO: tests...
  #dbm.query_range((0, 100))
  #dbm.query_range((50, 0)) # should raise an exception
  #...


  dbm.close_connection()
