"""Minimal client for the Thermowatt (MyThermowatt / Thermann Control) cloud API.

Reverse-engineered from the official app's traffic. This is a synchronous
client using `requests`; callers inside Home Assistant must run its methods
via `hass.async_add_executor_job(...)` rather than calling them directly from
the event loop.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from .const import API_KEY, BASE_URL

_LOGGER = logging.getLogger(__name__)


class ThermowattAuthError(Exception):
    """Raised when login/refresh fails - bad credentials or stale app_version."""


class ThermowattApiError(Exception):
    """Raised for any other non-2xx response from the Thermowatt API."""


class ThermowattClient:
    """Thin wrapper around the Thermowatt REST API."""

    def __init__(self, email: str, password: str, device_uuid: str, app_version: str) -> None:
        self._email = email
        self._password = password
        self._device_uuid = device_uuid
        self._app_version = app_version
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        # A single session is intentional: it preserves cookies set by the
        # backend's load balancer between requests.
        self.session = requests.Session()

    def _reset_headers(self) -> None:
        auth_header = self.session.headers.get("Authorization")
        self.session.headers.clear()
        if auth_header:
            self.session.headers["Authorization"] = auth_header
        self.session.headers.update(
            {
                "app": "MyThermowatt",
                "platform": "iOS",
                "version": self._app_version,
                "lang": "en",
            }
        )

    def _update_auth(self, access: str, refresh: str) -> None:
        self._access_token = access
        self._refresh_token = refresh
        self.session.headers["Authorization"] = f"Bearer {access}"

    def login(self) -> None:
        """Authenticate and store access/refresh tokens. Raises ThermowattAuthError on failure."""
        self._reset_headers()
        self.session.headers["x-api-key"] = API_KEY

        payload = {
            "username": self._email,
            "password": self._password,
            "device_id": self._device_uuid,
        }
        try:
            resp = self.session.post(f"{BASE_URL}/login", json=payload, verify=True, timeout=15)
        except requests.RequestException as err:
            raise ThermowattAuthError(f"Network error during login: {err}") from err

        if resp.status_code != 200:
            raise ThermowattAuthError(
                f"Login failed with HTTP {resp.status_code}. If this used to work, "
                "check whether the Thermann Control / MyThermowatt app has a newer "
                "version than the app_version configured for this integration."
            )
        try:
            result = resp.json()["result"]
            self._update_auth(result["accessToken"], result["refreshToken"])
        except (KeyError, ValueError) as err:
            raise ThermowattAuthError(f"Unexpected login response shape: {err}") from err

    def refresh_session(self) -> bool:
        """Try to refresh the access token. Returns True on success."""
        if not self._refresh_token:
            return False
        self._reset_headers()
        self.session.headers["x-api-key"] = API_KEY
        payload = {"username": self._email, "refreshToken": self._refresh_token}
        try:
            resp = self.session.post(f"{BASE_URL}/refresh", json=payload, verify=True, timeout=15)
        except requests.RequestException:
            return False
        if resp.status_code != 200:
            return False
        try:
            result = resp.json()["result"]
            self._update_auth(result["accessToken"], result["refreshToken"])
            return True
        except (KeyError, ValueError):
            return False

    def _request(self, method: str, endpoint: str, serial: str | None = None, **kwargs) -> requests.Response:
        self._reset_headers()
        if serial:
            self.session.headers["seriale"] = serial

        url = f"{BASE_URL}{endpoint}"
        resp = self.session.request(method, url, verify=True, timeout=15, **kwargs)

        if resp.status_code == 401:
            if self.refresh_session():
                self._reset_headers()
                if serial:
                    self.session.headers["seriale"] = serial
                resp = self.session.request(method, url, verify=True, timeout=15, **kwargs)
            else:
                # Refresh failed; re-login from scratch.
                self.login()
                if serial:
                    self.session.headers["seriale"] = serial
                resp = self.session.request(method, url, verify=True, timeout=15, **kwargs)

        return resp

    def list_devices(self) -> list[dict[str, Any]]:
        """Return the list of thermostats/boilers on this account."""
        resp = self._request("GET", "/user-info")
        if resp.status_code != 200:
            raise ThermowattApiError(f"Could not list devices: HTTP {resp.status_code}")
        return resp.json().get("result", {}).get("termostati", [])

    def get_status(self, serial: str) -> dict[str, Any]:
        resp = self._request("GET", "/status", serial=serial)
        if resp.status_code != 200:
            raise ThermowattApiError(f"Status poll failed for {serial}: HTTP {resp.status_code}")
        return resp.json().get("result", {})

    def set_temperature(self, serial: str, temp_c: int) -> None:
        resp = self._request("POST", "/manual", serial=serial, json={"T_SetPoint": temp_c})
        if resp.status_code != 200:
            raise ThermowattApiError(f"Set temperature failed: HTTP {resp.status_code}")

    def set_mode(self, serial: str, mode: str, current_setpoint: int = 60) -> None:
        if mode == "manual":
            self._request("POST", "/manual", serial=serial, json={"T_SetPoint": current_setpoint})
        elif mode == "eco":
            self._request("POST", "/eco", serial=serial, headers={"Content-Type": "text/plain"}, data="")
        elif mode == "auto":
            self._request("POST", "/auto", serial=serial, headers={"Content-Type": "text/plain"}, data="")
        elif mode == "holiday":
            import datetime

            future_date = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime("%Y-%m-%d")
            self._request("POST", "/holiday", serial=serial, json={"end_date": future_date})
        elif mode == "off":
            self._request("POST", "/off", serial=serial, headers={"Content-Type": "text/plain"}, data="")
        else:
            raise ValueError(f"Unknown mode: {mode}")
