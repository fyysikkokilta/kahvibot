## ADC Drivers

This folder contains drivers used to read values from a hardware sensor using 
GPIO. A driver is simply a python file which implements a `read_adc` function, 
which returns an integer value representing the digital output from the ADC.

To use your own driver, put `from drivers.your_driver import read_adc` at the
beginning of `sensor/__init__.py`. You will also probably need to rewrite the 
`compute_nCups` function there, depending on the values your ADC returns and
your calibration.
