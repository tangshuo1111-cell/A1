"""General fast lane weather helpers."""

from __future__ import annotations

import re
import time

import httpx

from application.chat.budget_clock import format_ms

WEATHER_CITY_MAP: dict[str, tuple[str, float, float]] = {
    "广州": ("广州", 23.1291, 113.2644),
    "北京": ("北京", 39.9042, 116.4074),
    "上海": ("上海", 31.2304, 121.4737),
    "深圳": ("深圳", 22.5431, 114.0579),
    "杭州": ("杭州", 30.2741, 120.1551),
    "成都": ("成都", 30.5728, 104.0668),
    "武汉": ("武汉", 30.5928, 114.3055),
    "南京": ("南京", 32.0603, 118.7969),
    "重庆": ("重庆", 29.5630, 106.5516),
    "西安": ("西安", 34.3416, 108.9398),
    "天津": ("天津", 39.3434, 117.3616),
    "苏州": ("苏州", 31.2989, 120.5853),
}


def weather_city_from_message(message: str) -> tuple[str, str] | None:
    msg = (message or "").strip()
    if "天气" not in msg:
        return None
    for zh, _query in WEATHER_CITY_MAP.items():
        if zh in msg:
            return zh, zh
    match = re.search(r"([\u4e00-\u9fa5]{2,8})(?:今天|明天|现在)?的?天气", msg)
    if match:
        zh = match.group(1)
        return zh, zh
    return None


def weather_desc(code: int | None) -> str:
    if code is None:
        return "天气"
    if code == 0:
        return "晴"
    if code in {1, 2, 3}:
        return "多云"
    if code in {45, 48}:
        return "有雾"
    if code in {51, 53, 55, 56, 57}:
        return "毛毛雨"
    if code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "有雨"
    if code in {71, 73, 75, 77, 85, 86}:
        return "有雪"
    if code in {95, 96, 99}:
        return "雷阵雨"
    return "天气"


def try_fast_weather_answer(message: str) -> tuple[str, dict[str, object]] | None:
    city = weather_city_from_message(message)
    if city is None:
        return None
    city_zh, city_key = city
    t0 = time.perf_counter()
    city_meta = WEATHER_CITY_MAP.get(city_key)
    if city_meta is None:
        return None
    city_name, lat, lon = city_meta
    try:
        timeout = httpx.Timeout(1.2, connect=0.8, read=1.0, write=0.8, pool=0.8)
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "Asia/Shanghai",
                    "forecast_days": 1,
                },
            )
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current") or {}
        daily = data.get("daily") or {}
        temp = current.get("temperature_2m")
        feels = current.get("apparent_temperature")
        humidity = current.get("relative_humidity_2m")
        wind = current.get("wind_speed_10m")
        desc = weather_desc(current.get("weather_code"))
        max_list = daily.get("temperature_2m_max") or []
        min_list = daily.get("temperature_2m_min") or []
        rain_list = daily.get("precipitation_probability_max") or []
        max_c = max_list[0] if max_list else None
        min_c = min_list[0] if min_list else None
        rain = rain_list[0] if rain_list else None
        parts = [f"{city_name}当前{desc}"]
        if temp is not None:
            parts.append(f"气温 {temp}℃")
        if feels is not None:
            parts.append(f"体感 {feels}℃")
        if min_c is not None and max_c is not None:
            parts.append(f"今日约 {min_c}-{max_c}℃")
        if humidity is not None:
            parts.append(f"湿度 {humidity}%")
        if rain is not None:
            parts.append(f"最高降水概率 {rain}%")
        if wind is not None:
            parts.append(f"风速约 {wind} km/h")
        return "，".join(parts) + "。数据源：Open-Meteo。", {
            "fast_path": "weather",
            "fast_path_provider": "open-meteo",
            "fast_weather_city": city_name,
            "fast_weather_elapsed_ms": format_ms((time.perf_counter() - t0) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        return (
            f"我刚才走了天气快路径，但天气源暂时没返回可用结果（{type(exc).__name__}）。你可以稍后再试，或让我走网页搜索查一次。",
            {
                "fast_path": "weather_failed",
                "fast_weather_city": city_zh,
                "fast_weather_error": type(exc).__name__,
                "fast_weather_elapsed_ms": format_ms((time.perf_counter() - t0) * 1000),
            },
        )
