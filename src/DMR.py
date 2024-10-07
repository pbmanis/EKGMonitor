

import numpy as np
from matplotlib import pyplot as plt
from pyqtgraph import multiprocess as mp

""" class DMR
This class generates Dynamic Moving Ripple (DMR) stimuli with randomly
generated parameters. DMRs are an extension of moving Ripple by
Monty A. Escabi and Christoph E. Schreiner: Nonlinear Spectrotemporal
Sound Analysis by Neurons in the Auditory Midbrain. The Journal of
Neuroscience, May 15, 2002, 22(10):4114-4131.
The basic formula is
 S(x,t) = M/2 * sin( 2 * pi(omega of t + Omega of x) + Phase phi of t)
where M is the modulation depth of the envelope in decibels (30dB or 45dB)
and x = log2 (F/F0) where F0 is the basefreq (500 Hz) and F is the
frequency of the tone.
The phase phi is a function of time and controls the time-varying
temporal modulation rate ( Phase Phi of t = Integral from 0 till t of
Fm of t as a function of t where Fm is the time-varying temporal
modulation rate).
Fm and Omega are slowly time variying signals (Fm <= 1.5 Hz and Omega <=
3 Hz)
See also Script_Generate_FMBanks

Author: arne.f.meyer@uni-oldenburg.de
Date  : 22-Nov-2010 09:41:44

converted to python pbmanis 3/31/2017
python3/cleanup 1/28/2021

Some of this code may be from:

# ---------------------------------------------------------------------
# Copyright (c) 2010 Arne F. Meyer, Max F.K. Happel, Jan Diepenbrock,
#                    Frank W. Ohl, Jörn Anemüller
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# ---------------------------------------------------------------------

"""

cf = 2e3
Fs = 44100  # sample frequency
level = 80.0
seed = 34978
fmod = 20.0
dmod = 20.0


class DMR(object):
    def __init__(self):
        # Stimulus parameters
        self.nStimLen = 10  # stimulus length is s
        self.nFsStim = 44100.0  # sampling frequency in Hz

        # DMR parameters
        self.nMaxFreq = 22050.0
        self.nMinFreq = 250
        self.nRampLen = 0.005
        self.nGain = 0.5

        self.nFsFm = 3.0  # max. time-varying temporal modulation rate
        self.nFsRd = 6  # max instantaneous ripple density
        self.nBaseFreq = 500.0  # base frequency in Hz
        self.nCarriersOct = 43  # number of carrier freqq. per octave, Escabi and Schreiner used 230 carriers over 5.32 octaves (0.5 - 20kHz)
        self.nMaxFmRate = 3.0  # max. time-varying temporal modulation rate
        self.nMaxRdRate = 6.0  # max instantaneous ripple density
        self.nOctaves = 5.0  # number of oktaves covered
        self.nAmp = 45.0
        self.nAmpFm = 350.0  # max abs. amplitude of temp. modulation rate in Hz
        self.nAmpRd = 4.0  # max abs. ripple density per octave
        self.nFsEnvFreq = 43.0
        self.nFsEnvTime = 4410.0
        self.calculated = False

    def set_params(self, Fs=44100, duration=10.0):
        self.nStimeLen = duration
        self.nFsStim = Fs
        self.nMaxFreq = self.nFsStim / 2.0
        self.nFsEnvTime = self.nFsStim / self.nStimLen

    def calculate_params(self):
        """ 
        Generate parameters
        Parameters
        ----------
        None
        
        Returns
        -------
        Nothing
        
        Modifies
        --------
        self.vPhase, self.vRD, self.vPahses, self.nLoopSteps, self.vLogFreq
        self.vCarrierFreq
        """

        # Define some variables from basic parameters
        self.vTime = np.linspace(
            1.0 / self.nFsStim, self.nStimLen, int(self.nStimLen * self.nFsStim)
        )  # time vector
        vTimeFm = np.linspace(
            0.0, self.nStimLen, int(self.nStimLen * self.nFsFm)
        )  # vector for sampling of temporal modulation rate
        vTimeRD = np.linspace(
            0, self.nStimLen, int(self.nStimLen * self.nFsRd)
        )  # vector for sampling of inst. ripple density

        # Vector containing carrier frequencies
        self.vCarrierFreq = (
            self.nBaseFreq
            * 2.0 ** np.linspace(0, self.nOctaves, int(self.nCarriersOct * self.nOctaves)).T
        )

        # Use an uniform distribution for frequency modulation
        vFm = np.random.uniform(size=vTimeFm.shape[0])
        vFmUpSamp = np.interp(self.vTime, vTimeFm, vFm)  # 'cubic')
        vFm = (
            vFmUpSamp * self.nMaxFmRate * 2.0
        ) - self.nMaxFmRate  # take Fm from -amp_Fm to amp_Fm Hz

        # Computation of Phase of t (integral of temporal modulationrate)
        self.vPhase = np.cumsum(vFm) / self.nFsStim
        # print 'vphase: ', vPhase.shape
        # Use an uniform distribution for ripple density
        vRD = np.random.uniform(size=vTimeRD.shape[0])
        vRDUpSamp = np.interp(self.vTime, vTimeRD, vRD)  # ,vTime,'cubic')
        self.vRD = vRDUpSamp * self.nMaxRdRate  # take RD from 0 to amp_Rd cyc/octaves

        self.nLoopSteps = self.vCarrierFreq.shape[0]
        self.vPhases = np.random.uniform(size=self.vCarrierFreq.shape[0]) * 2.0 * np.pi
        self.vLogFreq = np.log2(self.vCarrierFreq / self.nBaseFreq)

    def make_wave(self, iStep:int):
        """
        Make the waveform
        
        Parameters
        ----------
        
        iStep : int: no default
            step size for the waveform generation
        
        Returns
        -------
        w - the computed waveform
        """
        
        w = np.sin(
            2.0 * np.pi * self.vCarrierFreq[iStep] * self.vTime + self.vPhases[iStep]
        ) * 10.0 ** (
            (
                (self.nAmp / 2.0)
                * np.sin(2.0 * np.pi * self.vLogFreq[iStep] * self.vRD + self.vPhase)
                - self.nAmp / 2.0
            )
            / 20.0
        )
        return w

    def make_waveform(self):
        """ Compute the stimulus by multiplying carriers with the (exponentialized)
        envelope.
        Parameters
        ----------
        None
        
        Returns
        -------
        Nothing
        
        Modifies
        --------
        self.vStim
                
        """
        
        if not self.calculated:
            self.calculate_params()
        self.vStim = np.zeros(self.vTime.shape[0])
        # this calculation can be easily parallelized, so we do it
        tasks = []
        nworkers = mp.Parallelize.suggestedWorkerCount()
        for iStep in range(0, self.nLoopSteps):
            tasks.append(iStep)
        results = [None] * len(tasks)
        #    with mp.Parallelize(enumerate(tasks), workers=nworkers, results=results, progressDialog='Running parallel calculation..') as tasker:
        with mp.Parallelize(
            enumerate(tasks), workers=nworkers, results=results
        ) as tasker:
            for i, iStep in tasker:
                result = self.make_wave(iStep)
                #                print 'i: ', i
                tasker.results[i] = result
        for i, r in enumerate(results):
            self.vStim = self.vStim + r

        # original non-parallel code, for reference
        # for iStep in range(0, self.nLoopSteps):
        #     w = (np.sin( 2.0*np.pi*self.vCarrierFreq[iStep] * self.vTime + self.vPhases[iStep]) *
        #             10.**( ((self.nAmp/2.0) *
        #             np.sin( 2.0*np.pi*self.vLogFreq[iStep]*self.vRD + self.vPhase) -
        #             self.nAmp/2.0) /20. ))
        #     self.vStim = self.vStim + w

        # Normalization
        self.vStim = self.nGain * self.vStim / np.max(np.fabs(self.vStim))

    def savestim(self):
        # if bSaveStim
        #     wavwrite(vStim, nFsStim, 16, fullfile(sDataDir, 'Stimulus_DMRs.wav'))
        # end
        pass

    def plot_waveform(self):
        """
        Plot the waveform
        
        Parameters
        ----------
        None
        
        Returns
        -------
        Nothibng
        """
        ax1 = plt.subplot(311)
        plt.plot(self.vTime, self.vStim)
        #        plt.plot(vFm)
        #        plt.plot(vRD)
        plt.show()

    def plot_spectrogram(self):
        """
        Plotting the stimulus spectrogram
        
        Parameters
        ----------
        None
        
        Returns
        -------
        Nothing

        """
        
        nWinLen = 0.01
        nOverlap = nWinLen / 2

        ax1 = plt.subplot(311)
        plt.plot(self.vTime, self.vStim)
        plt.subplot(312, sharex=ax1)
        mSpec, vFreq, t, im = plt.specgram(
            self.vStim,
            NFFT=int(nWinLen * self.nFsStim),
            noverlap=int(nOverlap * self.nFsStim),
            Fs=self.nFsStim,
            cmap="viridis",
        )
        # [mSpec, vFreq, vTime] = spectrogram(vStim, ceil(nWinLen * nFsStim), ...
        #     round(nOverlap * nFsStim), [], nFsStim)
        nFsSpec = 1.0 / (t[1] - t[0])
        # nPlotLen              = 1
        # vPlotIdx              = 1:ceil(nPlotLen * nFsSpec)
        #
        # figure('Name','Stimulus spectrogram')
        # imagesc(vTime(vPlotIdx), vFreq, 20*log10(abs(mSpec(:,vPlotIdx))))
        # axis xy colorbar
        # xlabel('Time / s', 'FontSize', 16), xlim([0 nPlotLen])
        # ylabel('Frequency / Hz', 'FontSize', 16), ylim([nMinFreq nMaxFreq])
        # set(gca(), 'FontSize', 14)
        # if bSavePlots
        #     saveas(gcf(), fullfile(sDataDir, 'Spectrogram_DMRs'), 'psc2')
        # end
        plt.show()


def xcorr(x:np.array, y:np.array, maxlag:int=1):
    """
    Compute the cross-correlogram of two time series.
    
    Parameters
    ----------
    x, y : np.array (float, no default)
        The two arrays to be cross correlated.
    
    maxlag : int (default: 1)
        Window for the resulting array. Correspondings to the number
        of points either side of 0 for the resulting array
    
    Returns
    -------
    c : the cross correlation result
    """
    xl = x.size
    yl = y.size

    c = np.zeros(2 * maxlag + 1)

    for i in range(maxlag + 1):
        tmp = np.corrcoef(x[0 : min(xl, yl - i)], y[i : i + min(xl, yl - i)])
        c[maxlag - i] = tmp[1][0]
        tmp = np.corrcoef(x[i : i + min(xl - i, yl)], y[0 : min(xl - i, yl)])
        c[maxlag + i] = tmp[1][0]

    return c


def plotxcorr():
    # Frequency-wise autocorrelation function
    nMaxLagSec = 0.2
    nMaxLag = int(np.max(nMaxLagSec * nFsSpec))

    mCorr = np.zeros((mSpec.shape[0], 2 * nMaxLag + 1))  # was maxlag + 1 for matlab
    for iFreq in range(mSpec.shape[0]):
        mCorr[iFreq, :] = xcorr(
            np.fabs(mSpec[iFreq, :]), np.fabs(mSpec[iFreq, :]), maxlag=nMaxLag
        )
        mCorr[iFreq, :] = mCorr[iFreq, :] / np.max(mCorr[iFreq, :])

    ax2 = plt.subplot(313)
    # figure('Name','Frequency-wise stimulus autocorrelation')
    # imagesc((-nMaxLag:nMaxLag) / nFsSpec, vFreq, mCorr)
    plt.imshow(
        mCorr,
        extent=[-nMaxLag / nFsSpec, nMaxLag / nFsSpec, np.min(vFreq), np.max(vFreq)],
        aspect="auto",
        cmap="viridis",
    )

    plt.show()




