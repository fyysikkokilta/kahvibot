"""
Small script for labeling pictures.

Usage:
  1. Put images to be labeled in the folder img/data/ (add/change folders in the the data_folders variable below)
  2. $ python3 label_data.py
  3. Once all pictures have been labeled (or if you interrupt with Ctrl+C), the script spits out a JSON file containing the labels.
  4. When running the script again, the script scans for all .json files in its directory, reads labels from them and skips already labeled data. If you don't want this, you can comment out the load_existing_labels() call below.
"""
import cv2
import sys
import time
import os
import json
import matplotlib.pyplot as plt
from datetime import datetime

plt.close("all")

def bgr2gray(img):
  return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

data_folders = [
    "img/data",
    ]

fig = plt.figure()


labels = {}

def load_existing_labels():
  for label_file in os.listdir():
    if not label_file.endswith(".json"): continue

    with open(label_file, "r") as f:
        data = json.loads(f.read())
        for k, v in data.items():
          if k not in labels:
            labels[k] = v
          else:
            #print("label found more than once for {}".format(k))
            pass

load_existing_labels()

try:

  new_label_count = 0
  for folder in data_folders:
    filenames = os.listdir(folder)
    for i, filename in enumerate(filenames):

      img_path = os.path.join(folder, filename)

      if img_path in labels:
        print("label already found for {}, skipping".format(filename))
        continue

      img = cv2.imread(img_path)

      ax = fig.gca()
      ax.clear()
      ax.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
      fig.canvas.draw()
      fig.canvas.flush_events()

      plt.show(block = False)

      answer = None
      while answer is None or not (-2 <= answer <= 10):
        try:
          answer = float(
              input("{}/{} how much coffee? (0-10, -1: unknown, -2: decanter missing): ".format(i + 1, len(filenames)))
              )
          if int(answer) != answer:
            raise ValueError

        except ValueError:
          answer = None
          print("please give an integer in the range -2..10")
          pass

      labels[img_path] = answer
      new_label_count += 1


except KeyboardInterrupt:
  print("stopping.")

finally:
  if labels and new_label_count > 0:
    filename = "labels-{}.json".format(datetime.now().strftime("%Y-%m-%d-%H%M%S"))

    print("writing to {}".format(filename))
    with open(filename, "w") as f:
      f.write(json.dumps(labels))
