from __future__ import annotations

import logging
from typing import Optional

import requests

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
    "Connection": "keep-alive",
}


class HttpClient:
    def __init__(self, timeout: int = 20) -> None:
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.timeout = timeout
        self.log = logging.getLogger(self.__class__.__name__)

    def get(self, url: str, *, params: Optional[dict] = None) -> requests.Response:
        self.log.debug("GET %s params=%s", url, params)
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response

    def get_json(self, url: str, *, params: Optional[dict] = None) -> dict:
        resp = self.get(url, params=params)
        return resp.json()
