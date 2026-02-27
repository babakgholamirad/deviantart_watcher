#!/usr/bin/env python3
"""Flask entrypoint for the DeviantArt watcher web UI.

Variables in this module:
- `app`: Flask app that serves the index page, static assets, and API routes.
- `JOB_STATE`: shared in-memory download job tracker used by API endpoints.

How this module works:
1. Builds the Flask app and delegates route wiring to `web_backend.routes`.
2. Bootstraps the local database once at import so gallery APIs are ready.
3. Runs Flask in threaded mode so UI actions can run while downloads are active.
"""

from __future__ import annotations

from flask import Flask

from web_backend.environment import BASE_DIR, bootstrap_database
from web_backend.job_state import DownloadJobState
from web_backend.routes import register_routes

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
JOB_STATE = DownloadJobState()
register_routes(app, JOB_STATE)
bootstrap_database()


def main() -> None:
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()
