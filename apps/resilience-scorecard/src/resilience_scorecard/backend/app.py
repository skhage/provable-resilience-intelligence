"""Lakelink Fiber — Provable Resilience Intelligence App.

FastAPI entry point serving the resilience scorecard and proactive action queue.
The React/TypeScript frontend is served as static files at /.
The API is mounted at /api.
"""

from .core import create_app
from .router import router

app = create_app(routers=[router])
