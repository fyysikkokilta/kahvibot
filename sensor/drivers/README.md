## ADC Drivers

This folder contains drivers used to read values from a hardware sensor using 
GPIO. A driver is simply a python file which implements two functions:
`read_adc`, which returns an integer value representing the digital output from
the ADC and `cleanup`, which is called when the program that was reading the
sensor exits.

To use your own driver, put `from .drivers import your_driver as driver` at the
beginning of `sensor/__init__.py`. You will also probably need to rewrite the 
`compute_nCups` function there, depending on the values your ADC returns and
your calibration.
