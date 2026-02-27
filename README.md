# DeviantArt Watcher

Downloads new DeviantArt uploads and serves a local web UI gallery.

## What it does

- Uses DeviantArt OAuth2 API to fetch gallery uploads
- Tracks seen deviations in SQLite (not JSON)
- Stores image metadata (`image_title` + `tags`) in DB for search
- Supports multiple artists
- Supports pagination, optional flags, dark/light theme
- Supports deleting one image or all images of an artist from the UI

## Project structure

- `deviantart_watcher.py`: CLI entrypoint
- `web_app.py`: Flask server + API endpoints
- `index.html`: page markup
- `web/styles.css`: styles
- `web/app.js`: frontend logic
- `da_watcher/`: downloader, API client, DB, config

## Database

SQLite database file is `DB_FILE` (default `state.db`).

Tables created automatically:

- `artists`
- `seen_deviations`
- `images`

At startup, app migrates legacy `STATE_FILE` JSON (default `state.json`) into DB and syncs `downloads/` into `images`.

## Setup

```powershell
cd C:\Users\HOME\Projects\deviantart_watcher
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set in `.env`:

- `DA_CLIENT_ID`
- `DA_CLIENT_SECRET`
- `DA_USERNAMES`

Optional:

- `DB_FILE=state.db`
- `STATE_FILE=state.json` (legacy migration source)

## Run CLI

```powershell
python .\deviantart_watcher.py
```

## Run Web UI

```powershell
python .\web_app.py
```

Open: `http://127.0.0.1:5000`

## Web UI features

- Download run with pagination (`start_page`, `end_page`, `page_size`)
- Optional flags (`INCLUDE_MATURE`, `ALLOW_PREVIEW`, `SEED_ONLY`, `VERBOSE`)
- Gallery grouped by artist
- Search by image name/title and tags
- Click image to open lightbox with previous/next arrows
- Trash icon button to delete one image
- Trash icon button to delete all images of an artist
