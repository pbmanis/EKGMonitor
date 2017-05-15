# EKGMonitor

Python code for an EKG monitor for experiments. The monitor can read from a soundcard as input, or from an Adruino with the Olimex EKG/EMG shield (actually, any analog input to the Arduino...)

Originally based on:
Originally based on http://www.swharden.com/wp/2009-08-14-diy-ecg-machine-on-the-cheap/
Some test signals are taken from that project.

Tested on Mac OSX 10.11 with Python 2.7; Windows 7 64 bit Python 2.7

Requirements
------------

Pyqtgraph (Graphcs and parameters)
numpy (computation)
scipy (filtering)
biosppy.signals (ecg waveform detection and analysis)
sounddevice (connections to sound cards)


Connections
-----------

    * Select the acquisition mode by changing the
    entry on line 43. Set mode='soundcard' to use a soundcard, or 'olimex' to use an arduino input.

    * Sound card: This requires that an external 
    amplifier be configured (filtering, gain) and connected to one channel 
    of the soundcard input. We use a Grass P511J, with the low-pass filter at 300 Hz and the high filter at about 1 Hz, with a gain of 1000-10000X. 

    * Arduino/Olimex: This mode uses the Olimex shield, which provides 
    an instrumentation amplifier, filters and some noise rejection. 
    The Arduino provides the A/D conversion. 
    The Arduino (Due/UNO) should be running *ADReadTimed*, 
    which provides a minimal configuration to talk to the program, and control data collection.
    The Olimex board could be replaced with a simple shield with a good instrumentation op amp
        (such as the AD524/624 series) and a LPF.


Use
---

usage is quite basic. Start the program. Pressing the "start" button will initiate acquisition with the default parameters, which include low-pass filtering the input at 40 Hz, as well as attempting to provide a notch filter at 60 Hz. The "invert" checkbox will invert the signal to help with detection. Every run is saved to disk as a pickled python file automatically, with the current data/time that the run started. The acquisition may be paused and continued. The number of epochs is controlled by the repetitions and normally should be set to a very large number for continuous monitoring. 

The default is to collect 1 second of data every 5 seconds. The mean heart rate, and rate variability are computed. The lower plots show the template trace set (left), detected beats (middle), and a continuing run of variability over time (right).








