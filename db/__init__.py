"""
This module handles inserting to and reading from a mongodb database.

Possibly in the future, different collections (~tables, see mongodb reference) 
may be used corresponding to different levels of aggregation. In this case the 
db manager handles aggregation and querying the appropriate database if the 
query is a range.
"""
from pymongo import MongoClient
import sys
import os

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
      #self.calibrationDicts = db["calibration-history"]

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
    #self.datacollection.insert_one(
    #    {
    #  "timestamp": 
    #  }) 

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


"""
Return a suitable folder name for dumping database contents by using a 
timestamp. Don't create the folder, that must be done elsewhere.
"""
def get_default_dump_path():
  import time
  folderBaseName = os.path.join(
      os.path.dirname(os.path.abspath(__file__)), 
      "dump",
      "dump-" + time.strftime("%Y-%m-%d-%H%M", time.localtime())
      )

  folderName = folderBaseName

  i = 1
  while os.path.exists(folderName):
    folderName = folderBaseName + "-" + str(i)
    i += 1

  return folderName

"""
Dump database contents using mongoexport and drop collections if specified. 
"""
def dump_database(dump_path, config_dict, purge = False):

  dbm = DatabaseManager(config_dict)
  db = dbm.db

  # filter out system collections
  collectionNames = list(filter(
      lambda x: not x.startswith("system."),
      db.collection_names()
      ))
  
  # doing this check here prevents from creating folders if it's not necessary.
  if not collectionNames:
    print("Database {} appears to be empty. Exiting.".format(db.name))
    sys.exit(0)


  if not os.path.exists(dump_path):
    # TODO: create folder as necessary
    os.makedirs(dump_path)

  else:

    if not os.path.isdir(dump_path):
      print("Error: {} is not a directory. Aborting.".format(dump_path))
      sys.exit(1)

    ans = input(
        "WARNING: the folder {} already exists. Do you want to overwrite its contents? (y/n) ".format(dump_path)
        ).lower()

    if not ans in ["y", "yes"]:
      print("Aborting.")
      sys.exit(1)
    

  os.chdir(dump_path)

  print("Dumping database content to {}.".format(os.getcwd()))

  for collName in collectionNames:

    fname = collName + ".json"

    command = "mongoexport --db {} --collection {} --out {}".format(
        db.name, collName, fname
        )

    print("executing {}".format(command))
    retval = os.system(command)

    if retval != 0:
      raise Exception("Shell exited with error (return value {}).".format(retval))

    if purge:
      print("Dropping collection {}.".format(collName))
      db.drop_collection(collName)




"""
Main function for testing and manual database management
"""
if __name__ == "__main__":
  import argparse

  try:
    import config
  except ImportError:
    print("Could not import config, try adding the kiltiskahvi folder to your PYTHONPATH. Exiting.")
    sys.exit(1)


  ap = argparse.ArgumentParser(description = "Dump or delete database contents or run whatever is in the main function.")

  ap.add_argument("-c", "--config",
      dest = "config_file",
      help = "use CONFIG_FILE as the configuration file instead of the default")

  ap.add_argument("--dump",
      dest = "dump_path",
      nargs = "?",
      const = get_default_dump_path(),
      default = None,
      help = "Dump entire kiltiskahvi database contents in JSON format using mongoexport. Data is dumped to the specified folder or to kiltiskahvi/db/dump/ by default."
      )

  ap.add_argument("--purge",
      dest = "purge_dump_path",
      nargs = "?",
      const = get_default_dump_path(),
      default = None,
      help = "Same as --dump but also delete database contents. Use at your own risk."
      )


  args = ap.parse_args()

  cfg = config.get_config_dict(args.config_file)

  if args.purge_dump_path:
    dump_database(args.purge_dump_path, cfg, purge = True)
    sys.exit(0)

  elif args.dump_path:
    dump_database(args.dump_path, cfg)
    sys.exit(0)



  dbm = DatabaseManager(cfg)


  #TODO: tests...
  #dbm.query_range((0, 100))
  #dbm.query_range((50, 0)) # should raise an exception
  #...


  dbm.close_connection()
