import sys
from dataclasses import dataclass, field
from time import sleep
from typing import Union

import pyaudio
import pyqtgraph as pg
import pyqtgraph.dockarea as PGD
# import arduino_comms
import serial
from pyqtgraph.parametertree import Parameter, ParameterTree
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
from pyqtgraph.Qt.QtCore import QObject, QRunnable, QThreadPool, pyqtSlot

import buttons
import si5351mcu  # our pythbon version of Pavel Milanes arduino library
import tuning_dial

THREAD_PERIOD = 20  # VFO thread period, in msec

class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.

    Supported signals are:

        finished
            No data
        error
            tuple (exctype, value, traceback.format_exc() )
        result
            object data returned from processing, anything

    """

    finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(tuple)
    result = QtCore.pyqtSignal(object)
    paused = QtCore.pyqtSignal()
    resume = QtCore.pyqtSignal()


# threaded class around tuning_dial to handle tuning while keeping gui open
# include ability to pause and resume.
class Tuning(QRunnable):

    def __init__(self, tuner):
        """
        Params
        ------
        tuner: Tuner class to read dial, and report values

        """
        super(Tuning, self).__init__()
        self._paused = False  # flag for suspencing thread
        self._running = False # to stop the event 
        
        self.signals = WorkerSignals()
        self.Tuner = tuner

    @pyqtSlot()
    def run(self):
        """
        Check the dial setting periodically (often enough to seem responsive)
        Display the frequency to the label.
        """
        self._running = True
        while self._running:
            if self._paused:  # if paused, just wait for resume or stop

                return None  # don't do anything
            new_freq = self.Tuner.read_dial(
                verbose=False
            )  # Tuner updates the display itself
            if new_freq is not None:
                self.signals.result.emit(
                    new_freq
                )  # notify we need to update the display
            sleep(float(THREAD_PERIOD/1000.0))  # Short delay to prevent excessive CPU usage
    
    def pause(self):
        # pause the thread - during some update operations, and
        # when transmitting.
        self._paused=True  # set False to block the thread
        self.signals.paused.emit()

    def resume(self):
        # allow the VFO control to continue
        self._paused=False
        self.signals.resume.emit()

    @pyqtSlot()
    def stop(self):
        """
        Stop the thread from running.
        This is needed at the end of the program to terminate cleanly.
        """
        self._paused = False # resume if paused
        self._running = False # set running False
        self.signals.finished.emit()  # send a signal 


class SU_Het:
    def __init__(self):

        # first confirm that the hardware is working
        self.VFO_HDW = si5351mcu.Si5351mcu()

        self.VFO_HDW.enable(clk=0)
        self.VFO_HDW.set_frequency(clk=0, freq=7000000, mode=1)
        self.VFO_HDW.setPower(0, 3)
        self.qapp = pg.mkQApp()
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setFixedPitch(False)
        font.setPointSize(11)
        self.primary_font = font
        self.primary_button_size = QtCore.QSize(80, 50)
        self.max_rows = 8
        self.grid_initialize()
        self.build_ui()

        # now create the tuning dials, and put the reading
        # actions into a separate thread
        tuner = tuning_dial.TuningDial(using_threaded=True)
        tuner.add_vfo(
            "A",
            initial_frequency=7e6,
            display_widget=self.VFO_A,
            info_widget=self.VFO_A_Info,
            role="VFO",
        )
        tuner.add_vfo(
            "B",
            initial_frequency=7e6,
            display_widget=self.VFO_B,
            info_widget=self.VFO_B_Info,
            role="VFO",
        )
        tuner.set_active_vfo_by_name("A")
        self.Tuner = tuner
        self.Tuning = Tuning(self.Tuner)

        self.timer = pg.QtCore.QTimer()
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.recurring_timer)
        self.timer.start()

        # Once the GUI is setup, we can go ahead and start the thread
        # that reads the VFO tuning dial.
        self.threadpool = QThreadPool()
        self.threadpool.start(self.Tuning)  # start reading the VFO

        self.current_freqs = {
            "160": [1.80, 1.80],
            "80": [3.5, 3.5],
            "60": [5.2, 5.2],
            "40": [7.0, 7.0],
            "30": [10.1, 10.1],
            "20": [14.0, 14.0],
            "17": [18.068, 18.068],
            "15": [21.0, 21.0],
            "12": [24.890, 24.890],
            "10": [28.0, 28.0],
            "6": [50.0, 50.0],
        }
        self.current_band = "40"
        init_freq = 1e6 * self.current_freqs[self.current_band][0]
        self.Tuner.set_frequency(init_freq)
        vfo = self.Tuner.get_active_vfo()
        self.VFO_HDW.set_frequency(clk=0, freq=vfo.frequency) # update the synthesizer
        # self.updateDisplay()
        # now catch the signals from the Tuner when something changes, and hanle it here
        self.Tuning.signals.result.connect(self.updateDisplay)
        self.Tuning.signals.finished.connect(self.stop_vfo_thread)
        # self.Tuning.signals.paused.connect(self.pause_vfo_thread)

    def recurring_timer(self):
        pass  # do nothing

    def build_ui(self):
        """build_ui Create the User Interface"""
        self.qapp.setStyle("fusion")
        dark_palette = QtGui.QPalette()
        white = QtGui.QColor(255, 255, 255)
        black = QtGui.QColor(0, 0, 0)
        red = QtGui.QColor(255, 0, 0)

        # set the general palette colors

        dark_palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(53, 53, 53))
        dark_palette.setColor(QtGui.QPalette.ColorRole.WindowText, white)
        dark_palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(25, 25, 25))
        dark_palette.setColor(
            QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(53, 53, 53)
        )
        dark_palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, white)
        dark_palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, white)
        dark_palette.setColor(QtGui.QPalette.ColorRole.Text, white)
        dark_palette.setColor(
            QtGui.QPalette.ColorRole.Button, QtGui.QColor(55, 55, 192)
        )
        dark_palette.setColor(QtGui.QPalette.ColorRole.ButtonText, white)
        dark_palette.setColor(QtGui.QPalette.ColorRole.BrightText, red)
        dark_palette.setColor(QtGui.QPalette.ColorRole.Link, QtGui.QColor(42, 130, 218))
        dark_palette.setColor(
            QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(42, 130, 218)
        )
        dark_palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, black)

        self.qapp.setPalette(dark_palette)
        self.qapp.setStyleSheet(
            "QToolTip { color: #ffffff; background-color: #2a82da; border: 1px solid white; }"
        )

        # Create main window with a grid layout
        self.mainWin = QtWidgets.QMainWindow()

        self.mainWin.setWindowTitle("Su_Het Controller")
        self.mainWin.resize(800, 460)

        self.dockArea = PGD.DockArea()
        self.mainWin.setCentralWidget(self.dockArea)

        # Initial Dock Arrangment
        self.Dock_Buttons = PGD.Dock("Buttons", size=(800, 380), fontSize=28)
        self.Dock_Graphs = PGD.Dock("Graphs", size=(800, 380), fontSize=28)
        self.Dock_Graphs2 = PGD.Dock("Graphs2", size=(800, 380), fontSize=28)
        self.Dock_Report = PGD.Dock("Reporting", size=(800, 40), fontSize=28)
        self.Dock_Freqs = PGD.Dock("VFO", size=(800, 400), fontSize=28)
        # set up spatial relationships

        self.dockArea.addDock(self.Dock_Freqs, "left")
        self.dockArea.addDock(
            self.Dock_Buttons,
            "bottom",
            self.Dock_Freqs,
        )
        self.dockArea.addDock(self.Dock_Graphs, "below", self.Dock_Buttons)
        self.dockArea.addDock(self.Dock_Graphs2, "below", self.Dock_Graphs)
        self.dockArea.addDock(self.Dock_Report, "bottom", self.Dock_Graphs)
        self.Dock_Buttons.raiseDock()
        # set titles and add graphs to the graph docks
        self.Graphs = pg.PlotWidget(title="Graphs")
        self.Dock_Graphs.addWidget(self.Graphs, rowspan=5, colspan=1)
        self.Graphs2 = pg.PlotWidget(title="Graphs")
        self.Dock_Graphs2.addWidget(self.Graphs2, rowspan=5, colspan=1)

        # add a textedit to the report dock
        self.textbox = QtWidgets.QTextEdit()
        self.textbox.setReadOnly(True)
        self.textbox.setText("Messages will appear here")
        self.Dock_Report.addWidget(self.textbox)

        # note that Docks use QGridLayout to position items,
        self.grid_initialize()
        self.Dock_Buttons.layout.setHorizontalSpacing(3)
        self.Dock_Buttons.layout.setVerticalSpacing(3)

        # build buttons in groups
        self.button_groups = {
            "Bands": buttons.ButtonGroup(
                names=["160", "80", "40", "30", "20", "17", "15", "12", "10", "6"],
                buttons=[],
                callback=self.band_select,
                groupname="Bands",
            ),
            "Modes": buttons.ButtonGroup(
                names=["CW", "USB", "LSB"],
                buttons=[],
                callback=self.mode_select,
                groupname="Modes",
            ),
            "Bandwidths": buttons.ButtonGroup(
                names=["500 Hz", "2100 Hz"],
                buttons=[],
                callback=self.bandwidth_select,
                groupname="Bandwidths",
            ),
            "Preamp": buttons.ButtonGroup(
                names=["On", "Off"],
                buttons=[],
                callback=self.preamp_select,
                groupname="Preamp",
            ),
            "AGC": buttons.ButtonGroup(
                names=["Fast", "Slow", "Off"],
                buttons=[],
                callback=self.agc_select,
                groupname="AGC",
            ),
            "TuningRate": buttons.ButtonGroup(
                names=["1 Hz", "10 Hz", "50 Hz", "100 Hz", "500 Hz"],
                buttons=[],
                callback=self.rate_select,
                groupname="TuningRate",
            ),
            "Quit": buttons.PushButton(
                name="Quit",
                callback=self.quit,
                unpressed=QtGui.QColor(192, 192, 192),
                pressed=QtGui.QColor(255, 0, 0),
            ),
        }

        for group_name, bg in self.button_groups.items():
            # print("Button Group: ", group_name, bg)
            if isinstance(bg, buttons.PushButton):
                self.place_button(self.Dock_Buttons.layout, bg.button, name=bg.name)

            elif isinstance(bg, buttons.ButtonGroup):
                #     print("Button Group: ", group_name)
                #     print("   ", bg.buttons)
                self.Dock_Buttons.layout.addLayout(bg.group_box, 0, self.grid_column)
                self.advance_column()
            else:
                raise ValueError(f"Unknown button type: {bg!s}")

        self.Dock_Buttons.widgetArea.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed
        )

        # size policy is different for the spacer
        self.spacer = QtWidgets.QSpacerItem(
            10,
            10,
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Ignored,
        )
        self.Dock_Buttons.layout.addItem(self.spacer, 0, 3, 0, 1)

        # configure frequency displays
        freq_font = QtGui.QFont()
        freq_font.setFamily("dseg")
        freq_font.setFixedPitch(False)
        freq_font.setPointSize(42)

        self.VFO_A = QtWidgets.QPushButton("7.000000")
        self.VFO_A.setFont(freq_font)
        self.VFO_B = QtWidgets.QPushButton("7.000000")
        self.VFO_B.setFont(freq_font)

        self.VFO_A_Info = QtWidgets.QLabel("")
        self.VFO_B_Info = QtWidgets.QLabel("")
        self.VFO_version = QtWidgets.QLabel("")
        self.VFO_version.setFixedSize(40, 20)

        self.VFOSpacer1 = QtWidgets.QSpacerItem(
            10,
            0,
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Ignored,
        )
        self.VFOSpacer2 = QtWidgets.QSpacerItem(
            10,
            0,
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Ignored,
        )

        # add a little information panel below the main dial for troubleshooting
        info_font = QtGui.QFont()
        info_font.setFamily("monospaced")
        info_font.setFixedPitch(True)
        info_font.setPointSize(9)
        self.Dock_Freqs.layout.addWidget(self.VFO_A_Info, 4, 0, 1, 1)
        self.VFO_A_Info.setFont(info_font)
        self.Dock_Freqs.layout.addWidget(self.VFO_version, 4, 1, 1, 1)
        self.VFO_version.setFont(info_font)
        self.VFO_version.setAlignment(pg.QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.VFO_version.setText("V 0.1")

        self.Dock_Freqs.layout.addWidget(self.VFO_B_Info, 4, 3, 1, 1)
        self.VFO_B_Info.setFont(info_font)
        self.VFO_B_Info.setText("B info")
        self.VFO_A_Info.setText("A info")

        # These buttons live in the VFO frequency display area:
        self.SwapButton = buttons.PushButton(
            name="Swap",
            callback=self.swapAB,
            unpressed=QtGui.QColor(192, 192, 192),
            pressed=QtGui.QColor(255, 0, 0),
            size=QtCore.QSize(20, 30),
        )
        self.BEqualsAButton = buttons.PushButton(
            name="Copy A to B",
            callback=self.copyAtoB,
            unpressed=QtGui.QColor(192, 192, 192),
            pressed=QtGui.QColor(255, 0, 0),
            size=QtCore.QSize(10, 30),
        )
        self.AEqualsBButton = buttons.PushButton(
            name="Copy B to A",
            callback=self.copyBtoA,
            unpressed=QtGui.QColor(192, 192, 192),
            pressed=QtGui.QColor(255, 0, 0),
            size=QtCore.QSize(10, 30),
        )
        
        self.VFO_A.setFixedSize(320, 80)
        self.VFO_B.setFixedSize(320, 80)
        self.Dock_Freqs.layout.addWidget(self.VFO_A, 0, 0, 3, 1)

        self.Dock_Freqs.layout.addWidget(self.SwapButton.button, 1, 1, 1, 2)
        self.Dock_Freqs.layout.addWidget(self.BEqualsAButton.button, 2, 1, 1, 1)
        self.Dock_Freqs.layout.addWidget(self.AEqualsBButton.button, 2, 2, 1, 1)
        self.Dock_Freqs.layout.addWidget(self.VFO_B, 0, 3, 3, 1)

        self.VFO_A.clicked.connect(self.select_vfo_A)
        self.VFO_B.clicked.connect(self.select_vfo_B)

        self.mainWin.show()

    def updateDisplay(self, frequency:Union[float, None]=None):
        """Service the signal from the VFO tuning thread
        """
        if frequency is None:  # likely thread is paused
            return
        vfo = self.Tuner.get_active_vfo()
        self.VFO_HDW.set_frequency(clk=0, freq=frequency) # update the synthesizer
        vfo.display_widget.setText(f"{float(vfo.frequency)/1e6:10.6f}")
        infotxt = f"R: {vfo.reference_frequency:.0f}"
        infotxt += f"E: {vfo.reference_encoder_steps:d} raw: {vfo.raw_encoder_steps:d}"
        infotxt += f"I: {vfo.increment:d} {vfo.role:s}"
        vfo.info_widget.setText(infotxt)

    def updateDisplayOnly(self, vfo_name):
        # update the VFO display for the named VFO
        vfo = self.Tuner.vfo_data[vfo_name]
        print("update vfo only: ", vfo_name)
        print("vfo: ", vfo)
        vfo.display_widget.setText(f"{float(vfo.frequency)/1e6:10.6f}")
        infotxt = f"R: {vfo.reference_frequency:.0f}"
        infotxt += f"E: {vfo.reference_encoder_steps:d} raw: {vfo.raw_encoder_steps:d}"
        infotxt += f"I: {vfo.increment:d} {vfo.role:s}"
        vfo.info_widget.setText(infotxt)


    def select_vfo_A(self):
        self.Tuner.set_active_vfo_by_name("A")
        self.updateDisplay()

    def select_vfo_B(self):
        self.Tuner.set_active_vfo_by_name("B")
        self.updateDisplay()

    def swapAB(self):
        self.Tuning.pause()  
        self.Tuner.add_vfo("temp")
        self.Tuner.copy_vfo(from_vfo="A", to_vfo="temp")
        self.Tuner.copy_vfo(from_vfo="B", to_vfo="A")
        self.Tuner.copy_vfo(from_vfo="temp", to_vfo="B")
        self.Tuner.delete_vfo("temp")
        self.updateDisplayOnly(vfo_name="A")
        self.updateDisplayOnly(vfo_name="B")
        self.Tuning.resume()

    def copyAtoB(self):
        """
        Copy the values from VFO A to VFO B, update the display
        and the frequency.
        Do not change the active VFO
        """
        self.Tuning.pause()
        self.Tuner.copy_vfo(from_vfo="A", to_vfo="B")
        self.updateDisplayOnly(vfo_name="B")
        self.Tuning.resume()

    def copyBtoA(self):
        """
        Copy the values from VFO B to VFO A, update the display
        and the frequency.
        Do not change the active VFO
        """
        self.Tuning.pause()
        self.Tuner.copy_vfo(from_vfo="B", to_vfo="A")
        self.updateDisplayOnly(vfo_name="A")
        self.Tuning.resume()

    def grid_initialize(self):
        self.grid_row = 0
        self.grid_column = 0

    def advance_row(self):
        self.grid_row += 1
        if self.grid_row > self.max_rows:
            self.grid_row = 0
            self.grid_column += 1

    def advance_column(self):
        self.grid_column += 1
        self.grid_row = 0

    def place_button(self, grid, button, name: str):
        if name == "|":  # push next button to next column, top position
            self.advance_column()
            return
        if name == "-":  # push next button to next row, but same column (spacing)
            self.advance_row()
            return
        if name == "*":  # put next button in last position
            # get rows and columns, then set to last one
            self.grid_ro
            w = grid.rowCount() - 1
            self.grid_column = grid.columnCount() - 1
            return

        grid.addWidget(button, self.grid_row, self.grid_column)
        self.advance_row()

    ## Callbacks for the buttons
    ## currently these just tell us that a button was hit.

    def band_select(self, argument):
        selected_band = argument.text()
        self.textappend(f"Band: {selected_band:s}", color="cyan")
        # bandmap = {'160': 0, '80': 1, '60': 2, '40': 3, '30': 4, '20': 5,
        #            '17': 6, '15': 7, '12': 8, '10': 9, '6': 10}
        # bandno = int(bandmap[argument.text()])
        bandmap = {
            "160": 1.8e6,
            "80": 3.5e6,
            "60": 5.2e6,
            "40": 7e6,
            "30": 10.1e6,
            "20": 14e6,
            "17": 18.068e6,
            "15": 21e6,
            "12": 24.86e6,
            "10": 28e6,
            "6": 50.0e6,
        }
        # save current frequency from VFOs before setting the new reference
        self.current_freqs[self.current_band][0] = (
            self.Tuner.get_active_vfo().frequency / 1e6
        )
        self.current_band = selected_band
        # retrieve last settings on the newly selected band
        self.Tuner.set_frequency(
            1e6 * self.current_freqs[self.current_band][0]
        )  # on current vfo
        self.VFO_HDW.set_frequency(clk=0, freq = 1e6 * self.current_freqs[self.current_band][0])

        # self.Tuner.
        # bandcmd = f"BN{bandno:d};"
        # print("bandcmd: ", bandcmd)
        # self.serial_connection.flush()
        # # self.AC.sendMessage(bandcmd)
        # self.serial_connection.write(bandcmd.encode('utf-8'))

    def rate_select(self, argument):
        ratemap = {"1 Hz": 1, "10 Hz": 10, "50 Hz": 50, "100 Hz": 100, "500 Hz": 500}
        self.Tuner.set_increment(ratemap[argument.text()])

    def mode_select(self, argument):
        self.textappend(f"mode: {argument.text():s}", color="yellow")

    def bandwidth_select(self, argument):
        self.textappend(f"Bandwidth: {argument.text():s}", color="green")

    def preamp_select(self, argument):
        self.textappend(f"Preamp: {argument.text():s}", color="blue")

    def agc_select(self, argument):
        self.textappend(f"AGC: {argument.text():s}", color="magenta")

    def pause_vfo_thread(self):  # pause thread
        self.threadpool.waitForDone(5*THREAD_PERIOD)

    def stop_vfo_thread(self):  # stop thread
        self.threadpool.waitForDone(5*THREAD_PERIOD)

    def quit(self):
        print("Quiting")
        self.VFO_HDW.disable(clk=0)
        self.VFO_HDW.setPower(0, 0)
        self.VFO_HDW.powerDown(0)
        self.timer.stop()
        print("... timer stopped")
        self.Tuning.stop()
        self.threadpool.waitForDone(5*THREAD_PERIOD)  # end thread'
        print("... threadpool ended")
        self.mainWin.close()
        print("... mainwindow closed")
        # self.qapp.quit()
        exit()

    def textclear(self):
        self.textbox.clear()

    def textappend(self, text, color="white"):
        self.textbox.setTextColor(QtGui.QColor(color))
        self.textbox.append(text)
        self.textbox.setTextColor(QtGui.QColor("white"))


# Run application
if __name__ == "__main__":
    SH = SU_Het()
    if (sys.flags.interactive != 1) or not hasattr(QtCore, "PYQT_VERSION"):
        QtGui.QGuiApplication.instance().exec()
