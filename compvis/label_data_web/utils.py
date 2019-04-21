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
    # return an empty list on aggregation if left/right doesn't exist
    def ifn(s): return {"$ifNull": [ s, [] ]}

    # this works maybe with a newer version of mongo?
    #agg = self.data.aggregate([{
    #  "$project": {
    #    "count": {
    #      "$sum": [
    #        {"$size": ifn("$left" )},
    #        {"$size": ifn("$right")},
    #        ]
    #    }
    #  },
    #  }])
    #
    #return sum(map(lambda x: x["count"], agg))

    agg = self.data.aggregate([{
      "$group": {
        "_id": "filename",
        "count_l": { "$sum": {"$size": ifn("$left") } },
        "count_r": { "$sum": {"$size": ifn("$right")} },
        }
      }])
    return sum(map(lambda x: x["count_l"] + x["count_r"], agg))

  def get_unlabeled_items(self, all_filenames):
    #TODO: check left/right separately?
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
  import json
  import time
  dbm = DBManager(database_name)
  items = list(dbm.data.find({}, {"_id": False}))
  print("exporting {} items".format(len(items)))
  filename = "exported-data-{}.json".format(time.strftime("%Y%m%d-%H-%M-%S"))
  with open(filename, "w") as f:
    s = "[\n{}\n]".format(",\n".join([json.dumps(x) for x in items]))
    f.write(s)
    print("exported {} items to {}".format(len(items), filename))

if __name__ == "__main__":
  import argparse

  parser = argparse.ArgumentParser()
  parser.add_argument("--export", dest="export", action="store_true")
  args = parser.parse_args()

  if args.export:
    from app import DATABASE_NAME
    export_database(DATABASE_NAME)

