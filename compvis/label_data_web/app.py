"""
A simple flask server for labeling pictures and storing the labels in a
database. For details, see README.md

Note that in our special case, the pictures are cropped (using HTML/css). If
you don't want this, you can simply remove the "cropped" wrapper div from
label-data.html.
"""
from utils import DBManager
from flask import Flask, render_template, request, url_for, redirect
import os
import random
import time

DATABASE_NAME = "coffeedata-labels"

dbm = DBManager(DATABASE_NAME)

app = Flask(__name__, template_folder = ".", static_url_path = "", static_folder = ".")

DATA_FOLDER = "img/data"
try:
  all_filenames = os.listdir(DATA_FOLDER)
  assert len(all_filenames) > 0, "Folder {} was empty.".format(DATA_FOLDER)
except FileNotFoundError as e:
  raise FileNotFoundError("Could not find images to be labelled in folder {}.".format(DATA_FOLDER)) from e

# helper functions
print("\ndata items without a label: {} / {}\n".format(len(dbm.get_unlabeled_items(all_filenames)), len(all_filenames)))

SPAM_TIME = 0.3 # if an ip sends a message more often than this, it is spam.

visitors = {} # a map ip-address: timestamp, to prevent spam

@app.route("/kahvi", methods=["GET", "POST"])
def root():

  ip = request.remote_addr
  timestamp = time.time()
  form = request.form

  spam = False
  if ip in visitors and abs(visitors[ip] - timestamp) < SPAM_TIME:
    spam = True

  visitors[ip] = timestamp


  if request.method == "POST":
    if not spam:

      #print(form)

      f_path = form["filename"]
      fname = os.path.basename(f_path)
      value = float(form["choice"])
      side = form["side"]

      # maximum security data validation
      assert -2 <= value <= 10
      if fname not in all_filenames:
        print("not adding data for {}".format(fname))
        return # causes internal server error

      print("inserting {}: {} ({}) - {}".format(fname, value, side, ip))
      dbm.add_entry(fname, side, value, timestamp)

      return redirect(url_for("root"))

    else:
      print("ignoring submission from {}".format(ip))


  # TODO: not used anywhere - pass as argument to redirect somehow
  # https://stackoverflow.com/questions/17057191/redirect-while-passing-arguments
  n_images = int(form["count"]) + 1 if "count" in form else 0

  side = random.choice(["left", "right"])

  data_filename = random.choice(all_filenames)
  data_path = os.path.join(DATA_FOLDER, data_filename)

  return render_template("label-data.html",
      image_to_label = url_for("static", filename = data_path),
      example_full_url = url_for("static", filename = "/img/example_full.jpg"),
      example_empty_url = url_for("static", filename = "/img/example_empty.jpg"),
      n_images = n_images,
      side = side, # this is for cropping the image, remove if unnecessary
      )
