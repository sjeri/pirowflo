"""
Python script to broadcast waterrower data over BLE and ANT

      PiRowFlo for Waterrower
                                                                 +-+
                                               XX+-----------------+
                  +-------+                 XXXX    |----|       | |
                   +-----+                XXX +----------------+ | |
                   |     |             XXX    |XXXXXXXXXXXXXXXX| | |
    +--------------X-----X----------+XXX+------------------------+-+
    |                                                              |
    +--------------------------------------------------------------+

To begin choose an interface from where the data will be taken from either the S4 Monitor connected via USB or
the Smartrow pulley via bluetooth low energy

Then select which broadcast methode will be used. Bluetooth low energy or Ant+ or both.

e.g. use the S4 connected via USB and broadcast data over bluetooth and Ant+

python3 waterrowerthreads.py -i s4 -b -a
"""

import logging
import logging.config
import threading
import argparse
from queue import Queue
from collections import deque

from adapters.ble import waterrowerble
from adapters.s4 import wrtobleant
from adapters.ant import waterrowerant
from adapters.smartrow import smartrowtobleant
from adapters.fit.fitfileservice import FitThread
import pathlib
import signal

loggerconfigpath = str(pathlib.Path(__file__).parent.absolute()) +'/' +'logging.conf'

logger = logging.getLogger(__name__)
Mainlock = threading.Lock()


class Graceful:

    def __init__(self):
        self.run = True
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self,signum, frame):
        Mainlock.acquire()
        self.run = False
        logger.info("Quit gracefully program has been interrupt externally - exiting")
        Mainlock.release()

def main(args=None):
    logging.config.fileConfig(loggerconfigpath, disable_existing_loggers=False)
    grace = Graceful()

    def BleService():
        logger.info("Start BLE Advertise and BLE GATT Server")
        bleService = waterrowerble.main()
        bleService()


    def Waterrower():
        logger.info("Waterrower Interface started")
        Waterrowerserial = wrtobleant.main()
        Waterrowerserial()

    def Smartrow():
        logger.info("Smartrow Interface started")
        Smartrowconnection = smartrowtobleant.main()
        Smartrowconnection()

    def ANTService():
        logger.info("Start Ant and start broadcast data")
        antService = waterrowerant.main()
        antService()


    threads = []
    if args.interface == "s4":
        logger.info("inferface S4 monitor will be used for data input")
        t = threading.Thread(target=Waterrower, args=())
        t.daemon = True
        t.start()
        threads.append(t)
    else:
        logger.info("S4 not selected")

    if args.interface == "sr":
        logger.info("inferface smartrow will be used for data input")
        t = threading.Thread(target=Smartrow, args=())
        t.daemon = True
        t.start()
        threads.append(t)
    else:
        logger.info("sr not selected")

    if args.blue == True:
        t = threading.Thread(target=BleService, args=())
        t.daemon = True
        t.start()
        threads.append(t)
    else:
        logger.info("Bluetooth service not used")
    if args.antfe == True:
        t = threading.Thread(target=ANTService, args=())
        # [] are needed to tell threading that the list "deque" is one args and not a list of arguement !
        t.daemon = True
        t.start()
        threads.append(t)
    else:
        logger.info("Ant service not used")

    if args.fit:
        fit = FitThread()
        fit.daemon = True
        fit.start()
        threads.append(fit)
    else:
        logger.info("FIT service not used")
        fit = None

    while grace.run:
        for thread in threads:
            if grace.run == True:
                thread.join(timeout=10)
                if not thread.is_alive():
                    logger.info("Thread died - exiting")
                    return
    else:  # run things to be done before actual INTERRUPT is finished
        if fit and fit.is_alive():
            fit.terminate()

if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter, )
        parser.add_argument("-i", "--interface", choices=["s4","sr"], default="s4", help="choose  Waterrower interface S4 monitor: s4 or Smartrow: sr")
        parser.add_argument("-b", "--blue", action='store_true', default=False,help="Broadcast Waterrower data over bluetooth low energy")
        parser.add_argument("-a", "--antfe", action='store_true', default=False,help="Broadcast Waterrower data over Ant+")
        parser.add_argument("-f", "--fit", action='store_true', default=False,help="Store a FIT file for the session, dumped on Interrupt, " +
                                                                                   "Upload FIT file to GC on session end, " +
                                                                                   "provide HRM to select user from config file based on registered HRM")
        args = parser.parse_args()
        logger.info(args)
        main(args)
    except KeyboardInterrupt:
        print("code has been shutdown")

