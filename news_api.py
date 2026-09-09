import json
import os

import requests


BASE = "http://172.237.44.223:8000"
API_KEY = os.environ["FLOOD_API_KEY"]
COHORT = "rasuwa-bhotekoshi-floods"


def search_floods(q=None, limit=20, offset=0, since=None, sort="published_at:desc"):
    """Query the news index, filtered to the floods cohort."""

    filt = {"term": {"cohort": COHORT}}

    if since:
        filt = {
            "bool": {
                "must": [
                    filt,
                    {"range": {"published_at": {"gte": since}}},
                ]
            }
        }

    params = {
        "index": "news",
        "filter": json.dumps(filt),
        "limit": limit,
        "offset": offset,
        "sort": sort,
    }

    if q:
        params["q"] = q

    response = requests.get(
        f"{BASE}/v1/full-text/search",
        headers={"X-API-Key": API_KEY},
        params=params,
        timeout=15,
    )

    response.raise_for_status()

    return response.json()["data"]["results"]


if __name__ == "__main__":
    for doc in search_floods(limit=5):
        print(doc.get("published_at"), "|", doc.get("title", "")[:70])