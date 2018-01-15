## Measuring coffee with OpenCV

**TODO**: description


## Installing OpenCV on a Raspberry Pi

**NOTE**: This might change if a Python 3-compatible OpenCV package is released for Raspbian. Then it should be just `sudo apt install python3-opencv` or something. But for now, OpenCV must be compiled from source.

Steps mostly based on [this tutorial](https://www.pyimagesearch.com/2016/04/18/install-guide-raspberry-pi-3-raspbian-jessie-opencv-3/), with slight modifications in e.g. compiler flags.

1. Install dependencies: `sudo apt install build-essential cmake pkg-config`.
1. Install  I/O packages:

   `sudo apt install libjpeg-dev libtiff5-dev libjasper-dev libpng12-dev`

   `sudo apt install libavcodec-dev libavformat-dev libswscale-dev libv4l-dev libxvidcore-dev libx264-dev` (might not be necessary but just in case)

1. Install matrix operation libraries to improve performance: `sudo apt install libatlas-base-dev gfortran`
1. Python development packages: `sudo apt install python3-dev`
1. Download OpenCV source:

   `cd <working_directory> && mkdir opencv && cd opencv`

   ```
   wget -O opencv_contrib-3.4.0.zip https://github.com/opencv/opencv_contrib/archive/3.4.0.zip`
   wget -O opencv-3.4.0.zip https://github.com/opencv/opencv/archive/3.4.0.zip
   unzip opencv-3.4.0.zip && unzip opencv_contrib-3.4.0.zip
   ```

1. Note: we're not installing using a virtual environment as in the tutorial (this might not be a good idea). We assume here that `pip3` is installed.
1. Set compiler flags and compile:

   `cd opencv-3.4.0 && mkdir build && cd build`

   ```
   cmake -D CMAKE_BUILD_TYPE=RELEASE \
     -D CMAKE_INSTALL_PREFIX=/usr/local \
	 -D INSTALL_PYTHON_EXAMPLES=OFF \
	 -D OPENCV_EXTRA_MODULES_PATH=../../opencv_contrib-3.4.0/modules \
	 -D BUILD_EXAMPLES=OFF \
	 -D BUILD_opencv_apps=OFF \
	 -D BUILD_DOCS=OFF \
	 -D BUILD_PERF_TESTS=OFF \
	 -D BUILD_TESTS=OFF ..
   ```

   Check the CMake output that the Python 3 interpreter is set corrcetly.

   Compile using 3 threads: `make -j3` (this is the longest step). If the installation gets stuck at the end, try `make clean` and then `make` to compile with just a single thread. After this is done,

   `sudo make install && sudo ldconfig`

	OpenCV should now be installed.

1. Test that the installation works:

   ```
   python3
   >>> import cv2
   >>> cv2.__version__
   ```

1. Finally, clean up the folders to free up storage space: `cd .. && rm -r opencv*` and you're done. (Note: this breaks C++ error messages but what are you gonna do.)

**TODO**: info on calibration etc
