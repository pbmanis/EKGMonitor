import pyvisa as pv
import time
import numpy as np

rm = pv.ResourceManager()
resources = rm.list_resources()
inst = resources[1]
sdg810 = rm.open_resource(inst)
print(sdg810.query("*IDN?"))
sdg810.write("*RST")
for i in range(10):
    sdg810.write("C1:OUTP ON")
    sdg810.query("*OPC?")
    time.sleep(0.05)
    print(i, sdg810.query("C1:OUTP?"))
    sdg810.write("C1:OUTP OFF")
    time.sleep(0.2)
    print("...", sdg810.query("C1:OUTP?"))

sdg810.write("C1:OUTP OFF")
