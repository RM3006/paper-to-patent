"""PatentSearch API client resource.

Supplementary use only — full-corpus ingest uses the PatentsView bulk TSV files.
This client is for targeted lookups (e.g. fetching a specific patent's details,
or supplementary enrichment queries in Parts 3–4).
"""

import time
from collections.abc import Iterator
from typing import Any

import httpx
from dagster import ConfigurableResource

from nexus.logging import logger

_MAX_RETRIES = 3
_RETRY_BASE_S = 2
MAX_RETRY_WAIT_S = 60


class PatentSearchClient(ConfigurableResource):  # pyright: ignore[reportMissingTypeArgument]
    """HTTP client for the PatentSearch API at search.patentsview.org.

    Provides header auth (X-Api-Key), exponential backoff on 429/5xx,
    and cursor-based pagination via the _after parameter.

    Never used for full-corpus pulls — those go through the bulk TSV files.
    """

    api_key: str
    base_url: str = "https://search.patentsview.org/api/v1"

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Single GET with exponential backoff on 429/5xx. Returns parsed JSON.

        Raises RuntimeError if the rate-limit cooldown exceeds MAX_RETRY_WAIT_S
        or if all retries are exhausted.
        """
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = {
            "X-Api-Key": self.api_key,
            "User-Agent": "paper-to-patent/0.1",
        }
        for attempt in range(_MAX_RETRIES):
            resp = httpx.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 429:
                wait = int(
                    resp.headers.get("Retry-After", _RETRY_BASE_S * (2**attempt))
                )
                if wait > MAX_RETRY_WAIT_S:
                    raise RuntimeError(
                        f"PatentSearch API rate-limited for {wait}s. "
                        "Wait for the cooldown to expire then retry."
                    )
                logger.warning(
                    "PatentSearch 429; retrying in %ds (attempt %d/%d)",
                    wait,
                    attempt + 1,
                    _MAX_RETRIES,
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result
        raise RuntimeError(
            f"PatentSearch GET {endpoint!r} failed after {_MAX_RETRIES} retries."
        )

    def paginate(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        per_page: int = 100,
        results_key: str = "hits",
    ) -> Iterator[dict[str, Any]]:
        """Yield individual records across all pages using cursor pagination.

        Stops when a page returns fewer results than per_page, or when the
        response carries no 'next' cursor.
        """
        page_params: dict[str, Any] = dict(params or {})
        page_params["per_page"] = per_page

        while True:
            response = self.get(endpoint, page_params)
            hits: list[dict[str, Any]] = response.get(results_key, [])
            yield from hits
            if len(hits) < per_page:
                break
            cursor: str | None = response.get("next")
            if cursor is None:
                break
            page_params["_after"] = cursor
