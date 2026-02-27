/*
Module: galleryStorage.js

Variables and behavior:
- Persists artist order and open/closed group state in localStorage.
- Updates the favorites filter button visual state.

How this module works:
- Exposes focused getters/setters so the renderer stays simple and deterministic.
*/

import { ARTIST_GROUP_STATE_STORAGE_KEY, ARTIST_ORDER_STORAGE_KEY } from "./constants.js";

export function updateFavoritesOnlyButton(button, showFavoritesOnly) {
  if (!button) {
    return;
  }
  button.setAttribute("aria-pressed", showFavoritesOnly ? "true" : "false");
  button.classList.toggle("active", showFavoritesOnly);
  button.textContent = showFavoritesOnly ? "Show All" : "Show Favorites";
}

export function getStoredArtistOrder() {
  try {
    const raw = localStorage.getItem(ARTIST_ORDER_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
  } catch (_error) {
    return [];
  }
}

export function saveArtistOrder(order) {
  const cleaned = Array.from(new Set(order.filter((item) => typeof item === "string" && item.trim())));
  localStorage.setItem(ARTIST_ORDER_STORAGE_KEY, JSON.stringify(cleaned));
}

export function persistArtistOrderFromDom(artistGroupsElement) {
  const order = Array.from(artistGroupsElement.querySelectorAll(".artist-group"))
    .map((node) => node.dataset.artist || "")
    .filter(Boolean);

  if (order.length) {
    saveArtistOrder(order);
  }
}

export function sortGroupsByStoredOrder(groups) {
  const storedOrder = getStoredArtistOrder();
  const orderMap = new Map(storedOrder.map((artist, index) => [artist, index]));

  const sortedGroups = [...groups].sort((a, b) => {
    const indexA = orderMap.has(a.artist) ? orderMap.get(a.artist) : Number.MAX_SAFE_INTEGER;
    const indexB = orderMap.has(b.artist) ? orderMap.get(b.artist) : Number.MAX_SAFE_INTEGER;
    if (indexA !== indexB) {
      return indexA - indexB;
    }
    return String(a.artist).localeCompare(String(b.artist), undefined, { sensitivity: "base" });
  });

  const normalizedOrder = storedOrder.filter((artist) => sortedGroups.some((group) => group.artist === artist));
  for (const group of sortedGroups) {
    if (!normalizedOrder.includes(group.artist)) {
      normalizedOrder.push(group.artist);
    }
  }
  saveArtistOrder(normalizedOrder);

  return sortedGroups;
}

function getStoredArtistGroupState() {
  try {
    const raw = localStorage.getItem(ARTIST_GROUP_STATE_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_error) {
    return {};
  }
}

function saveArtistGroupState(state) {
  localStorage.setItem(ARTIST_GROUP_STATE_STORAGE_KEY, JSON.stringify(state));
}

export function setArtistGroupOpenState(artist, isOpen) {
  if (!artist) {
    return;
  }
  const state = getStoredArtistGroupState();
  state[artist] = Boolean(isOpen);
  saveArtistGroupState(state);
}

export function getArtistGroupOpenState(artist) {
  const state = getStoredArtistGroupState();
  if (Object.prototype.hasOwnProperty.call(state, artist)) {
    return Boolean(state[artist]);
  }
  return true;
}
