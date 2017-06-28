"""
This module handles inserting to and reading from a mongodb database.

For each measurement, we store the raw value of the sensor, a timestamp, the
number of cups the sensor value corresponds to and possible additional
information (standard deviation? something else?). The no. of cups as a
function of raw sensor value may change depending on the sensor and calibration
parameters. 

The calibration parameters are stored separately, and a new entry is added only
when the parameters change. This should make earlier raw sensor values
compatible with newer measurements (in theory), as long as the method for
calculating them is known. 
A user need not worry about this, as the no. of cups is assumed to be correct
for each calibration.

Possibly in the future, different collections (~tables, see mongodb docs) may 
be used corresponding to different levels of aggregation. In this case the db 
manager handles aggregation and querying the appropriate database if the query 
is a range.

NOTE: The mongodb database is located in /var/lib/mongodb (default for debian
(I think)). All db paths are handled automagically by mongodb, so we try not to
fiddle with those at all.
"""
import pymongo
import sys
import os
import syslog
import re

DUMMY_TAG = "dummy"

#TODO: does the connection need to be closd manually w/ mongodb?
"""
A class to handle database queries. 
"""
class DatabaseManager(object):

  def __init__(self, config_dict, dummy = False):
    #TODO
    
    # override query function with dummy function
    # note: this if-else structure is pretty stupid...
    if dummy:
      self.query_range = self.query_dummy_range
      self.query = self.query_dummy
      syslog.syslog(
          syslog.LOG_WARNING, 
          "db: Overwriting query functions with dummy ones."
      )

    else:

      db_config = config_dict["database"]

      db_name = db_config["dbname"]

      # test the connection with a client with a timeout of 10ms.
      try:
        pymongo.MongoClient("localhost", 27017, serverSelectionTimeoutMS = 10).server_info()
      except pymongo.errors.ServerSelectionTimeoutError as e:
        if "Errno 111" in e.args[0]:
          raise ConnectionRefusedError("Database connection refused. Is mongodb running?") from e
        else:
          raise

      self.client = pymongo.MongoClient("localhost", 27017) # hard-coded local db.
      self.db = self.client[db_name]
      self.datacollection = self.db["data"]
      self.data_latest_collection = self.db["data-latest"]

      self.range_query_max_items = int(db_config["range_query_max_items"])

      """
      A collection holding a single entry: the latest calibration parameters
      in dictionary form. Another collection keeps track of the history of
      calibration parameters. These are updated only when the calibration
      values change.
      """
      #TODO: this whole thing
      #TODO: check for changed parameters
      #self.calibrationParams = db["calibration-last"]
      # this contains a history of calibration dictionaries.
      #self.calibrationDicts = db["calibration-history"]

      """
      Read the compute_nCups function from the appropriate file and store it in
      the database (if necessary).
      """
      #TODO
      p = os.path
      nCups_function_filename = p.join(
        p.dirname(p.dirname(p.abspath(__file__))),
        "sensor",
        "compute_nCups.py"
        )
      nCups_function_string = None
      with open(nCups_function_filename, "r") as f:
        nCups_function_string = f.read()

      # remove description from the beginning of the string
      nCups_function_string = re.sub(
          r'""".+?"""\n?', #replace this pattern (a text block)...
          "", # ... with empty
          nCups_function_string, # in this str
          count = 1, # replace only first occurrence.
          flags = re.DOTALL # this makes '.' match newline as well
          )

      if db["nCups-function-last"].find_one({"_id": 0}) != nCups_function_string:
        db["nCups-function-history"].insert_one(nCups_function_string)
        db["nCups-function-last"].insert_one(
            {"_id" : 0,  "str" : nCups_function_string},
            upsert = True
            )




  #############
  # INSERTING #
  #############

  """
  Insert a data point into the database.
  Perform simple verification that the given data dictionary contains some
  required fields.

  Might add support for inserting multiple data points in the future.
  """
  #TODO: inserting multiple data points?
  def insert_data(self, data_dict):

    if type(data_dict) != dict:
      raise NotImplementedError("Insert_data can only handle single data point dictionaries as of now.")

    # simple (and dirty) data validation, raises a KeyError if a required field is missing
    # TODO: is there a better place for defining the required fields??
    required_fields = ["timestamp", "rawValue", "isCoffee"]
    [data_dict[field] for field in required_fields]

    # handle multiple datapoints #TODO (this check isn't good if we're using a dict)
    #if hasattr(timestamp, "__iter__"): 
    #  #TODO
    #  pass

    # insert a copy as insert_one modifies the dict ...
    self.datacollection.insert_one(data_dict.copy())
    self.data_latest_collection.update({"_id" : 0}, data_dict.copy(), upsert = True)

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
  Query the latest measurement.
  This assumes that data_latest_collection contains always only one record.
  """
  def query_latest(self):
    try:
      #TODO: adjust timeout...
      return self.data_latest_collection.find_one()
    except pymongo.errors.ServerSelectionTimeoutError:
      return None

  """
  Query all datapoints within the given tuple (start, end), inclusive, where
  start and end are floats representing unix time.
  Returs a pymongo cursor object which can then be iterated over.
  Returns a maximum of self.range_query_max_items items, which is set in the
  configuration.
  If the item limit is exceeded, returns the latest items instead of every nth
    item...
  """
  #TODO: if count is more than max_items, return every nth item, where n = count // MAX_ITEMS (or sth)
  def query_range(self, r, projection = {}):
    try:
      (start, end) = r

      # TODO: is this necessary? or is mongodb error checking sufficient?
      assert (
          (type(start) == float or type(start) == int) and
          (type(end) == float or type(end) == int)
          ), "Start or end wasn't float or int: {}".format(r)

      
      #TODO: aggregate collections

      proj = {"_id": False}
      proj.update(projection)

      query_result = (
          self
          .datacollection
          .find({"timestamp": {"$gte": start, "$lte": end}}, projection = proj)
          .sort("timestamp", pymongo.ASCENDING)
          # don't return more than this many items
          .limit(self.range_query_max_items)
          )

      return query_result

    except (ValueError, TypeError, AssertionError) as e:
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

  if purge:
    ans = input(
        "Are you sure you want to erase ALL data from the database? (y/n) "
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
Remove all entries from the database that are marked as 'dummy'.
"""
def clean_database(config_dict):
  dbm = DatabaseManager(config_dict)
  dc = dbm.datacollection

  tagged = dc.find({DUMMY_TAG: {"$exists" : True}})

  c = tagged.count()

  if c > 0:
    ans = input("Found {} dummy entries. Are you sure you want to remove them? (y/n) ".format(c)).lower()
    if not ans in ["yes", "y"]:
      print("Aborting.")
      return

    removedCount = 0
    for entry in tagged:
      res = dc.delete_one(entry)
      if res.acknowledged:
        removedCount += res.deleted_count

    print("Removed {} entries.".format(removedCount))

  else:
    print("No dummy entries found. Exiting.")


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
      help = "Use CONFIG_FILE as the configuration file instead of the default."
      )

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

  ap.add_argument("--clean",
      dest = "clean",
      action = "store_true",
      help = "Remove dummy entries from the database and exit. Dummy entries are created when the daemon runs but GPIO pins are not available."
      )

  args = ap.parse_args()

  # TODO: is config even necessary for the DB manager? -- yes, for checking changes in the calibration (might not be the smartest way to do it though.
  cfg = config.get_config_dict(args.config_file)

  if args.purge_dump_path:
    dump_database(args.purge_dump_path, cfg, purge = True)
    sys.exit(0)

  elif args.dump_path:
    dump_database(args.dump_path, cfg)
    sys.exit(0)

  elif args.clean:
    clean_database(cfg)
    sys.exit(0)



  dbm = DatabaseManager(cfg)


  #TODO: tests...
  #dbm.query_range((0, 100))
  #dbm.query_range((50, 0)) # should raise an exception
  #...
