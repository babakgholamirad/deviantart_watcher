/*
Module: icons.js

Variables and behavior:
- Provides SVG markup for trash/star icons and helpers to build icon-only buttons.

How this module works:
- Keeps icon/button creation in one place so renderer code stays focused on layout logic.
*/

export function buildTrashIcon() {
  return `
    <svg class="trash-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M9 3h6l1 2h5v2H3V5h5l1-2Zm-2 6h2v9H7V9Zm4 0h2v9h-2V9Zm4 0h2v9h-2V9Z"></path>
    </svg>
  `;
}

export function buildStarIcon() {
  return `
    <svg class="star-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2.5 14.95 8.48 21.55 9.44 16.77 14.1 17.9 20.68 12 17.58 6.1 20.68 7.23 14.1 2.45 9.44 9.05 8.48Z"></path>
    </svg>
  `;
}

export function createIconButton(className, ariaLabel, iconMarkup, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `icon-btn ${className}`;
  button.setAttribute("aria-label", ariaLabel);
  button.title = ariaLabel;
  button.innerHTML = iconMarkup;
  button.addEventListener("click", onClick);
  return button;
}

export function createTrashButton(className, ariaLabel, onClick) {
  return createIconButton(`danger-btn ${className}`, ariaLabel, buildTrashIcon(), onClick);
}
