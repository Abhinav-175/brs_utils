import logging

logger = logging.getLogger("BRS Auto Centering")
logger.setLevel(logging.DEBUG)

# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)-8s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)
logger.propagate = False
