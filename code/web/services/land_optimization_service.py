"""Land optimization service for surfacing smart-land diagnostics to the web layer.

Reads _land_report_data produced by LandAnalysisMixin (Roadmap 14) from the
active builder session and formats it for JSON API responses.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from code.web.services.base import BaseService
from code import logging_util

logger = logging_util.logging.getLogger(__name__)
logger.setLevel(logging_util.LOG_LEVEL)
logger.addHandler(logging_util.file_handler)
logger.addHandler(logging_util.stream_handler)


class LandOptimizationService(BaseService):
    """Thin service that extracts and formats land diagnostics from a build session."""

    def __init__(self) -> None:
        super().__init__()

    def get_land_report(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Extract _land_report_data from the active builder in ``session``.

        Args:
            session: The dict returned by ``get_session(sid)``.

        Returns:
            A copy of ``_land_report_data``, or an empty dict if unavailable.
        """
        ctx = session.get('build_ctx') or {}
        builder = ctx.get('builder') if isinstance(ctx, dict) else None
        if builder is None:
            return {}
        report = getattr(builder, '_land_report_data', None)
        return dict(report) if report else {}

    def format_for_api(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Return a JSON-serialisable copy of ``report``.

        Converts any non-primitive values (numpy types, DataFrames, etc.) to
        strings so the result can be passed straight to ``JSONResponse``.

        Args:
            report: Raw _land_report_data dict.

        Returns:
            A plain-dict copy safe for JSON serialisation.
        """
        if not report:
            return {}
        try:
            return json.loads(json.dumps(report, default=str))
        except Exception as exc:  # pragma: no cover
            logger.warning('LandOptimizationService.format_for_api failed: %s', exc)
            return {}
