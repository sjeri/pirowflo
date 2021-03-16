'''
uses https://github.com/cyberjunky/python-garminconnect as pip module
and is based on the sample code from the same site. Their copyrights apply.
extended with upload functionality as the module only supports getters not setters.
'''

import os.path
import time
from datetime import date, timedelta

today = date.today()
import logging
logger = logging.getLogger(__name__)

from garminconnect import (
    Garmin,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
    GarminConnectAuthenticationError,
)
import requests


def handle_gc_exceptions(func):
    def executor(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (
                GarminConnectConnectionError, GarminConnectAuthenticationError,
                GarminConnectTooManyRequestsError) as err:
            logger.info(f"{func.__name__}: Error occurred during Garmin Connect Client init: %s" % err)
            raise err

    return executor


class ActivityUploader:
    def __init__(self):
        self.client = None

    @handle_gc_exceptions
    def login(self, email, password):
        logger.info(f"GC login called")
        self.client = Garmin(email, password)
        self.client.login()
        self.client.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36',
            'origin': 'https://sso.garmin.com',
            'NK': 'NT'
        }
        logger.info(f"GC login done")

    @handle_gc_exceptions
    def get_user(self):
        """
        Get full name from profile
        """
        logger.info(f"GC get user")
        return self.client.get_full_name()

    @handle_gc_exceptions
    def get_stats(self):
        """
        Get stats and body composition data
        """
        logger.info(f"GC get stats for {today.isoformat()}")
        return self.client.get_stats(today.isoformat())

    @handle_gc_exceptions
    def get_body_composition(self):
        """
        Get stats and body composition data
        """
        logger.info(f"GC get body composition for range {today.isoformat()} - 30 days")
        sdate = today - timedelta(30)
        return self.client.get_body_composition30d(sdate.isoformat(), today.isoformat())

    @handle_gc_exceptions
    def get_userinfo(self):
        """
        Get userInfo and biometricProfile
        """
        logger.info(f"GC get userInfo and biometricProfile")
        userinfo = self.client.get_userInfo()
        return {**userinfo.get('userInfo'), **userinfo.get('biometricProfile')}

    @handle_gc_exceptions
    def upload_activity(self, activityname, filename):
        """
        upload activity
        """
        activity_id, uploaded = self.client.upload_activity(filename)
        if uploaded:
            return self.client.set_activity_name(activity_id, activityname)
        else:
            logger.info("File already present")


def extend_class(cls):
    return lambda f: (setattr(cls, f.__name__, f) or f)


@extend_class(Garmin)
def post_data(self, url, **args):
    """
    Post data
    """
    retrycnt = 0
    resp_json = None
    while retrycnt < 2:
        try:
            response = self.req.post(url, **args)
            self.logger.info(f"GC response code: {response.status_code}")
            if response.status_code != 204:
                self.logger.info(f"GC message: {response.text}")
            if response.status_code == 429:
                raise GarminConnectTooManyRequestsError("Too many requests")
            if response.status_code not in (200, 201, 204, 409):
                if response.status_code == 412:
                    self.logger.info('You may have to give explicit consent for uploading files to Garmin')
                raise GarminConnectConnectionError('Failed to post to GC')
            self.logger.info("Fetch response code %s", response.status_code)
            response.raise_for_status()
            if response.status_code != 204:
                resp_json = response.json()
            break
        except requests.exceptions.HTTPError or GarminConnectConnectionError as err:
            retrycnt = retrycnt + 1
            if retrycnt < 2:
                self.logger.info(
                    "Exception occurred during data transfer - perhaps session expired - trying relogin: %s" % err)
                self.login()
                continue
            self.logger.info(
                "Exception occurred during data transfer, relogin without effect: %s" % err)
            raise GarminConnectConnectionError("Error connecting") from err
    self.logger.info("Fetch response json %s", resp_json)
    return resp_json


@extend_class(Garmin)
def upload_activity(self, path):
    """
    Upload an activity to Garmin
    """
    files = {
        "file": (os.path.basename(path), open(path, 'rb')),
    }
    url = 'https://connect.garmin.com/modern/proxy/upload-service/upload/.fit'
    res = self.post_data(url, files=files, headers=self.headers)
    response = res['detailedImportResult']
    if len(response["successes"]) == 0:
        if len(response["failures"]) == 0:
            raise GarminConnectConnectionError('Unknown error: {}'.format(response))
        if response["failures"][0]["messages"][0]['code'] not in (202):
            raise GarminConnectConnectionError(response["failures"][0]["messages"])
        return response["failures"][0]["internalId"], False  # no upload because present
    return response["successes"][0]["internalId"], True  # uploaded


@extend_class(Garmin)
def set_activity_name(self, activity_id, activity_name):
    """
    Update the activity name
    """
    URL_ACTIVITY_BASE = 'https://connect.garmin.com/modern/proxy/activity-service/activity'
    url = '{}/{}'.format(URL_ACTIVITY_BASE, activity_id)
    data = {'activityId': activity_id, 'activityName': activity_name}
    headers = self.headers.copy()
    headers['X-HTTP-Method-Override'] = 'PUT'
    return self.post_data(url, json=data, headers=headers)


@extend_class(Garmin)
def get_body_composition30d(self, sdate, edate):  # cDate = 'YYYY-mm-dd'
    """
    Fetch available body composition data for specified range
    """
    bodycompositionurl = self.url_body_composition + \
                         '?startDate=' + sdate + '&endDate=' + edate
    self.logger.info("Fetching body composition with url %s", bodycompositionurl)
    return self.fetch_data(bodycompositionurl)


@extend_class(Garmin)
def get_userInfo(self):
    """
    Fetch user info
    """
    userinfourl = "https://connect.garmin.com/modern/proxy/userprofile-service/userprofile/personal-information/" \
                  + self.display_name + '?_=' + str(round(time.time() * 1000))
    self.logger.info("Fetching userInfo with url %s", userinfourl)
    return self.fetch_data(userinfourl)
