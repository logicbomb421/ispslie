import os, sys, socket, time, json, timeit
from functools import lru_cache
from datetime import datetime
import requests
from speedtest import Speedtest, SpeedtestResults
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import PointSettings

ENV_VAR_PREFIX = "ISPSLIE"


@lru_cache
def _get_config_value(key: str, default=None):
    if not key:
        raise RuntimeError("Unidentified config value!")
    return os.getenv(f"{ENV_VAR_PREFIX}_{key.upper()}", default)


DEFAULT_WRITE_PRECEISION = _get_config_value("write_precision", WritePrecision.S)
SERVER_JSON_PATH = _get_config_value("speedtest_server", None)


def log(msg, **kwargs):
    print(f"{datetime.now().isoformat(): <26} | {msg}", **kwargs)
    sys.stdout.flush()


def _print_dots(current, total, start=False, end=False):
    sys.stdout.write(".")
    if current + 1 == total and end is True:
        sys.stdout.write("\n")
    sys.stdout.flush()


def _monkeypatch_servers(file_path: str, client: Speedtest):
    """
    Monkeypatch for server list inconsistency issue.

    Since the server list seems to be inconsistent, and the get_servers implementation does
    not seem to account for this even when passing in a server ID, we need to save the server
    we actually want to use as JSON and load it at runtime.

    ref: https://github.com/sivel/speedtest-cli/pull/763 <-- maintainer refused similar feature but hasn't fixed underlying issue...
    """
    with open(file_path, "r") as fd:
        # force best server
        client._best = json.load(fd)
    # include override in servers dict
    client.servers[client._best["d"]] = [client._best]
    # set result server (originally set at the end of get_servers)
    client.results.server = client._best
    # manually check latency here (simple approach - best effort, no crash)
    res = requests.get(f"{client._best['url']}/latency.txt?x={int(timeit.time.time() * 1000)}")
    if res.status_code == 200 and res.text == "test=test\n":
        client.results.ping = float(round(res.elapsed.microseconds / 1000, 2))


def perform_speedtest() -> SpeedtestResults:
    log("Performing speedtest")
    client = Speedtest(secure=True)
    server_json_path = _get_config_value("speedtest_server", None)
    if server_json_path:
        log(f"Using server specified in: {server_json_path}")
        _monkeypatch_servers(server_json_path, client)
    log("Testing download speed", end="")
    # FYI: single connection to simulate an average file transfer
    client.download(threads=_get_config_value("speedtest_threads", 1), callback=_print_dots)
    log("Testing upload speed", end="")
    client.upload(threads=_get_config_value("speedtest_threads", 1), callback=_print_dots)
    return client.results


# {"url": "http://speedtest.rd.oc.cox.net:8080/speedtest/upload.php", "lat": "33.6402", "lon": "-117.6028", "name": "Orange County, CA", "country": "United States", "cc": "US", "sponsor": "Cox - Orange County", "id": "16620", "host": "speedtest.rd.oc.cox.net:8080", "d": 119.68037789752829, "latency": 23.742}
# '{"url": "http://us.speed.twnoc.net:8080/speedtest/upload.php", "lat": "33.6842", "lon": "-117.7925", "name": "Irvine, CA", "country": "United States", "cc": "US", "sponsor": "Yuan-Jhen Info", "id": "54705", "host": "us.speed.twnoc.net:8080", "d": 135.3814200501346, "latency": 23.12}'
# '{"url": "http://sp2.janusnetworks.com:8080/speedtest/upload.php", "lat": "32.7153", "lon": "-117.1564", "name": "San Diego, CA", "country": "United States", "cc": "US", "sponsor": "Janus Networks", "id": "29471", "host": "sp2.janusnetworks.com:8080", "d": 40.1714695092494, "latency": 21.895}'

# SERVERS
# 16615 - San Diego, CA, Cox - San Diego
# 29471 - San Diego, CA, Janus Networks, 40.1714695092494

# RETURN OBJECT SCHEMA
# {
#     "download": 61874645.64676421,
#     "upload": 11433801.08981982,
#     "ping": 77.068,
#     "server": {
#         "url": "http://speedtest1.epbfi.com:8080/speedtest/upload.php",
#         "lat": "35.0456",
#         "lon": "-85.3097",
#         "name": "Chattanooga, TN",
#         "country": "United States",
#         "cc": "US",
#         "sponsor": "EPB Fiber Optics",
#         "id": "3965",
#         "host": "speedtest1.epbfi.com:8080",
#         "d": 2898.873387528197,
#         "latency": 77.068,
#     },
#     "timestamp": "2023-02-15T23:26:52.742114Z",
#     "bytes_sent": 14663680,
#     "bytes_received": 77764561,
#     "share": null,
#     "client": {
#         "ip": "72.199.196.20",
#         "lat": "32.8338",
#         "lon": "-116.7505",
#         "isp": "Cox Communications",
#         "isprating": "3.7",
#         "rating": "0",
#         "ispdlavg": "0",
#         "ispulavg": "0",
#         "loggedin": "0",
#         "country": "US",
#     },
# }


def results_to_points(results: SpeedtestResults) -> ([Point], PointSettings):
    log("Parsing results")
    points = []
    settings = PointSettings()
    settings.add_default_tag("server_id", results.server["id"])
    settings.add_default_tag("server_name", results.server["name"])
    settings.add_default_tag("server_sponsor", results.server["sponsor"])
    settings.add_default_tag("server_country", results.server["country"])
    settings.add_default_tag("isp_name", results.client["isp"])
    settings.add_default_tag("isp_addr", results.client["ip"])
    settings.add_default_tag("hostname", socket.gethostname())
    points.append(
        Point("download")
        .field("bytes_received", results.bytes_received)
        .field("bps", float(round(results.download, 2)))
        .time(results.timestamp, write_precision=DEFAULT_WRITE_PRECEISION)
    )
    points.append(
        Point("upload")
        .field("bytes_sent", results.bytes_sent)
        .field("bps", float(round(results.upload, 2)))
        .time(results.timestamp, write_precision=DEFAULT_WRITE_PRECEISION)
    )
    points.append(
        Point("ping")
        .field("ms", float(round(results.ping, 2)))
        .time(results.timestamp, write_precision=DEFAULT_WRITE_PRECEISION)
    )
    return points, settings


def write_points(client, parsed: ([Point], PointSettings)):
    log("Committing results to database")
    database = "internet_speed"
    points, settings = parsed
    with client.write_api(point_settings=settings) as writer:
        writer.write(
            bucket=_get_config_value("influxdb_database", "wan_speed"),
            org=_get_config_value("influxdb_retention_policy", "autogen"),
            record=points,
        )


def main():
    try:
        # FYI: batching client needs to be a singleton
        with InfluxDBClient(url=_get_config_value("influxdb_uri", "http://localhost:8086")) as client:
            while True:
                results = perform_speedtest()
                parsed = results_to_points(results)
                write_points(client, parsed)
                secs = int(_get_config_value("collection_interval", 5 * 60))
                log(f"Run complete. Next run in {secs} second(s)")
                time.sleep(secs)
    except KeyboardInterrupt:
        sys.exit()
    except Exception as ex:
        log("FATAL: ", end="")
        log(ex)
        sys.exit(1)


if __name__ == "__main__":
    main()
