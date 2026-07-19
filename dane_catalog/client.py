"""Shared HTTP client with retry, optional Socrata app token and optional
read-through proxy support (including proxy rotation).

Direct access to datos.gov.co (Socrata) and microdatos.dane.gov.co works from
most residential/ISP connections. Some datacenter IP ranges are blocked by the
upstream CDNs (HTTP 403/401); in that case pass ``proxy=...`` to route GET
requests through public CORS proxies, or provide a Socrata app token.
"""

from __future__ import annotations

import time
import urllib.parse

import requests

DEFAULT_USER_AGENT = (
    "dane-data-catalog/1.0 "
    "(+https://github.com/) "
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Public read-through proxies known to fetch Socrata/NADA endpoints from
# allowed IP ranges. Templates must contain ``{url}``.
PROXIES = {
    "allorigins": "https://api.allorigins.win/raw?url={url}",
    "corslol": "https://api.cors.lol/?url={url}",
}

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 520, 522, 524}


class HttpClient:
    """Small GET-only JSON client with retries and proxy support."""

    def __init__(
        self,
        proxy: str | None = None,
        app_token: str | None = None,
        timeout: int = 60,
        max_retries: int = 8,
        backoff: float = 3.0,
        pause: float = 0.4,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        """
        Parameters
        ----------
        proxy:
            ``None`` for direct requests; one of the keys in
            :data:`PROXIES`; ``"rotate"`` to alternate between all known
            proxies on each retry; or a custom URL template containing
            ``{url}``.
        app_token:
            Optional Socrata application token (``X-App-Token``). Strongly
            recommended for heavy use; required from some cloud IP ranges.
        timeout:
            Per-request timeout in seconds.
        max_retries:
            Attempts per request before giving up.
        backoff:
            Base seconds for backoff on retryable errors.
        pause:
            Politeness delay between successful requests.
        """
        self.proxy_templates = self._resolve_proxies(proxy)
        self.app_token = app_token
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.pause = pause
        self._rotation = 0
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": user_agent, "Accept": "application/json"}
        )
        if app_token:
            self.session.headers["X-App-Token"] = app_token

    @staticmethod
    def _resolve_proxies(proxy: str | None) -> list[str]:
        if not proxy:
            return []
        if proxy == "rotate":
            return list(PROXIES.values())
        if proxy in PROXIES:
            return [PROXIES[proxy]]
        return [proxy]

    def _wrap(self, url: str, attempt: int) -> str:
        if not self.proxy_templates:
            return url
        idx = (self._rotation + attempt) % len(self.proxy_templates)
        return self.proxy_templates[idx].format(
            url=urllib.parse.quote(url, safe="")
        )

    def get_json(self, url: str, params: dict | None = None):
        """GET ``url`` and return the decoded JSON body, with retries."""
        if params:
            qs = urllib.parse.urlencode(params)
            url = f"{url}{'&' if '?' in url else '?'}{qs}"
        last_error: str = ""
        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(
                    self._wrap(url, attempt), timeout=self.timeout
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                self._rotation += 1
                time.sleep(self.backoff * (attempt + 1))
                continue
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError:
                    data = None
                if data is not None:
                    time.sleep(self.pause)
                    return data
                last_error = f"non-JSON body: {resp.text[:200]}"
            elif (
                resp.status_code in (403, 401)
                and not self.proxy_templates
                and not self.app_token
            ):
                raise RuntimeError(
                    f"HTTP {resp.status_code} from upstream. Your IP range may "
                    "be blocked by the CDN. Retry with --proxy rotate or "
                    "provide a Socrata app token (--app-token)."
                )
            elif resp.status_code in RETRYABLE_STATUS or resp.status_code in (403, 401):
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            else:
                raise RuntimeError(
                    f"GET {url} failed with HTTP {resp.status_code}: "
                    f"{resp.text[:300]}"
                )
            # rotate proxy for next attempt and back off
            self._rotation += 1
            time.sleep(self.backoff * (attempt + 1))
        raise RuntimeError(
            f"GET {url} failed after {self.max_retries} attempts. {last_error}"
        )
