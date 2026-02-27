/*
Module: constants.js

Variables exported:
- `THEME_STORAGE_KEY`: localStorage key for light/dark theme preference.
- `ARTIST_ORDER_STORAGE_KEY`: localStorage key for custom artist group ordering.
- `ARTIST_GROUP_STATE_STORAGE_KEY`: localStorage key for per-artist open/closed UI state.

How this module works:
- Centralizes string keys so all modules use the same persisted names.
*/

export const THEME_STORAGE_KEY = "da_watcher_theme";
export const ARTIST_ORDER_STORAGE_KEY = "da_watcher_artist_order";
export const ARTIST_GROUP_STATE_STORAGE_KEY = "da_watcher_artist_group_state";
