import numpy as np
import matplotlib.pyplot as mpl
min_slider = 0
max_slider = 1000
min_freq = 1000.
max_freq = 48000.

def slider_to_freq_linear(slider):
    return min_freq + (max_freq - min_freq) * slider / (max_slider - min_slider)

def slider_to_freq_log(slider):
    return min_freq * (max_freq / min_freq) ** (slider / max_slider)

def slider_to_freq_antilog(slider):
    return min_freq * (max_freq / min_freq) ** (1 - slider / -max_slider)

def slider_to_freq_octaves(slider, octaves):
    return min_freq * 2 ** (octaves * slider / max_slider)

if __name__ == "__main__":

    sa = []
    flinear = []
    flog = []
    foct = []
    fanti = []

    for s in range(min_slider, max_slider + 1, 50):
        f1 = slider_to_freq_linear(s)
        f2 = slider_to_freq_log(s)
        f3 = slider_to_freq_octaves(s, 6)
        f4 = slider_to_freq_antilog(s)
        print(f"{s}: {f1} {f2} {f3} {f4}")
        sa.append(s)
        flinear.append(f1)
        flog.append(f2)
        foct.append(f3)
        fanti.append(f4)
    
    f, ax = mpl.subplots(4, 1, figsize=(4, 11))
    ax[0].plot(sa, flinear, label="Linear")
    ax[0].set_title("Linear")
    ax[0].set_xlabel("Slider")
    ax[0].set_ylabel("Frequency (Hz)")
    ax[1].plot(sa, flog, label="Log")
    ax[1].set_title("Log")
    ax[1].set_xlabel("Slider")
    ax[1].set_ylabel("Frequency (Hz)")
    ax[2].plot(sa, foct, label="Octaves")
    ax[2].set_title("Octaves")
    ax[2].set_xlabel("Slider")
    ax[2].set_ylabel("Frequency (Hz)")
    ax[3].plot(sa, fanti, label="Antilog")
    ax[3].set_title("Antilog")
    ax[3].set_xlabel("Slider")
    ax[3].set_ylabel("Frequency (Hz)")


    mpl.tight_layout()
    mpl.show()

    