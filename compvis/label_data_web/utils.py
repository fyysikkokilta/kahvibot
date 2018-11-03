"""
Some helper functions for the web app, related to e.g. database management
"""

class DBManager():
  def __init__(self, db_name):
    import pymongo
    from pymongo import MongoClient

    # test the connection with a client with a timeout of 10ms.
    try:
      MongoClient("localhost", 27017, serverSelectionTimeoutMS = 10).server_info()
    except pymongo.errors.ServerSelectionTimeoutError as e:
      if "Errno 111" in e.args[0]:
        raise ConnectionRefusedError("Database connection refused. Is mongodb running?") from e
      else:
        raise

    self.client = MongoClient()
    self.db = self.client[db_name]
    self.data = self.db["data"]

  def get_label_count(self):
    # https://docs.mongodb.com/manual/reference/operator/aggregation/size/
    agg = dbm.data.aggregate([
      # https://stackoverflow.com/questions/14789684/find-mongodb-records-where-array-field-is-not-empty
      #{"$project": $ne: [] ... }, #TODO
      { "$project": { "count_l": {"$size" : "$right"}}
       },
      #TODO { ... sum ... }
      ])

  def get_unlabeled_items(self, all_filenames):
    filenames_in_db = { x["filename"] for x in self.data.find(projection = {"filename": True})}
    return list(set(all_filenames) - filenames_in_db)

  def add_entry(self, filename, side, value, timestamp):
    existing_data = self.data.find_one({"filename": filename})

    # array containing all entries for 'left' or 'right'
    side_data = None
    if existing_data is None or side not in existing_data:
      side_data = []
    else:
      side_data = existing_data[side]

    side_data.append({"value": value, "timestamp": timestamp})

    self.data.update_one({"filename": filename},
          {
            "$set": {side: side_data}
          },
          upsert = True)

def export_database(database_name):
  raise NotImplementedError()
  import json
