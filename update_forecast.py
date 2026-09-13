"""
Field Heat Watch — weekly forecast updater.

Pulls a 7-day forecast from the free National Weather Service API for
2549 Hackmann Rd, St. Charles, MO, estimates a WBGT risk band for the
practice window using the same model as the site, and writes the
result to data/forecast.json for the static site to read.

Runs automatically every Saturday morning via GitHub Actions
(.github/workflows/update.yml), and can also be triggered manually
from the Actions tab any time.

No API key needed — the NWS API is free and public. It does require
a descriptive User-Agent identifying who's calling it; edit CONTACT
below to your own email before first use, per NWS API policy.
"""

import json
import urllib.request
from datetime import datetime, timezone

LAT, LON = 38.7906, -90.5164  # 2549 Hackmann Rd, St. Charles, MO
CONTACT = "FieldHeatWatch (contact: your-email@example.com)"  # <-- edit this
PRACTICE_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday"}
PRACTICE_WINDOW = "2:40 PM - 5:00 PM"

HEADERS = {"User-Agent": CONTACT, "Accept": "application/geo+json"}


def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def estimate_cloud_pct(short_forecast):
    text = short_forecast.lower()
    if "sunny" in text and "mostly" not in text and "partly" not in text:
        return 5
    if "mostly sunny" in text:
        return 20
    if "partly" in text:
        return 45
    if "mostly cloudy" in text:
        return 75
    if "cloudy" in text or "overcast" in text:
        return 90
    return 40  # unknown / fog / etc: moderate default


def is_storm_risk(short_forecast):
    text = short_forecast.lower()
    return any(w in text for w in ["thunderstorm", "t-storm", "shower"])


def core_level(temp, cloud, hum, bucket="midday"):
    """Same risk model used in the site's JS predictor, kept in sync."""
    if temp < 86:
        base = 0
    elif temp < 90:
        base = 1
    elif temp < 96:
        base = 2
    elif temp < 103:
        base = 3
    else:
        base = 4

    if cloud >= 90:
        base -= 2
    elif cloud >= 70:
        base -= 1

    if bucket == "morning" or bucket == "evening":
        base -= 1

    if hum is not None and hum >= 70:
        base += 1

    return max(0, min(4, round(base)))


def main():
    points = fetch_json(f"https://api.weather.gov/points/{LAT},{LON}")
    forecast_url = points["properties"]["forecast"]
    forecast = fetch_json(forecast_url)

    days = []
    seen_dates = set()

    for period in forecast["properties"]["periods"]:
        if not period["isDaytime"]:
            continue  # one card per calendar day, use the daytime period

        start = datetime.fromisoformat(period["startTime"])
        date_key = start.strftime("%Y-%m-%d")
        if date_key in seen_dates:
            continue
        seen_dates.add(date_key)

        dow = start.strftime("%A")
        temp = period["temperature"]
        short = period["shortForecast"]
        cloud = estimate_cloud_pct(short)

        hum = None
        rh = period.get("relativeHumidity")
        if isinstance(rh, dict) and rh.get("value") is not None:
            hum = rh["value"]

        base_level = core_level(temp, cloud, hum, bucket="midday")
        low = max(0, base_level - 1)
        high = min(4, base_level + 1)

        days.append({
            "dow": dow,
            "date": start.strftime("%-m/%-d"),
            "hi": temp,
            "sky": short,
            "humidity": hum,
            "cloudEstimate": cloud,
            "stormRisk": is_storm_risk(short),
            "practice": dow in PRACTICE_DAYS,
            "lvlLow": low,
            "lvlHigh": high,
        })

        if len(days) >= 7:
            break

    output = {
        "location": "2549 Hackmann Rd, St. Charles, MO",
        "practiceWindow": PRACTICE_WINDOW,
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "days": days,
    }

    with open("data/forecast.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote {len(days)} days to data/forecast.json")


if __name__ == "__main__":
    main()
