import pyvisa as pv
import time
import numpy as np

# import tkinter as TK
# from tkinter import ttk
import threading
from threading import Event
import sounddevice as SD
import sound
import pyqtgraph as pg
from pyqtgraph.parametertree import Parameter, ParameterTree
import pyqtgraph.dockarea as PGD

DEFAULT_AUDIO_RATE = 44100


def attach_sdg():
    rm = pv.ResourceManager()
    resources = rm.list_resources()
    resnum = None
    for i, res in enumerate(resources):
        print("resource: ", res)
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
    twave = np.linspace(0, len(wave) / rate, len(wave))
    tmax = np.max(twave)
    tnew = np.arange(0, tmax, 1.0 / rate)
    dwave = np.interp(tnew, twave, wave)
    # now play it.
    SD.play(dwave, rate)


# sdg810 = attach_sdg()
class Stim:
    def __init__(self):
        # first find the hardware:
        self.sdg810 = attach_sdg()
        if self.sdg810 is None:
            # use soundcard
            pass
        self.event = Event()
        # self.root = TK.Tk()
        # self.root.title("SDG810 Controller: pulsing")
        print("sdg 810 found? ", self.sdg810)
        self.running = False
        self.thread = None
        self.stop_thread = False
        self.frequency = 1000.
        self.duration = 0.05
        self.interval = 0.2
        if self.sdg810 is not None:
            self.device = "SDG810"
        else:
            self.device = "Soundcard"
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

        self.running = True
        self.win.show()
        self.ptreedata.sigTreeStateChanged.connect(self.command_dispatcher)
        # self.root.mainloop()

    def command_dispatcher(self, param, changes):
        # print("param: ", param)
        print("changes: ", changes)
        for param, change, data in changes:
            path = self.ptreedata.childPath(param)
            # print("path: ", path)
            match path[0]:
                case "Device":
                    if data == 'SDG810' and self.sdg810 is not None:
                        self.device = data
                    else:
                        self.device = "Soundcard"
                case "Quit":
                    self.quit()
                case "Start":
                    self.start()
                case "Stop":
                    self.stop()
                case ("Stimulus", "Frequency"):
                    self.frequency = float(data)
                    self.event.set()
                case ("Stimulus", "Duration"):
                    self.duration = float(data)
                    self.event.set()
                case ("Stimulus", "Interval"):
                    self.interval = float(data)
                case _:
                    pass

    def showfreq(self, event):
        self.frequency = float(event)
        return

    def start(self):
        if self.thread is None:  # only start once.

            self.thread = threading.Thread(target=self.run, args=(self.duration, self.frequency))
            self.thread.start()
            self.running = True
        else:
            self.running = True  # set the running flag.
    
    def get_duration(self):
        return self.duration
    
    def get_freq(self):
        return self.frequency
    
    def run(self, duration, frequency):
        time.sleep(0.1)
        # print("Called run: ", sdg810.query("*IDN?"))
        if self.sdg810 is not None:
            self.sdg810.write("*RST")
        while True:
            print("self.event: ", self.event.is_set())
            if self.event.is_set():
                duration = self.duration
                frequency = self.frequency
                print("duration: ", duration)
                self.event.clear()
            if self.running:
                if self.device == "SDG810":
                    self.sdg810.write("C1:OUTP ON")
                    self.sdg810.query("*OPC?")
                    time.sleep(duration)
                else:
                    # play a sound on the soundcard
                    print("sound card output: ")
                    print("dur: ", duration, "freq; ", frequency)
                    wave = sound.TonePip(
                        rate=DEFAULT_AUDIO_RATE,
                        f0=frequency,
                        duration=duration,
                        dbspl=None,
                        pip_duration=duration,
                        pip_starts=[0.0],
                        ramp_duration=0.005,
                    )
                    play_wave(wave.sound, DEFAULT_AUDIO_RATE)
                    SD.wait()  # duration of sound is set by the waveform

                # print(self.sdg810.query("C1:OUTP?"))
                if self.device == "SDG810":
                    self.sdg810.write("C1:OUTP OFF")
                else:
                    SD.stop()
                time.sleep(self.interval)
                # print("...", self.sdg810.query("C1:OUTP?"))
            elif self.stop_thread:
                if self.sdg810 is not None:
                    self.sdg810.write("C1:OUTP OFF")
                else:
                    SD.stop()
                break
            else:
                time.sleep(0.02)

    def quit(self):
        print("Quitting")
        self.running = False
        self.stop_thread = True
        if self.sdg810 is not None:
            self.sdg810.write("C1:OUTP OFF")
        else:
            SD.wait()
            SD.stop()
        if self.thread is not None:
            self.thread.join(2)
        # self.root.destroy()
        exit()

    def stop(self):
        self.running = False


if __name__ == "__main__":

    STIM = Stim()
    pg.exec()
