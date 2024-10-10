import pyvisa as pv
import time
import numpy as np

import threading
from threading import Event

import pyqtgraph as pg
from pyqtgraph.parametertree import Parameter, ParameterTree
import pyqtgraph.dockarea as PGD
from pyqtgraph.Qt.QtCore import QObject, QRunnable, QThreadPool, pyqtSlot, pyqtSignal
from pyqtgraph.Qt import QtCore, QtWidgets
import sounddevice as SD
import sound

DEFAULT_AUDIO_RATE = 44100  # 96000  # 44100  # in Hz. Mac Mini will do 96K (see via Utility)
THREAD_PERIOD = 20  # thread period, in msec


def attach_sdg():
    rm = pv.ResourceManager()
    resources = rm.list_resources()
    resnum = None
    for i, res in enumerate(resources):
        # print("resource: ", res)
        if res.find("SDG0") >= 0:
            resnum = i
    if resnum is None:
        print("SDG not found in (py)VISA. Available resources: ", resources)
        return None
    else:
        print("Found: ", resources[resnum])
    inst = resources[resnum]
    sdg810 = rm.open_resource(inst)
    return sdg810


def play_wave(wave, rate):
    # play a waveform on the default sound device.
    # Wave is the waveform
    # rate is the sample rate at which the waveform was generated.
    # downsample wave for speaker
    # twave = np.linspace(0, len(wave) / rate, len(wave))
    # tmax = np.max(twave)
    # tnew = np.arange(0, tmax, 1.0 / rate)
    # dwave = np.interp(tnew, twave, wave)
    # now play it.

    SD.play(wave, rate)
    SD.wait()  # duration of sound is set by the waveform
    time.sleep(0.01)
    SD.stop()


class WorkerSignals(QRunnable, QObject):
    """
    Defines the signals available from a running worker thread.

    Supported signals are:

        finished
            No data returned
        error
            returns tuple (exctype, value, traceback.format_exc() )
        result
            returns object data returned from processing, anything
        paused
            no data returned
        resume
            no data returned

    """

    finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(tuple)
    result = QtCore.pyqtSignal(object)
    paused = QtCore.pyqtSignal()
    resume = QtCore.pyqtSignal()
    start = QtCore.pyqtSignal()

    # def __init__(cls):
    #     super(WorkerSignals, cls).__init__()
    #     pass
    # def run(cls):
    #     pass


# threaded class to handle parameter changes while keeping gui open
# includes ability to pause and resume.
class Worker(QObject):

    sig_finished = QtCore.pyqtSignal()
    sig_error = QtCore.pyqtSignal(tuple)
    sig_result = QtCore.pyqtSignal(object)
    sig_paused = QtCore.pyqtSignal()
    sig_resume = QtCore.pyqtSignal()
    sig_start = QtCore.pyqtSignal()

    def __init__(self, parameters=None):
        """
        Params
        ------
        UI_params: UI class to read settings and report values

        """
        super(Worker, self).__init__()
        self._paused = False  # flag for suspencing thread
        self._running = False  # to stop the event
        self.frequency = 1000.0
        self.old_freq = self.frequency
        self.duration = 0.05
        self.old_dur = self.duration
        self.interval = 0.2
        self.old_interval = self.interval
        self.wave = None
        # self.signals = WorkerSignals()
        self.params = parameters
        print("worker init complete...")

    def run(self):
        pass

    @pyqtSlot()
    def run_stim(self):
        """
        Check the parameters periodically (often enough to seem responsive)
        present the stimuli as needed.
        """
        print("worker run")
        while self._running:
            if self._paused:
                self.signals.paused.emit()
                break
            if self.params.device == "SDG810":
                self.params.sdg810.write("C1:OUTP ON")
                self.params.sdg810.query("*OPC?")
                time.sleep(self.duration)
                self.params.sdg810.write("C1:OUTP OFF")
            else:
                # play a sound on the soundcard
                # print("dur: ", new_dur, "freq; ", new_freq)
                # only recompute the waveform if uupdate is needed
                if (
                    (self.frequency != self.old_freq)
                    or self.wave is None
                    or (self.duration != self.old_dur)
                ):
                    self.wave = sound.TonePip(
                        rate=DEFAULT_AUDIO_RATE,
                        f0=self.frequency,
                        duration=self.duration,
                        dbspl=None,
                        pip_duration=self.duration,
                        pip_starts=[0.0],
                        ramp_duration=0.005,
                    )

                play_wave(self.wave.sound, DEFAULT_AUDIO_RATE)

            time.sleep(self.interval - float(THREAD_PERIOD / 1000.0))

            time.sleep(float(THREAD_PERIOD / 1000.0))  # Short delay to prevent excessive CPU usage
        print("running ended")

    @pyqtSlot(float)
    def set_frequency(self, freq: float):
        print("slot freq")
        self.frequency = freq

    @pyqtSlot(float)
    def set_duration(self, duration: float):
        print("slot dur")
        self.duration = duration
        print("... duration: ", duration)

    @pyqtSlot(float)
    def set_interval(self, interval:float):
        print("slot Interval")
        self.interval = interval

    # @pyqtSlot()
    # def start(self):
    #     print("start called")
    #     if not self._running:
    #         self._running = True
    # self.run()
    # self.run()

    @pyqtSlot()
    def pause(self):
        # pause the thread - during some update operations, and
        # when transmitting.
        print("slot pause")
        self._paused = True  # set False to block the thread
        self._running = False
        self.sig_paused.emit()

    @pyqtSlot()
    def start(self):
        """
        Start the thread.
        """
        print("slot start")
        if not self._running:
            print("setting running")
            self._running = True
            self._paused = False
            self.run_stim()
            self.sig_start.emit()

    @pyqtSlot()
    def stop(self):
        """
        Stop the thread from running.
        This is needed at the end of the program to terminate cleanly.
        """
        self._paused = False  # resume if paused
        self._running = False  # set running False
        self.sig_finished.emit()  # send a signal


# sdg810 = attach_sdg()
class AudioStimulator(QObject):

    # set up some signals
    signal_change_frequency = QtCore.pyqtSignal(float)
    signal_change_duration = QtCore.pyqtSignal(float)
    signal_change_interval = QtCore.pyqtSignal(float)
    signal_paused = QtCore.pyqtSignal()
    signal_start = QtCore.pyqtSignal()
    signal_stop = QtCore.pyqtSignal()

    def __init__(self):
        # first find the hardware:
        self.sdg810 = attach_sdg()  # result will be None if no sdg180 found, then use soundcard
        self.event = Event()
        if self.sdg810 is not None:
            self.device = "SDG810"
        else:
            self.device = "Soundcard"
        print(f"Device is {self.device:s}")
        self.running = False
        self.thread = None
        self.stop_thread = False
        self.frequency = 1000.0
        self.duration = 0.05
        self.interval = 0.2
        super(AudioStimulator, self).__init__()

        ptreewidth = 200
        self.app = pg.mkQApp()
        self.params = [
            {
                "name": "Device",
                "type": "list",
                "limits": ["SDG810", "Soundcard"],
                "value": self.device,
            },
            {"name": "Start", "type": "action"},
            {"name": "Stop", "type": "action"},
            {"name": "Quit", "type": "action"},
            {
                "name": "Stimulus",
                "type": "group",
                "children": [
                    {"name": "Frequency", "type": "float", "value": self.frequency},
                    {
                        "name": "Duration",
                        "type": "list",
                        "limits": [0.02, 0.05, 0.10, 0.20, 0.50, 1.00],
                        "value": self.duration,
                    },
                    {
                        "name": "Interval",
                        "type": "list",
                        "limits": [0.1, 0.2, 0.25, 0.5, 1.0],
                        "value": self.interval,
                    },
                ],
            },
        ]
        self.ptree = ParameterTree()
        self.ptreedata = Parameter.create(name="Models", type="group", children=self.params)
        self.ptree.setStyleSheet(
            """
            QTreeView {
                background-color: '#282828';
                alternate-background-color: '#646464';   
                color: rgb(238, 238, 238);
            }
            QLabel {
                color: rgb(238, 238, 238);
            }
            QTreeView::item:has-children {
                background-color: '#212627';
                color: '#00d4d4';
            }
            QTreeView::item:selected {
                background-color: '##c1c3ff';
            }
                """
        )
        self.ptree.setParameters(self.ptreedata)

        self.ptree.setMaximumWidth(ptreewidth + 50)
        self.ptree.setMinimumWidth(ptreewidth)
        self.win = pg.QtWidgets.QMainWindow()
        self.win.setWindowTitle("Stimulus Controller")
        self.win.resize(800, 250)
        self.dockArea = PGD.DockArea()
        self.Dock_Params = PGD.Dock("Params", size=(ptreewidth, 1024))
        self.dockArea.addDock(self.Dock_Params, "left")
        self.Dock_Params.addWidget(self.ptree)
        self.win.setCentralWidget(self.dockArea)

        self.win.show()
        self.ptreedata.sigTreeStateChanged.connect(self.command_dispatcher)
        self.threadpool = QThreadPool()  # threadpool will be instantiated in the start routine

        self.timer = pg.Qt.QtCore.QTimer()
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.recurring_timer)
        self.timer.start()
        print("Gui set up")

        self.Stimulation = Worker(parameters=self)
        # print(dir(self.Stimulation))
        print("stimulation worker created")
        self.signal_change_frequency.connect(self.Stimulation.set_frequency)
        print("... 1")
        self.signal_change_duration.connect(self.Stimulation.set_duration)
        # print("... 2")
        self.signal_change_interval.connect(self.Stimulation.set_interval)
        print("... 3")
        self.signal_paused.connect(self.Stimulation.pause)
        print("... 4")
        self.signal_start.connect(self.Stimulation.start)
        print("... 5")
        self.Stimulation.sig_finished.connect(self.done)
        self.signal_stop.connect(self.Stimulation.stop)
        # self.signal_paused.emit()
        print("... 6")

        print("signals created")
        # self.Stimulation.signals.finished.connect(self.done)
        self.threadpool.start(self.Stimulation.start)  # start reading the updated parameters

        print("thread started")

    def recurring_timer(self):
        # print("recurring")
        pass

    def getdur(self):
        return self.duration
    
    def done(self):
        pass

    def command_dispatcher(self, param, changes):
        print("param: ", param)
        print("changes: ", changes)
        for param, change, data in changes:
            path = self.ptreedata.childPath(param)
            print("path: ", path)
            match path[0]:
                case "Device":
                    if data == "SDG810" and self.sdg810 is not None:
                        self.device = data
                    else:
                        self.device = "Soundcard"
                case "Quit":
                    self.quit()
                case "Start":
                    self.start()
                case "Stop":
                    self.stop()
                case "Stimulus":
                    match path[1]:
                        case "Frequency":
                            self.signal_change_frequency.emit(float(data))
                        case "Duration":
                            print("dur hit", float(data))
                            self.signal_change_duration.emit(float(data))
                        case "Interval":
                            self.signal_change_interval.emit(float(data))
                case _:
                    pass

    def start(self):
        print("***** start called")
        self.signal_start.emit()

    def stop(self):
        print("***** stop called")
        self.signal_stop.emit()
        # self.Stimulation.stop()

    # def get_duration(self, verbose: bool = False):
    #     return self.duration

    # def get_frequency(self, verbose: bool = False):
    #     return self.frequency

    def quit(self):
        print("Quitting")
        self.stop()
        if self.sdg810 is not None:
            self.sdg810.write("C1:OUTP OFF")
        else:
            # SD.wait()
            SD.stop()
        self.threadpool.waitForDone(5 * THREAD_PERIOD)
        # if self.thread is not None:
        #     self.thread.join(2)
        exit()


if __name__ == "__main__":

    STIM = AudioStimulator()
    pg.exec()
