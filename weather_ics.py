#!/usr/bin/env python3
"""
Generate a weather forecast ICS file from Open-Meteo (no API key required).
Default: Shanghai 16-day forecast, all-day events.

Usage:
    python weather_ics.py                          # Shanghai -> shanghai_weather.ics
    python weather_ics.py --city beijing           # preset city
    python weather_ics.py --lat 1.35 --lon 103.82 --name "Singapore" --out sg.ics
"""
import argparse
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

# WMO weather codes -> (emoji, Chinese label)
WMO = {
    0:  ("☀️", "晴"),
    1:  ("🌤", "多云转晴"),
    2:  ("⛅️", "多云"),
    3:  ("☁️", "阴"),
    45: ("🌫", "雾"),
    48: ("🌫", "冻雾"),
    51: ("🌦", "毛毛雨"),
    53: ("🌦", "毛毛雨"),
    55: ("🌦", "毛毛雨"),
    56: ("🌧", "冻雨"),
    57: ("🌧", "冻雨"),
    61: ("🌧", "小雨"),
    63: ("🌧", "中雨"),
    65: ("🌧", "大雨"),
    66: ("🌧", "冻雨"),
    67: ("🌧", "冻雨"),
    71: ("🌨", "小雪"),
    73: ("🌨", "中雪"),
    75: ("❄️", "大雪"),
    77: ("🌨", "霰"),
    80: ("🌦", "阵雨"),
    81: ("🌧", "强阵雨"),
    82: ("⛈", "暴雨"),
    85: ("🌨", "阵雪"),
    86: ("❄️", "强阵雪"),
    95: ("⛈", "雷阵雨"),
    96: ("⛈", "雷雨冰雹"),
    99: ("⛈", "雷雨冰雹"),
}

PRESETS = {
    "shanghai":  (31.2304, 121.4737, "上海"),
    "beijing":   (39.9042, 116.4074, "北京"),
    "shenzhen":  (22.5431, 114.0579, "深圳"),
    "hangzhou":  (30.2741, 120.1551, "杭州"),
    "singapore": (1.3521,  103.8198, "新加坡"),
}


def fetch_forecast(lat: float, lon: float, days: int = 16) -> dict:
    qs = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join([
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "precipitation_probability_max",
            "wind_speed_10m_max",
            "sunrise",
            "sunset",
        ]),
        "timezone": "auto",
        "forecast_days": days,
    })
    url = f"https://api.open-meteo.com/v1/forecast?{qs}"
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read())


def escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")


def build_ics(data: dict, city_name: str) -> str:
    daily = data["daily"]
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//liutong//weather-ics//ZH",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape(city_name)}天气",
        f"X-WR-CALDESC:{escape(city_name)} 16天预报 · Open-Meteo",
        "X-WR-TIMEZONE:Asia/Shanghai",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]

    for i, date_str in enumerate(daily["time"]):
        code = daily["weather_code"][i]
        tmax = daily["temperature_2m_max"][i]
        tmin = daily["temperature_2m_min"][i]
        precip = daily["precipitation_sum"][i] or 0
        pop = daily["precipitation_probability_max"][i] or 0
        wind = daily["wind_speed_10m_max"][i] or 0
        sunrise = daily["sunrise"][i].split("T")[1]
        sunset = daily["sunset"][i].split("T")[1]

        emoji, label = WMO.get(code, ("", f"代码{code}"))
        ymd = date_str.replace("-", "")
        next_day = datetime.strptime(date_str, "%Y-%m-%d")
        next_ymd = (next_day.replace(day=next_day.day) ).strftime("%Y%m%d")
        # DTEND for all-day = day after start
        from datetime import timedelta
        dtend = (next_day + timedelta(days=1)).strftime("%Y%m%d")

        summary = f"{emoji} {label} {round(tmax)}°/{round(tmin)}°"
        if pop >= 30:
            summary += f" 🌧{int(pop)}%"

        desc_parts = [
            f"{label}",
            f"气温 {round(tmin)}°C ~ {round(tmax)}°C",
            f"降水概率 {int(pop)}%  累计 {precip:.1f}mm",
            f"最大风速 {wind:.1f} km/h",
            f"日出 {sunrise}  日落 {sunset}",
            "",
            "Data: Open-Meteo (CC BY 4.0)",
        ]
        desc = escape("\n".join(desc_parts))

        uid = f"weather-{city_name}-{ymd}@liutong.local"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{ymd}",
            f"DTEND;VALUE=DATE:{dtend}",
            f"SUMMARY:{escape(summary)}",
            f"DESCRIPTION:{desc}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    # ICS requires CRLF line endings
    return "\r\n".join(lines) + "\r\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", choices=PRESETS.keys(), default="shanghai")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--name", type=str)
    ap.add_argument("--days", type=int, default=16)
    ap.add_argument("--out", type=str)
    args = ap.parse_args()

    if args.lat is not None and args.lon is not None:
        lat, lon, name = args.lat, args.lon, (args.name or f"{args.lat},{args.lon}")
    else:
        lat, lon, name = PRESETS[args.city]
        if args.name:
            name = args.name

    out = args.out or f"{args.city if args.lat is None else 'custom'}_weather.ics"
    data = fetch_forecast(lat, lon, args.days)
    ics = build_ics(data, name)
    Path(out).write_text(ics, encoding="utf-8")
    print(f"Wrote {out}  ({len(data['daily']['time'])} days)")


if __name__ == "__main__":
    main()
