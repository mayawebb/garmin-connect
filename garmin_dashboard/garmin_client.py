"""Small, mockable client for Garmin Connect's documented Personal API."""

from collections.abc import Iterator
from datetime import date
import time
from typing import Any

import requests


BASE_URL = "https://personal.connectapi.garmin.com"
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"
ACTIVITIES_PATH = "/activitylist-service/activities/search/activities"


class GarminApiError(RuntimeError):
    """Safe-to-display Garmin error; deliberately excludes response bodies."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GarminClient:
    """Exchange a Personal API key for an in-memory bearer token and read pages."""

    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
        page_size: int = 20,
        retries: int = 2,
        retry_delay: float = 1.0,
        sleep=time.sleep,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("A Garmin Personal API key is required")
        if page_size <= 0 or retries < 0 or retry_delay < 0:
            raise ValueError("Invalid pagination or retry configuration")
        self._api_key = api_key.strip()
        self._session = session or requests.Session()
        self.page_size = page_size
        self.retries = retries
        self.retry_delay = retry_delay
        self._sleep = sleep
        self._access_token: str | None = None

    def __enter__(self) -> "GarminClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._session.close()

    def authenticate(self, *, force: bool = False) -> str:
        """Exchange the key through Garmin's token endpoint; no refresh token exists."""
        if self._access_token and not force:
            return self._access_token
        response = self._request(
            "POST",
            TOKEN_PATH,
            headers={"Accept": "*/*", "Authorization": f"ApiKey {self._api_key}"},
        )
        token = response.text.strip()
        if not token:
            raise GarminApiError("Garmin returned an empty access token")
        self._access_token = token
        return token

    def iter_activities(
        self,
        *,
        activity_type: str | None = None,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield activity summaries using documented start/limit offset parameters.

        Garmin's Swagger describes the activity search as paginated. Pages are
        requested at offsets 0, limit, 2*limit, etc. A short page ends the scan.
        """
        start = 0
        while True:
            response = self._get_activities_page(start, activity_type, start_date, end_date)
            try:
                page = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError) as exc:
                raise GarminApiError("Garmin returned an invalid activity response") from exc
            if not isinstance(page, list):
                raise GarminApiError("Garmin returned an unexpected activity response")
            for row in page:
                if not isinstance(row, dict):
                    raise GarminApiError("Garmin returned an unexpected activity record")
                yield row
            if len(page) < self.page_size:
                break
            start += self.page_size

    def fetch_wellness(self, start_date: date | str, end_date: date | str) -> dict[str, Any]:
        """Fetch range-based daily summary, sleep summary, and HRV summary payloads."""
        start = start_date.isoformat() if isinstance(start_date, date) else start_date
        end = end_date.isoformat() if isinstance(end_date, date) else end_date
        if end < start:
            raise ValueError("end_date must be on or after start_date")
        return {
            "daily_summaries": self._get_json(
                "/usersummary-service/v2/dailysummaries",
                params={"startDate": start, "endDate": end},
            ),
            "sleep_summaries": self._get_json(
                "/sleep-service/sleep/dailySleepSummariesByDate",
                params={"startDate": start, "endDate": end},
            ),
            "hrv_summaries": self._get_json(
                f"/hrv-service/hrv/daily/{start}/{end}",
            ),
        }

    def download_activity(self, activity_id: str | int) -> bytes:
        """Download one original activity ZIP from Garmin's documented endpoint."""
        token = self.authenticate()
        path = f"/download-service/files/activity/{activity_id}"
        for attempt in range(2):
            response = self._request(
                "GET",
                path,
                headers={
                    "Accept": "application/zip, application/x-zip-compressed, application/octet-stream",
                    "Authorization": f"Bearer {token}",
                },
                raise_on_error=False,
            )
            if response.status_code == 401 and attempt == 0:
                token = self.authenticate(force=True)
                continue
            if not response.ok:
                raise GarminApiError(
                    f"Garmin activity-file request failed (HTTP {response.status_code})",
                    response.status_code,
                )
            if not response.content:
                raise GarminApiError("Garmin returned an empty activity file")
            return response.content
        raise GarminApiError("Garmin authentication failed (HTTP 401)", 401)

    def _get_json(self, path: str, *, params: dict[str, str] | None = None) -> Any:
        token = self.authenticate()
        for attempt in range(2):
            response = self._request(
                "GET",
                path,
                params=params,
                headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
                raise_on_error=False,
            )
            if response.status_code == 401 and attempt == 0:
                token = self.authenticate(force=True)
                continue
            if not response.ok:
                raise GarminApiError(
                    f"Garmin wellness request failed (HTTP {response.status_code})",
                    response.status_code,
                )
            if not response.content:
                return None
            try:
                return response.json()
            except (ValueError, requests.exceptions.JSONDecodeError) as exc:
                raise GarminApiError("Garmin returned an invalid wellness response") from exc
        raise GarminApiError("Garmin authentication failed (HTTP 401)", 401)

    def _get_activities_page(
        self,
        start: int,
        activity_type: str | None,
        start_date: date | str | None,
        end_date: date | str | None,
    ) -> requests.Response:
        token = self.authenticate()
        params: dict[str, str | int] = {
            "start": start,
            "limit": self.page_size,
        }
        if activity_type is not None:
            params["activityType"] = activity_type
        if start_date is not None:
            params["startDate"] = start_date.isoformat() if isinstance(start_date, date) else start_date
        if end_date is not None:
            params["endDate"] = end_date.isoformat() if isinstance(end_date, date) else end_date
        for attempt in range(2):
            response = self._request(
                "GET",
                ACTIVITIES_PATH,
                params=params,
                headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
                raise_on_error=False,
            )
            if response.status_code == 401 and attempt == 0:
                token = self.authenticate(force=True)
                continue
            if not response.ok:
                raise GarminApiError(
                    f"Garmin activity request failed (HTTP {response.status_code})",
                    response.status_code,
                )
            return response
        raise GarminApiError("Garmin authentication failed (HTTP 401)", 401)

    def _request(self, method: str, path: str, *, raise_on_error: bool = True, **kwargs: Any) -> requests.Response:
        url = f"{BASE_URL}{path}"
        for attempt in range(self.retries + 1):
            try:
                response = self._session.request(method, url, timeout=30, **kwargs)
            except requests.RequestException as exc:
                if attempt >= self.retries:
                    raise GarminApiError(f"Garmin network request failed ({type(exc).__name__})") from exc
                self._sleep(self.retry_delay * (2**attempt))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self.retries:
                    retry_after = response.headers.get("Retry-After") if hasattr(response, "headers") else None
                    try:
                        delay = max(self.retry_delay * (2**attempt), float(retry_after)) if retry_after else self.retry_delay * (2**attempt)
                    except ValueError:
                        delay = self.retry_delay * (2**attempt)
                    self._sleep(delay)
                    continue
            if raise_on_error and not response.ok:
                raise GarminApiError(f"Garmin token request failed (HTTP {response.status_code})", response.status_code)
            return response
        raise GarminApiError("Garmin network request failed")
