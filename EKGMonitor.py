# -*- coding: utf-8 -*-
"""
Sound-card based Electrocardiogram monitor 

Provides:
    Ongoing measurement of heart rate from episodic samples of ECG signal.
    Storage of the rate and sampled ECG to disk.
    Reading display of the stored data.
    Test files read from disk for verification of operation.

Requirements:
    pyqtgraph for plotting
    biosppy for ECG event extraction
    sounddevice for acess to the sound cards
    numpy and scipy for numerical operations and signal analysis functions
All other imports are from standard Python modules

Originally based on http://www.swharden.com/wp/2009-08-14-diy-ecg-machine-on-the-cheap/
Some test signals are taken from that project

Paul B. Manis, Ph.D. July 21-31, 2016

"""
import sys
import datetime
import pickle
import platform
import serial
import time
import numpy as np
import scipy.signal
import pyqtgraph as pg
from PyQt4 import QtGui, QtCore
from pyqtgraph.parametertree import Parameter, ParameterTree
#import sounddevice as sd
from biosppy.signals import ecg as b_ecg

# perform some initialization and system-dependent activities.
# The "s.default_device" parameter may need to be set to correct select from the hardware that is 
# available on a given system. The printed "devices" list should help with this.


mode = 'olimex'  # use olimex on arduino
#mode - 'soundcard'  # use system sound card
assert mode in ['olimex', 'soundcard']

# if mode == 'soundcard':
#     devices = sd.query_devices()
#     print devices
#     opsys = platform.system()
#     if opsys in ['Windows']:
#         sd.default.device = 22  # check but should be rear microphone input
#     elif opsys in ['Darwin']:
#         indev = sd.query_devices(kind='input')
#         sd.default.device = 0, 1  # should be the input
#     else:
#         raise ValueError('Platform %s is not supported', opsys)
    
#     print 'Using audio input device : %d' % sd.default.device[0]
#     NChannels = 2


class Arduino():
    def __init__(self, buffer):# routines for talking to arduino
        self.serbuf = buffer
        
    def read_data_buffer(self):
        b = ''
        inbuf = False
        while self.serbuf.inWaiting() > 0:  # read the whole buffer
            c = self.serbuf.read()
            if c == '[':
                inbuf = True
                continue
            if inbuf and c == ']':
                return b
            else:
                if inbuf:
                    b+=c
        return b

    def send_command(self, c):
        self.serbuf.write(c)
        
    def read_response(self):
        b = ''
        while self.serbuf.inWaiting() > 0:  # read the whole buffer
            b += self.serbuf.read()
        return b

    def flushbuf(self):
        while self.serbuf.inWaiting() > 0:
            self.serbuf.read()

    def wait_done(self):
        while self.serbuf.inWaiting() == 0:
            pass
        c = self.serbuf.read()
        self.flushbuf()

    def wait_response(self, timeout=2):
        a = time.clock()
        while self.serbuf.inWaiting() == 0:
            if (time.clock() - a) < timeout:
                pass
            else:
                print('ard timeout on wait')
                return
    #    print 'chars: ', self.serbuf.inWaiting()
    
    def print_ard_info(self):
        self.serbuf.write('i')
        self.wait_response()
        c = self.read_response()
        print 'info: ', c

    def set_sample(self, rate, points):
        """
        Sample duration
        rate : seconds/point sampling (e.g., 0.004 for 250 Hz)
        points: number of points in the buffer
        """
        print ('setting rate, points: ', rate, points)
        self.serbuf.write('s %d;\n' % int(rate*1e6))
        print 'rate: ', int(rate*1e6)  # microseconds
        self.serbuf.write('n %d;\n' % int(points))
        print 'points: ', int(points)
    #    self.wait_response()
        print self.read_response()
    #    ard_flushbuf(s)
        self.sampleduration = points * rate
        print 'sampledur: ', self.sampleduration
        self.serbuf.write('i')
        print 'interrogate: '
    #    self.wait_response()
        print self.read_response()
        return self.sampleduration

if mode == 'olimex':
    NChannels = 1
    DEFAULT_BAUDRATE = 115200
    source = 'COM5' # /dev/cu.usbmodem621'
    serial_obj = serial.Serial(source, DEFAULT_BAUDRATE)
    Ard = Arduino(serial_obj)
    Ard.flushbuf()
    time.sleep(1)
    Ard.set_sample(0.008, 256)
#    Ard.sampleduration = 0.004*256
    print('ard olimex serial set')
    

# files that can be read from disk, with information and needed parameters
knownFiles = {'EKG_testsignals.snd': {'fs': 1000., 'subject': 'human',
                    'type': 'snd', 'channel': 0, 'invert': False},
              'mouseECG.p': {'fs': 44100., 'subject': 'mouse',
                      'type': 'pickled', 'channel': 0, 'invert': True},
            }

#fname='EKG_testsignals.snd' #CHANGE THIS AS NEEDED
#fname = 'scottecg.snd'
fname = 'mouseECG.p'
testMode = False


def checkfs():
    """
    Verify the sample frequencies supported by the sound card and the API.
    Many systems have a high, fixed frequency, but some (ex: Mac OSX) also
    can provide down-sampled data
    
    Parameters
    ----------
    None
    
    Returns
    -------
    supported samplerates, as a list that is a subset of the possible sample rates
    """
    possibleSamplerates = [1./1000, 1./2000, 1./4000, 1./8000, 1,.11025, 1/22050, 
                            1./32000, 1./44100, 1./48000, 1./96000, 1./128000]
    device = sd.default.device[0]

    supported_samplerates = []
    for fs in possibleSamplerates:
        try:
            sd.check_input_settings(device=device, samplerate=int(1./fs), channels=NChannels)
        except Exception as e:
            print(fs, e)
        else:
            supported_samplerates.append(fs)
    return supported_samplerates

if mode == 'soundcard':
    samplerates = checkfs()
else:
    samplerates = [0.004]
    #Ard.sampleduration = Ard.set_sample(1e6/samplerates[0], 256)  # just over 1 sec, 250 Hz rate


class MeasureECG:
    """
    Class to measure the ECG
    Provides ability to read data from disk or capture from a sound card, and
    low-pass filtering
    Data and acquisition parameters can be access through the class variables
    The class is designed to be instantiated once before use.
    ecg = MeasureECG()
    
    """
    def __init__(self, finfo=None, mode='soundcard'):
        self.analysisSampleFreq = 1000. # Hz, for the data we will use (not the rate at which the signal is sampled)
        self.sampleFreq = self.analysisSampleFreq # actual frequency after decimation
        if mode == 'soundcard':
            self.device = sd.default.device[0] # define sound card
        else:
            self.device = None
        self.NChannels = NChannels
        self.fs = samplerates[0]  # use the lowest one we found
        if self.fs > 2*self.analysisSampleFreq:
            self.decimate = int(self.fs/self.analysisSampleFreq)  # decimate to about 1 kHz
        else:
            self.decimate = 1
            self.analysisSampleFreq = self.fs
        if finfo is not None:
            self.invertData = finfo['invert']
        else:
            self.invertData = False
        self.NotchFreq = 60.
        self.NotchEnabled = True

    def setfs(self, fs):
        self.fs = fs  # set from file and compute a new decimation value
        self.decimate = int((1./self.fs)/self.analysisSampleFreq)  # decimate to about 1 kHz

    def setThreshold(self, threshold=10000):
        """
        Set detection threshold
        (Note, when using ecg from biosppy, the threshold is not used)
        
        Parameters
        ----------
        threshold: float (default : 10000)
            threshold for event detection, in input units
        
        Returns:
        Nothing
        """
        
        self.threshold = threshold
        
    def LPFilter(self, data, fc=40., numtaps=5):
        """
        Design and use a low-pass filter to filter the data
        Uses a default Hamming window
        
        Parameters
        ----------
        data : array or numpy array of floats
            the input data set
        fc : floa, (default : 40)
            cutoff frequency (Hz)
        numtaps: int (default : 5)
            number of filter taps
            note: numtaps is 1 > flter order.
        
        Returns
        -------
        filtered data
        """
        coeffs = scipy.signal.firwin(numtaps, fc/(self.sampleFreq/2.0), pass_zero=True)
        dfilt = scipy.signal.lfilter(coeffs, 1.0, data)
        return dfilt

    def NotchFilter(self, data, fn=60., Q=50.):
        """
        Design and use a Notch (band reject) filter to filter the data
        Uses a default Hamming window
        
        Parameters
        ----------
        data : array or numpy array of floats
            the input data set
        fn : float, (default : 60)
            notch frequency (Hz)
        Q: float (default : 50)
            filter "Q" quality factor
        
        Returns
        -------
        filtered data
        """
        fnyq = fn/(self.sampleFreq/2.0)
        wp = [0.96*fnyq, 1.04*fnyq]
        ws = [0.99*fnyq, 1.01*fnyq]
        
        # b, a = scipy.signal.iirnotch(fn/(self.sampleFreq/2.0), Q)  # scipy 19... not yet available
        b, a = scipy.signal.iirdesign(wp, ws, gpass=1.0, gstop=60.)
        dfilt = scipy.signal.lfilter(b, a, data)
        return dfilt
        
    def loadFile(self, fname, startAt=0, length=None, Hz=1000):
        """
        Load a file for testing purposes
        
        Parameters
        ----------
        fname : string (no default)
            full filename including path
        startAt : int (default : 0)
            Position in file data set for start of extraction
        length : int (default : None)
            number of points in file, from start position, to return
            if None, the entire file is returned in self.currentSegment
        Hz : float (default : 1000)
            Sample rate in Hz for data (file does not include rate information)
        
        Returns
        -------
        Nothing
        """
        try:
            finfo = knownFiles[fname]
        except:
            raise ValueError('%s not in list of known test file' % fname)
        if finfo['invert']:
            self.invertData = True
        else:
            self.invertData = False
        if finfo['type'] in ['snd']:
            self.currentSegment = np.memmap(fname, dtype='h', mode='r')
        elif finfo['type'] in ['pickled']:
            try:
                fh = open(fname, 'rb')
                self.currentSegment = pickle.load(fh)
                fh.close()
            except:
                try:
                    fh = open(fname, 'rU')  # possibly text file from windows..
                    self.currentSegment = pickle.load(fh)
                    fh.close()
                except:
                    raise ValueError('sorry, unable to unpickle')
                
        else:
            raise ValueError('loadFile: type %s not supported' % finfo['type'])
        if finfo['fs'] is not None:
            Hz = finfo['fs']
            self.sampleFreq = Hz
            self.setfs(Hz)
        self.xs = np.linspace(0., len(self.currentSegment)*Hz,
             len(self.currentSegment))   # generate x time base axis
        rawlen = length*self.decimate
        sa = int(startAt*self.decimate)
        self.currentSegment = self.currentSegment[sa:sa+rawlen]  # slice out desired region
        self.xs = self.xs[sa:sa+rawlen]
        if len(self.currentSegment.shape) > 1:  # depends on how many channels recorded and which needed
            self.currentSegment = scipy.signal.decimate(self.currentSegment[:,finfo['channel']], self.decimate)
        else:
            self.currentSegment = scipy.signal.decimate(self.currentSegment, self.decimate)
        self.sampleFreq = self.sampleFreq/self.decimate  # update sample frequency
        duration = len(self.currentSegment)/self.sampleFreq
        self.lastTimes = np.linspace(0, duration, self.currentSegment.shape[0])  # time base
    
    def captureSegment(self, duration=1.0):
        """
        Read a segment of input from the sound card.
        Blocks until the input is complete.
        
        Parameters
        ----------
        duration : float (default: 1.0)
            seconds
            duration of segment to record
        
        Returns
        -------
        Nothing
        """

        if self.device is not None:
            try:
                sd.check_input_settings(self.device, samplerate=int(self.fs), channels=self.NChannels)
            except:
                raise ValueError('Invalid sample rate for input device')
            self.currentSegment = sd.rec(int(duration / self.fs), samplerate=int(1./self.fs), 
                    blocking=True, channels=2)
            self.currentSegment = scipy.signal.decimate(self.currentSegment[:,1], self.decimate)
            self.sampleFreq = (1./self.fs)/self.decimate
            self.lastTimes = np.linspace(0, duration, self.currentSegment.shape[0])
        else: # read from adruino/olimex
            Ard.send_command('a')
            time.sleep(Ard.sampleduration*2.+0.2)
            Ard.wait_response(timeout=2.)
            b = Ard.read_data_buffer()
            if len(b) == 0:
                 return
            b = '[' + b + ']'
            ib = np.array(eval(b))
            self.currentSegment = ib # scipy.signal.decimate(ib, self.decimate)
            self.currentSegment = self.currentSegment - np.mean(self.currentSegment)
            self.sampleFreq = (1./self.fs)# /self.decimate
            print self.sampleFreq
            self.lastTimes = np.linspace(0, duration, len(self.currentSegment))
        
            


class Updater():
    """
    Take a sample of data and plot it with some analysis
    This class should be instantiated (updater = Updater()), and after configuration,
    a call to updater.update(...) used to update the data and display to the screen
    """
    def __init__(self, testMode, ecg, pltd=None, params=None, ptree=None, invert=False, notchEnabled=True):
        """
        Parameters
        ----------
        testMode : Boolean (no default)
            if True, read a test file instead of acquiring input from the sound card
        ecg : Object (class: MeasureECG)
            An instance of the MeasureECG class that collects the data.
        pltd : Dict (default: None)
            A dictionary of the plot handles in the window
        
        Returns:
        Nothing
        """
        self.testMode = testMode
        self.ecg = ecg
        self.pltd = pltd
        self.params = params
        self.clips = 10*self.ecg.sampleFreq  # 10 seconds
        self.maxSamples = 10
        self.invertData = invert
        self.setSampling()
        self.NSamples = 0
        self.LPFFreq = 40.0
        self.NotchEnabled = notchEnabled
        self.NotchFreq = 60.0
        self.filename = None
        self.InfoText = ''
        self.ptreedata = ptree
        self.prepareRun()

    def setSampling(self, interval=5., duration=1.):
        """
        Set the sample intervals and episode durations
        
        Parameters
        ----------
        interval : float, seconds (default : 5.0)
            Interval between samples of the ECG
        duration : float, seconds (default : 1.0)
            Duration of the ECG to sample at each interval
        
        Returns
        -------
        Nothing
        """
        self.readInterval = interval
        self.readDuration = duration
    
    def setMaxSamples(self, maxsamples=3):
        """
        Parameters
        ----------
        maxsamples : (default : 3)
            Set the number of samples to take
        
        Returns
        -------
        Nothing
        """
        self.maxSamples = maxsamples

    def makeFilename(self):
        """
        Construct a filename based on the current date/time
        
        Parameters
        ----------
        None
        
        Returns
        -------
        Nothing
        """
        n = datetime.datetime.now()
        self.filename = ('{0:04d}.{1:02d}.{2:02d}_{3:02d}.{4:02d}.{5:02d}.p'.
            format(n.year, n.month, n.day, n.hour, n.minute, n.second))
        acqProp = self.ptreedata.child('Acquisition Parameters')
        acqProp['Filename'] = self.filename

    def change(self, param, changes):
        """
        Respond to changes in the parametertree and update class variables
        
        Parameters
        ----------
        param : parameter list
        
        changes : changes as returned from the parameter tree object
        
        Returns
        -------
        Nothing
        
        """
        for param, change, data in changes:
            path = ptreedata.childPath(param)
            # if path is not None:
            #     childName = '.'.join(path)
            # else:
            #     childName = param.name()
            #
            # Parameters and user-supplied information
            #
            if path[1] == 'Filename':
                self.filename = data
            if path[1] == 'Interval':
                self.readInterval = data
            if path[1] == 'Duration':
                self.readDuration = data
            if path[1] == 'Invert':
                self.invertData = data
            if path[1] == 'MaxSamples':
                self.maxSamples = data
            if path[1] == 'LPF':
                self.LPFFreq = data
            if path[1] == 'Notch':
                self.NotchFreq = data
            if path[1] == 'NotchEnabled':
                self.NotchEnabled = data
            if path[1] == 'Info':
                self.InfoText = data
            #
            # Actions:
            #
            if path[1] == 'Start New':
                self.startRun()
            if path[1] == 'Stop/Pause':
                self.stopRun()
            if path[1] == 'Continue':
                self.continueRun()
            if path[1] == 'Save Visible':
                self.storeData()
            if path[1] == 'Load File':
                fn = self.getFilename()
                if fn is not None:
                    self.loadData(filename=fn)
            if path[1] == 'New Filename':
                self.filename = self.makeFilename()
    
    def setAllParameters(self, params):
        """
        Set all of the local parameters from the parameter tree
        
        Parameters
        ----------
        ptree : ParameterTree object
        
        Returns
        -------
        Nothing
        """
        for p in params[0]['children']:
            if p['type'] == 'action':
                continue
            if p == 'Filename':
                self.filename = p['value']
            if p == 'Interval':
                self.readInterval = p['value']
            if p == 'Duration':
                self.readDuration = p['value']
            if p == 'Invert':
                self.invertData = p['value']
            if p == 'MaxSamples':
                self.maxSamples = p['value']
            if p == 'LPF':
                self.LPFFreq = p['value']
            if p == 'Notch':
                self.NotchFreq = p['value']
            if p == 'NotchEnabled':
                self.NotchEnabled = p['value']
            if p == 'Info':
                self.InfoText = p['value']

    def startRun(self):
        """
        Initialize variables for the start of a run
        then use continueRun to get timers
        
        Parameters
        ----------
        None
        
        Returns
        -------
        Nothing
        """
        
        self.runtime = 0
        self.NSamples = 0
        self.startTime = datetime.datetime.now()
        self.prepareRun()  # reset the data arrays
        self.continueRun()
    
    def continueRun(self):
        """
        Start the timing and data collection, without reinitializing
        any variables
        Parameters
        ----------
        None
        
        Returns
        -------
        Nothing        
        
        """
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(updater.update)
        self.timedWrite = QtCore.QTimer()
        self.timedWrite.timeout.connect(updater.storeData)
        self.update() # do the first update, then start time
        self.timer.start(self.readInterval * 1000)
        self.timedWrite.start(30 * 1000.)  # update file in 1 minute increments
    
    def stopRun(self):
        """
        End a run, and write data
        
        Parameters
        ----------
        None
        
        Returns
        -------
        Nothing
        """
        self.timer.stop()
        self.timedWrite.stop()
        self.storeData()

    def prepareRun(self):
        """
        Clear out all arrays for the data collection run
        
        Parameters
        ----------
        None
        
        Returns
        -------
        Nothing
        """
        self.runningRate = []
        self.runningVar = []
        self.runningTime = []
        self.RRInterval = []
        self.varplot = None
        self.currentWave = []
        self.out = []
        self.makeFilename()
        
    def setLPF(self, freq):
        """
        Store the low-pass filter frequency to be used in analysis
        
        Parameters
        ----------
        freq: float, cutoff frequency in Hz (no default)
        
        Returns
        -------
        Nothing
        """
        self.ecg.setLPF(freq)
        self.LPFFreq = freq
        
    def setNotch(self, freq):
        """
        Store the Notch filter frequency to be used in analysis
    
        Parameters
        ----------
        freq: float, Notch frequency in Hz (no default)
    
        Returns
        -------
        Nothing
        """
        self.ecg.setNotch(freq)
        self.NotchFreq = freq
        
    def setFilename(self, filename):
        """
        Store the filename
        
        Parameters
        ----------
        filename : string
        
        Returns
        -------
        Nothing
        """
        self.filename = filename

    def getFilename(self):
        """
        Open a dialog and get a user selected filename for reading
        
        Parameters
        ----------
        None
        
        Returns
        -------
        filename (string)
        or None if dialog cancelled
        """
        dlg = QtGui.QFileDialog()
        dlg.setFileMode(QtGui.QFileDialog.ExistingFile)
        dlg.setFilter("pickled files (*.p)")
        filenames = QtCore.QStringList()
        if dlg.exec_():
            filenames = dlg.selectedFiles()
            return(str(filenames[0]))
        else:
            return(None)

    def storeData(self):
        """
        Store data to data structure:
        All info goes in a dict
        alldata = {'runtime', 'out', 'runningRate', runningvar, runningtime, RRInterval, NSamples, 
        LPFFreq, NotchFreq, Interval, Duration, maxSamples}
        
        then pickle it.
        Parameters
        ----------
        None
        
        Returns
        -------
        Nothing
        """
        
        data = {'runningTime': self.runningTime, 'runningRate': self.runningRate, 
                'runningVar': self.runningVar, 'RRInterval': self.RRInterval,
                'out': [x.as_dict() for x in self.out],
                'LPFFreq': self.LPFFreq, 'NotchFreq': self.NotchFreq, 'NotchEnabled': self.NotchEnabled,
                'readInterval': self.readInterval,
                'readDuration': self.readDuration, 'NSamples': self.NSamples,
                'InfoText': self.InfoText}
                
        acqProp = self.ptreedata.child('Acquisition Parameters')
        self.filename = acqProp['Filename']
        with open(self.filename, 'wb') as fh:
            pickle.dump(data, fh)

    def loadData(self, filename=None):
        """
        get data, put into our structure, then display it.
        
        Parameters
        ----------
        filename : string (default: None)
        
        Returns
        -------
        Nothing
        """
        acqProp = self.ptreedata.child('Acquisition Parameters')
        
        if filename is None:
            self.filename = acqProp['Filename']
        else:
            self.filename = filename
        print('Opening file: %s' % self.filename)
        with open(self.filename, 'rb') as fh:
          data = pickle.load(fh)
        self.runningTime = data['runningTime']
        self.runningRate = data['runningRate']
        self.runningVar = data['runningVar']
        self.RRInterval = data['RRInterval']
        self.out = data['out']
        self.LPFFreq = data['LPFFreq']
        try:  # added later; may not be in all files.
            self.NotchFreq = data['NotchFreq']
            self.NotchEnabled = data['NotchEnabled']
        except:
            self.NotchFreq = 60.
            self.NotchEnabled = False
        self.readInterval = data['readInterval']
        self.readDuration = data['readDuration']
        self.NSamples = data['NSamples']
        self.InfoText = data['InfoText']

        acqProp = self.ptreedata.child('Acquisition Parameters')
        acqProp['Info'] = self.InfoText
        self.plotResults(readmode=True)

    def update(self):
        """
        Perform read of part of the data from either a file 
        or from the soundcard
        Filters data and updates graphics
        
        Parameters
        ----------
        None
        
        Returns
        -------
        Nothing
        """
        if testMode:
            self.ecg.loadFile(fname, startAt=self.NSamples*self.clips, length=self.clips)
        else:
            self.ecg.captureSegment(duration=self.readDuration)
        if self.invertData:
            self.ecg.currentSegment = - self.ecg.currentSegment
        self.ecg.currentSegment = self.ecg.currentSegment - np.mean(self.ecg.currentSegment) 
        filtered_signal = self.ecg.currentSegment
        filtered_signal = self.ecg.LPFilter(self.ecg.currentSegment,
                         fc=self.LPFFreq/self.ecg.sampleFreq)
        if self.ecg.NotchEnabled:
            filtered_signal = self.ecg.NotchFilter(filtered_signal,
                         fn=self.NotchFreq/self.ecg.sampleFreq)
        ctime = datetime.datetime.now()
        self.runtime = (ctime - self.startTime).seconds/60.
        self.pltd['plt_first'].plot(self.ecg.lastTimes, filtered_signal, clear=True, pen=pg.mkPen('g'))
        try:  # do analysis on potential ecg signal
            self.out.append(b_ecg.ecg(signal=filtered_signal, sampling_rate=self.ecg.sampleFreq,
                 show=False, before=0.1, after=0.15))
        except:  # catch lack of a signal
            print 'No beats detected'
            self.NSamples = self.NSamples + 1
            # then plot to the template window to show us what is really there
            self.pltd['plt_first'].plot(self.ecg.lastTimes, self.ecg.currentSegment, clear=True, pen=pg.mkPen('r'))
            return
        print "%s   %8.1f bpm" % (ctime, np.mean(self.out[-1]['heart_rate']))
        self.runningRate.append(np.mean(self.out[-1]['heart_rate']))
        self.runningVar.append(np.std(self.out[-1]['heart_rate']))
        self.runningTime.append(self.runtime)
        interval = np.diff(self.out[-1]['ts'][self.out[-1]['rpeaks']])    
        self.RRInterval.append(interval)
        self.plotResults()

        pg.QtGui.QApplication.processEvents()
        self.NSamples = self.NSamples + 1
        if self.NSamples >= self.maxSamples:
            print 'Max samples reached, stopping', self.maxSamples, self.NSamples
            self.timer.stop()
            return

    def plotResults(self, readmode=False):
        """
        Post the current traces and analysis to the pyqtgraph window
        
        Parameters
        ----------
        readmode : Boolean (default: False)
            Set to true when reading from a file
        
        Returns
        -------
        Nothing
        """
        self.pltd['plt_hr'].plot(self.runningTime, self.runningRate, pen=pg.mkPen('r', width=1),
            symbol='s', symbolSize=6, symbolBrush=pg.mkBrush('r'), symbolPen=None,
            clear=True)
#        if self.varplot is not None:
#            self.pltd['plt_var'].removeItem(self.varplot)
        self.pltd['plt_var'].plot(self.runningTime, self.runningVar, pen=pg.mkPen('b'),
            symbol='o', symbolSize=6, symbolBrush=pg.mkBrush('b'), symbolPen=None,
            clear=True)
        # self.pltd['plt_var'].addItem(self.varplot)

        if readmode:
            for intvl in self.RRInterval:
                self.pltd['plt_RRI'].plot(intvl[1:], intvl[:-1], pen=pg.mkPen(None),
                symbol='o', symbolSize=4, symbolBrush=pg.mkBrush('c'), symbolPen=pg.mkPen('c'), 
                clear=False)
        else:
            self.pltd['plt_RRI'].plot(self.RRInterval[-1][1:], self.RRInterval[-1][:-1],
                pen=pg.mkPen(None),
                symbol='o', symbolSize=4, symbolBrush=pg.mkBrush('c'), symbolPen=pg.mkPen('c'), 
                clear=False)
        if self.NSamples == 0 or readmode is True:
            for j in range(self.out[-1]['templates'].shape[0]):
                self.pltd['plt_first'].plot(self.out[-1]['templates_ts'], self.out[-1]['templates'][j],
                    pen=pg.mkPen('r', width=0.5))
        if len(self.currentWave) > 0:
            for j in range(len(self.currentWave)):
                self.pltd['plt_current'].removeItem(self.currentWave[j]) # remove previous plots
            self.currentWave = []
        for j in range(self.out[-1]['templates'].shape[0]):
            self.currentWave.append(pg.PlotCurveItem(self.out[-1]['templates_ts'],
                self.out[-1]['templates'][j], pen=pg.mkPen('w', width=0.5)))
            self.pltd['plt_current'].addItem(self.currentWave[-1])


if __name__ == '__main__':

    ecg = MeasureECG(knownFiles[fname], mode)

    # Build GUI and window

    app = pg.mkQApp()
    win = QtGui.QWidget()
    layout = QtGui.QGridLayout()
    win.setLayout(layout)
    win.show()
    win.setWindowTitle('EKG Monitor')
    win.setGeometry( 100 , 100 , 1024 , 600)
    #win.resize(1024,800)

    # Define parameters that control aquisition and buttons...
    params = [
        {'name': 'Acquisition Parameters', 'type': 'group', 'children': [
            {'name': 'MaxSamples', 'type': 'int', 'value': 10, 'limits': [1, 10000], 'default': 10},
            {'name': 'Interval', 'type': 'float', 'value': 5., 'limits': [0.5, 300], 'suffix': 's', 'default': 5},
            {'name': 'Invert', 'type': 'bool', 'value': False, 'default': False},
            {'name': 'Duration', 'type': 'float', 'value': 1., 'step': 0.5, 'limits': [0.5, 10], 'suffix': 's', 'default': 1.},
            {'name': 'LPF', 'type': 'float', 'value': 40., 'step': 5, 'limits': [10, 200.], 'suffix': 'Hz',
        'default': 40.},
            {'name': 'NotchEnabled', 'type': 'bool', 'value': True, 'default': True},
            {'name': 'Notch', 'type': 'float', 'value': 60., 'step': 5, 'limits': [10., 240.], 'suffix': 'Hz',
        'default': 60.},
            {'name': 'Filename', 'type': 'str', 'value': 'test.p', 'default': 'test.p'},
            {'name': 'Info', 'type': 'text', 'value': 'Enter Info about subject'},
    #        ]},
    #    {'name': 'Actions', 'type': 'group', 'chidren': [
            {'name': 'New Filename', 'type': 'action'},
            {'name': 'Start New', 'type': 'action'},
            {'name': 'Stop/Pause', 'type': 'action'},
            {'name': 'Continue', 'type': 'action'},
            {'name': 'Save Visible', 'type': 'action'},
            {'name': 'Load File', 'type': 'action'},
            ]},
        ]
    ptree = ParameterTree()
    ptreedata = Parameter.create(name='params', type='group', children=params)
    ptree.setParameters(ptreedata)

    # build layout for plots and parameters
    layout.addWidget(ptree, 0, 0, 5, 2) # Parameter Tree on left

    # add space for the graphs
    view = pg.GraphicsView()
    l = pg.GraphicsLayout(border=(50,50,50))
    view.setCentralItem(l)
    layout.addWidget(view, 0, 3, 5, 3)  # data plots on right

    plt_hr = l.addPlot()
    plt_hr.getAxis('left').setLabel('Rate (bpm)', color="#ff0000")
    plt_hr.setTitle('Heart Rate', color="#ff0000")
    plt_hr.getAxis('bottom').setLabel('t (min)', color="#ff0000")
    plt_hr.setYRange(0, 300)
    ## create a new ViewBox, link the right axis to its coordinate system
    l.nextRow()
    plt_var = l.addPlot() # 
    #pg.ViewBox(parent=plt_hr) # trying to put on one axis, but doesn't work following example
    #plt_hr.showAxis('right')
    #plt_hr.scene().addItem(plt_var)  # add variance to HR plot scene
    #plt_hr.getAxis('right').linkToView(plt_var)  # add view of Y axes
    plt_var.setXLink(plt_hr)
    #plt_hr.getAxis('right').setLabel('HR Variability', color='#0000ff')
    plt_var.getAxis('left').setLabel('Variability (bpm)', color='#0000ff')
    plt_var.setTitle('HR Variability', color="#ff0000")
    plt_var.setYRange(0, 20)
    plt_var.getAxis('bottom').setLabel('t (min)', color='#0000ff')

    l.nextRow()
    l2 = l.addLayout(colspan=3, border=(50,0,0))  # embed a new layout
    l2.setContentsMargins(10,10,10,10)
    plt_first = l2.addPlot(Title="First Waveforms")
    plt_first.getAxis('bottom').setLabel('t (s)')
    plt_first.getAxis('left').setLabel('V')
    plt_first.setTitle('First Template')
    plt_current = l2.addPlot(Title="Current Waveforms")
    plt_current.getAxis('bottom').setLabel('t (s)')
    plt_current.getAxis('left').setLabel('V')
    plt_current.setTitle('Current')
    plt_RRI = l2.addPlot(Title="RRI")
    plt_RRI.setTitle('RRI')
    plt_RRI.getAxis('bottom').setLabel('t (s)')
    plt_RRI.getAxis('left').setLabel('t (s)')


    #
    # Initialize the updater with needed information about the plots
    #
    updater = Updater(testMode, ecg, pltd={'plt_first': plt_first, 'plt_var': plt_var,
        'plt_hr': plt_hr, 'plt_current': plt_current, 'plt_RRI': plt_RRI}, ptree=ptreedata,
        invert=ecg.invertData, notchEnabled=ecg.NotchEnabled)

    updater.setAllParameters(params)  # synchronize parameters with the tree

    ptreedata.sigTreeStateChanged.connect(updater.change)  # connect parameters to their updates

    ## Start Qt event loop unless running in interactive mode.
    ## Event loop will wait for the GUI to activate the updater and start sampling.
    if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
        QtGui.QApplication.instance().exec_()




