# DeviantArt New Upload Downloader

This app checks one or more DeviantArt users' galleries and downloads newly detected images.
It uses DeviantArt's official OAuth2 API instead of HTML scraping.

## What it does

- Authenticates with your DeviantArt `client_id` and `client_secret`
- Polls each configured user's gallery (`/gallery/all`)
- Tracks seen deviation IDs per user in a local `state.json`
- Downloads only items not seen before
- Optionally saves preview/content images if original download is unavailable

## Project structure

- `deviantart_watcher.py`: thin CLI entrypoint
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

## 4) Run

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

Seed state only (mark current posts as seen, download nothing):

```powershell
python .\deviantart_watcher.py --seed-only
```

Enable preview fallback for non-downloadable deviations:

```powershell
python .\deviantart_watcher.py --allow-preview
```

## Common options

- `--pages 3` number of gallery pages checked each cycle
- `--limit 24` items per page (max 24)
- `--output-dir downloads`
- `--state-file state.json`
- `--include-mature`
- `--verbose`

## Notes

- Downloading requires respecting each artist's permissions and DeviantArt terms.
- If an item is not marked downloadable, it is skipped unless `--allow-preview` is enabled.
- Use Windows Task Scheduler if you prefer scheduled runs over `--interval`.

