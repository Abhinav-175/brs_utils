import logging

logger = logging.getLogger("BRS Auto Switching")
logger.setLevel(logging.DEBUG)

# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)-8s: %(message)s",
 datefmt="%Y-%m-%d %H:%M:%S")

ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)
logger.propagate = False

# logger -----------------------------------------

# Scheduler -----------------------------------------

import datetime
import time


def schedule_run(func, Run_Interval):
    """Schedule run function 

    Parameters
    ----------
    func : function
        The function to be run. No arguments will be passed to this function.
    Run_Interval : float
        Run the function evey this number of seconds.
    """
    try:
        while True:
            logger.info(f"Running a check at : {datetime.datetime.now()}")
            func()
            time.sleep(Run_Interval)
    except KeyboardInterrupt:
        logger.info("Program interrupted by user.")
        exit()

# Scheduler -----------------------------------------

# CLI argument parsers -----------------------------------------
import argparse
parser = argparse.ArgumentParser()

parser.add_argument(
    "-c", "--config", 
    type = str, 
    help = "The path of the .ini config file. " 
           "Use the -g or --get-config tag to get a sample config.")

parser.add_argument("-g", "--get_config", action="store_true", 
help="Generate a sample configuration file.")

args = parser.parse_args()
# print(args.config)
# CLI argument parsers -----------------------------------------

# Config file parsers -----------------------------------------
import configparser


def generate_sample_config()->None:
    config = configparser.ConfigParser()
    config.optionxform = str
    config["Default"] = {
        "Optic": "ETMX",
        "STS_chn": "L1:ISI-GND_STS_ETMX_X_DQ",
        "SC_STS_chn": "L1:ISI-GND_SENSCOR_ETMX_SUPER_X_OUT_DQ",
        "Switch_chn": "L1:SEI-CS_SENSCOR_X_INIT_CHAN",
        "Filter": "zpk([],[],1,'n')",
        "Run_Interval": "500",
        "TS_Length": "1000"}

    path = "brs_switch_sample.ini"

    with open(path, "w") as configfile:
        logger.info(f"Generating sample configuration file "
                    f"in current directory: {path}")
        config.write(configfile)

if args.get_config:
    generate_sample_config()
    exit()

config = configparser.ConfigParser()
config.optionxform = str
config.read(args.config)

STS_chn = config["Default"]["STS_chn"] 
SC_STS_chn = config["Default"]["SC_STS_chn"]
SCFilter = str(config["Default"]["Filter"])
Switch_chn = config["Default"]["Switch_chn"]
Run_Interval = int(config["Default"]["Run_Interval"])
TS_len = int(config["Default"]["TS_Length"])

BRS_on_state = 8
BRS_off_state = 1

# Config file parsers -----------------------------------------


# Main --------------------------------------------------------

import numpy as np
from gwpy.timeseries import TimeSeries as ts
from gwpy.frequencyseries import FrequencySeries as fs
import control
import kontrol
import scipy
from lal import gpstime
import os

#import ezca


def filtobj(zpk):
    """
    Create a filter using knotrol.core.foton.foton2tf

    Parameters
    ----------
    zpk : A str of foton style zpk filter
    
    Output
    ------
    A control tf object.
    """
    filt = kontrol.core.foton.foton2tf(zpk)
    #filt = kontrol.load_transfer_function(zpk)
    return(filt)


def zpkonts(filt, data: ts):
    """
    returns the filtered timeseries

    Parameters
    ----------
    filt : control tf object, use filtobj function to create this object.
    data : gwpy.timeseries.TimeSeries object to propogate Timeseries and times.

    Output
    ------
    filtered timeseries numpy array
    """
    _, data_filt = control.forced_response(filt,
            U = data.value,
            T = data.times)
    return(data_filt)


def RMS(x):
    return(np.sqrt(np.mean(x**2)))


def ts2asd(data,fs,nperseg):    
    """
    returns frequency axis and ASD of a timeseries

    Parameters
    ----------
    data : numpy array of the timeseries
    fs : sampling rate of this timeseries
    nperseg : fft segment length (used len(data) for no averaging)

    Output
    ------
    returns numpy array of frequencies and ASD frequency series
    """
    f, Pxx = scipy.signal.welch(data, fs=fs, nperseg=nperseg)
    return(f, np.sqrt(Pxx))


def RMSseries(x, binwidth):
    """Calculates the RMS frequency series of a 
    given spectra.

    Summed and integrated from high to low freq
    
    Parameters
    ----------
    x : numpy array of ASD frequency series
    binwidth : binwidth/frequency resolution of the spectra

    Output
    ------
    returns a RMS frequency series, integrated from high to low freq
    """
    x_flipped = np.flip(x)
    cs_x = np.cumsum(x_flipped)
    return(binwidth * np.flip(cs_x))


#switchtoA = switcher(chaA)
#switchtoB = switcher(chaB)


def pathswitcher():
    """Compares the RMS of the STS signal with
    and without the BRS and switches the path to
    the one with lower DC RMS.
    
    Parameters
    ----------
    No explicit input parameters, utilizes global variables.

    Output
    ------
    Does not return anything
    """
    endtime = gpstime.gps_time_now()
    starttime = endtime - TS_len

    STS_ts = ts.get(STS_chn,starttime, endtime, host = "l1nds1")
    SC_STS_ts = ts.get(SC_STS_chn,starttime,endtime, host = "l1nds1")

    filt = filtobj(SCFilter)

    STS_RMS = RMS(zpkonts(filt, STS_ts))
    SC_STS_RMS = RMS(zpkonts(filt, SC_STS_ts))


    if STS_RMS > SC_STS_RMS:
        logger.info(f"STSrms = {round(STS_RMS,2)}, SC_STS_rms = {round(SC_STS_RMS,2)}\n"
                "switched sensor correction with BRS ON")
    else:
        logger.info(f"STSrms = {round(STS_RMS,2)}, SC_STS_rms = {round(SC_STS_RMS,2)}\n"
                "switched sensor correction with BRS OFF")


if __name__ == "__main__":
    log_file = os.path.splitext(args.config)[0]
    loghandler = logging.FileHandler(f"{log_file}.log")
    loghandler.setLevel(logging.DEBUG)
    logging.addHandler(loghandler)

    schedule_run(pathswitcher, Run_Interval)
