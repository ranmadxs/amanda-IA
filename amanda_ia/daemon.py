from argparse import ONE_OR_MORE, ArgumentParser
from . import __version__
from .nluSvc import NLUService
import os
from dotenv import load_dotenv
from aia_utils.logs_cfg import config_logger
import logging
config_logger()
logger = logging.getLogger(__name__)
#from aia_utils.logs.logs_cfg import config_logger
#import logging
#config_logger()
#logger = logging.getLogger(__name__)
load_dotenv()
from aia_utils.toml_utils import getVersion

def run():
    """
    entry point
    """
    logger.info(f"Start Daemon cortex NLU v{getVersion()}")
    nluSvc = NLUService(os.environ['CLOUDKAFKA_TOPIC_PRODUCER'], os.environ['CLOUDKAFKA_TOPIC_CONSUMER'], __version__)
    nluSvc.kafkaListener()