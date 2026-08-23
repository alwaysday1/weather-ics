import unittest

from weather_ics import build_ics, fold_ics_line, group_cma_alerts


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


class WeatherIcsTests(unittest.TestCase):
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
