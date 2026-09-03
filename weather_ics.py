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
import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
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

# Province-level administrative code used by weather.cma.cn's public warning
# feed.  Only Shanghai is enabled by default because this project currently
# has no reliable coordinate-to-adcode lookup.
CMA_ADCODE = {
    "shanghai": "31",
}

CMA_ALARM_URL = "https://weather.cma.cn/api/map/alarm"
CMA_ALARM_DETAIL_URL = "https://weather.cma.cn/web/alarm/{alert_id}.html"
ALERT_LEVEL = {
    "1": ("红色", 4, "🚨"),
    "2": ("橙色", 3, "🟠"),
    "3": ("黄色", 2, "🟡"),
    "4": ("蓝色", 1, "🔵"),
}

HTTP_TIMEOUT_SECONDS = 20
RETRY_DELAYS_SECONDS = (2, 4, 8)


def _fetch_json(request, source: str, validate) -> dict:
    attempts = len(RETRY_DELAYS_SECONDS) + 1
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read())
            if not validate(payload):
                raise ValueError(f"{source} returned an invalid response")
            return payload
        except urllib.error.HTTPError as exc:
            if exc.code != 429 and not 500 <= exc.code <= 599:
                raise
            last_error = exc
        except (TimeoutError, urllib.error.URLError, http.client.HTTPException, ValueError) as exc:
            last_error = exc

        if attempt < attempts:
            delay = RETRY_DELAYS_SECONDS[attempt - 1]
            print(
                f"Warning: {source} request attempt {attempt}/{attempts} failed: "
                f"{last_error}; retrying in {delay}s",
                file=sys.stderr,
            )
            time.sleep(delay)

    raise RuntimeError(f"{source} unavailable after {attempts} attempts") from last_error


def _valid_forecast_payload(payload: dict) -> bool:
    if not isinstance(payload, dict) or not isinstance(payload.get("daily"), dict):
        return False

    daily = payload["daily"]
    fields = (
        "time",
        "weather_code",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "precipitation_probability_max",
        "wind_speed_10m_max",
        "sunrise",
        "sunset",
    )
    days = daily.get("time")
    return (
        isinstance(days, list)
        and len(days) > 0
        and all(isinstance(daily.get(field), list) and len(daily[field]) == len(days) for field in fields)
    )


def _valid_cma_payload(payload: dict) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("code") == 0
        and isinstance(payload.get("data"), list)
    )


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
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "weather-ics/1.0 (+https://github.com/alwaysday1/weather-ics)",
        },
    )
    return _fetch_json(request, "Open-Meteo", _valid_forecast_payload)


def fetch_cma_alerts(adcode: str) -> list[dict]:
    """Fetch current official weather warnings for a province-level adcode."""
    qs = urllib.parse.urlencode({"adcode": adcode})
    request = urllib.request.Request(
        f"{CMA_ALARM_URL}?{qs}",
        headers={
            "Accept": "application/json",
            "User-Agent": "weather-ics/1.0 (+https://github.com/alwaysday1/weather-ics)",
        },
    )
    payload = _fetch_json(request, "CMA", _valid_cma_payload)
    return payload["data"]


def escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")


def fold_ics_line(line: str, limit: int = 75) -> list[str]:
    """Fold an ICS content line without splitting UTF-8 characters."""
    folded = []
    current = ""
    content_limit = limit
    prefix = ""
    for char in line:
        if current and len((current + char).encode("utf-8")) > content_limit:
            folded.append(prefix + current)
            current = char
            prefix = " "
            content_limit = limit - 1
        else:
            current += char
    folded.append(prefix + current)
    return folded


def _alert_effective(alert: dict) -> datetime:
    return datetime.strptime(alert["effective"], "%Y/%m/%d %H:%M")


def _alert_type_key(alert: dict) -> str:
    type_code = str(alert.get("type") or "")
    if len(type_code) > 1 and type_code[-1] in ALERT_LEVEL:
        return type_code[:-1]
    headline = str(alert.get("headline") or alert.get("title") or "天气预警")
    return re.sub(r"(?:红色|橙色|黄色|蓝色)?预警.*$", "", headline)


def _alert_signal(alert: dict) -> str:
    text = str(alert.get("headline") or alert.get("title") or "天气预警")
    match = re.search(r"发布(?:中心城区)?(.+?)(?:红色|橙色|黄色|蓝色)预警", text)
    return match.group(1) if match else "天气"


def _alert_level(alert: dict) -> tuple[str, int, str]:
    type_code = str(alert.get("type") or "")
    if type_code and type_code[-1] in ALERT_LEVEL:
        return ALERT_LEVEL[type_code[-1]]
    text = str(alert.get("headline") or alert.get("title") or "")
    for level, rank, emoji in ALERT_LEVEL.values():
        if level in text:
            return level, rank, emoji
    return "", 0, "⚠️"


def _alert_area(alert: dict) -> str:
    title = str(alert.get("title") or "")
    match = re.search(r"上海市(.+?)发布", title)
    if match:
        return match.group(1)
    headline = str(alert.get("headline") or "")
    if "中心城区" in headline:
        return "中心城区"
    match = re.match(r"(.+?)气象台", headline)
    return match.group(1) if match else "上海市"


def _alert_duration_hours(alert: dict) -> int:
    """Infer display length from official wording; CMA does not expose expiry."""
    description = str(alert.get("description") or "")
    matches = [int(value) for value in re.findall(r"(?:未来)?(\d+)小时内", description)]
    return max(matches, default=24)


def group_cma_alerts(alerts: list[dict]) -> list[dict]:
    """Merge city/district copies of the same warning into one calendar event."""
    grouped = defaultdict(list)
    for alert in alerts:
        try:
            effective = _alert_effective(alert)
        except (KeyError, TypeError, ValueError):
            continue
        grouped[(_alert_type_key(alert), effective.date())].append(alert)

    result = []
    for (type_key, issue_date), items in grouped.items():
        items.sort(key=_alert_effective)
        strongest = max(items, key=lambda item: _alert_level(item)[1])
        level, rank, emoji = _alert_level(strongest)
        primary = next(
            (
                item
                for item in items
                if _alert_level(item)[1] == rank
                and (
                    str(item.get("id", "")).startswith("310199")
                    or str(item.get("headline", "")).startswith(("上海市气象台", "上海中心气象台"))
                )
            ),
            strongest,
        )
        start = min(_alert_effective(item) for item in items)
        end = max(
            _alert_effective(item) + timedelta(hours=_alert_duration_hours(item))
            for item in items
        )
        areas = sorted({_alert_area(item) for item in items})
        result.append(
            {
                "uid_key": f"{type_key}-{issue_date:%Y%m%d}",
                "signal": _alert_signal(strongest),
                "level": level,
                "rank": rank,
                "emoji": emoji,
                "start": start,
                "end": end,
                "areas": areas,
                "primary": primary,
                "count": len(items),
            }
        )
    return sorted(result, key=lambda item: (item["start"], -item["rank"]))


def build_ics(data: dict, city_name: str, alerts: list[dict] | None = None) -> str:
    daily = data["daily"]
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//liutong//weather-ics//ZH",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape(city_name)}天气",
        f"X-WR-CALDESC:{escape(city_name)} {len(daily['time'])}天预报 · Open-Meteo",
        "X-WR-TIMEZONE:Asia/Shanghai",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]

    for i, date_str in enumerate(daily["time"]):
        code = daily["weather_code"][i]
        tmax = daily["temperature_2m_max"][i]
        tmin = daily["temperature_2m_min"][i]
        # Open-Meteo may return null for the tail days of the 16-day horizon;
        # skip any day missing essential fields rather than crashing on round(None).
        if code is None or tmax is None or tmin is None:
            continue
        precip = daily["precipitation_sum"][i] or 0
        pop = daily["precipitation_probability_max"][i] or 0
        wind = daily["wind_speed_10m_max"][i] or 0
        sunrise = (daily["sunrise"][i] or "T").split("T")[1]
        sunset = (daily["sunset"][i] or "T").split("T")[1]

        emoji, label = WMO.get(code, ("", f"代码{code}"))
        ymd = date_str.replace("-", "")
        next_day = datetime.strptime(date_str, "%Y-%m-%d")
        # DTEND for all-day = day after start
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
            f"LAST-MODIFIED:{now}",
            f"DTSTART;VALUE=DATE:{ymd}",
            f"DTEND;VALUE=DATE:{dtend}",
            f"SUMMARY:{escape(summary)}",
            f"DESCRIPTION:{desc}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]

    for alert in group_cma_alerts(alerts or []):
        primary = alert["primary"]
        official_url = CMA_ALARM_DETAIL_URL.format(alert_id=primary.get("id", ""))
        areas = "、".join(alert["areas"])
        summary = f"{alert['emoji']} 上海{alert['signal']}{alert['level']}预警"
        desc_parts = [
            str(primary.get("headline") or summary),
            str(primary.get("description") or ""),
            "",
            f"覆盖：{areas}",
            f"同类预警合并：{alert['count']} 条（市级/区级）",
            "日历结束时间按预警原文时长推算；解除状态请以官方页面为准。",
            f"详情：{official_url}",
            "",
            "Data: 中国气象局 / 国家预警信息发布中心",
        ]
        lines += [
            "BEGIN:VEVENT",
            f"UID:cma-alert-shanghai-{alert['uid_key']}@liutong.local",
            f"DTSTAMP:{now}",
            f"LAST-MODIFIED:{now}",
            f"DTSTART;TZID=Asia/Shanghai:{alert['start']:%Y%m%dT%H%M%S}",
            f"DTEND;TZID=Asia/Shanghai:{alert['end']:%Y%m%dT%H%M%S}",
            f"SUMMARY:{escape(summary)}",
            f"DESCRIPTION:{escape(chr(10).join(desc_parts))}",
            f"URL:{official_url}",
            "CATEGORIES:天气预警",
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    # RFC 5545 requires CRLF and recommends folding content lines at 75 octets.
    folded_lines = [folded for line in lines for folded in fold_ics_line(line)]
    return "\r\n".join(folded_lines) + "\r\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", choices=PRESETS.keys(), default="shanghai")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--name", type=str)
    ap.add_argument("--days", type=int, default=16)
    ap.add_argument("--out", type=str)
    ap.add_argument(
        "--alerts",
        choices=("auto", "cma", "none"),
        default="auto",
        help="official warnings: auto enables CMA for supported presets; cma fails if unavailable",
    )
    ap.add_argument("--alert-adcode", help="CMA province-level adcode, e.g. 31 for Shanghai")
    args = ap.parse_args()

    if args.lat is not None and args.lon is not None:
        lat, lon, name = args.lat, args.lon, (args.name or f"{args.lat},{args.lon}")
    else:
        lat, lon, name = PRESETS[args.city]
        if args.name:
            name = args.name

    out = args.out or f"{args.city if args.lat is None else 'custom'}_weather.ics"
    data = fetch_forecast(lat, lon, args.days)
    alerts = []
    adcode = args.alert_adcode or (CMA_ADCODE.get(args.city) if args.lat is None else None)
    if args.alerts == "cma" and not adcode:
        ap.error("--alerts cma requires --alert-adcode for custom coordinates or unsupported cities")
    if args.alerts == "cma" or (args.alerts == "auto" and adcode):
        try:
            alerts = fetch_cma_alerts(adcode)
        except Exception as exc:
            if args.alerts == "cma":
                raise
            print(f"Warning: official weather alerts unavailable: {exc}", file=sys.stderr)

    ics = build_ics(data, name, alerts)
    Path(out).write_text(ics, encoding="utf-8")
    print(
        f"Wrote {out}  ({len(data['daily']['time'])} days, "
        f"{len(group_cma_alerts(alerts))} alert events)"
    )


if __name__ == "__main__":
    main()
