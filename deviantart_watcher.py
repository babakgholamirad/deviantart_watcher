#!/usr/bin/env python3
"""CLI entrypoint for the DeviantArt watcher."""

from da_watcher.watcher import run


if __name__ == "__main__":
    raise SystemExit(run())
