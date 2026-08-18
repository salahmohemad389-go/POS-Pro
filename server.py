"""Vercel/FastAPI deployment entrypoint."""
import os

# Vercel Marketplace database integrations commonly inject DATABASE_URL.
# POS Pro uses POS_DATABASE_URL internally, so map it automatically when needed.
if not os.environ.get("POS_DATABASE_URL") and os.environ.get("DATABASE_URL"):
    os.environ["POS_DATABASE_URL"] = os.environ["DATABASE_URL"]

from app.main import app

__all__ = ["app"]
