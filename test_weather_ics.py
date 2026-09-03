import io
import json
import unittest
import urllib.error
from contextlib import redirect_stderr
from unittest.mock import patch

from weather_ics import build_ics, fetch_cma_alerts, fetch_forecast, fold_ics_line, group_cma_alerts


FORECAST = {
    "daily": {
        "time": ["2026-08-23"],
        "weather_code": [1],
        "temperature_2m_max": [34.2],
        "temperature_2m_min": [27.1],
        "precipitation_sum": [2.4],
        "precipitation_probability_max": [45],
        "wind_speed_10m_max": [18.5],
        "sunrise": ["2026-08-23T05:25"],
        "sunset": ["2026-08-23T18:27"],
    }
}

ALERTS = [
    {
        "id": "31019941600000_20260823100000",
        "headline": "上海市气象台发布中心城区大风蓝色预警[Ⅳ级/一般]",
        "effective": "2026/08/23 10:00",
        "description": "预计未来24小时内中心城区将出现大风。",
        "type": "p0007004",
        "title": "发布大风蓝色预警",
    },
    {
        "id": "31011541600000_20260823103000",
        "headline": "浦东新区气象台发布大风黄色预警[Ⅲ级/较重]",
        "effective": "2026/08/23 10:30",
        "description": "预计未来12小时内浦东新区将出现大风。",
        "type": "p0007003",
        "title": "上海市浦东新区发布大风黄色预警",
    },
]


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.payload


class WeatherIcsTests(unittest.TestCase):
    @patch("time.sleep")
    @patch("weather_ics.urllib.request.urlopen")
    def test_forecast_retries_http_500_then_succeeds(self, urlopen, sleep):
        urlopen.side_effect = [
            urllib.error.HTTPError("https://example.test", 500, "Internal Server Error", {}, None),
            FakeResponse(json.dumps(FORECAST).encode()),
        ]

        with redirect_stderr(io.StringIO()):
            result = fetch_forecast(31.2304, 121.4737)

        self.assertEqual(result, FORECAST)
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(2)

    @patch("time.sleep")
    @patch("weather_ics.urllib.request.urlopen")
    def test_forecast_retries_invalid_json_then_succeeds(self, urlopen, sleep):
        urlopen.side_effect = [
            FakeResponse(b""),
            FakeResponse(json.dumps(FORECAST).encode()),
        ]

        with redirect_stderr(io.StringIO()):
            result = fetch_forecast(31.2304, 121.4737)

        self.assertEqual(result, FORECAST)
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(2)

    @patch("time.sleep")
    @patch("weather_ics.urllib.request.urlopen")
    def test_forecast_retries_structurally_invalid_payload(self, urlopen, sleep):
        urlopen.side_effect = [
            FakeResponse(b"{}"),
            FakeResponse(json.dumps(FORECAST).encode()),
        ]

        with redirect_stderr(io.StringIO()):
            result = fetch_forecast(31.2304, 121.4737)

        self.assertEqual(result, FORECAST)
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(2)

    @patch("time.sleep")
    @patch("weather_ics.urllib.request.urlopen")
    def test_forecast_does_not_retry_http_400(self, urlopen, sleep):
        urlopen.side_effect = urllib.error.HTTPError(
            "https://example.test", 400, "Bad Request", {}, None
        )

        with self.assertRaises(urllib.error.HTTPError):
            fetch_forecast(31.2304, 121.4737)

        self.assertEqual(urlopen.call_count, 1)
        sleep.assert_not_called()

    @patch("time.sleep")
    @patch("weather_ics.urllib.request.urlopen")
    def test_forecast_raises_after_four_timeouts(self, urlopen, sleep):
        urlopen.side_effect = TimeoutError("timed out")

        with redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "Open-Meteo unavailable after 4 attempts"):
                fetch_forecast(31.2304, 121.4737)

        self.assertEqual(urlopen.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4, 8])

    @patch("time.sleep")
    @patch("weather_ics.urllib.request.urlopen")
    def test_cma_retries_network_error_then_succeeds(self, urlopen, sleep):
        payload = {"code": 0, "data": ALERTS}
        urlopen.side_effect = [
            urllib.error.URLError("network unreachable"),
            FakeResponse(json.dumps(payload).encode()),
        ]

        with redirect_stderr(io.StringIO()):
            result = fetch_cma_alerts("31")

        self.assertEqual(result, ALERTS)
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(2)

    def test_groups_district_alerts_and_keeps_strongest_level(self):
        grouped = group_cma_alerts(ALERTS)

        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["signal"], "大风")
        self.assertEqual(grouped[0]["level"], "黄色")
        self.assertEqual(grouped[0]["count"], 2)
        self.assertEqual(grouped[0]["primary"]["id"], ALERTS[1]["id"])
        self.assertEqual(grouped[0]["areas"], ["中心城区", "浦东新区"])

    def test_builds_one_timed_alert_event_with_official_link(self):
        ics = build_ics(FORECAST, "上海", ALERTS)

        self.assertEqual(ics.count("BEGIN:VEVENT"), 2)
        self.assertIn("SUMMARY:🟡 上海大风黄色预警", ics.replace("\r\n ", ""))
        self.assertIn("DTSTART;TZID=Asia/Shanghai:20260823T100000", ics)
        self.assertIn("DTEND;TZID=Asia/Shanghai:20260824T100000", ics)
        self.assertIn("https://weather.cma.cn/web/alarm/31011541600000_20260823103000.html", ics.replace("\r\n ", ""))

    def test_utf8_content_lines_are_folded_to_75_octets(self):
        folded = fold_ics_line("DESCRIPTION:" + "上海气象预警" * 20)

        self.assertGreater(len(folded), 1)
        self.assertTrue(all(len(line.encode("utf-8")) <= 75 for line in folded))
        self.assertTrue(all(line.startswith(" ") for line in folded[1:]))


if __name__ == "__main__":
    unittest.main()
