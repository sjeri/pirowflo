
from time import sleep
from . import antdongle as ant
from . import antfe as fe
from pymemcache.client.base import Client as MemCclient
from pymemcache import serde
import time
import logging
logger = logging.getLogger(__name__)

def main():
    EventCounter = 0
    messages = []       # messages to be sent to
    AntHRMpaired = False
    HRM_Rate = 0
    HRM_ID = None
    HRM_Age = time.time()
    try:
        mcclient = MemCclient('unix:/var/run/memcached/memcached.sock', serde=serde.pickle_serde, key_prefix=b'pirowflo_')
        mcclient.version()
    except Exception:
        mcclient = None
    Antdongle = ant.clsAntDongle() # define the ANt+ dongle
    Antdongle.Calibrate()   # reset the dongle and defines it as node
    sleep(0.25)
    Antdongle.Trainer_ChannelConfig() # define the channel needed for fitness equipements
    sleep(0.25)
    Antdongle.SlaveHRM_ChannelConfig(0) #device ID is any! whoever is first, wins...
    sleep(0.25)
    Waterrower = fe.antFE(Antdongle) # hand over the class to antfe to give acces to the dongle
    last_message_time = None
    while True:
        StartTime = time.time()
        if mcclient: #as long as the deque data from WR are not empty
            WaterrowerValuesRaw = mcclient.get_many((
                'message_time', 'stroke_rate', 'total_strokes', 'total_distance_m',
                'instantaneous_pace', 'speed', 'watts', 'total_kcal', 'total_kcal_hour',
                'total_kcal_min', 'heart_rate', 'elapsedtime', 'work', 'stroke_length',
                'force', 'watts_avg', 'pace_avg'))  # ant_in_q.pop() # remove it from the deque and put in variable
            mt = WaterrowerValuesRaw.pop('message_time', None)
            if len(WaterrowerValuesRaw.keys()) > 0 and mt != last_message_time:
                last_message_time = mt
                if AntHRMpaired:
                    WaterrowerValuesRaw['heart_rate'] = HRM_Rate
                    mcclient.set_many({'HRM_Rate': HRM_Rate, 'HRM_ID': HRM_ID}, expire=3)
                Waterrower.EventCounter = EventCounter # set the eventcounter of the instance
                Waterrower.BroadcastTrainerDataMessage(WaterrowerValuesRaw) # insert data into instance, heartrate is 250ms old value from previous run
                messages.append(Waterrower.fedata) # depending on the event counter value load the message arrey with the either Fitness equipement, rowerdata, manu data or product data
        if len(messages) > 0:
            data = Antdongle.Write(messages, True, False) # check if length of array is greater than 0 if yes then send data over Ant+
        else:
            data = Antdongle.Read(False)
        for d in data:
            synch, length, id, info, checksum, _rest, Channel, DataPageNumber = Antdongle.DecomposeMessage(d)
            if id == Antdongle.msgID_BroadcastData:
                if Channel == Antdongle.channel_HRM_s:
                    if not AntHRMpaired:
                        msg = Antdongle.msg4D_RequestMessage(Antdongle.channel_HRM_s, Antdongle.msgID_ChannelID)
                        Antdongle.Write([msg], False, False)
                    if DataPageNumber & 0x7f in (0,1,2,3,4,5,6,7,89,95):
                        _Channel, _DataPageNumber, _Spec1, _Spec2, _Spec3, \
                        _HeartBeatEventTime, _HeartBeatCount, HRM_Rate = Antdongle.msgUnpage_Hrm(info)
                        HRM_Age = time.time()
                    elif DataPageNumber in (89, 95):
                        pass
                    else:
                        logger.warning("Unknown HRM data page")
            elif id == Antdongle.msgID_ChannelID:
                Channel, DeviceNumber, DeviceTypeID, _TransmissionType = Antdongle.unmsg51_ChannelID(info)
                if DeviceNumber == 0:
                    pass
                elif Channel == Antdongle.channel_HRM_s and DeviceTypeID == Antdongle.DeviceTypeID_HRM:
                    AntHRMpaired = True
                    HRM_ID = DeviceNumber
                    HRM_Age = time.time()
                    logger.info('Heart Rate Monitor paired: %s' % DeviceNumber)
                else:
                    logger.info('Unexpected device %s on channel %s' % (DeviceNumber, Channel))
            EventCounter += 1
            EventCounter = int(EventCounter) & 0xff
            messages = []
        else:
            pass
        if (time.time() - HRM_Age) > 10:
            HRM_Rate = 0
            HRM_ID = None
            AntHRMpaired = False
        SleepTime = 0.25 - (time.time() - StartTime)
        if SleepTime > 0:
            time.sleep(SleepTime)


def FakeRower(WRValues_test):
    WRValues_test_updated = {}
    WRValues_test_updated.update({'stroke_rate': 23})
    WRValues_test_updated.update({'total_strokes': WRValues_test['total_strokes'] + 1})
    WRValues_test_updated.update({'total_distance_m': WRValues_test['total_distance_m'] + 1})
    WRValues_test_updated.update({'speed': 500000 })
    WRValues_test_updated.update({'watts': 150})
    WRValues_test_updated.update({'total_kcal': WRValues_test['total_kcal'] + 1})
    WRValues_test_updated.update({'elapsedtime': WRValues_test['elapsedtime'] +1})
    return WRValues_test_updated

if __name__ == '__main__':

    # WRValues_test = {
    #             'stroke_rate': 23,
    #             'total_strokes': 10,
    #             'total_distance_m': 10,
    #             'instantaneous pace': 0,
    #             'speed': 10,
    #             'watts': 50,
    #             'total_kcal': 0,
    #             'total_kcal_hour': 0,
    #             'total_kcal_min': 0,
    #             'heart_rate': 120,
    #             'elapsedtime': 25,
    #         }
    main()