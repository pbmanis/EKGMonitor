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

DEFAULT_AUDIO_RATE = (
    96000  # 44100  # 96000  # 44100  # in Hz. Mac Mini will do 96K (see via Utility)
)
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
    SD.stop()


# threaded class to handle parameter changes while keeping gui open
# includes ability to pause and resume.
class Worker(QObject):
    # define signals that we will emit.
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
        self._running = False  # to stop the event
        self._quit = False
        self.frequency = 1000.0
        self.old_freq = self.frequency
        self.duration = 0.05
        self.old_dur = self.duration
        self.interval = 0.2
        self.old_interval = self.interval
        self.stimulus = "Tone"
        self.old_stimulus = self.stimulus
        self.dblevel = 100.0
        self.old_level = self.dblevel
        self.wave = None
        self.params = parameters

        print("worker init complete...")

    @pyqtSlot()
    def run(self):
        """
        Check the parameters periodically (often enough to seem responsive)
        present the stimuli as needed.
        """
        # print("worker: run started")
        nreps = 0
        while True:
            if self._quit:
                # print("worker: quit set: running ended")
                return
            if not self._running:
                continue
            if self.params.device == "SDG810":
                self.params.sdg810.write("C1:OUTP ON")
                self.params.sdg810.query("*OPC?")
                time.sleep(self.duration)
                self.params.sdg810.write("C1:OUTP OFF")
            else:
                # play a sound on the soundcard
                # only recompute the waveform if uupdate is needed
                if (
                    (self.frequency != self.old_freq)
                    or self.wave is None
                    or (self.duration != self.old_dur)
                    or (self.interval != self.old_interval)
                    or (self.stimulus != self.old_stimulus)
                    or (self.dblevel != self.old_level)
                ):
                    match self.stimulus:
                        case "Tone":
                            self.wave = sound.TonePip(
                                rate=DEFAULT_AUDIO_RATE,
                                f0=self.frequency,
                                duration=self.duration,
                                dbspl=self.dblevel,
                                pip_duration=self.duration,
                                pip_starts=[0.0],
                                ramp_duration=0.005,
                            )
                        case "Noise":
                            self.wave = sound.NoisePip(
                                rate=DEFAULT_AUDIO_RATE,
                                duration=self.duration,
                                dbspl=self.dblevel,
                                pip_duration=self.duration,
                                pip_starts=[0.0],
                                ramp_duration=0.005,
                                seed=12345
                            )
                        case "Click":
                            self.wave = sound.ClickTrain(
                                rate=DEFAULT_AUDIO_RATE,
                                duration=self.duration,
                                dbspl=self.dblevel,
                                click_duration=0.0001,
                                click_starts=[0.0, self.duration*0.45, self.duration*0.90],
                            )
                        case _:
                            raise ValueError("Unknown stimulus")
                            self.quit()

                    if self.frequency != self.old_freq:
                        self.old_freq = self.frequency
                    if self.duration != self.old_dur:
                        self.old_dur = self.duration
                    if self.interval != self.old_interval:
                        self.old_interval = self.interval
                    if self.stimulus != self.old_stimulus:
                        self.old_stimulus = self.stimulus
                    if self.dblevel != self.old_level:
                        self.old_level = self.dblevel


                play_wave(self.wave.sound, DEFAULT_AUDIO_RATE)

            time.sleep(self.interval)
            nreps += 1
            # print("nreps: ", nreps)
            time.sleep(float(THREAD_PERIOD / 1000.0))  # Short delay to allow GUI to process
        # print("running ended")

    @pyqtSlot(float)
    def set_frequency(self, freq: float):
        # print("slot freq")
        self.frequency = freq

    @pyqtSlot(float)
    def set_duration(self, duration: float):
        # print("slot dur")
        self.duration = duration
        # print("... duration: ", duration)

    @pyqtSlot(float)
    def set_interval(self, interval: float):
        # print("slot Interval")
        self.interval = interval
    
    @pyqtSlot(int)
    def set_level(self, level: int):
        print("slot level")
        self.dblevel = level

    @pyqtSlot(str)
    def set_stimulus(self, stimulus: str):
        # print("slot stimulus")
        self.stimulus = stimulus

    @pyqtSlot()
    def start_stim(self):
        """
        Start the thread.
        """
        # print("slot start_stim")
        if not self._running:
            # print("setting running")
            self._running = True

    @pyqtSlot()
    def stop_stim(self):
        """
        Stop the run routine from generating stimuli.
        This is needed at the end of the program to terminate cleanly.
        """
        # print("slot stop_stim called")
        self._running = False  # set running False
        self.sig_finished.emit()  # send a signal

    @pyqtSlot()
    def quit(self):
        """quit: called to end the thread by returning from the run routine."""
        # print("slot quit called")
        self._running = False
        self._quit = True
        self.sig_finished.emit()


class SliderWithValue(pg.QtWidgets.QSlider):

    def __init__(self, parent=None, value_mapper: callable = None):
        super(SliderWithValue, self).__init__(parent)
        self.value_mapper = value_mapper
        self.stylesheet = """
        QSlider::groove:vertical {
                background-color: #222;
                width: 30px;
        }
        QSlider::handle:vertical {
            border: 1px #438f99;
            border-style: outset;
            margin: -2px 0;
            width: 30px;
            height: 3px;
            background-color: #438f99;
        }
        QSlider::sub-page:vertical {
            background: #4B4B4B;
        }
        QSlider::groove:horizontal {
                background-color: #222;
                height: 120px;
        }
        QSlider::handle:horizontal {
            border: 1px #438f99;
            border-style: outset;
            margin: -2px 0;
            width: 3px;
            height: 10px;
            background-color: #438f99;
        }
        
        """
        # this is the color of the area Behind the bar...
        # QSlider::sub-page:horizontal {
        #     background: #438f99;
        # }
        # 4B4B4B
        self.setStyleSheet(self.stylesheet)
        # painter = pg.Qt.QtGui.QPainter(self)
        # rect = self.geometry()
        # print(rect)
        # for tick in [1, 4, 8, 16, 24, 32, 48]:
        #     painter.drawText(
        #         pg.Qt.QtCore.QPoint(
        #             int(tick*1000),
        #             int(rect.height())),
        #             str(tick),

        #     )
        #     path = pg.Qt.QtGui.QPainterPath()
        #     path.moveTo(tick, rect.height()+20)
        #     path.lineTo(tick, rect.height()-20)
        #     painter.drawPath(path)
        #     item = QtWidgets.QGraphicsPathItem(path)
        #     item.setBrush(pg.mkBrush(255, 255, 255))
        #     item.setPen(pg.mkPen(255, 255, 255))

    def paintEvent(self, event):
        pg.QtWidgets.QSlider.paintEvent(self, event)

        if self.value_mapper is None:
            curr_value = str(self.value())
            round_value = round(float(curr_value), 2)
        else:
            round_value = self.value_mapper(self.value())[1]  # get string formatted version

        painter = pg.Qt.QtGui.QPainter(self)
        # painter.setPen(pg.Qt.QtGui.QPen(pg.Qt.QtCore.Qt.white))

        font_metrics = pg.Qt.QtGui.QFontMetrics(self.font())
        font_width = font_metrics.boundingRect(str(round_value)).width()
        font_height = font_metrics.boundingRect(str(round_value)).height()

        rect = self.geometry()
        if self.orientation() == QtCore.Qt.Orientation.Horizontal:
            horizontal_x_pos = int(self.value() / 2)  # int(rect.width() - font_width - 5)
            horizontal_y_pos = int(rect.height() * 0.75)  # 0.75)

            painter.drawText(
                pg.Qt.QtCore.QPoint(horizontal_x_pos, horizontal_y_pos), str(round_value)
            )

        elif self.orientation() == QtCore.Qt.Orientation.Vertical:
            # vertical_x_pos = int(rect.width() - font_width - 5)
            # vertical_y_pos = int(rect.height() * 0.75)

            painter.drawText(
                pg.Qt.QtCore.QPoint(
                    int(rect.width() / 2.0 - font_width / 2.0), int(rect.height() + 20)
                ),
                str(round_value),
            )
        else:
            pass

        painter.drawRect(rect)


# sdg810 = attach_sdg()
class AudioStimulator(QObject):

    # set up some signals
    signal_change_frequency = QtCore.pyqtSignal(float)
    signal_change_duration = QtCore.pyqtSignal(float)
    signal_change_interval = QtCore.pyqtSignal(float)
    signal_change_stimulus = QtCore.pyqtSignal(str)
    signal_change_level = QtCore.pyqtSignal(int)
    signal_paused = QtCore.pyqtSignal()
    signal_start = QtCore.pyqtSignal()
    signal_stop = QtCore.pyqtSignal()
    signal_quit = QtCore.pyqtSignal()

    def __init__(self):
        # first find the hardware:
        self.sdg810 = attach_sdg()  # result will be None if no sdg180 found, then use soundcard
        self.event = Event()
        if self.sdg810 is not None:
            self.device = "SDG810"
        else:
            self.device = "Soundcard"
        self.stimulus = "Tone"
        print(f"Device is {self.device:s}")
        self.running = False
        self.thread = None
        self.stop_thread = False
        self.frequency = 1000.0
        self.duration = 0.05
        self.interval = 0.2
        self.dblevel = 100.0
        self.maximum_frequency = int(DEFAULT_AUDIO_RATE / 2.0)
        self.minimum_frequency = 1000.0

        self.max_slider = 1000
        self.min_slider = 0

        super(AudioStimulator, self).__init__()

        ptreewidth = 220
        self.app = pg.mkQApp()
        self.params = [
            {
                "name": "Device",
                "type": "list",
                "limits": ["SDG810", "Soundcard"],
                "value": self.device,
            },
            {
                "name": "Sound Type",
                "type": "list",
                "limits": ["Tone", "Noise", "Click"],
                "value": self.stimulus,
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
                    {
                        "name": "Level",
                        "type": "list",
                        "limits": [40, 50, 60, 70, 80, 90, 100],
                        "value": self.dblevel,
                    }
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
        self.win.resize(800, 275)
        self.dockArea = PGD.DockArea()
        self.Dock_Params = PGD.Dock("Params", size=(ptreewidth, 1024))
        self.dockArea.addDock(self.Dock_Params, "left")
        self.Dock_Params.addWidget(self.ptree)
        self.Dock_Slider = PGD.Dock("Frequency, Intensity", size=(700, 200))
        # self.app.setStyleSheet("QSlider::handle:horizontal {background-color: white; border:1px solid; height: 20px; width: 20px; margin: -10px 0;}")
        # self.app.setStyleSheet("QSlider::groove:horizontal {border: 1px solid; height: 10px; margin: 0 px; background-color: black; width: 10px;}")
        self.freq_slider = SliderWithValue(
            QtCore.Qt.Orientation.Horizontal,
            value_mapper=self.map_slider_to_frequency,
        )  # pg.QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.freq_slider.setMinimum(self.min_slider)
        self.freq_slider.setMaximum(self.max_slider)
        self.freq_slider.setValue(self.map_frequency_to_slider(self.frequency))
        self.freq_slider.setTickPosition(pg.Qt.QtWidgets.QSlider.TickPosition.TicksBelow)
        self.freq_slider.setSizePolicy(
            pg.QtWidgets.QSizePolicy.Policy.MinimumExpanding, pg.QtWidgets.QSizePolicy.Policy.Fixed
        )
        self.freq_slider.setTickInterval(1)
        self.freq_slider.setSingleStep(1)
        self.Dock_Slider.addWidget(self.freq_slider)

        self.dblevel_slider = SliderWithValue(
            QtCore.Qt.Orientation.Horizontal,
            value_mapper=None,
        )  # pg.QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.dblevel_slider.setMinimum(0)
        self.dblevel_slider.setMaximum(100)
        self.dblevel_slider.setValue(int(self.dblevel))
        self.dblevel_slider.setTickPosition(pg.Qt.QtWidgets.QSlider.TickPosition.TicksBelow)
        self.dblevel_slider.setSizePolicy(
            pg.QtWidgets.QSizePolicy.Policy.MinimumExpanding, pg.QtWidgets.QSizePolicy.Policy.Fixed
        )
        self.dblevel_slider.setTickInterval(5)
        self.dblevel_slider.setSingleStep(5)
        self.Dock_Slider.addWidget(self.dblevel_slider)
    
        self.dockArea.addDock(self.Dock_Slider, "right")
        self.win.setCentralWidget(self.dockArea)

        self.win.show()
        self.ptreedata.sigTreeStateChanged.connect(self.command_dispatcher)
        self.threadpool = QThreadPool()  # threadpool will be instantiated in the start routine

        self.timer = pg.Qt.QtCore.QTimer()
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.recurring_timer)
        self.timer.start()

        self.Stimulation = Worker(parameters=self)
        self.signal_change_frequency.connect(self.Stimulation.set_frequency)
        self.freq_slider.valueChanged.connect(
            lambda: self.signal_change_frequency.emit(
                float(self.map_slider_to_frequency(self.freq_slider.value())[0])
            )
        )
        self.dblevel_slider.valueChanged.connect(
            lambda: self.signal_change_level.emit(self.dblevel_slider.value())
        )

        self.signal_change_duration.connect(self.Stimulation.set_duration)
        self.signal_change_interval.connect(self.Stimulation.set_interval)
        self.signal_change_stimulus.connect(self.Stimulation.set_stimulus)
        self.signal_change_level.connect(self.Stimulation.set_level)
        self.signal_start.connect(self.Stimulation.start_stim)
        self.signal_stop.connect(self.Stimulation.stop_stim)
        self.signal_quit.connect(self.Stimulation.quit)
        self.threadpool.start(self.Stimulation.run)  # start reading the updated parameters

    def recurring_timer(self):
        time.sleep(0.01)

    def map_slider_to_frequency(self, value: int):
        """done Convert slider value from range 1 to 1000 to frequency in Hz.
        The slider position is treated as a log scale, so the frequency is
        calculated as 1000 * 2^(value/

        Parameters
        ----------

        value : int
            slider position
        """
        # print("value: ", value)
        # print("min_freq: ", self.minimum_frequency)
        # print("max_freq: ", self.maximum_frequency)
        # print("max_slider: ", self.max_slider)

        fr = self.minimum_frequency * (self.maximum_frequency / self.minimum_frequency) ** (
            value / self.max_slider
        )
        frstr = f"{fr:.1f}"
        return (fr, frstr)

        # min_freq * (max_freq / min_freq) ** (value / max_slider)

    def map_frequency_to_slider(self, freq: float):
        """map_slider_from_frequency Convert frequency to the slider
        position.

        Parameters
        ----------
        freq : float
            _description_
        """
        return int(
            self.max_slider
            * np.log2(freq / self.minimum_frequency)
            / np.log2(self.maximum_frequency / self.minimum_frequency)
        )


    def command_dispatcher(self, param, changes):
        for param, change, data in changes:
            path = self.ptreedata.childPath(param)
            match path[0]:
                case "Device":
                    if data == "SDG810" and self.sdg810 is not None:
                        self.device = data
                    else:
                        self.device = "Soundcard"
                case "Sound Type":
                    self.stimulus = data
                    self.signal_change_stimulus.emit(data)
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
                        case "Level":
                            self.signal_change_level.emit(int(data))
                case _:
                    pass

    def start(self):
        # print("***** start called")
        self.signal_start.emit()

    def stop(self):
        # print("***** stop called")
        self.signal_stop.emit()

    def quit(self):
        # print("Quitting")
        # immediate stop of all stimuli
        if self.sdg810 is not None:
            self.sdg810.write("C1:OUTP OFF")
        else:
            SD.stop()
        self.stop()
        self.signal_quit.emit()
        self.threadpool.waitForDone(5 * THREAD_PERIOD)
        exit()


if __name__ == "__main__":

    STIM = AudioStimulator()
    pg.exec()
