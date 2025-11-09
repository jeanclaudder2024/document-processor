"""Standalone FastAPI application to serve the CMS static files."""

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CMS_DIR = os.path.join(BASE_DIR, "cms")

app = FastAPI(title="Petrodeal CMS", version="1.0.0")

if not os.path.isdir(CMS_DIR):
    raise RuntimeError(f"CMS directory not found at {CMS_DIR}")

app.mount("/", StaticFiles(directory=CMS_DIR, html=True), name="cms")

