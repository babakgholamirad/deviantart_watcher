# DeviantArt New Upload Downloader

This app checks one or more DeviantArt user galleries and downloads newly detected images.
It uses the official DeviantArt OAuth2 API instead of HTML scraping.

## What it does

- Authenticates with your DeviantArt client_id and client_secret
- Polls each configured user gallery (/gallery/all)
- Tracks seen deviation IDs per user in state.json
- Downloads only items not seen before
- Optionally saves preview/content images if original download is unavailable
- Includes a local web page (index.html) with a gallery and a download form

## Project structure

- deviantart_watcher.py: thin CLI entrypoint
- web_app.py: local Flask server for the landing page and gallery API
- index.html: page structure
- web/styles.css: page styles
- web/app.js: frontend logic (form submit, gallery rendering, lightbox, theme, navigation arrows)
- da_watcher/config.py: argument parsing and env/config validation
- da_watcher/api.py: DeviantArt OAuth + API client
- da_watcher/storage.py: output filename/state management helpers
- da_watcher/watcher.py: polling loop and per-user processing logic

## Setup

powershell commands:
cd C:\Users\HOME\Projects\deviantart_watcher
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env

In .env, set DA_CLIENT_ID, DA_CLIENT_SECRET, and DA_USERNAMES.

## Run CLI

python .\deviantart_watcher.py

## Run Web UI

python .\web_app.py

Open: http://127.0.0.1:5000

The landing page lets you:

- Fill DA_CLIENT_ID, DA_CLIENT_SECRET, and DA_USERNAMES
- Set pagination controls (start_page, end_page, page_size)
- Toggle optional flags (INCLUDE_MATURE, ALLOW_PREVIEW, SEED_ONLY, VERBOSE)
- Click Start Download to run a one-time download job
- See loading animation while the job is running
- View images grouped by artist folder (collapsible sections)
- Click any image to expand it in a full-screen viewer with next/previous arrows
- See there is no pictures when gallery is empty

## Notes

- Downloading requires respecting artist permissions and DeviantArt terms.
- If an item is not marked downloadable, it is skipped unless ALLOW_PREVIEW=true.

