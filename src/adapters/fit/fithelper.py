"""
code base: https://github.com/inonoob/Coxswain2Fit
parts of below code were from here
https://github.com/SuperTaiyaki/fitconverter/blob/master/write_fit.py (9e6149c)
and got refactored.

The original code is copyright as follows:

Copyright (c) 2013 Jeremy Chin

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""

import logging
import struct
from datetime import datetime

logger = logging.getLogger(__name__)


def fit_main_header(output):
    output.write(struct.pack("=BBHL4sH", 14, 0x20, 2140, 0, b'.FIT', 0x0000))


def degree_to_semicircle(degree):
    return int(float(degree) * (2 ** 31 / 180))


def epoch_calc_sec(training_datetime):
    epoch = (datetime.fromisoformat("1989-12-31 00:00:00"))
    training_datetime_calc = datetime.strptime(training_datetime, "%Y-%m-%dT%H:%M:%S.%fZ")
    return int((training_datetime_calc - epoch).total_seconds())


def file_id(output, rid=0, time_created=966665266, activity_type=4, manufacturer=118, product=1, serial=1234567891):
    data_array = [(0, "enum", activity_type), (1, "uint16", manufacturer),
                  (2, "uint16", product), (3, "uint32z", serial), (4, "uint32", time_created)]
    bytes_data = write_field(rid, data_array, True, 0)
    output.write(bytes_data[0] + bytes_data[1])


def event(output, timestamp=966665266, event=0, event_type=0, timer_trigger=0):
    data_array = [(253, "uint32", timestamp), (0, "enum", event), (1, "enum", event_type),
                  (3, "enum", timer_trigger)]
    bytes_data = write_field(21, data_array, True, 0)
    output.write(bytes_data[0] + bytes_data[1])


def user_profile(output, gender=1, age=30, height=170, weight=700, resting_heart_rate=60,
                 default_max_heart_rate=200):
    data_array = [(1, "enum", gender), (2, "uint8", age), (3, "uint8", height), (4, "uint16", weight),
                  (8, "uint8", resting_heart_rate), (11, "uint8", default_max_heart_rate)]
    bytes_data = write_field(3, data_array, True, 0)
    output.write(bytes_data[0] + bytes_data[1])


def sport(output, sport=4, sub_sport=14):
    data_array = [(0, "enum", sport), (1, "enum", sub_sport)]
    bytes_data = write_field(12, data_array, True, 0)
    output.write(bytes_data[0] + bytes_data[1])


def zones_target(output, max_heart_rate=199):
    data_array = [(1, "uint8", max_heart_rate)]
    bytes_data = write_field(7, data_array, True, 0)
    output.write(bytes_data[0] + bytes_data[1])


def hr_zone(message_index=0, high_bpm=100):
    data_array = [(254, "uint16", message_index), (1, "uint8", high_bpm)]
    return write_field(8, data_array, True, 0)


def checksum(f):
    f.seek(0)
    bytes = f.read()
    crc_table = [0x0, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
                 0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]
    crc = 0
    count = 0
    for byte in bytes:
        count += 1
        tmp = crc_table[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ crc_table[byte & 0xF]
        tmp = crc_table[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ crc_table[(byte >> 4) & 0xF]
    f.write(struct.pack("=H", crc))
    return crc


def write_field(fid, spec, write_data=True, record_id=0):
    types = {"enum": (0x00, 1, "B"),
             "sint8": (0x01, 1, "b"),
             "uint8": (0x02, 1, "B"),
             "sint16": (0x83, 2, "h"),
             "uint16": (0x84, 2, "H"),
             "sint32": (0x85, 4, "l"),
             "uint32": (0x86, 4, "L"),
             "string": (0x07, -1, "s"),
             "float32": (0x88, 4, "f"),
             "float64": (0x89, 8, "d"),
             "uint8z": (0x0a, 1, "B"),
             "uint16z": (0x8b, 2, "S"),
             "uint32z": (0x8c, 4, "L"),
             "byte": (0x0d, -1, "s")}
    header = (record_id & 0x0f) | 0x40
    ret = struct.pack("=BBBHB", header, 0, 0, fid, len(spec))
    data = b""
    if write_data:
        data = struct.pack("=B", record_id)
    for elem in spec:
        size_flag, size, size_type = types[elem[
            1]]
        ret += struct.pack("=BBB", elem[0], size, size_flag)
        if write_data:
            data += struct.pack("=" + size_type, elem[2])
    return [ret, data]


def check_file_size(f):
    f.seek(0, 2)
    size = f.tell()
    f.seek(4, 0)
    f.write(struct.pack("=L", size - 14))
    return f


def export_file(f, filename):
    export = open(filename, "w+b")
    export.write(f.getbuffer())
    logger.info(">>> file exported to {}".format(filename))
    logger.info("finished")
