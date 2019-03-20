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

CALLBACK_VERSION = 2.0
CALLBACK_TYPE = 'aggregate'
CALLBACK_NAME = 'influxdb'
CALLBACK_NEEDS_WHITELIST = True


class CallbackModule(CallbackBase):
    def __init__(self, display=None, options=None):
        super(CallbackModule, self).__init__(display=None, options=None)
        self.play = ""
        self.start_time = {}
        self.all_end_times = {}
        self.influx = {}

    def _connect_to_influxdb(self):
        args = dict(
            host="icinga-master-dev-eu-central-1.intern.hosting",
            port=8086,
            username="root",
            password="root",
            database="ansible",
            ssl=False,
            verify_ssl=True,
            timeout=5,
            use_udp=False,
            proxies={},
        )
        influxdb_api_version = tuple(influxdb_version.split("."))
        if influxdb_api_version >= ('4', '1', '0'):
            # retries option is added in version 4.1.0
            args.update(retries=3)

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
        self.influx["use_udp"] = self.get_option('influx_use_upd') or False
        self.influx["retries"] = self.get_option('influx_retries') or 3
        self.influx["measurement"] = self.get_option('influx_measurement_name') or "ansible_plays"
        if self.influx["host"] is None:
            self._display.warning(
                "No Influx Host provided. Can be provided with the `INFLUX_HOST` environment variable or in the ini")
        if self.influx["database"] is None:
            self._display.warning(
                "No Influx database provided. Can be provided with the `INFLUX_DATABASE` environment variable"
                " or in the ini")
        self._display.info("Influx Host: %s", self.influx["host"])

    def v2_playbook_on_play_start(self, play):
        self.play = play.name
        self.start_time[self.play] = self.time_in_milliseconds()
        self.all_end_times[self.play] = {}

    def v2_playbook_on_stats(self, stats):
        influxdb = self.connect_to_influxdb()
        data_points = []
        for play, play_results in self.all_end_times.items():
            for host, host_end_time in play_results.items():
                duration = host_end_time - self.start_time[play]
                self._display.display("duration for '" + host + "': " + str(duration))
                data_point = dict(
                    measurement="ansible_plays",
                    tags=dict(
                        host=host,
                        play=play
                    ),
                    time=str(datetime.utcnow()),
                    fields=dict(
                        duration=duration
                    )
                )
                data_points.append(data_point)
        influxdb.write_points(data_points)
        influxdb.close()

    @staticmethod
    def time_in_milliseconds():
        return int(round(time.time() * 1000))

    def v2_runner_on_ok(self, result):
        self.all_end_times[self.play][str(result._host)] = self.time_in_milliseconds()

    def v2_runner_on_async_failed(self, result):
        self.all_end_times[self.play][str(result._host)] = self.time_in_milliseconds()

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self.all_end_times[self.play][str(result._host)] = self.time_in_milliseconds()

    def v2_runner_on_skipped(self, result):
        self.all_end_times[self.play][str(result._host)] = self.time_in_milliseconds()

    def v2_runner_on_unreachable(self, result):
        self.all_end_times[self.play][str(result._host)] = self.time_in_milliseconds()

    def v2_runner_on_async_poll(self, result):
        self.all_end_times[self.play][str(result._host)] = self.time_in_milliseconds()

    def v2_runner_on_async_ok(self, result):
        self.all_end_times[self.play][str(result._host)] = self.time_in_milliseconds()
