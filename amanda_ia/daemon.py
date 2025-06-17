from argparse import ONE_OR_MORE, ArgumentParser
from . import __version__
import os
from dotenv import load_dotenv
from aia_utils.logs_cfg import config_logger
from amanda_ia.aia import AIAService
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
    logger.info(f"Start Daemon amanda-IA v{getVersion()}")
    aiaSvc = AIAService(os.environ['CLOUDKAFKA_TOPIC_PRODUCER'], os.environ['CLOUDKAFKA_TOPIC_CONSUMER'], __version__)
    aiaSvc.startModel()
    aiaSvc.kafkaListener()
