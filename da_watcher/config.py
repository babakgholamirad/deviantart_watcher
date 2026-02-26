from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .api import DEFAULT_USER_AGENT
from .env_utils import env_bool, env_int, load_env_file, resolve_usernames


@dataclass
class AppConfig:
    client_id: str
    client_secret: str
    usernames: List[str]
    output_dir: Path
    state_file: Path
    pages: int
    limit: int
    interval: int
    include_mature: bool
    allow_preview: bool
    seed_only: bool
    max_seen: int
    timeout: int
    user_agent: str
    verbose: bool


def parse_config() -> AppConfig:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file", default=".env")
    pre_args, _ = pre_parser.parse_known_args()
    load_env_file(Path(pre_args.env_file))

    parser = argparse.ArgumentParser(
        description="Download newly uploaded images from one or more DeviantArt users."
    )
    parser.add_argument("--env-file", default=pre_args.env_file, help="Path to optional .env file.")
    parser.add_argument("--client-id", default=os.getenv("DA_CLIENT_ID"), help="DeviantArt client_id.")
    parser.add_argument(
        "--client-secret",
        default=os.getenv("DA_CLIENT_SECRET"),
        help="DeviantArt client_secret.",
    )
    parser.add_argument(
        "--username",
        action="append",
        default=None,
        help="Target DeviantArt username (repeat flag for multiple users).",
    )
    parser.add_argument(
        "--usernames",
        default=None,
        help="Comma-separated DeviantArt usernames.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.getenv("OUTPUT_DIR", "downloads")),
        help="Directory where images are saved.",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(os.getenv("STATE_FILE", "state.json")),
        help="Path to local state file.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=env_int("PAGES_PER_CHECK", 3),
        help="How many gallery pages to inspect per check.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=env_int("PAGE_SIZE", 24),
        help="Items per page (API max: 24).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=env_int("POLL_INTERVAL_SECONDS", 0),
        help="Polling interval in seconds. Use 0 to run once and exit.",
    )
    parser.add_argument(
        "--include-mature",
        action=argparse.BooleanOptionalAction,
        default=env_bool("INCLUDE_MATURE", False),
        help="Include mature content if the account has permission.",
    )
    parser.add_argument(
        "--allow-preview",
        action=argparse.BooleanOptionalAction,
        default=env_bool("ALLOW_PREVIEW", False),
        help="Download preview/content images when original download is unavailable.",
    )
    parser.add_argument(
        "--seed-only",
        action=argparse.BooleanOptionalAction,
        default=env_bool("SEED_ONLY", False),
        help="Record current items as seen without downloading.",
    )
    parser.add_argument(
        "--max-seen",
        type=int,
        default=env_int("MAX_SEEN_IDS", 5000),
        help="Max number of seen IDs to keep in state.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=env_int("REQUEST_TIMEOUT_SECONDS", 30),
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--user-agent",
        default=os.getenv("USER_AGENT", DEFAULT_USER_AGENT),
        help="Custom User-Agent header.",
    )
    parser.add_argument(
        "--verbose",
        action=argparse.BooleanOptionalAction,
        default=env_bool("VERBOSE", False),
        help="Enable debug logs.",
    )

    args = parser.parse_args()

    missing = []
    if not args.client_id:
        missing.append("DA_CLIENT_ID / --client-id")
    if not args.client_secret:
        missing.append("DA_CLIENT_SECRET / --client-secret")

    usernames = resolve_usernames(
        cli_usernames=args.username,
        cli_usernames_csv=args.usernames,
        env_usernames_csv=os.getenv("DA_USERNAMES", ""),
        env_username_single=os.getenv("DA_USERNAME", ""),
    )
    if not usernames:
        missing.append("DA_USERNAMES (or DA_USERNAME) / --username / --usernames")
    if missing:
        parser.error(f"Missing required values: {', '.join(missing)}")

    if args.pages < 1:
        parser.error("--pages must be >= 1")
    if args.limit < 1 or args.limit > 24:
        parser.error("--limit must be between 1 and 24")
    if args.interval < 0:
        parser.error("--interval must be >= 0")
    if args.max_seen < 100:
        parser.error("--max-seen should be >= 100")

    return AppConfig(
        client_id=args.client_id,
        client_secret=args.client_secret,
        usernames=usernames,
        output_dir=args.output_dir,
        state_file=args.state_file,
        pages=args.pages,
        limit=args.limit,
        interval=args.interval,
        include_mature=args.include_mature,
        allow_preview=args.allow_preview,
        seed_only=args.seed_only,
        max_seen=args.max_seen,
        timeout=args.timeout,
        user_agent=args.user_agent,
        verbose=args.verbose,
    )

