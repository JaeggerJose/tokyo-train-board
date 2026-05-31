import requests
from datetime import datetime

ODPT_KEY = "YOUR_KEY"

BASE = "https://api.odpt.org/api/v4"


def get_station_timetable(station_id: str, railway_id: str):
    url = f"{BASE}/odpt:StationTimetable"

    params = {
        "acl:consumerKey": ODPT_KEY,
        "odpt:station": station_id
    }

    res = requests.get(url, params=params)
    data = res.json()

    # filter 山手線
    for item in data:
        if item.get("odpt:railway") == railway_id:
            return item["odpt:stationTimetableObject"]

    return []
