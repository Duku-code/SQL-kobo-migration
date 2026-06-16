import logging
from typing import Any, Dict, Optional

import requests

from config import load_config

logger = logging.getLogger(__name__)


class KoboClientError(Exception):
    pass


class KoboClient:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.base_url = self.config.kobo_base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Token {self.config.kobo_api_token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{path}"
        logger.debug("Kobo GET %s params=%s", url, params)
        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        if not response.ok:
            logger.error(
                "Kobo API request failed: %s %s %s",
                response.status_code,
                response.reason,
                response.text,
            )
            raise KoboClientError(
                f"Kobo API request failed: {response.status_code} {response.reason} - {response.text}"
            )
        return response.json()

    def fetch_form_definition(self, form_id: str) -> Dict[str, Any]:
        """Fetch Kobo form definition JSON for a given form ID."""
        path = f"/api/v2/assets/{form_id}"
        return self._get(path)

    def fetch_submissions(self, form_id: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetch submissions for a Kobo form. Returns the API response JSON."""
        path = f"/api/v2/assets/{form_id}/data"
        return self._get(path, params=params)

    @staticmethod
    def parse_webhook_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize webhook payload to a submission record dictionary."""
        if not isinstance(payload, dict):
            raise KoboClientError("Webhook payload must be a JSON object")

        if "data" in payload and isinstance(payload["data"], dict):
            return payload["data"]

        if "submission" in payload and isinstance(payload["submission"], dict):
            return payload["submission"]

        raise KoboClientError("Unsupported Kobo webhook payload format")
