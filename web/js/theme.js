/*
Module: theme.js

Variables and behavior:
- Uses localStorage key `THEME_STORAGE_KEY` for persisted theme preference.
- Maintains one internal timer (`themeTransitionTimer`) to control transition class cleanup.

How this module works:
1. `initializeTheme(button)` sets the initial theme from storage or system setting.
2. `toggleTheme(button)` switches dark/light, stores preference, and animates transition.
*/

import { THEME_STORAGE_KEY } from "./constants.js";

let themeTransitionTimer = null;

function getSystemTheme() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(button, theme, animate = false) {
  const resolved = theme === "dark" ? "dark" : "light";
  const root = document.documentElement;

  if (themeTransitionTimer) {
    window.clearTimeout(themeTransitionTimer);
    themeTransitionTimer = null;
  }

  if (animate) {
    root.classList.add("theme-transitioning");
  }

  root.setAttribute("data-theme", resolved);
  if (button) {
    button.textContent = resolved === "dark" ? "Light" : "Dark";
  }

  if (animate) {
    themeTransitionTimer = window.setTimeout(() => {
      root.classList.remove("theme-transitioning");
      themeTransitionTimer = null;
    }, 380);
  }
}

export function initializeTheme(button) {
  const saved = localStorage.getItem(THEME_STORAGE_KEY);
  if (saved === "dark" || saved === "light") {
    applyTheme(button, saved, false);
    return;
  }
  applyTheme(button, getSystemTheme(), false);
}

export function toggleTheme(button) {
  const current = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  const next = current === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_STORAGE_KEY, next);
  applyTheme(button, next, true);
}
