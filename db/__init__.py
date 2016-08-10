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
#TODO
schema = {}

"""
A class to handle database queries. Opens a database connection upon creation,
which needs to be closed manually.
"""
class DatabaseManager(object):

  def __init__(self, config):
    #TODO
    db_path = config["paths"]["db_path"]
    self._conn = sqlite3.connect(db_path)

  def query_range(r):
    try:
      (start, end) = r
      c = self._conn.cursor()
      c.execute("SELECT * FROM ???")
      query_result = c.fetchall()
      return query_result
    except (ValueError, TypeError) as e:
      #TODO: do this properly...
      raise DBException("Invalid database range: {}.".format(e))

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

  #TODO: options for resetting, initializing etc.

  args = ap.parse_args()

  cfg = config.get_config_dict(args.config_file)

  dbm = DatabaseManager(cfg)

  #TODO: tests...
  #dbm.query_range((0, 100))
  #dbm.query_range((50, 0)) # should raise an exception
  #...


  dbm.close_connection()

