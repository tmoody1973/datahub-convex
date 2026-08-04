# Copyright 2026 Radio Milwaukee / Liner Notes contributors
# SPDX-License-Identifier: Apache-2.0
"""Thin client for Convex's streaming export REST API.

Docs: https://docs.convex.dev/http-api/#streaming-export
Endpoints used:
  GET /api/json_schemas?deltaSchema=true&format=json  -> {table: JSON Schema}
  GET /api/list_snapshot?tableName=<t>[&cursor=...]   -> {values, cursor, hasMore}
"""

from typing import Any, Dict, Optional, Tuple

import requests

PAGE_SIZE_HINT = 1024  # server-side page size; informational only


class ConvexStreamingExportClient:
    def __init__(self, url: str, deploy_key: str, timeout: int = 60):
        self.base_url = url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Convex {deploy_key}"
        self.timeout = timeout

    def _get(self, path: str, params: Optional[Dict[str, str]] = None) -> Any:
        response = self.session.get(
            f"{self.base_url}{path}", params=params, timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def list_schemas(self) -> Dict[str, Dict[str, Any]]:
        """Return {table_name: JSON Schema (draft-07)} for every table."""
        return self._get(
            "/api/json_schemas", params={"deltaSchema": "true", "format": "json"}
        )

    def count_rows(self, table: str, max_pages: int) -> Tuple[int, bool]:
        """Count rows by paging list_snapshot.

        Returns (count, exact). exact is False when max_pages was hit
        before the snapshot was exhausted.
        """
        count = 0
        cursor: Optional[str] = None
        for _ in range(max_pages):
            params: Dict[str, str] = {"tableName": table}
            if cursor:
                params["cursor"] = cursor
            page = self._get("/api/list_snapshot", params=params)
            count += len(page.get("values", []))
            if not page.get("hasMore"):
                return count, True
            cursor = page.get("cursor")
        return count, False
