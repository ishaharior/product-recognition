"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Request

from app.core.runtime import AppState


def get_state(request: Request) -> AppState:
    return request.app.state.station
