"""
Cloud Backend Entrypoint for Railway / Uvicorn
Redirects to the implementation in backend.server
"""
from backend.server import app

__all__ = ["app"]
