/*
Module: galleryRenderer.js

Variables and behavior:
- Renders grouped artist cards, preserves group open state/order, and supports drag reordering.
- Builds lightbox item lists on every render.
- Invokes callbacks for delete and favorite actions.

How this module works:
1. `createGalleryRenderer(...)` accepts DOM references + callbacks.
2. `render(...)` paints all groups/cards and syncs lightbox items.
3. `setGallerySearching(...)` applies temporary visual state while search requests run.
*/

import { createIconButton, createTrashButton, buildStarIcon } from "./icons.js";
import {
  getArtistGroupOpenState,
  persistArtistOrderFromDom,
  setArtistGroupOpenState,
  sortGroupsByStoredOrder,
} from "./galleryStorage.js";
import { buildLightboxCaption } from "./lightbox.js";

function restartGroupOpenAnimation(details) {
  details.classList.remove("opening");
  // Force reflow so the same class can retrigger animation on each open.
  void details.offsetWidth;
  details.classList.add("opening");
  window.setTimeout(() => {
    details.classList.remove("opening");
  }, 360);
}

export function createGalleryRenderer({
  artistGroups,
  emptyText,
  galleryCount,
  lightboxController,
  getCurrentSearchQuery,
  getFavoritesOnly,
  onDeleteImage,
  onDeleteArtist,
  onToggleFavorite,
}) {
  let draggedArtistGroup = null;

  function setGallerySearching(isSearching) {
    artistGroups.classList.toggle("is-searching", isSearching);
  }

  function attachArtistDragHandlers(details) {
    details.addEventListener("dragstart", (event) => {
      draggedArtistGroup = details;
      details.classList.add("dragging");
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", details.dataset.artist || "");
      }
    });

    details.addEventListener("dragend", () => {
      details.classList.remove("dragging");
      draggedArtistGroup = null;
      persistArtistOrderFromDom(artistGroups);
    });

    details.addEventListener("dragover", (event) => {
      event.preventDefault();
      if (!draggedArtistGroup || draggedArtistGroup === details) {
        return;
      }

      const rect = details.getBoundingClientRect();
      const placeBefore = event.clientY < rect.top + rect.height / 2;
      if (placeBefore) {
        artistGroups.insertBefore(draggedArtistGroup, details);
      } else {
        artistGroups.insertBefore(draggedArtistGroup, details.nextSibling);
      }
    });

    details.addEventListener("drop", (event) => {
      event.preventDefault();
      persistArtistOrderFromDom(artistGroups);
    });
  }

  function render(groups, totalCount, options = {}) {
    const animateResults = Boolean(options.animateResults);

    artistGroups.innerHTML = "";
    const lightboxItems = [];
    galleryCount.textContent = `${totalCount} image(s)`;

    if (!totalCount) {
      emptyText.style.display = "block";
      const searchQuery = getCurrentSearchQuery();
      const favoritesOnly = getFavoritesOnly();

      if (favoritesOnly && searchQuery) {
        emptyText.textContent = `No favorite pictures found for "${searchQuery}".`;
      } else if (favoritesOnly) {
        emptyText.textContent = "No favorite pictures yet.";
      } else if (searchQuery) {
        emptyText.textContent = `No pictures found for "${searchQuery}".`;
      } else {
        emptyText.textContent = "there is no pictures";
      }

      lightboxController.setItems([]);
      return;
    }

    emptyText.style.display = "none";

    const sortedGroups = sortGroupsByStoredOrder(groups);

    sortedGroups.forEach((group, groupIndex) => {
      const details = document.createElement("details");
      details.className = "artist-group";
      details.open = getArtistGroupOpenState(group.artist);
      details.draggable = true;
      details.dataset.artist = group.artist;
      details.addEventListener("toggle", () => {
        setArtistGroupOpenState(group.artist, details.open);
      });

      if (animateResults) {
        details.classList.add("entering");
        details.style.setProperty("--group-index", String(groupIndex));
      }

      const summary = document.createElement("summary");
      summary.addEventListener("click", () => {
        // Before click toggle: details.open reflects the old state.
        if (!details.open) {
          window.setTimeout(() => {
            if (details.open) {
              restartGroupOpenAnimation(details);
            }
          }, 0);
        }
      });

      const summaryTitleWrap = document.createElement("div");
      summaryTitleWrap.className = "artist-summary-title";

      const dragHandle = document.createElement("span");
      dragHandle.className = "drag-handle";
      dragHandle.textContent = "::";
      dragHandle.title = "Drag to reorder artist groups";

      const summaryTitle = document.createElement("span");
      summaryTitle.textContent = group.artist;

      summaryTitleWrap.appendChild(dragHandle);
      summaryTitleWrap.appendChild(summaryTitle);

      const summaryActions = document.createElement("div");
      summaryActions.className = "artist-summary-actions";

      const countBadge = document.createElement("span");
      countBadge.className = "artist-count";
      countBadge.textContent = `${group.count} image(s)`;

      const deleteArtistButton = createTrashButton(
        "delete-artist-btn",
        `Delete all images for ${group.artist}`,
        async (event) => {
          event.preventDefault();
          event.stopPropagation();
          await onDeleteArtist(group.artist);
        }
      );

      summaryActions.appendChild(countBadge);
      summaryActions.appendChild(deleteArtistButton);

      summary.appendChild(summaryTitleWrap);
      summary.appendChild(summaryActions);

      const grid = document.createElement("div");
      grid.className = "artist-grid";

      group.images.forEach((image, imageIndex) => {
        const card = document.createElement("article");
        card.className = "card";
        card.style.setProperty("--item-index", String(imageIndex));
        if (animateResults) {
          card.classList.add("entering");
        }

        const img = document.createElement("img");
        const src = `${image.url}?v=${encodeURIComponent(image.mtime)}`;
        img.src = src;
        img.alt = image.title || image.name;
        img.loading = "lazy";

        const metaRow = document.createElement("div");
        metaRow.className = "card-meta-row";

        const metaText = document.createElement("div");
        metaText.className = "card-meta-text";

        const cardTitle = document.createElement("div");
        cardTitle.className = "card-title";
        cardTitle.textContent = image.title || image.name;

        const pathMeta = document.createElement("div");
        pathMeta.className = "card-meta";
        pathMeta.textContent = image.relative_path;

        metaText.appendChild(cardTitle);
        metaText.appendChild(pathMeta);

        const tags = Array.isArray(image.tags) ? image.tags : [];
        if (tags.length) {
          const tagsMeta = document.createElement("div");
          tagsMeta.className = "card-tags";
          tagsMeta.textContent = `# ${tags.join("  # ")}`;
          metaText.appendChild(tagsMeta);
        }

        const actions = document.createElement("div");
        actions.className = "card-actions";

        const favoriteAria = image.is_favorite
          ? `Remove favorite for ${image.relative_path}`
          : `Mark favorite for ${image.relative_path}`;

        const favoriteButton = createIconButton(
          "favorite-btn",
          favoriteAria,
          buildStarIcon(),
          async (event) => {
            event.preventDefault();
            event.stopPropagation();
            await onToggleFavorite(image.relative_path, !Boolean(image.is_favorite), favoriteButton);
          }
        );

        if (image.is_favorite) {
          favoriteButton.classList.add("is-favorite");
        }

        const deleteImageButton = createTrashButton(
          "delete-image-btn",
          `Delete ${image.relative_path}`,
          async (event) => {
            event.preventDefault();
            event.stopPropagation();
            await onDeleteImage(image.relative_path, card);
          }
        );

        actions.appendChild(favoriteButton);
        actions.appendChild(deleteImageButton);

        metaRow.appendChild(metaText);
        metaRow.appendChild(actions);

        const itemIndex = lightboxItems.length;
        lightboxItems.push({
          url: src,
          caption: buildLightboxCaption(image),
        });

        card.addEventListener("click", () => {
          lightboxController.openAt(itemIndex);
        });

        card.appendChild(img);
        card.appendChild(metaRow);
        grid.appendChild(card);
      });

      details.appendChild(summary);
      details.appendChild(grid);
      attachArtistDragHandlers(details);
      artistGroups.appendChild(details);
    });

    lightboxController.setItems(lightboxItems);

    if (animateResults) {
      window.setTimeout(() => {
        artistGroups.querySelectorAll(".entering").forEach((node) => {
          node.classList.remove("entering");
        });
      }, 720);
    }
  }

  return {
    render,
    setGallerySearching,
  };
}
