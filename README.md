# DeviantArt New Upload Downloader

This app checks one or more DeviantArt users' galleries and downloads newly detected images.
It uses DeviantArt's official OAuth2 API instead of HTML scraping.

## What it does

- Authenticates with your DeviantArt `client_id` and `client_secret`
- Polls each configured user's gallery (`/gallery/all`)
- Tracks seen deviation IDs per user in a local `state.json`
- Downloads only items not seen before
- Optionally saves preview/content images if original download is unavailable
- Includes a local web page (`index.html`) with a gallery and a download form

## Project structure

- `deviantart_watcher.py`: thin CLI entrypoint
- `web_app.py`: local Flask server for the landing page and gallery API
- `index.html`: landing page with form, loading animation, and gallery UI
- `da_watcher/config.py`: argument parsing and env/config validation
- `da_watcher/api.py`: DeviantArt OAuth + API client
- `da_watcher/storage.py`: output filename/state management helpers
- `da_watcher/watcher.py`: polling loop and per-user processing logic

## 1) Create DeviantArt API credentials

1. Go to the DeviantArt developers portal: `https://www.deviantart.com/developers/`
2. Create an app and copy:
   - `client_id`
   - `client_secret`

## 2) Install dependencies

```powershell
cd C:\Users\HOME\Projects\deviantart_watcher
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 3) Configure environment

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set:

- `DA_CLIENT_ID`
- `DA_CLIENT_SECRET`
- `DA_USERNAMES` (comma-separated, example: `artistA,artistB,artistC`)

`DA_USERNAME` is still supported for single-user mode.

## 4) Run CLI

Run once:

```powershell
python .\deviantart_watcher.py
```

Watch continuously every 5 minutes:

```powershell
python .\deviantart_watcher.py --interval 300
```

Override users from CLI:

```powershell
python .\deviantart_watcher.py --usernames "artistA,artistB"
python .\deviantart_watcher.py --username artistA --username artistB
```

## 5) Run Web UI

Start local server:

```powershell
python .\web_app.py
```

Open in browser:

- `http://127.0.0.1:5000`

The landing page lets you:

- Fill `DA_CLIENT_ID`, `DA_CLIENT_SECRET`, and `DA_USERNAMES`
- Click **Start Download** to run a one-time download job
- See loading animation while the job is running
- View downloaded images from `downloads/`
- See `there is no pictures` when gallery is empty

## Notes

- Downloading requires respecting each artist's permissions and DeviantArt terms.
- If an item is not marked downloadable, it is skipped unless `ALLOW_PREVIEW=true` is set.
- Use Windows Task Scheduler if you prefer scheduled runs over `--interval`.

