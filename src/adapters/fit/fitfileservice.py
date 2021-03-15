"""
code base: https://github.com/inonoob/Coxswain2Fit
parts of below code were inspired by https://github.com/SuperTaiyaki/fitconverter/blob/master/write_fit.py
"""

import configparser
import io
import logging
import os
import threading
from collections import defaultdict
from collections import deque
from datetime import datetime
from enum import Enum
from pathlib import Path
from time import sleep

from pymemcache import serde
from pymemcache.client.base import Client as MemCclient

from .gc_client import ActivityUploader
from . import fithelper

logger = logging.getLogger(__name__)


class Gender(Enum):
    MALE = 1
    FEMALE = 2


class DataLogger:
    def __init__(self):
        self.lap_WRValues = []

    def reset(self):
        self.lap_WRValues = []

    def store(self, raw_values):
        refined_values = {'message_time': raw_values['message_time'],
                          'timestamp': int(fithelper.epoch_calc_sec(raw_values['message_time'])),
                          'lat_d': int(fithelper.degree_to_semicircle(52.471106)),
                          'lon_d': int(fithelper.degree_to_semicircle(13.114244)), 'hr': int(raw_values['heart_rate']),
                          'cadence': int(min(253, raw_values['stroke_rate'] / 2)),
                          'distance': int(raw_values['total_distance_m'] * 100), 'speed': int(raw_values['speed'] * 10),
                          'watts': int(min(65533, max(0, raw_values['watts']))),
                          'calories': int(raw_values['total_kcal']), 'total_strokes': int(raw_values['total_strokes']),
                          'total_distance_m': int(raw_values['total_distance_m'])}
        lap = int(raw_values['total_distance_m'] // 500)
        if not lap < len(self.lap_WRValues):
            self.lap_WRValues.append([])
        self.lap_WRValues[lap].append(refined_values)

    def dump_fit(self, body_data=None):
        start_time = self.lap_WRValues[0][0]['message_time']
        end_time = self.lap_WRValues[-1][-1]['message_time']
        output = io.BytesIO()
        fithelper.fit_main_header(output)
        fithelper.file_id(output)
        fithelper.event(output, timestamp=self.lap_WRValues[0][0]['timestamp'], event=0, event_type=0, timer_trigger=1)
        fithelper.user_profile(output, **body_data)
        fithelper.zones_target(output)
        fithelper.sport(output)
        self.laps_creator(output)
        fithelper.event(output, timestamp=self.lap_WRValues[-1][-1]['timestamp'] + 1, event=0, event_type=4, timer_trigger=0)
        self.session(output)
        self.activity(output)
        fithelper.check_file_size(output)
        fithelper.checksum(output)
        filename_date = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%Y-%m-%dT%H_%M_%SZ")
        filename = f"rowing-session-{filename_date}.fit"
        fithelper.export_file(output, filename)
        logger.info(">>> file export done")
        return start_time, end_time, filename

    def activity(self, output):
        timestamp = self.lap_WRValues[-1][-1]['timestamp'] + 1
        total_timer_time = (self.lap_WRValues[-1][-1]['timestamp'] - self.lap_WRValues[0][0]['timestamp']) * 1000
        num_sessions = 1
        data_array = [(253, "uint32", timestamp), (0, "uint32", total_timer_time), (1, "uint16", num_sessions)]
        bytes_data = fithelper.write_field(34, data_array, True, 0)
        output.write(bytes_data[0] + bytes_data[1])

    def session(self, output):
        first_lap_index = 0
        res = defaultdict(list)
        [res[k].append(v) for record in [record for lap in self.lap_WRValues for record in lap] for k, v in
         record.items()]
        sorted_records = dict(res)
        timestamp = self.lap_WRValues[-1][-1]['timestamp'] + 1
        start_time = self.lap_WRValues[0][0]['timestamp']
        start_position_lat = self.lap_WRValues[0][0]['lat_d']
        start_position_long = self.lap_WRValues[0][0]['lon_d']
        sport = 4
        sub_sport = 14
        total_timer_time = total_elasped_time = (self.lap_WRValues[-1][-1]['timestamp'] - self.lap_WRValues[0][0][
            'timestamp']) * 1000
        total_distance = self.lap_WRValues[-1][-1]['distance'] - self.lap_WRValues[0][0]['distance']
        total_calories = self.lap_WRValues[-1][-1]['calories'] - self.lap_WRValues[0][0]['calories']
        avg_speed = int(sum(sorted_records['speed']) / len(sorted_records['speed']))
        max_speed = max(sorted_records['speed'])
        avg_heart_rate = int(sum(sorted_records['hr']) / len(sorted_records['hr']))
        max_heart_rate = max(sorted_records['hr'])
        avg_cadence = int(sum(sorted_records['cadence']) / len(sorted_records['cadence']))
        max_cadence = max(sorted_records['cadence'])
        avg_power = int(sum(sorted_records['watts']) / len(sorted_records['watts']))
        max_power = max(sorted_records['watts'])
        num_lap = len(self.lap_WRValues)
        total_work = avg_power * ((self.lap_WRValues[-1][-1]['timestamp'] - self.lap_WRValues[0][0]['timestamp']))
        min_heart_rate = min(sorted_records['hr'])
        logger.info(self.lap_WRValues[-1][-1])
        stroke_count = self.lap_WRValues[-1][-1]['total_strokes']
        data_array = [(253, "uint32", timestamp), (2, "uint32", start_time), (3, "sint32", start_position_lat),
                      (4, "sint32", start_position_long), (5, "enum", sport), (6, "enum", sub_sport),
                      (7, "uint32", total_elasped_time), (8, "uint32", total_timer_time), (9, "uint32", total_distance),
                      (11, "uint16", total_calories), (14, "uint16", avg_speed), (15, "uint16", max_speed),
                      (16, "uint8", avg_heart_rate), (17, "uint8", max_heart_rate), (18, "uint8", avg_cadence),
                      (19, "uint8", max_cadence), (20, "uint16", avg_power), (21, "uint16", max_power),
                      (25, "uint16", first_lap_index), (26, "uint16", num_lap), (48, "uint32", total_work),
                      (64, "uint8", min_heart_rate), (10, "uint32", stroke_count)]
        bytes_data = fithelper.write_field(18, data_array, True, 0)
        output.write(bytes_data[0] + bytes_data[1])

    def heart_rate_zone_creator(self, heart_rate_zone_array, output_file):
        heart_rate_zone_creation_message = fithelper.hr_zone()
        output_file.write(heart_rate_zone_creation_message[0])
        for index, current_hr_zone in enumerate(heart_rate_zone_array):
            heart_rate_zone_creation_data = fithelper.hr_zone(current_hr_zone)
            output_file.write(heart_rate_zone_creation_data[1])

    def record_creator(self, lap, output_file):
        for index, record in enumerate(self.lap_WRValues[lap]):
            data_array = [(253, "uint32", record['timestamp']), (0, "sint32", record['lat_d']),
                          (1, "sint32", record['lon_d']),
                          (3, "uint8", record['hr']), (4, "uint8", record['cadence']),
                          (5, "uint32", record['distance']), (6, "uint16", record['speed']),
                          (7, "uint16", record['watts'])]
            bytes_data = fithelper.write_field(20, data_array, True, 0)
            output_file.write(bytes_data[0])
            output_file.write(bytes_data[1])
        return output_file

    def laps_creator(self, output_file):
        creation_array = [(253, "uint32", 966665266), (2, "uint32", 0), (3, "sint32", 0), (4, "sint32", 0),
                          (5, "sint32", 0), (6, "sint32", 0), (7, "uint32", 0), (8, "uint32", 0), (9, "uint32", 0),
                          (11, "uint16", 0), (13, "uint16", 0), (14, "uint16", 0), (15, "uint8", 0), (16, "uint8", 0),
                          (17, "uint8", 0), (18, "uint8", 0), (19, "uint16", 0), (20, "uint16", 0), (254, "uint16", 0)]
        for index, lap_records in enumerate(self.lap_WRValues):
            timestamp = lap_records[-1]['timestamp']
            start_time = lap_records[0]['timestamp'] if index == 0 else lap_records[0]['timestamp'] + 1
            start_position_lat = lap_records[0]['lat_d']
            start_position_long = lap_records[0]['lon_d']
            end_position_lat = lap_records[-1]['lat_d']
            end_position_long = lap_records[-1]['lon_d']
            total_timer_time = total_elasped_time = (lap_records[-1]['timestamp'] - lap_records[0]['timestamp']) * 1000
            total_calories = lap_records[-1]['calories'] if index == 0 else lap_records[-1]['calories'] - self.lap_WRValues[index - 1][-1]['calories']
            total_distance = lap_records[-1]['distance'] if index == 0 else lap_records[-1]['distance'] - self.lap_WRValues[index - 1][-1]['distance']
            res = defaultdict(list)
            [res[k].append(v) for lap_record in lap_records for k, v in lap_record.items()]
            sorted_records = dict(res)
            avg_speed = int(sum(sorted_records['speed']) / len(sorted_records['speed']))
            max_speed = max(sorted_records['speed'])
            avg_heart_rate = int(sum(sorted_records['hr']) / len(sorted_records['hr']))
            max_heart_rate = max(sorted_records['hr'])
            avg_cadence = int(sum(sorted_records['cadence']) / len(sorted_records['cadence']))
            max_cadence = max(sorted_records['cadence'])
            avg_power = int(sum(sorted_records['watts']) / len(sorted_records['watts']))
            max_power = max(sorted_records['watts'])
            self.record_creator(index, output_file)
            data_array = [(253, "uint32", timestamp), (2, "uint32", start_time), (3, "sint32", start_position_lat),
                          (4, "sint32", start_position_long), (5, "sint32", end_position_lat),
                          (6, "sint32", end_position_long), (7, "uint32", total_elasped_time),
                          (8, "uint32", total_timer_time), (9, "uint32", total_distance),
                          (11, "uint16", total_calories), (13, "uint16", avg_speed), (14, "uint16", max_speed),
                          (15, "uint8", avg_heart_rate), (16, "uint8", max_heart_rate), (17, "uint8", avg_cadence),
                          (18, "uint8", max_cadence), (19, "uint16", avg_power), (20, "uint16", max_power),
                          (254, "uint16", index)]
            bytes_data = fithelper.write_field(19, data_array, True, 0)
            output_file.write(fithelper.write_field(19, creation_array, True, 0)[0])
            output_file.write(bytes_data[1])
        return output_file


class FitThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.setName(self.__class__.__name__ + "-" + self.getName())
        logger.info("initializing thread " + self.getName())
        self.paused = False
        self.in_queue = deque(maxlen=1)
        self.reset_in_queue = deque(maxlen=1)
        self.pause_cond = threading.Condition(threading.Lock())
        self.dl = None
        self.loop = True
        try:
            self.mcclient = MemCclient('127.0.0.1:11211', serde=serde.pickle_serde, key_prefix=b'pirowflo_')
            self.mcclient.version()
        except Exception:
            self.mcclient = None
            logger.warning("memcached not listening on 127.0.0.1:11211. No recording going to happen")
        logger.info("initialized thread " + self.getName())

    def run(self):
        logger.info("starting thread " + self.getName())
        reset_occured = False
        while self.loop:
            with self.pause_cond:
                while self.paused:
                    self.pause_cond.wait()
            reset = self.mcclient.get('RESET', default=None) if self.mcclient else None
            if reset and not reset_occured:
                self.dump()
                self.dl = None
                reset_occured = True
            elif reset and reset_occured:
                pass
            else:
                if not self.dl:
                    self.dl = DataLogger()
                if self.mcclient:
                    WRValues = self.mcclient.get_many((
                        'message_time', 'stroke_rate', 'total_strokes', 'total_distance_m',
                        'instantaneous_pace', 'speed', 'watts', 'total_kcal', 'total_kcal_hour',
                        'total_kcal_min', 'heart_rate', 'elapsedtime', 'work', 'stroke_length',
                        'force', 'watts_avg', 'pace_avg', 'HRM_Rate'))
                    hrm = WRValues.get('HRM_Rate', 0)
                    if len(WRValues.keys()) > 0:
                        self.dl.store(WRValues)
                        if hrm > 0:
                            WRValues['heart_rate'] = hrm
                else:
                    pass
            sleep(1)
        logger.info("closing thread " + self.getName())

    def dump(self):
        # store FIT only on session larger than 50m (this avoids trouble when e.g. BLE device initiates initial reset)
        if len(self.dl.lap_WRValues) > 0 and self.dl.lap_WRValues[-1][-1]['distance'] > 5000:
            try:
                config = configparser.ConfigParser()
                logger.info(f"looking for rowers.conf in {os.path.join(os.path.dirname(__file__), 'rowers.conf')} " +
                            f"and {str(Path.home())}/rowers.conf")
                config.read([os.path.join(os.path.dirname(__file__), 'rowers.conf'), str(Path.home()) + '/rowers.conf'])
                hrm_id = self.mcclient.get("HRM_ID", default=None) if self.mcclient else None
                profilename = config['DEFAULT'].get('ActiveProfile', None)
                if hrm_id:
                    for section in config.sections():
                        config_hrm_id = config[section].get('hrm_id', None)
                        if config_hrm_id and str(config_hrm_id) == str(hrm_id):
                            profilename = section
                            break
                profile = {}
                if profilename:
                    profile = config[f"{profilename}"]
                    logger.info(f"Profile: {profilename}")
                else:
                    logger.info(f"no rowers.conf profile found")
                username, password = None, None
                if 'gc_username' in profile:
                    username = profile['gc_username']
                    password = profile['gc_password']
                userinfo, userstats, gcau = {}, {}, None
                if username:
                    logger.info(f"attempt garmin connect upload for user: {username}")
                    gcau = ActivityUploader()
                    gcau.login(email=username, password=password)
                    logger.info(f"User: {gcau.get_user()}")
                    userinfo = gcau.get_userinfo()
                    userstats = gcau.get_stats()
                bodydata = {}
                bodydata['gender'] = Gender[userinfo.get('genderType') or profile.get('gender', 'MALE')].value
                bodydata['age'] = int(userinfo.get('age') or profile.get('age', 40))
                bodydata['height'] = int(userinfo.get('height') or profile.get('height', 178))
                bodydata['weight'] = int(float(userinfo.get('weight') or profile.get('weight', 85.8) * 1000) / 1000 * 10)
                bodydata['resting_heart_rate'] = int(userstats.get('restingHeartRate') or profile.get('minhr', 60))
                bodydata['default_max_heart_rate'] = 220 - bodydata['age'] \
                    if bodydata['gender'] == Gender.MALE.value else 226 - bodydata['age']
                logger.info(bodydata)
                logger.info(f"weight: {round(bodydata['weight'] / 10, 2):.2f}")
                start, end, filename = self.dl.dump_fit(bodydata)
                logger.info(f"start:{start}, end:{end}, target:{filename}")
                if gcau:
                    gcau.upload_activity("Indoor Rowing " + start, os.path.abspath(filename))
                else:
                    logger.info(f"no garmin connect profile configured")
            except Exception as e:
                logger.info('Error: {}'.format(e))
            self.dl.reset()
        else:
            logger.info("No session to store")

    def pause(self):
        self.paused = True
        self.pause_cond.acquire()

    def resume(self):
        self.paused = False
        self.pause_cond.notify()
        self.pause_cond.release()

    def terminate(self):
        logger.info("terminate fitfileservice")
        self.loop = False
        self.dump()
