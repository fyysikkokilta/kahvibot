"""
This file contains the function for computing the no. of cups with a given raw
sensor value. The sensor object parameter is assumed to have an attribute 
'calibration' which is a dict that contains all necessary values for the
computation. 
The function is in a separate file like this so it can be backed up to the
database to make old data raw compatible if it's necessary.
"""
def compute_nCups(sensor, raw_value):
  #import warnings
  #raise NotImplementedError("No. of cups computation not implemented yet.")
  return raw_value / 1024. * 10
