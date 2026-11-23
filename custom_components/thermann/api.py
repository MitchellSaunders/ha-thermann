"""Minimal client for the Thermowatt (MyThermowatt / Thermann Control) cloud API.

Reverse-engineered from the official app's traffic. This is a synchronous
client using `requests`; callers inside Home Assistant must run its methods
via `hass.async_add_executor_job(...)` rather than calling them directly from
the event loop.

Rate-limit safety rules this client follows:
- It never sends a password login on its own. `login()` is only called
  explicitly (setup / config flow / reauth). A 401 during normal use triggers
  at most one token refresh; if that fails, ThermowattAuthError is raised and
  the caller must stop polling.
- HTTP 429 raises ThermowattRateLimitError (with Retry-After when given) so
  the caller can back off.
"""
from __future__ import annotations

import datetime
import logging
import threading
from typing import Any

import requests

from .const import API_KEY, BASE_URL

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = 15


class ThermowattApiError(Exception):
    """Raised for any non-2xx response or network failure."""


class ThermowattAuthError(ThermowattApiError):
    """Credentials/tokens rejected. Polling must stop until the user re-authenticates."""


class ThermowattRateLimitError(ThermowattApiError):
    """HTTP 429 from the backend."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _retry_after(resp: requests.Response) -> float | None:
    value = resp.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


class ThermowattClient:
    """Thin wrapper around the Thermowatt REST API."""

    def __init__(
        self,
        email: str,
        password: str,
        device_uuid: str,
        app_version: str,
        access_token: str | None = None,
        refresh_token: str | None = None,
    ) -> None:
        self._email = email
        self._password = password
        self._device_uuid = device_uuid
        self._app_version = app_version
        self._access_token = access_token
        self._refresh_token = refresh_token
        # A single session is intentional: it preserves cookies set by the
        # backend's load balancer between requests. Headers are passed per
        # request (never stored on the session) so concurrent calls from
        # different executor threads can't clobber each other.
        self.session = requests.Session()
        # Serialises requests so a poll and a user command can't both hit a
        # 401 and race to refresh the same refresh token.
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ tokens

    @property
    def tokens(self) -> tuple[str | None, str | None]:
        return self._access_token, self._refresh_token

    @property
    def has_tokens(self) -> bool:
        return bool(self._access_token and self._refresh_token)

    def _base_headers(self, *, api_key: bool = False, serial: str | None = None) -> dict[str, str]:
        headers = {
            "app": "MyThermowatt",
            "platform": "iOS",
            "version": self._app_version,
            "lang": "en",
        }
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        if api_key:
            headers["x-api-key"] = API_KEY
        if serial:
            headers["seriale"] = serial
        return headers

    def _send(self, method: str, url: str, headers: dict[str, str], **kwargs) -> requests.Response:
        try:
            return self.session.request(method, url, headers=headers, verify=True, timeout=_TIMEOUT, **kwargs)
        except requests.RequestException as err:
            raise ThermowattApiError(f"Network error calling {url}: {err}") from err

    @staticmethod
    def _parse_tokens(resp: requests.Response) -> tuple[str, str]:
        result = resp.json()["result"]
        return result["accessToken"], result["refreshToken"]

    # ------------------------------------------------------------------ auth

    def login(self) -> None:
        """Password login. Only call this from setup, config flow or reauth."""
        with self._lock:
            payload = {
                "username": self._email,
                "password": self._password,
                "device_id": self._device_uuid,
            }
            resp = self._send("POST", f"{BASE_URL}/login", self._base_headers(api_key=True), json=payload)

            if resp.status_code == 429:
                raise ThermowattRateLimitError("Login rate limited (HTTP 429)", _retry_after(resp))
            if resp.status_code in (400, 401, 403):
                raise ThermowattAuthError(
                    f"Login rejected with HTTP {resp.status_code}. Check email/password, or "
                    "whether the Thermann Control / MyThermowatt app has a newer version "
                    "than the app_version configured for this integration."
                )
            if resp.status_code != 200:
                raise ThermowattApiError(f"Login failed with HTTP {resp.status_code}")
            try:
                self._access_token, self._refresh_token = self._parse_tokens(resp)
            except (KeyError, ValueError, TypeError) as err:
                raise ThermowattApiError(f"Unexpected login response shape: {err}") from err

    def _refresh_locked(self) -> bool:
        """Try to refresh the access token once. Caller must hold the lock."""
        if not self._refresh_token:
            return False
        payload = {"username": self._email, "refreshToken": self._refresh_token}
        resp = self._send("POST", f"{BASE_URL}/refresh", self._base_headers(api_key=True), json=payload)
        if resp.status_code == 429:
            raise ThermowattRateLimitError("Token refresh rate limited (HTTP 429)", _retry_after(resp))
        if resp.status_code != 200:
            _LOGGER.debug("Token refresh failed: HTTP %s", resp.status_code)
            return False
        try:
            self._access_token, self._refresh_token = self._parse_tokens(resp)
        except (KeyError, ValueError, TypeError):
            return False
        return True

    # ------------------------------------------------------------------ requests

    def _request(self, method: str, endpoint: str, serial: str | None = None, **kwargs) -> requests.Response:
        """Send an authenticated request; raise on any non-200 response."""
        url = f"{BASE_URL}{endpoint}"
        extra_headers = kwargs.pop("headers", None) or {}

        with self._lock:
            if not self.has_tokens:
                raise ThermowattAuthError("Not logged in")

            resp = self._send(method, url, {**self._base_headers(serial=serial), **extra_headers}, **kwargs)

            if resp.status_code == 401:
                # One refresh, one retry. Never fall back to a password login
                # here: a loop of logins is what gets accounts locked.
                if not self._refresh_locked():
                    raise ThermowattAuthError("Session expired and token refresh failed")
                resp = self._send(method, url, {**self._base_headers(serial=serial), **extra_headers}, **kwargs)
                if resp.status_code == 401:
                    raise ThermowattAuthError("Still unauthorised after token refresh")

        if resp.status_code == 429:
            raise ThermowattRateLimitError(f"{method} {endpoint} rate limited (HTTP 429)", _retry_after(resp))
        if resp.status_code != 200:
            raise ThermowattApiError(f"{method} {endpoint} failed: HTTP {resp.status_code}")
        return resp

    @staticmethod
    def _result(resp: requests.Response) -> Any:
        try:
            return resp.json().get("result", {})
        except ValueError as err:
            raise ThermowattApiError(f"Invalid JSON from {resp.url}") from err

    def list_devices(self) -> list[dict[str, Any]]:
        """Return the list of thermostats/boilers on this account."""
        result = self._result(self._request("GET", "/user-info"))
        return result.get("termostati", []) if isinstance(result, dict) else []

    def get_status(self, serial: str) -> dict[str, Any]:
        result = self._result(self._request("GET", "/status", serial=serial))
        return result if isinstance(result, dict) else {}

    def set_temperature(self, serial: str, temp_c: int) -> None:
        self._request("POST", "/manual", serial=serial, json={"T_SetPoint": temp_c})

    def set_mode(self, serial: str, mode: str, current_setpoint: int = 60) -> None:
        text_plain = {"headers": {"Content-Type": "text/plain"}, "data": ""}
        if mode == "manual":
            self._request("POST", "/manual", serial=serial, json={"T_SetPoint": current_setpoint})
        elif mode == "eco":
            self._request("POST", "/eco", serial=serial, **text_plain)
        elif mode == "auto":
            self._request("POST", "/auto", serial=serial, **text_plain)
        elif mode == "holiday":
            future_date = (datetime.date.today() + datetime.timedelta(days=30)).strftime("%Y-%m-%d")
            self._request("POST", "/holiday", serial=serial, json={"end_date": future_date})
        elif mode == "off":
            self._request("POST", "/off", serial=serial, **text_plain)
        else:
            raise ValueError(f"Unknown mode: {mode}")
