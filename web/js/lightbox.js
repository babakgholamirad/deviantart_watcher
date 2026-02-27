/*
Module: lightbox.js

Variables and behavior:
- Tracks `items` (images), `currentIndex`, and controls lightbox open/close/navigation state.

How this module works:
1. `setItems` updates the currently navigable image list.
2. `openAt`, `step`, and `close` manage modal state and next/previous buttons.
3. `onOverlayClick` and `onKeyDown` expose event handlers for UI wiring.
*/

export function buildLightboxCaption(image) {
  const tags = Array.isArray(image.tags) ? image.tags : [];
  const favoritePrefix = image.is_favorite ? "\u2605 " : "";
  const tagText = tags.length ? ` | tags: ${tags.join(", ")}` : "";
  return `${favoritePrefix}${image.title || image.relative_path}${tagText}`;
}

export function createLightboxController(elements) {
  const state = {
    items: [],
    currentIndex: -1,
  };

  function updateNavState() {
    const atStart = state.currentIndex <= 0;
    const atEnd = state.currentIndex >= state.items.length - 1;
    elements.prevButton.disabled = atStart;
    elements.nextButton.disabled = atEnd;
  }

  function isOpen() {
    return elements.lightbox.classList.contains("show");
  }

  function setItems(items) {
    state.items = Array.isArray(items) ? items : [];
    if (state.currentIndex >= state.items.length) {
      state.currentIndex = -1;
    }
    updateNavState();
  }

  function openAt(index) {
    if (!state.items.length || index < 0 || index >= state.items.length) {
      return;
    }

    state.currentIndex = index;
    const item = state.items[state.currentIndex];
    elements.image.src = item.url;
    elements.caption.textContent = item.caption;
    updateNavState();

    elements.lightbox.classList.add("show");
    elements.lightbox.setAttribute("aria-hidden", "false");
  }

  function step(delta) {
    if (!isOpen()) {
      return;
    }

    const nextIndex = state.currentIndex + delta;
    if (nextIndex < 0 || nextIndex >= state.items.length) {
      return;
    }
    openAt(nextIndex);
  }

  function close() {
    elements.lightbox.classList.remove("show");
    elements.lightbox.setAttribute("aria-hidden", "true");
    elements.image.src = "";
    elements.caption.textContent = "";
    state.currentIndex = -1;
    elements.prevButton.disabled = true;
    elements.nextButton.disabled = true;
  }

  function onOverlayClick(event) {
    if (event.target === elements.lightbox) {
      close();
    }
  }

  function onKeyDown(event) {
    if (!isOpen()) {
      return;
    }

    if (event.key === "Escape") {
      close();
    } else if (event.key === "ArrowLeft") {
      step(-1);
    } else if (event.key === "ArrowRight") {
      step(1);
    }
  }

  close();

  return {
    setItems,
    openAt,
    step,
    close,
    onOverlayClick,
    onKeyDown,
    isOpen,
  };
}
