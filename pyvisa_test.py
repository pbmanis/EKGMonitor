import pyvisa as pv
import time
import numpy as np
import tkinter as TK
from tkinter import ttk
import threading

def attach_sdg():
    rm = pv.ResourceManager()
    resources = rm.list_resources()
    i = None
    for i, res in enumerate(resources):
        if res.find("SDG0")> 0:
            resnum = i
    if i is None:
        print("SDG not found in resources: ", resources)
        exit()
    else:
        print("Found: ", resources[i])
    inst = resources[i]
    sdg810 = rm.open_resource(inst)
    return sdg810

# sdg810 = attach_sdg()
class Stim():
    def __init__(self, sdg810):
        self.root = TK.Tk()
        self.root.title("SDG810 Controller: pulsing")
        self.sdg810 = sdg810
        self.running = False
        self.thread=None
        self.stop_thread = False

        self.TK_frame = ttk.Frame(self.root, padding=10)
        self.TK_frame.grid()
        ttk.Label(self.TK_frame, text="Commands").grid(column=0, row=0)
        ttk.Button(self.TK_frame, text="Start", command=self.start).grid(column=1, row=1)
        ttk.Button(self.TK_frame, text="Stop", command=self.stop).grid(column=1, row=2)
        ttk.Button(self.TK_frame, text="Quit", command=self.quit).grid(column=1, row=3)
        self.running = True
        self.root.mainloop()
    
    def start(self):
        if self.thread is None:  # only start once.
            self.thread = threading.Thread(target=self.run)
            self.thread.start()
            self.running = True
        else:
            self.running=True # set the running flag.

    def run(self):
        time.sleep(0.1)
        # print("Called run: ", sdg810.query("*IDN?"))
        self.sdg810.write("*RST")
        while True:
            if self.running:
                self.sdg810.write("C1:OUTP ON")
                self.sdg810.query("*OPC?")
                time.sleep(0.05)
                # print(self.sdg810.query("C1:OUTP?"))
                self.sdg810.write("C1:OUTP OFF")
                time.sleep(0.2)
                # print("...", self.sdg810.query("C1:OUTP?"))
            elif self.stop_thread:
                break
            else:
                time.sleep(0.1)

    def quit(self):
        print("Quitting")
        self.running = False
        self.stop_thread = True
        self.sdg810.write("C1:OUTP OFF")
        if self.thread is not None:
            self.thread.join(2)
        self.root.destroy()
        exit()

    def stop(self):
        self.running = False
    
   

if __name__ == "__main__":
    s = attach_sdg()
    STIM = Stim(sdg810=s)
