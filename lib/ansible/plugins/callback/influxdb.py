# Copyright: (c) 2018, Johannes Brunswicker <johannes.brunswicker@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = '''
    callback: influxdb
    type: notification
    requirements:
      - "python >= 2.6"
      - "influxdb >= 0.9"
    short_description: create influxdb datapoint per play and host
    author:
      - Johannes Brunswicker (@MatrixCrawler)
    version_added: "2.8"
    options:
      influx_host:
        description: The hostname of the influxDB.
        required: True
        env:
          - name: INFLUX_HOST
        ini:
          - section: callback_influxdb
            key: influx_host
      influx_port:
        description: The port of the influxDB.
        required: False
        type: int
        default: 8086
        env:
          - name: INFLUX_PORT
        ini:
          - section: callback_influxdb
            key: influx_port
      influx_database:
        description: The database name in the influxDB in which the measurement shall be stored. Has to exist.
        required: True
        env:
          - name: INFLUX_DATABASE
        ini:
          - section: callback_influxdb
            key: influx_database
      influx_username:
        description: The username for the influxDB.
        required: True
        env:
          - name: INFLUX_USERNAME
        ini:
          - section: callback_influxdb
            key: influx_username
      influx_password:
        description: The password for the influxDB.
        required: True
        env:
          - name: INFLUX_PASSWORD
        ini:
          - section: callback_influxdb
            key: influx_password
      influx_use_ssl:
        description: Whether to use SSL or not.
        required: False
        type: bool
        default: False
        env:
          - name: INFLUX_USE_SSL
        ini:
          - section: callback_influxdb
            key: influx_use_ssl
      influx_verify_ssl:
        description: Whether to verify the SSL Certificate or not.
        required: False
        type: bool
        default: True
        env:
          - name: INFLUX_VERIFY_SSL
        ini:
          - section: callback_influxdb
            key: influx_verify_ssl
      influx_timeout:
        description: The timeout for the influxDB connection in seconds.
        required: False
        type: int
        default: 5
        env:
          - name: INFLUX_TIMEOUT
        ini:
          - section: callback_influxdb
            key: influx_timeout
      influx_retries:
        description: The retries for the influxDB action.
        required: False
        type: int
        default: 3
        env:
          - name: INFLUX_RETRIES
        ini:
          - section: callback_influxdb
            key: influx_retries
      influx_measurement_name:
        description: The name for the measurement stored into influxDB.
        required: False
        type: str
        default: ansible_plays
        env:
          - name: INFLUX_MEASUREMENT_NAME
        ini:
          - section: callback_influxdb
            key: influx_measurement_name

'''

import time
from datetime import datetime

from ansible.plugins.callback import CallbackBase

try:
    from influxdb import InfluxDBClient
    from influxdb import __version__ as influxdb_version
    from influxdb import exceptions

    HAS_INFLUXDB = True
except ImportError:
    HAS_INFLUXDB = False


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'aggregate'
    CALLBACK_NAME = 'influxdb'
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self, display=None, options=None):
        super(CallbackModule, self).__init__(display=display, options=options)
        if not HAS_INFLUXDB:
            self._display.warning("The required python influxdb library (influxdb) is not installed. "
                                  "pip install influxdb")
            self.disabled = True

        self.play = ""
        self.start_time = {}
        self.all_end_times = {}
        self.influx = {}

    def _connect_to_influxdb(self):
        """
        This will connect to influxDB
        :return: InfluxDBClient
        """
        args = dict(
            host=self.influx["host"],
            port=self.influx["port"],
            username=self.influx["username"],
            password=self.influx["password"],
            database=self.influx["database"],
            ssl=self.influx["ssl"],
            verify_ssl=self.influx["verify_ssl"],
            timeout=self.influx["timeout"],
        )
        influxdb_api_version = tuple(influxdb_version.split("."))
        if influxdb_api_version >= ('4', '1', '0'):
            # retries option is added in version 4.1.0
            args.update(retries=self.influx["retries"])

        return InfluxDBClient(**args)

    def set_options(self, task_keys=None, var_options=None, direct=None):
        super(CallbackModule, self).set_options(task_keys, var_options, direct)
        self.influx["host"] = self.get_option('influx_host')
        self.influx["port"] = self.get_option('influx_port') or 8086
        self.influx["database"] = self.get_option('influx_database')
        self.influx["username"] = self.get_option('influx_username')
        self.influx["password"] = self.get_option('influx_password')
        self.influx["ssl"] = self.get_option('influx_use_ssl') or False
        self.influx["verify_ssl"] = self.get_option('influx_verify_ssl') or True
        self.influx["timeout"] = self.get_option('influx_timeout') or 5
        self.influx["retries"] = self.get_option('influx_retries') or 3
        self.influx["measurement"] = self.get_option('influx_measurement_name') or "ansible_plays"

        if self.influx["host"] is None:
            self._display.warning(
                "No Influx Host provided. Can be provided with the `INFLUX_HOST` environment variable or in the ini")
            self.disabled = True

        if self.influx["database"] is None:
            self._display.warning(
                "No Influx database provided. Can be provided with the `INFLUX_DATABASE` environment variable"
                " or in the ini")
            self.disabled = True

        self._display.info("Influx Host: %s", self.influx["host"])

    def v2_playbook_on_play_start(self, play):
        self.play = play.name
        self.start_time[self.play] = self.time_in_milliseconds()
        self.all_end_times[self.play] = {}

    def v2_playbook_on_stats(self, stats):
        influxdb = self.connect_to_influxdb()
        data_points = []
        for play, play_results in self.all_end_times.items():
            for host, host_data_point in play_results.items():
                duration = host_data_point["end_time"] - self.start_time[play]
                self._display.display("duration for '" + host + "': " + str(duration))
                data_point = dict(
                    measurement=self.influx["measurement"],
                    tags=dict(
                        host=host,
                        play=play
                    ),
                    time=str(datetime.utcnow()),
                    fields=dict(
                        duration=duration,
                        state=host_data_point["state"]
                    )
                )
                data_points.append(data_point)
        influxdb.write_points(data_points)
        influxdb.close()

    @staticmethod
    def time_in_milliseconds():
        return int(round(time.time() * 1000))

    def _create_data_point(self, hostname, state="ok"):
        data_point = dict(
            end_time=self.time_in_milliseconds(),
            state=state
        )
        self.all_end_times[self.play][str(hostname)] = data_point

    def v2_runner_on_ok(self, result):
        self._create_data_point(result._host, "ok")

    def v2_runner_on_async_failed(self, result):
        self._create_data_point(result._host, "failed")
        # self.all_end_times[self.play][str(result._host)] = self.time_in_milliseconds()

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self._create_data_point(result._host, "failed")
        # self.all_end_times[self.play][str(result._host)] = self.time_in_milliseconds()

    def v2_runner_on_skipped(self, result):
        self._create_data_point(result._host, "ok")
        # self.all_end_times[self.play][str(result._host)] = self.time_in_milliseconds()

    def v2_runner_on_unreachable(self, result):
        self._create_data_point(result._host, "unreachable")
        # self.all_end_times[self.play][str(result._host)] = self.time_in_milliseconds()

    # def v2_runner_on_async_poll(self, result):
    #     self.all_end_times[self.play][str(result._host)] = self.time_in_milliseconds()

    def v2_runner_on_async_ok(self, result):
        self._create_data_point(result._host, "ok")
        # self.all_end_times[self.play][str(result._host)] = self.time_in_milliseconds()
