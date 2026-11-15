from garmin_dashboard.garmin_client import GarminClient


import json


class Response:
    def __init__(self, *, text="", payload=None, status=200, headers=None):
        self.text = text
        self._payload = payload
        self.status_code = status
        self.ok = status < 400
        self.headers = headers or {}
        self.content = b"" if payload is None and not text else json.dumps(payload).encode() if payload is not None else text.encode()

    def json(self):
        return self._payload


class Session:
    def __init__(self, posts=(), gets=()):
        self.posts = list(posts)
        self.gets = list(gets)
        self.post_calls = []
        self.get_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self.posts.pop(0)

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self.gets.pop(0)

    def request(self, method, url, **kwargs):
        if method == "POST":
            return self.post(url, **kwargs)
        return self.get(url, **kwargs)

    def close(self):
        pass


def test_api_key_is_exchanged_and_activity_pages_use_documented_offsets():
    session = Session(
        posts=[Response(text="bearer-token")],
        gets=[Response(payload=[{"activityId": 1}, {"activityId": 2}]), Response(payload=[{"activityId": 3}])],
    )
    client = GarminClient("api-key", session=session, page_size=2, retry_delay=0)

    rows = list(client.iter_activities())

    assert [row["activityId"] for row in rows] == [1, 2, 3]
    token_url, token_request = session.post_calls[0]
    assert token_url.endswith("/personal-api-key/token")
    assert token_request["headers"]["Authorization"] == "ApiKey api-key"
    assert session.get_calls[0][1]["params"] == {"start": 0, "limit": 2}
    assert session.get_calls[1][1]["params"] == {"start": 2, "limit": 2}
    assert session.get_calls[0][1]["headers"]["Authorization"] == "Bearer bearer-token"


def test_expired_bearer_token_is_reexchanged_once():
    session = Session(
        posts=[Response(text="expired-token"), Response(text="new-token")],
        gets=[Response(status=401), Response(payload=[])],
    )
    client = GarminClient("api-key", session=session, retry_delay=0)

    assert list(client.iter_activities()) == []
    assert len(session.post_calls) == 2
    assert session.get_calls[0][1]["headers"]["Authorization"] == "Bearer expired-token"
    assert session.get_calls[1][1]["headers"]["Authorization"] == "Bearer new-token"


def test_rate_limit_response_is_retried():
    session = Session(
        posts=[Response(text="token")],
        gets=[Response(status=429, headers={"Retry-After": "0"}), Response(payload=[])],
    )
    client = GarminClient("api-key", session=session, retries=1, retry_delay=0)

    assert list(client.iter_activities()) == []
    assert len(session.get_calls) == 2


def test_wellness_uses_documented_date_range_endpoints():
    session = Session(posts=[Response(text="token")], gets=[Response(payload={}), Response(payload=[]), Response(payload=[])])
    client = GarminClient("api-key", session=session, retry_delay=0)

    payloads = client.fetch_wellness("2026-01-01", "2026-01-02")

    assert set(payloads) == {"daily_summaries", "sleep_summaries", "hrv_summaries"}
    assert session.get_calls[0][0].endswith("/usersummary-service/v2/dailysummaries")
    assert session.get_calls[0][1]["params"] == {"startDate": "2026-01-01", "endDate": "2026-01-02"}
    assert session.get_calls[1][0].endswith("/sleep-service/sleep/dailySleepSummariesByDate")
    assert session.get_calls[2][0].endswith("/hrv-service/hrv/daily/2026-01-01/2026-01-02")
