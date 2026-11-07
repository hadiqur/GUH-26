"""Stand-alone dev server for the Dial-a-Text dashboard.

    uvicorn dashboard_dev:app --reload --port 8001

Mounts only the dashboard router (which also serves static/account/). In the
real app, add to app/main.py:

    from app.dashboard_routes import router as dashboard_router
    app.include_router(dashboard_router)
"""

import logging

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

try:  # optional: read .env if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from app.dashboard_routes import router as dashboard_router  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Dial-a-Text dashboard (dev)")
app.include_router(dashboard_router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/account")
