"""
Tools for generating auditory stimuli.

This suite hosts a number of classes. The base class is the "Sound" class,
which provides methods for accessing various parameters and functions related
to the sound waveforms.

Each specific sound type (TonePip, NoisePip, etc) is based on the Sound class,
and provides the specific code to generate an appropriate waveform, given
the parameters.

To minimize potential issues, the construction of the specific sound classes
performs a verification of all keywords in the call (no keywords are optional).
Calling a specific sound class does not immediately generate the sound waveform.
Instead, The parameters are set up, and the waveform is actually generated when
needed by calling the generate method.

Much of the actual waveofrm calculation is performed by generic functions found
at the end of this file, outside the classes.

Notes:
1.  Conversion to "dBSPL" should only be used when generating stimuli for models.
    Otherwise, the amplitude is hardware dependent. To accomodate this,
    dBSPL should be None in a non-modeling environment.

    waveforms with amplitude 1 (except the noise, which will have peak amplitude
    larger than 1, but will have a standard deviation of 1).


"""

import numpy as np
import scipy
import scipy.signal
import src.DMR as DMR


def create(type, **kwds):
    """Create a Sound instance using a key returned by Sound.key()."""
    cls = globals()[type]
    return cls(**kwds)


class Sound(object):
    """
    Base class for all sound stimulus generators.
    """

    def __init__(self, duration, rate=100e3, **kwds):
        """
        Parameters
        ----------
        duration: float (no default):
            duration of the stimulus, in seconds

        rate : float (default: 100000.)
            sample rate for sound generation

        """
        self.opts = {"rate": rate, "duration": duration}
        self.opts.update(kwds)
        self._time = None
        self._sound = None

    @property
    def sound(self):
        """
        :obj:`array`: The generated sound array, expressed in Pascals.
        """
        if self._sound is None:
            self._sound = self.generate()
        return self._sound

    @property
    def inspect_sound(self):
        """
        :obj:`array`: The generated sound array, expressed in Pascals.
        """
        if self._sound is None:
            self._sound = self.generate()   
        return self
    
    @property
    def time(self):
        """
        :nparray: The time array to go with the sound.
        This should be total time of the waveform.
        """
        if self._time is None:
            self._time = np.linspace(0, self.opts["duration"], self.num_samples)
        return self._time

    @property
    def num_samples(self):
        """
        int: The number of samples in the sound array.
        """
        return int(self.opts["duration"] * self.opts["rate"])

    @property
    def dt(self):
        """
        float: the sample period (time step between samples).
        """
        return 1.0 / self.opts["rate"]

    @property
    def duration(self):
        """
        float: The duration of the sound
        """
        return self.opts["duration"]

    def key(self):
        """
        The sound can be recreated using ``create(**key)``.
        :obj:`dict`: Return dict of parameters needed to completely describe this sound.
        """
        k = self.opts.copy()
        k["type"] = self.__class__.__name__
        return k

    def measure_dbspl(self, tstart, tend):
        """
        Measure the sound pressure for the waveform in a window of time

        Parameters
        ----------
        tstart :
            time to start spl measurement (seconds).

        tend :
            ending time for spl measurement (seconds).

        Returns
        -------
        float : The measured amplitude (dBSPL) of the sound from tstart to tend

        """
        istart = int(tstart * self.opts["rate"])
        iend = int(tend * self.opts["rate"])
        return pa_to_dbspl(self.sound[istart:iend].std())

    def generate(self):
        """
        Generate and return the sound output. This method is defined by subclasses.
        """
        raise NotImplementedError()

    def __getattr__(self, name):
        if "opts" not in self.__dict__:
            raise AttributeError(name)
        if name in self.opts:
            return self.opts[name]
        else:
            return object.__getattr__(self, name)


class TonePip(Sound):
    """Create one or more tone pips with cosine-ramped edges.

    Parameters
    ----------
    rate : float
        Sample rate in Hz
    duration : float
        Total duration of the sound
    f0 : float or array-like
        Tone frequency in Hz. Must be less than half of the sample rate.
    dbspl : float
        Maximum amplitude of tone in dB SPL.
    pip_duration : float
        Duration of each pip including ramp time. Must be at least
        2 * ramp_duration.
    pip_start : array-like
        Start times of each pip
    ramp_duration : float
        Duration of a single ramp period (from minimum to maximum).
        This may not be more than half of pip_duration.

    """

    def __init__(self, **kwds):
        reqdWords = [
            "rate",
            "duration",
            "f0",
            "dbspl",
            "pip_duration",
            "pip_starts",
            "ramp_duration",
        ]
        for k in reqdWords:
            if k not in list(kwds.keys()):
                raise TypeError("Missing required argument '%s'" % k)
        if kwds["pip_duration"] < kwds["ramp_duration"] * 2:
            raise ValueError("pip_duration must be greater than (2 * ramp_duration).")
        if kwds["f0"] > kwds["rate"] * 0.5:
            raise ValueError("f0 must be less than (0.5 * rate).")
        Sound.__init__(self, **kwds)

    def generate(self):
        """
        Call to compute the tone pips

        Returns
        -------
        array :
            generated waveform

        """
        o = self.opts
        return piptone(
            self.time,
            ramp=o["ramp_duration"],
            rate=o["rate"],
            duration=o['duration'],
            f0=o["f0"],
            dbspl=o["dbspl"],
            pip_dur=o["pip_duration"],
            pip_starts=o["pip_starts"],
        )


class FMSweep(Sound):
    """Create an FM sweep with either linear or logarithmic rates,
    of a specified duration between two frequencies.

    Parameters
    ----------
    rate : float
        Sample rate in Hz
    duration : float
        Total duration of the sweep
    start : float
        t times of each pip
    freqs : list
        [f0, f1]: the start and stop times for the sweep
    ramp : string
        valid input for type of sweep (linear, logarithmic, etc)
    dbspl : float
        Maximum amplitude of pip in dB SPL.
    """

    def __init__(self, **kwds):
        for k in ["rate", "duration", "start", "freqs", "ramp", "dbspl"]:
            if k not in kwds:
                raise TypeError("Missing required argument '%s'" % k)
        Sound.__init__(self, **kwds)

    def generate(self):
        """
        Call to actually compute the the FM sweep

        Returns
        -------
        array :
            generated waveform

        """
        o = self.opts
        return fmsweep(
            self.time, o["start"], o["duration"], o["freqs"], o["ramp"], o["dbspl"]
        )


class NoisePip(Sound):
    """One or more noise pips with cosine-ramped edges.

    Parameters
    ----------
    rate : float
        Sample rate in Hz
    duration : float
        Total duration of the sound
    seed : int >= 0
        Random seed
    dbspl : float
        Maximum amplitude of tone in dB SPL.
    pip_duration : float
        Duration of each pip including ramp time. Must be at least
        2 * ramp_duration.
    pip_starts : array-like
        Start times of each pip
    ramp_duration : float
        Duration of a single ramp period (from minimum to maximum).
        This may not be more than half of pip_duration.

    """

    def __init__(self, **kwds):
        for k in [
            "rate",
            "duration",
            "dbspl",
            "pip_duration",
            "pip_starts",
            "ramp_duration",
            "seed",
        ]:
            if k not in kwds:
                raise TypeError("Missing required argument '%s'" % k)
        if kwds["pip_duration"] < kwds["ramp_duration"] * 2:
            raise ValueError("pip_duration must be greater than (2 * ramp_duration).")
        if kwds["seed"] < 0:
            raise ValueError("Random seed must be integer > 0")
        Sound.__init__(self, **kwds)

    def generate(self):
        """
        Call to compute the noise pips

        Returns
        -------
        array :
            generated waveform

        """
        o = self.opts
        if isinstance(o["pip_starts"], float | int):
            pip_starts = [o["pip_starts"]]
        else:
            pip_starts = o["pip_starts"]
        return pipnoise(
            self.time,
            ramp=o["ramp_duration"],
            rate=o["rate"],
            duration=o["duration"],
            dbspl=o["dbspl"],
            pip_dur=o["pip_duration"],
            pip_starts=pip_starts,
            seed=o["seed"],
        )


class NoiseBandPip(Sound):
    """
    One or more noise pips with cosine-ramped edges with limited frequencies/notches.
    Using method of Nelken and Young (Schalk and Sachs)
    Two independent noises are generated, and multiplied in quadature.
    To make a bandpass noise, they are low-pass filtered prior to multiplication
    To make a notch noise, they are band-pass filtered prior to multiplication


    Parameters
    ----------
    rate : float
        Sample rate in Hz
    duration : float
        Total duration of the sound
    seed : int >= 0
        Random seed
    dbspl : float
        Maximum amplitude of tone in dB SPL.
    pip_duration : float
        Duration of each pip including ramp time. Must be at least
        2 * ramp_duration.
    pip_start : array-like
        Start times of each pip
    ramp_duration : float
        Duration of a single ramp period (from minimum to maximum).
        This may not be more than half of pip_duration.
    type : string
        'Bandpass', 'BP+Notch'
    noisebw : float
        (bandwidth of noise)
    centerfreq : float
        Center frequency for signal or notch
    notchbw : float
        Bandwidth of notch

    """

    def __init__(self, **kwds):
        for k in [
            "rate",
            "duration",
            "dbspl",
            "pip_duration",
            "pip_starts",
            "ramp_duration",
            "seed",
            "noisebw",
            "type",
            "notchbw",
            "centerfreq",
        ]:
            if k not in kwds:
                raise TypeError("Missing required argument '%s'" % k)
        if kwds["pip_duration"] < kwds["ramp_duration"] * 2:
            raise ValueError("pip_duration must be greater than (2 * ramp_duration).")
        if kwds["seed"] < 0:
            raise ValueError("Random seed must be integer > 0")

        Sound.__init__(self, **kwds)

    # def generate(self):
    #     """
    #     Call to compute the noise pips

    #     Returns
    #     -------
    #     array :
    #         generated waveform

    #     """
    #     o = self.opts
    #     bbnoise1 = pipnoise(self.time, o['ramp_duration'], o['rate'],
    #                     o['dbspl'], o['pip_duration'], o['pip_starts'], o['seed'])
    #     bbnoise2 = pipnoise(self.time, o['ramp_duration'], o['rate'],
    #                     o['dbspl'], o['pip_duration'], o['pip_starts'], o['seed']+1)  # independent noises
    #     # fb1 = signalFilter_LPFButter(bbnoise1, o['noisebw'], o['rate'])
    #     # fb2 = signalFilter_LPFButter(bbnoise2, o['noisebw'], o['rate'])
    #     if o['type'] in ['Bandpass']:
    #         fb1 = signalFilter_LPFButter(bbnoise1, o['noisebw'], o['rate'])
    #         fb2 = signalFilter_LPFButter(bbnoise2, o['noisebw'], o['rate'])
    #         bpnoise = fb1*np.cos(2*np.pi*o['centerfreq']*self.time) + fb2*np.sin(2*np.pi*o['centerfreq']*self.time)

    #     if o['type'] in ['BP+Notch']:
    #         nn1 = signalFilterButter(bbnoise1, filtertype='bandpass',
    #             lpf=o['noisebw'], hpf=o['notchbw'], Fs=o['rate'], poles=4)
    #         nn2 = signalFilterButter(bbnoise2, filtertype='bandpass',
    #             lpf=o['noisebw'], hpf=o['notchbw'], Fs=o['rate'], poles=4)
    #         bpnoise = nn1*np.cos(2*np.pi*o['centerfreq']*self.time) + nn2*np.sin(2*np.pi*o['centerfreq']*self.time)

    #     return bpnoise


class ClickTrain(Sound):
    """One or more clicks (rectangular pulses).

    Parameters
    ----------
    rate : float
        Sample rate in Hz
    duration: float
        Duration of waveform
    dbspl : float
        Maximum amplitude of click in dB SPL.
    click_duration : float
        Duration of each click. Must be at least 1/rate.
    click_starts : array-like
        Start times of each click
    """

    def __init__(self, **kwds):
        for k in ["rate", "duration", "dbspl", "click_duration", "click_starts"]:
            if k not in kwds:
                raise TypeError("Missing required argument '%s'" % k)
        if kwds["click_duration"] < 1.0 / kwds["rate"]:
            raise ValueError("click_duration must be greater than sample rate.")

        Sound.__init__(self, **kwds)

    def generate(self):
        o = self.opts
        return clicks(
            self.time,
            rate=o["rate"],
            duration=o["duration"],
            dbspl=o["dbspl"],
            click_duration=o["click_duration"],
            click_starts=o["click_starts"],
        )


class SAMNoise(Sound):
    """One or more gaussian noise pips with cosine-ramped edges.

    Parameters
    ----------
    rate : float
        Sample rate in Hz
    duration : float
        Total duration of the sound
    seed : int >= 0
        Random seed
    dbspl : float
        Maximum amplitude of pip in dB SPL.
    pip_duration : float
        Duration of each pip including ramp time. Must be at least
        2 * ramp_duration.
    pip_start : array-like
        Start times of each pip
    ramp_duration : float
        Duration of a single ramp period (from minimum to maximum).
        This may not be more than half of pip_duration.
    fmod : float
        SAM modulation frequency
    dmod : float
        Modulation depth
    """

    def __init__(self, **kwds):
        parms = [
            "rate",
            "duration",
            "seed",
            "pip_duration",
            "pip_starts",
            "ramp_duration",
            "fmod",
            "dmod",
            "seed",
        ]
        for k in parms:
            if k not in kwds:
                raise TypeError("Missing required argument '%s'" % k)
        if kwds["pip_duration"] < kwds["ramp_duration"] * 2:
            raise ValueError("pip_duration must be greater than (2 * ramp_duration).")
        if kwds["seed"] < 0:
            raise ValueError("Random seed must be integer > 0")

        Sound.__init__(self, **kwds)

    def generate(self):
        """
        Call to compute the SAM noise

        Returns
        -------
        array :
            generated waveform

        """
        o = self.opts
        o["phase_shift"] = 0.0
        return modnoise(
            self.time,
            ramp=o["ramp_duration"],
            rate=o["rate"],
            duration=o["duration"],
            pip_dur=o["pip_duration"],
            starts=o["pip_starts"],
            dbspl=o["dbspl"],
            fmod=o["fmod"],
            phase_shift=o["phase_shift"],
            dmod=o["dmod"],
            seed=o["seed"],
        )


class SAMTone(Sound):
    """SAM tones with cosine-ramped edges.

    Parameters
    ----------
    rate : float
        Sample rate in Hz
    duration : float
        Total duration of the sound
    f0 : float or array-like
        Tone frequency in Hz. Must be less than half of the sample rate.
    dbspl : float
        Maximum amplitude of tone in dB SPL.
    pip_duration : float
        Duration of each pip including ramp time. Must be at least
        2 * ramp_duration.
    pip_start : array-like
        Start times of each pip
    ramp_duration : float
        Duration of a single ramp period (from minimum to maximum).
        This may not be more than half of pip_duration.
    fmod : float
        SAM modulation frequency, Hz
    dmod : float
        Modulation depth, %

    """

    def __init__(self, **kwds):

        for k in [
            "rate",
            "duration",
            "f0",
            "dbspl",
            "pip_duration",
            "pip_starts",
            "ramp_duration",
            "fmod",
            "dmod",
        ]:
            if k not in kwds:
                raise TypeError("Missing required argument '%s'" % k)
        if kwds["pip_duration"] < kwds["ramp_duration"] * 2:
            raise ValueError("pip_duration must be greater than (2 * ramp_duration).")
        if kwds["f0"] > kwds["rate"] * 0.5:
            raise ValueError("f0 must be less than (0.5 * rate).")

        Sound.__init__(self, **kwds)

    def generate(self):
        """
        Call to compute a SAM tone

        Returns
        -------
        array :
            generated waveform

        """
        o = self.opts
        basetone = piptone(
            self.time,
            ramp=o["ramp_duration"],
            rate=o["rate"],
            duration=o["duration"],
            f0=o["f0"],
            dbspl=o["dbspl"],
            pip_dur=o["pip_duration"],
            pip_starts=o["pip_starts"],
        )
        return sinusoidal_modulation(
            self.time,
            basestim=basetone,
            tstart=o["pip_starts"][0],
            fmod=o["fmod"],
            dmod=o["dmod"],
            phase_shift=0.0,
        )


class ComodulationMasking(Sound):
    """

    rate is the sample rate (Hz) for the stimulus
    duration is the ENTIRE duration of the stimulus (seconds)
    ramp_duration is the cos^2 ramp duration (seconds)
    masker_spl is the sound pressure level of the masker (dB SPL)
    target_spl is the sound pressure level of the target (dB SPL)
    masker_delay is the delay to the start of the stimulus (seconds)
    masker_duration is the duration of the masker tone pip (seconds)
    f0 is the center frequency of the target and the on-frequency masker (Hz)
    target_duration is the duration of the target tone pip (seconds)
    target_delay is the delay to the start of the tone pip (seconds)
    fmod is the modulation frequency (sinusoidal) (Hz)
    dmod is the modulation depth (0-1) (unitless)
    flanking_type is the type of flanking noise: str (
        options are : narrow band noise: NBNoise, multiple tones: MultiTone
    flanking_spacing is the spacing of the flanking tones in octaves (float)
    flanking_bands is the number of flanking tones on each side of the on-frequency target/masker (int)
    flanking_phase is the phase relationship of the flanking tones to the masker (str: 
        options are:  Comodulated, Codeviant, Random


    """

    def __init__(self, **kwds):
        for k in [
            "rate",
            "duration",
            "masker_spl",
            "target_spl",
            "masker_delay",
            "masker_duration",
            "target_f0",
            "masker_f0",
            "target_duration",
            "target_delay",
            "fmod",
            "dmod",
            "ramp_duration",
            "flanking_type",
            "flanking_spacing",
            "flanking_phase",
            "flanking_bands",
            "output"
        ]:
            if k not in kwds:
                raise TypeError("Missing required argument '%s'" % k)
        Sound.__init__(self, **kwds)


    def generate(self):
        """ first check parameters"""
        o = self.opts

        assert o["flanking_phase"] in ['Comodulated', 'Codeviant', 'Random']
        assert o["output"] in  ["Signal", 'Target', 'OFM', 'Flanking', 'Target+OFM'] 
        assert o["flanking_bands"] in [0, 1, 2, 3, 4, 5]
        assert o["flanking_spacing"] > 0.05 and o['flanking_spacing'] < 3
        assert o["flanking_type"] in ["MultiTone", "NBNoise", "None"]
        assert (o["fmod"] > 0.5) and (o['fmod'] < 1000)
        assert (o["dmod"] >= 0) and (o['dmod'] <= 100.)
        assert (o['masker_duration'] + o['masker_delay']) < o['duration']
        assert (o['target_duration'] + o['target_delay']) < o['duration']
        assert (o['masker_duration'] + o['masker_delay']) == (o['target_duration'] + o['target_delay'])
        assert (o['masker_duration'] + o['masker_delay']) > 0.1

        # print("CMMR Values: \n", o)
        if o['masker_f0'] is None:
            o['masker_f0'] = o['target_f0']
        # start with target tone
        tardelay = 0.5 / o["fmod"]  # delay target by one half cycle of the modulation frequency

        targettone = piptone(
            self.time,
            duration=o["duration"],
            ramp=o["ramp_duration"],
            rate=o["rate"],
            f0=o["target_f0"],
            dbspl=o["target_spl"],
            pip_dur=o["target_duration"],
            pip_starts=[o["target_delay"]-tardelay],
        )
        # so it is out of phase with the masker
        targettone = sinusoidal_modulation(
            self.time,
            basestim=targettone,
            tstart=o["target_delay"],
            fmod=o["fmod"],
            dmod=o["dmod"],
            phase_shift=np.pi,  # the phase shift is in radians.
        )
        # print(f"Target tone: {o['target_spl']:.1f} {np.min(targettone):.3f} {np.max(targettone):.3f}")
        on_freq_maskertone = piptone(
            self.time,
            duration=o['duration'],
            ramp=o["ramp_duration"],
            rate=o["rate"],
            f0=o["masker_f0"],
            dbspl=o["masker_spl"],
            pip_dur=o["masker_duration"],
            pip_starts=[o["masker_delay"]],
        )
        on_freq_maskertone = sinusoidal_modulation(
            self.time,
            basestim=on_freq_maskertone,
            tstart=[o["masker_delay"]],
            fmod=o["fmod"],
            dmod=o["dmod"],
            phase_shift=0.0,
        )
        # print(f"Masker tone: {o['masker_spl']:.1f} {np.min(targettone):.3f} {np.max(targettone):.3f}")
        # maskertone = np.zeros_like(maskertone)
        if o["flanking_type"] == "None":
            return (on_freq_maskertone + targettone) / 2.0  # scaling...
        if o["flanking_type"] in ["MultiTone"]:
            nband = o["flanking_bands"]
            octspace = o["flanking_spacing"]
            f0 = o["target_f0"]
            flankfs = [f0 * (2 ** (octspace * (k + 1))) for k in range(nband)]
            flankfs.extend([f0 / ((2 ** (octspace * (k + 1)))) for k in range(nband)])
            flankfs = sorted(flankfs)
            flanktone = [[]] * len(flankfs)

            for i, fs in enumerate(flankfs):
                match o["flanking_phase"]:
                    case "Comodulated":
                        phaseshift = 0.
                    case "Codeviant":
                        phaseshift = (i+1)*np.pi*2.0/nband
                    case "Random":
                        phaseshift = np.pi*2*np.random.uniform()
                    case _:
                        raise ValueError("Flanking phase not in valid choices: Comodulated, Codeviant, Random")
                flanktone[i] = piptone(
                    self.time,
                    duration=o['duration'],
                    ramp=o["ramp_duration"],
                    rate=o["rate"],
                    f0=flankfs[i],
                    dbspl=o["masker_spl"],
                    pip_dur=o["masker_duration"],
                    pip_starts=[o["masker_delay"]],
                    pip_phase=phaseshift,
                )
        # print('type, phase: ', o['flanking_type'], o['flanking_phase'])
        if o["flanking_type"] == "NBnoise":
            raise ValueError("Flanking type nbnoise not yet implemented")
        if o["flanking_phase"] == "Comodulated":
            ph = np.zeros(len(flankfs))
        if o["flanking_phase"] == "Codeviant":
            ph = (
                2.0
                * np.pi
                * np.arange(-o["flanking_bands"], o["flanking_bands"] + 1, 1)
                / o["flanking_bands"]
            )
        if o["flanking_phase"] == "Random":
            ph = (
                2.0 * np.random.uniform()
                * np.pi
                * np.arange(-o["flanking_bands"], o["flanking_bands"] + 1, 1)
                / o["flanking_bands"]
            )
            
        # print(('flanking phases: ', ph))
        # print((len(flanktone)))
        # print(('flanking freqs: ', flankfs))
        for i, fs in enumerate(flankfs):
            flanktone[i] = sinusoidal_modulation(
                self.time, flanktone[i], o["masker_delay"], o["fmod"], o["dmod"], ph[i]
            )
            if i == 0:
                maskers = flanktone[i]
            else:
                maskers = maskers + flanktone[i]
        signal = (on_freq_maskertone + maskers + targettone) / (o["flanking_bands"] + 2)
        # select what we want to plot
        if o["output"] == "Signal":
            return signal
        elif o["output"] == "Target":
            return targettone
        elif o["output"] == "OFM":
            return on_freq_maskertone
        elif o["output"] == "Flanking":
            return maskers
        elif o["output"] == "Target+OFM":
            return targettone + on_freq_maskertone


class DynamicRipple(Sound):
    def __init__(self, **kwds):
        for k in ["rate", "duration"]:
            if k not in kwds:
                raise TypeError("Missing required argument '%s'" % k)

        self.dmr = DMR.DMR()
        Sound.__init__(self, **kwds)

    def generate(self):
        """
        Call to compute a dynamic ripple stimulus

        Returns
        -------
        array :

           generated waveform
        """
        o = self.opts
        self.dmr.set_params(Fs=o["rate"], duration=o["duration"] + 1.0 / o["rate"])
        self.dmr.make_waveform()
        self._time = self.dmr.vTime  # get time from the generator, not linspace
        return self.dmr.vStim


class SpeechShapedNoise(Sound):
    """
    Adapted from http://www.srmathias.com/speech-shaped-noise/
    """

    def __init__(self, **kwds):
        for k in ["rate", "duration", "waveform", "samplingrate"]:
            if k not in kwds:
                raise TypeError("Missing required argument '%s'" % k)
        # if kwds['pip_duration'] < kwds['ramp_duration'] * 2:
        #     raise ValueError("pip_duration must be greater than (2 * ramp_duration).")
        Sound.__init__(self, **kwds)

    def generate(self):
        o = self.opts
        # print 'opts: ', o
        ssn, t = make_ssn(o["rate"], o["duration"], o["waveform"], o["samplingrate"])
        # self._time = t  # override time array because we read a wave file

        return ssn


class RandomSpectrumShape(Sound):
    """
    Random Spectral Shape stimuli
    log-spaced tones
    Amplitudes adjusted in groups of 4 or 8 (amp_group_size)
    Amplitude SD (amp_sd)
    Frequency range (octaves above and below f0) (octaves)
    spacing (fraction of octave: e.g, 1/8 or 1/64 as 8 or 64) (spacing)
    The tones are log space in 1/64 octave, then grouped into 
    sets of 4 or 8 to adjust the amplitudes.

    Generates one sample

    Young and Calhoun, 2005
    Yu and Young, 2000
    """

    def __init__(self, **kwds):
        for k in [
            "rate",
            "duration",
            "f0",
            "dbspl",
            "pip_duration",
            "pip_starts",
            "ramp_type",
            "ramp_duration",
            "amp_group_size",
            "amp_sd",
            "spacing",
            "octaves",
        ]:
            if k not in kwds:
                raise TypeError("Missing required argument '%s'" % k)
        
        if kwds["duration"] < kwds["ramp_duration"] * 2:
            raise ValueError("pip_duration must be greater than (2 * ramp_duration).")
        if kwds["f0"] > kwds["rate"] * 0.5:
            raise ValueError("f0 must be less than (0.5 * rate).")

        Sound.__init__(self, **kwds)

    def generate(self):
        o = self.opts
        assert o["ramp_type"] in ['linear', 'cos2']
        octaves = o["octaves"]
        spacing = o["spacing"]
        lowf = o["f0"] / octaves
        highf = o["f0"] * octaves
        # print("lowf: %8.3f  highf: %8.3f" % (lowf, highf), octaves)
        # print("log2 low: ", np.log2(lowf), "log2 high: ", np.log2(highf), "num: ", int(octaves*64.))
        
        # compute the frequencies to be used in this stimulus
        # frequencies are log-spaced
        freqlist = np.logspace(
            np.log2(lowf),
            np.log2(highf),
            num=int(octaves*64.),
            endpoint=True,
            base=2,
        )
        amplist = np.zeros_like(freqlist)
        # print("RSS frequencies: ", freqlist)
 
        db = o["dbspl"]
        # assign amplitudes
        if db == None:
            db = 80.0
        groupsize = o["amp_group_size"]
        # print("groupsize: ", groupsize, "sd: ", o["amp_sd"])
        # compute the distribution of amplitudes across the tones in the stimulus
        for i in range(0, len(freqlist), groupsize):

            if o["amp_sd"] > 0.0:
                a = np.random.normal(scale=o["amp_sd"])
            else:
                a = 0
            # print("i: ", i, a)
            amplist[i : i + groupsize] = a + db
        # print("RSS amplitudes: ", set(amplist))
        rng = np.random.default_rng()
        phase = np.pi * 2.0 * rng.standard_normal(len(freqlist))
        for i in range(len(freqlist)):
            wave = piptone(
                self.time,
                duration=o["duration"],
                ramp=o["ramp_duration"],
                rate=o["rate"],
                f0=freqlist[i],
                dbspl=amplist[i],
                pip_dur=o["pip_duration"],
                pip_starts=o["pip_starts"],
                pip_phase = phase[i],
            )
            if i == 0:
                result = wave
            else:
                result = result + wave
        # import matplotlib.pyplot as mpl
        # f, ax = mpl.subplots(2, 1)
        # ax[0].plot(self.time, result)
        # ax[1].stairs(amplist[:-1], freqlist)
        # ax[1].set_xscale('log')
        # mpl.show()
        return result # / len(freqlist)  # scale by number of sinusoids added


########################################################
# Below are functions that perform generic or specific calculations for waveforms
#########################################################


def next_pow_2(x):
    """Calculates the next power of 2 of a number."""
    return int(pow(2, np.ceil(np.log2(x))))


def pa_to_dbspl(pa, ref=20e-6):
    """Convert Pascals (rms) to dBSPL. By default, the reference pressure is
    20 uPa.
    """
    return 20 * np.log10(pa / ref)


def dbspl_to_pa(dbspl:float, ref:float=20e-6):
    """Convert dBSPL to Pascals (rms). By default, the reference pressure is
    20 uPa.
    """
    pascals =  ref * 10.0 ** (dbspl / 20.0)
    # print(f"dbspl_to_pa: {dbspl:.2f}  ref: {ref:.2e}, pa: {pascals:.3e}")
    return pascals

def linearramp(pin, mxpts, irpts):
    """
    Apply linear ramps to *pin*.

    Parameters
    ----------
    pin : array
        input waveform to apply ramp to
    mxpts : int
        point in array to start ramp down
    irpts : int
        duration of the ramp

    Returns
    -------
    array :
        waveform


    Original (adapted from Manis; makeANF_CF_RI.m)::

        function [out] = ramp(pin, mxpts, irpts)
            out = pin;
            out(1:irpts)=pin(1:irpts).*(0:(irpts-1))/irpts;
            out((mxpts-irpts):mxpts)=pin((mxpts-irpts):mxpts).*(irpts:-1:0)/irpts;
            return;
        end
    """
    out = pin.copy()
    r = np.linspace(0, 1, irpts)
    irpts = int(irpts)
    # print 'irpts: ', irpts
    # print len(out)
    out[:irpts] = out[:irpts] * r
    # print  out[mxpts-irpts:mxpts].shape
    # print r[::-1].shape
    out[mxpts - irpts - 1 : mxpts] = out[mxpts - irpts - 1 : mxpts] * r[::-1]
    return out


def piptone(
    t,
    ramp: float = 2.5,
    rate: float = 100000.0,
    f0: float = 1000.0,
    duration: float=0.25,
    dbspl: float = 40.0,
    pip_dur: float = 0.1,
    pip_starts: list = [0.1],
    pip_phase: float = 0.0,
):
    """
    Create a waveform with multiple sine-ramped tone pips. Output is in
    Pascals.

    Parameters
    ----------
    t : array
        array of time values
    ramp : float
        ramp duration
    rate : float
        sample rate
    f0 : float
        pip frequency
    duration: float
        duration of entire waveform.
    dspl : float
        maximum sound pressure level of pip
    pip_dur : float
        duration of pip including ramps
    pip_start : float
        list of starting times for multiple pips
    pip_phase : float, default = 0
        starting phase of pip in radians

    Returns
    -------
    array :
        waveform

    """
    # make pip template (one pip, not whole trace)
    pip_t = np.linspace(0, pip_dur, num=int(np.floor(pip_dur * rate)))
    pip = np.sin(
        2 * np.pi * f0 * pip_t + pip_phase
    )  # unramped stimulus, scaled -1 to 1
    # print("\npip unscaled: [-1 to 1]", np.min(pip), np.max(pip))
    # print("dbspl: ", dbspl)
    if dbspl is not None:
        pip = np.sqrt(2) * dbspl_to_pa(dbspl) * pip  # unramped stimulus
    else:
        pass  # no need to scale here
    # print("pip scaled: ", np.min(pip), np.max(pip))
    # add onset/offset ramps inside the duration of the pip
    ramp_pts = int(ramp * rate) + 1
    ramparray = np.sin(np.linspace(0, np.pi / 2.0, ramp_pts)) ** 2
    pip[:ramp_pts] *= ramparray
    pip[-ramp_pts:] *= ramparray[::-1]
    if not isinstance(pip_starts, list):
        raise ValueError("pip_starts must be a list of start times")
    # apply template to waveform
    # pip_pts = int(np.floor(rate * (pip_starts[-1] + pip_dur)))
    pin = np.zeros(int(duration*rate))
    for start in pip_starts:
        ts = int(np.floor(start * rate))
        # print("ts: ", ts, "len pip: ", len(pip), "len pin: ", len(pin), duration, rate)
        pin[ts : ts + len(pip)] += pip

    return pin


def pipnoise(t, ramp, rate, duration, dbspl, pip_dur, pip_starts, seed, scale=1.0):
    """
    Create a waveform with multiple sine-ramped noise pips. Output is in
    Pascals.

    Parameters
    ----------
    t : array
        array of time values
    ramp : float
        ramp duration
    rate : float
        sample rate
    duration: float
        duration of stimulus trace
    dbspl : float
        maximum sound pressure level of pip
    pip_dur : float
        duration of pip including ramps
    pip_start : float
        list of starting times for multiple pips
    seed : int
        random seed

    Returns
    -------
    array :
        waveform

    """

    rng = np.random.RandomState(seed)
    # make pip template
    pip_t = np.linspace(0, pip_dur, num=int(np.floor(pip_dur * rate)))
    pip = rng.randn(pip_t.shape[0])  # unramped stimulus, scaled -1 to 1
    if dbspl is not None:
        pip = dbspl_to_pa(dbspl) * pip * scale

    # add onset/offset ramps inside the duration of the pip
    ramp_pts = int(ramp * rate) + 1
    ramp = np.sin(np.linspace(0, np.pi / 2.0, ramp_pts)) ** 2
    pip[:ramp_pts] *= ramp
    pip[-ramp_pts:] *= ramp[::-1]
    if not isinstance(pip_starts, list | np.ndarray | tuple):
        raise ValueError("pip_starts must be a list of start times")
    # apply template to waveform
    pin = np.zeros(int(duration*rate))
    if pip_starts[-1]*rate + len(pip) > pin.shape[0]:
        raise ValueError(f"Pips would extend beyond alloted duration of stimulus ({np.max(pin):.3f}s)")
    for start in pip_starts:
        ts = int(np.floor(start * rate))
        pin[ts : ts + len(pip)] += pip

    return pin


def clicks(
    t,
    rate: float = 100000.0,
    duration: float=0.5,
    dbspl: float = 80.0,
    click_duration: float = 1e-4,
    click_starts:list = [0.1],
):
    """
    Create a waveform with multiple rectangular clicks. Output is in
    Pascals.

    Parameters
    ----------
    t : array
        array of time values
    rate : float
        sample frequency (Hz)
    duration: float
        duration of wavelist
    click_starts: list
        delay to each click in train
    click_duration : float (seconds)
        duration of each click
    dbspl : float
        maximum sound pressure level of pip

    Returns
    -------
    array :
        waveform

    """
    swave = np.zeros(int(duration*rate))
    if dbspl is not None:
        amp = dbspl_to_pa(dbspl)
    else:
        amp = 1.0
    t_click = int(np.floor(click_duration * rate))
    nclicks = len(click_starts)
    for n in range(nclicks):
        t0s = click_starts[n]  # time for nth click
        t0 = int(np.floor(t0s * rate))  # index
        if t0 + t_click > swave.shape[0]:
            raise ValueError("Clicks: train duration exceeds waveform duration")
        swave[t0 : t0 + t_click] = amp
    return swave


def sinusoidal_modulation(
    t: np.ndarray,
    basestim: np.ndarray,
    tstart: float,
    fmod: float,
    dmod: float,
    phase_shift: float,
):
    """
    Generate a sinusoidally amplitude-modulation of the input stimulus.
    For dmod=100%, the envelope max is 2, the min is 0; for dmod = 0, the max and min are 1
    maintains equal energy for all modulation depths.
    Equation from Rhode and Greenberg, J. Neurophys, 1994 (adding missing parenthesis) and
    Sayles et al. J. Physiol. 2013
    The envelope can be phase shifted (useful for co-deviant stimuli).

    Parameters
    ----------
    t : array
        array of waveform time values (seconds)
    basestim : array
        array of waveform values that will be subject to sinulsoidal envelope modulation
    tstart : float
        time at which the base sound starts (modulation starts then, with 0 phase crossing)
        (seconds)
    fmod : float
        modulation frequency (Hz)
    dmod : float
        modulation depth (percent)
    phase_shift : float
        modulation phase shift (starting phase, radians)

    """

    env = 1.0 + (dmod / 100.0) * np.sin(
        (2.0 * np.pi * fmod * (t - tstart)) + phase_shift - (np.pi / 2.)
    )  # envelope...
    return basestim * env


def make_ssn(rate:float, duration:float, sig:float, samplingrate:float):
    """
    Speech-shaped noise
    Adapted from http://www.srmathias.com/speech-shaped-noise/
    Created on Thu Jun 26 12:42:08 2014
    @author: smathias
    """
    # note rate is currently ignored...
    sig = np.array(sig).astype("float64")
    if (
        rate != samplingrate
    ):  # interpolate to the current system sampling rate from the original rate
        sig = np.interp(
            np.arange(0, len(sig) / rate, 1.0 / rate),
            np.arange(0, len(sig) / samplingrate),
            1.0 / samplingrate,
        )
    sig = 2 * sig / np.max(sig)
    z, t = noise_from_signal(sig, rate, keep_env=True)
    return z, t


def noise_from_signal(x, fs=40000, keep_env=True):
    """Create a noise with same spectrum as the input signal.
    Parameters
    ----------
    x : array_like
        Input signal.
    fs : int
         Sampling frequency of the input signal. (Default value = 40000)
    keep_env : bool
         Apply the envelope of the original signal to the noise. (Default
         value = False)
    Returns
    -------
    ndarray
        Noise signal.
    """
    x = np.asarray(x)
    n_x = x.shape[-1]
    n_fft = next_pow_2(n_x)
    X = np.fft.rfft(x, next_pow_2(n_fft))
    # Randomize phase.
    noise_mag = np.abs(X) * np.exp(2.0 * np.pi * 1j * np.random.random(X.shape[-1]))
    noise = np.real(np.fft.irfft(noise_mag, n_fft))
    out = noise[:n_x]
    if keep_env:
        env = np.abs(scipy.signal.hilbert(x))
        [bb, aa] = scipy.signal.butter(6.0, 50.0 / (fs / 2.0))  # 50 Hz LP filter
        env = scipy.signal.filtfilt(bb, aa, env)
        out *= env
    t = np.arange(0, (len(out)) / fs, 1.0 / fs)
    return out, t


def modnoise(
    t: np.ndarray,
    ramp: float,
    rate: float,
    duration: float,
    starts: list,
    pip_dur: float,
    dbspl: float,
    fmod: float,
    dmod: float,
    phase_shift: float,
    seed: int,
):
    """
    Generate an amplitude-modulated noise with linear ramps.

    Parameters
    ----------
    t : array
        array of waveform time values
    ramp : float
        ramp duration
    rate : float
        sample rate
    duration : float
        duration of noise
    starts : list
        start time for noise
    pip_dur : flost
        duration of noise pips
    dbspl : float
        sound pressure of stimulus
    fmod : float
        modulation frequency
    fmod : float
        modulation depth percent
    phase_shift : float
        modulation phase
    seed : int
        seed for random number generator

    Returns
    -------
    array :
        waveform

    """
    irpts = int(ramp * rate)
    mxpts = len(t) + 1
    pin = pipnoise(
        t,
        ramp=ramp,
        rate=rate,
        duration=duration,
        dbspl=dbspl,
        pip_dur=pip_dur,
        pip_starts=starts,
        seed=seed,
    )
    env = 1 + (dmod / 100.0) * np.sin(
        (2 * np.pi * fmod * t) - np.pi / 2 + phase_shift
    )  # envelope...

    pin = linearramp(pin, mxpts, irpts)
    env = linearramp(env, mxpts, irpts)
    return pin * env


def fmsweep(t:np.ndarray, start:float, duration:float, freqs:list, ramp:float, dbspl:float):
    """
    Create a waveform for an FM sweep over time. Output is in
    Pascals.

    Parameters
    ----------
    t : array
        time array for waveform
    start : float (seconds)
        start time for sweep
    duration : float (seconds)
        duration of sweep
    freqs : array (Hz)
        Two-element array specifying the start and end frequency of the sweep
    ramp : str
        The shape of time course of the sweep (linear, logarithmic)
    dbspl : float
        maximum sound pressure level of sweep

    Returns
    -------
    array :
        waveform


    """
    # TODO: implement start...correct for sampling rate issues.
    # Signature:
    # scipy.signal.chirp(t, f0, t1, f1, method='linear', phi=0, vertex_zero=True)[source]
    # print((freqs[0], freqs[1]))
    # print(duration)
    # print((np.max(t)))
    sw = scipy.signal.chirp(
        t, freqs[0], duration, freqs[1], method=ramp, phi=0, vertex_zero=True
    )
    if dbspl is not None:
        sw = np.sqrt(2) * dbspl_to_pa(dbspl) * sw
    else:
        pass  # do not scale here
    return sw


def signalFilter_LPFButter(signal, LPF, samplefreq, NPole=8):
    """Filter with Butterworth low pass, using time-causal lfilter

    Digitally low-pass filter a signal using a multipole Butterworth
    filter. Does not apply reverse filtering so that result is causal.

    Parameters
    ----------
    signal : array
        The signal to be filtered.
    LPF : float
        The low-pass frequency of the filter (Hz)
    HPF : float
        The high-pass frequency of the filter (Hz)
    samplefreq : float
        The uniform sampling rate for the signal (in seconds)
    npole : int
        Number of poles for Butterworth filter. Positive integer.

    Returns
    -------
    w : array
    filtered version of the input signal

    """
    flpf = float(LPF)
    sf = float(samplefreq)
    wn = [flpf / (sf / 2.0)]
    b, a = scipy.signal.butter(NPole, wn, btype="low", output="ba")
    zi = scipy.signal.lfilter_zi(b, a)
    out, zo = scipy.signal.lfilter(b, a, signal, zi=zi * signal[0])
    return np.array(out)


def signalFilterButter(
    signal, filtertype="bandpass", lpf=None, hpf=None, Fs=None, poles=8
):
    """Filter signal within a bandpass with elliptical filter

    Digitally filter a signal with an butterworth filter; handles
    bandpass filtering between two frequencies.

    Parameters
    ----------
    signal : array
        The signal to be filtered.
    LPF : float
        The low-pass frequency of the filter (Hz)
    HPF : float
        The high-pass frequency of the filter (Hz)
    Fs : float
        The uniform sampling rate for the signal (in seconds)

    Returns
    -------
    w : array
        filtered version of the input signal
    """
    sf2 = Fs / 2
    wn = [hpf / sf2, lpf / sf2]

    filter_b, filter_a = scipy.signal.butter(poles, wn, btype=filtertype)
    w = scipy.signal.lfilter(filter_b, filter_a, signal)  # filter the incoming signal
    return w

#*******************************************************
#                       TESTS 
# ******************************************************
def play_wave(wave, rate):
    # downsample wave for speaker
    twave = np.linspace(0, len(wave)/rate, len(wave))
    tmax = np.max(twave)
    newrate = 44100
    tnew = np.arange(0, tmax, 1./newrate)

    dwave = np.interp(tnew, twave, wave)
    sounddevice.play(dwave, 44100)
    time.sleep(1)

def test_noise_bandpass():

    """
    based on Nelken and Young, 1994.
    There are other ways to do this however.
    
    """
    Fs = 200000.0
    wave1 = NoisePip(
        rate=Fs,
        duration=2.0,
        dbspl=None,
        pip_duration=1.8,
        pip_starts=[0.05],
        ramp_duration=0.01,
        seed=1,
    )
    wave2 = NoisePip(
        rate=Fs,
        duration=2.0,
        dbspl=None,
        pip_duration=1.8,
        pip_starts=[0.05],
        ramp_duration=0.01,
        seed=2,
    )
    w1 = wave1.sound
    w2 = wave2.sound
    t = wave1.time
    ax = mpl.subplot(311)
    fx, Pxx_spec = scipy.signal.periodogram(w1, Fs)
    ax.plot(fx, Pxx_spec, "k-")
    f0 = 4000.0
    nbw = 800.0
    notchbw = 800.0
    lpf = 2000.0
    
    fb1 = signalFilter_LPFButter(w1, nbw, Fs)
    fb2 = signalFilter_LPFButter(w2, nbw, Fs)
    rn = fb1 * np.cos(2 * np.pi * f0 * t) + fb2 * np.sin(2 * np.pi * f0 * t)

    play_wave(rn, Fs)

    fx2, Pxx_spec2 = scipy.signal.periodogram(rn, Fs)
    ax2 = mpl.subplot(312)
    ax2.plot(fx2, Pxx_spec2, "b-")
    # now notched noise
    nn1 = signalFilterButter(
        w1, filtertype="bandpass", lpf=lpf, hpf=lpf-notchbw, Fs=Fs, poles=4
    )
    nn2 = signalFilterButter(
        w2, filtertype="bandpass", lpf=lpf, hpf=lpf-notchbw, Fs=Fs, poles=4
    )
    rn2 = nn1 * np.cos(2 * np.pi * f0 * t) + nn2 * np.sin(2 * np.pi * f0 * t)
    fx3, Pxx_spec3 = scipy.signal.periodogram(rn2, Fs)
    ax3 = mpl.subplot(313)
    ax3.plot(fx3, Pxx_spec3, "r-")

    mpl.show()


def test_tone_pip():
    rate=200000.
    wave1 = TonePip(
        rate=rate,
        f0=4000.,
        duration=0.5,
        dbspl=None,
        pip_duration=0.1,
        pip_starts=[0.05, 0.20],
        ramp_duration=0.005,
    )
    mpl.plot(wave1.time, wave1.sound)
    mpl.show()

def test_noise_pip():
    rate=200000.
    wave1 = NoisePip(
        rate=rate,
        f0=4000.,
        duration=0.5,
        dbspl=None,
        pip_duration=0.1,
        pip_starts=[0.05, 0.20],
        ramp_duration=0.005,
        seed=1,
    )
    mpl.plot(wave1.time, wave1.sound)
    mpl.show()

def test_RSS():
    rate=100000.
    
    wave1 = RandomSpectrumShape(
        rate=rate,
        duration=1.0,
        f0=4000.,
        dbspl=80.,
        pip_duration=0.4,
        pip_starts=[0.05],
        ramp_duration=0.005,
        amp_group_size=8,  # typically 4 or 8 for RSS
        amp_sd=12.0,  # as used by Young and Calhoun, 2005, Yu and Young, 2000 and Li et al., 2015
        spacing=1./8.,  # between stimuli, 1/8 octave
        octaves=4,  # width of stimulus
    )
    f, ax = mpl.subplots(2, 1, figsize=(10, 8))
    fx2, Pxx_spec2 = scipy.signal.periodogram(wave1.sound, rate, scaling="spectrum")
    # fx2, Pxx_spec2 = scipy.signal.welch(wave1.sound, rate, nfft=64000, nperseg=64000)
    ax[0].plot(wave1.time, wave1.sound)
    ax[1].semilogx(fx2, Pxx_spec2, "b-", linewidth=0.3)
    # ax[1].set_xlim([990, 1170])
    play_wave(wave1.sound, rate)
    mpl.show()


def test_cmmr():
    rate = 250000.
    outputs = ["Target", "OFM", "Flanking", "Signal", "Target+OFM"]
    nparts = len(outputs)
    waves = {}

    ftypes = ["Comodulated", "Codeviant", "Random"]
    ntypes = len(ftypes)
    f, ax = mpl.subplots(nparts, ntypes, figsize=(10, 8), )
    mpl.subplots_adjust(wspace=0.5, hspace=0.2)
    f.suptitle("CMMR")
    for j, ftype in enumerate(ftypes):
        for i, fp in enumerate(outputs):
            waves[fp] = ComodulationMasking(rate=rate, duration=1.0, 
                                    target_f0 = 2000., masker_f0 = 2000.,
                                    masker_delay=0.1, masker_duration=0.5,
                                    target_delay=0.3, target_duration=0.3,
                                    target_spl=70, masker_spl=70, 
                                    fmod=10.0, dmod=100,
                                    ramp_duration=0.0025,
                                    flanking_type="MultiTone", flanking_spacing=0.5,
                                    flanking_phase=ftype, flanking_bands=3,
                                    output = fp)
            play_wave(waves[fp].sound, rate)

            ax[i,j].plot(waves[fp].time, waves[fp].sound, linewidth=0.5)
            if i == 0:
                ax[i,j].set_title(f"{ftype}", fontsize=9)
            if j == 0:
                ax[i,j].set_ylabel(fp, fontsize=9)
            if i == nparts-1:
                ax[i,j].set_xlabel("Time (s)", fontsize=9)
            ax[i,j].tick_params('x', labelsize=7)
            ax[i,j].tick_params('y', labelsize=7)
            ax[i,j].spines['right'].set_visible(False)
            ax[i,j].spines['top'].set_visible(False)

    mpl.text(0.95, 0.03, s=f"pysound: {datetime.datetime.now()!s}", horizontalalignment='right', fontsize=6, fontweight='normal',
                     transform=f.transFigure)


    mpl.show()

def test_clicks():
    rate = 200000.
    wave1 = ClickTrain(
        rate=rate,
        duration=0.2,
        dbspl=80.,
        click_duration=0.0001,
        click_starts=[0.01, 0.02, 0.03, 0.035],
    )

    mpl.plot(wave1.time, wave1.sound)
    mpl.show()

if __name__ == "__main__":
    """
    Test sound generation
    """
    import matplotlib.pyplot as mpl
    import sounddevice
    import datetime
    import time
    # test_RSS()
    # test_tone_pip()
    # test_noise_pip()
    # test_clicks()
    test_cmmr()
    # test_noise_bandpass()
    
