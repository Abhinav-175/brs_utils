import argparse
import configparser
import datetime
import logging
import os
import time

import ezca
from logger import logger
import numpy as np


def parser():
    parser = argparse.ArgumentParser(description="BRS auto centering")
    parser.add_argument("-c", "--config", type=str, help="The path of the .ini config file. Use the -g or --get-config tag to get a sample config.")
    parser.add_argument("-g", "--get-config", action="store_true", help="Get sample configuration file.")
    return parser


def generate_sample_config():
    config = configparser.ConfigParser()
    config.optionxform = str
    config["Default"] = {
        "optics": "ITMX",
        "control_negated": False,
        "threshold_lower": 8192,
        "threshold_upper": -8192,
        "start_now": False,
        "interval_hour": "12",
        "n_grid": "64"}
    path = "brs_control_sample.ini"
    with open(path, "w") as configfile:
        logger.info(f"Generating sample configuration file in current directory: {path}")
        config.write(configfile)


def read_brs_config(config_path):
    """Read BRS config file and return the config parameters

    Parameters
    ----------
    config_path : str
        Path to the configuration file.

    Returns
    -------
    optics : str
        The optics where the BRS is in proximity (ITMX, ITMY, ETMX, or ETMY).
    control_negated : boolean
        Is True is increasing temperature cause BRS drift to decrease.
    threshold_lower : int
        Lower threshold of the BRS drift.
    threshold_upper : int
        Upper threshold of the BRS drift.
    start_now : boolean
        Start the iteration right away.
    interval_hour : float
        Control interval in hours.
    n_grid : int
        Number of grids of the temperature control.
    """
    config = configparser.ConfigParser()
    config.optionxform = str
    config.read(config_path)
    default = config["Default"]
    optics = default["optics"]
    control_negated = default.getboolean("control_negated")
    threshold_lower = default.getint("threshold_lower")
    threshold_upper = default.getint("threshold_upper")
    start_now = default.getboolean("start_now")
    interval_hour = default.getfloat("interval_hour")
    n_grid = default.getint("n_grid")
    
    #  print(optics, control_negated, 1+threshold_lower, 1+threshold_upper, start_now, interval_hour)
    return optics, control_negated, threshold_lower, threshold_upper, start_now, interval_hour, n_grid


def schedule_run(func, start_now, interval_hour, **kwargs):
    """Schedule run function 

    Parameters
    ----------
    func : function
        The function to be run.
    start_now : boolean
        Run the function as soon as schedule_run is called.
    interval_hour : float
        Run interval  in hours.
    **kwargs
        Keyword arguments passed to ``func``.
    """
    if start_now:
        func(**kwargs)
    time_now = datetime.datetime.now()
    time_delta = datetime.timedelta(hours=interval_hour)
    time_next = time_now + time_delta
    time_sleep = interval_hour*60*60/10  # sleep 10 times.
    logger.info(f"Next scheduled run: {time_next}")
    try:
        while 1:
            if datetime.datetime.now() > time_next:
                func(**kwargs)
                time_now = datetime.datetime.now()
                time_next = time_now + time_delta
                logger.info(f"Next scheduled run: {time_next}")
            time.sleep(time_sleep)
    except KeyboardInterrupt:
        logger.info("Program interrupted by user.")
        exit()


def brs_control(optics, control_negated, threshold_lower, threshold_upper, n_grid):
    """Check drift and compensate by adjusting temperature control

    Parameters
    ----------
    optics : str
        The optics where the BRS is in proximity (ITMX, ITMY, ETMX, or ETMY).
    control_negated : boolean
        Is True is increasing temperature cause BRS drift to decrease.
    threshold_lower : int
        Lower threshold of the BRS drift.
    threshold_upper : int
        Upper threshold of the BRS drift.
    n_grid : int
        Number of grids of the temperature control.
    """
    ## Stuff that needs to be iterated:

    #optics = "ITMY"
    #control_negated = False  # True if increasing temperature cause driftmon to decrease. Consult LLO alog 59481.
    #threshold_upper = 8192
    #threshold_lower = -8192
    time_now = datetime.datetime.now()
    logger.info(f"{time_now}: Starting BRS auto centering temperature control")

    ezca_instance = ezca.Ezca("")


    channel_drift = f"ISI-GND_BRS_{optics}_DRIFTMON"
    channel_control = f"ISI-GND_BRS_{optics}_HEATCTRLIN"

    drift = ezca_instance.read(channel_drift)
    control = ezca_instance.read(channel_control)
    # Round off unnecessary digits
    drift = np.round(drift, 2)  # To 2 decimal places.
    control = np.round(control, 2)  # To 1 decimal place.
    control_grid = np.round(np.sqrt(np.linspace(0, 100, n_grid)), 2)

    logger.info(f"Current drift: {drift}. Current temperature control: {control}")

    # Check if we need to increase/decrease the temperature
    increase_temperature = None  # True if we want to increase temperature, False for decreasing, None for doing nothing.

    if drift > threshold_upper:
        # Too high
        logger.info(f"Current drift ({drift}) is higher than upper threshold ({threshold_upper})")
        if control_negated:
            # Increase temperature
            increase_temperature = True
        else:
            # Decrease temperature
            increase_temperature = False
        pass
    elif drift < threshold_lower:
        # Too low
        logger.info(f"Current drift ({drift}) is lower than lower threshold ({threshold_lower})")
        if control_negated:
            # Decrease temperature
            increase_temperature = False
        else:
            increase_temperature = True
        pass
    else:
        # Stay right there
        logger.info(f"Current drift ({drift}) is within threshold boundaries ({threshold_lower}, {threshold_upper})")


    # Find the closest temperature settings.
    i_closest = np.argmin(np.abs(control_grid-control))


    # Find the closest increment/decrement settings from the grid.
    if increase_temperature is None:
        control_next = control
    elif increase_temperature:
        # If closest setting is higher, then change to closest.
        # If closest setting is lower, increment from closest and change.
        while (i_closest < len(control_grid)-1) and (control_grid[i_closest] <= control):
            i_closest += 1
        control_next = control_grid[i_closest]
    else:
        # If closest temperature is lower, then change to closest.
        # If closest setting is higher, decrement from closest and change.
        while (i_closest > 0) and (control_grid[i_closest] >= control):
            i_closest -= 1    
        control_next = control_grid[i_closest]

    # Apply the changes
    if control != control_next:
        logger.info(f"Setting temperature control channel '{channel_control}' from {control} to {control_next}")
        ezca_instance.write(channel_control, control_next)
    else:
        logger.info("Doing nothing")

    ## Iteration finish


if __name__ == "__main__":
    opts = parser().parse_args()
    config_path = opts.config
    get_config = opts.get_config
    

    if get_config:
        generate_sample_config()
        exit()

    if config_path is not None:
        optics, control_negated, threshold_lower, threshold_upper, start_now, interval_hour, n_grid = read_brs_config(config_path)

    filename = os.path.splitext(config_path)[0]
    filehandler = logging.FileHandler(f"{filename}.log")
    filehandler.setLevel(logging.DEBUG)
    logger.addHandler(filehandler)

    logger.info(f"Parsing configuration file {config_path}:"
            f"optics: {optics}, control_negated: {control_negated}, threshold_lower: {threshold_lower}, threshold_upper: {threshold_upper}, n_grid: {n_grid}")
    # print(optics, control_negated, 1+threshold_lower, 1+threshold_upper, start_now, interval_hour)

    kwargs = {
        "optics": optics,
        "control_negated": control_negated,
        "threshold_lower": threshold_lower,
        "threshold_upper": threshold_upper,
        "n_grid": n_grid
    }
    schedule_run(brs_control, start_now=start_now, interval_hour=interval_hour, **kwargs)
