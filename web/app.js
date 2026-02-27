/*
Module: app.js

Variables and behavior:
- This is the main UI coordinator. It wires all web modules together.
- Keeps current filters (`currentSearchQuery`, `showFavoritesOnly`) and search debounce state.

How this module works:
1. Initializes theme, defaults, job status, and first gallery render.
2. Handles user actions (run download, delete, favorite, search, lightbox navigation).
3. Delegates rendering, job polling, API calls, and storage behavior to focused modules.
*/

import { fetchDefaults, fetchGallery, fetchJobStatus, postJson } from "./js/api.js";
import dom from "./js/dom.js";
import { createGalleryRenderer } from "./js/galleryRenderer.js";
import { updateFavoritesOnlyButton } from "./js/galleryStorage.js";
import { createJobController } from "./js/jobController.js";
import { createLightboxController } from "./js/lightbox.js";
import { initializeTheme, toggleTheme } from "./js/theme.js";
import { toInt, wait } from "./js/utils.js";

let searchDebounceTimer = null;
let currentSearchQuery = "";
let showFavoritesOnly = false;

const lightboxController = createLightboxController({
  lightbox: dom.lightbox,
  image: dom.lightboxImage,
  caption: dom.lightboxCaption,
  prevButton: dom.lightboxPrev,
  nextButton: dom.lightboxNext,
});

const jobController = createJobController({
  startButton: dom.startButton,
  spinner: dom.spinner,
  statusText: dom.statusText,
  fetchJobStatus,
  onJobFinished: async () => {
    await loadGallery(currentSearchQuery, showFavoritesOnly);
  },
});

const galleryRenderer = createGalleryRenderer({
  artistGroups: dom.artistGroups,
  emptyText: dom.emptyText,
  galleryCount: dom.galleryCount,
  lightboxController,
  getCurrentSearchQuery: () => currentSearchQuery,
  getFavoritesOnly: () => showFavoritesOnly,
  onDeleteImage: deleteImage,
  onDeleteArtist: deleteArtist,
  onToggleFavorite: toggleFavorite,
});

function refreshFavoritesButton() {
  updateFavoritesOnlyButton(dom.favoritesOnlyButton, showFavoritesOnly);
}

async function loadDefaults() {
  const data = await fetchDefaults();
  if (!data) {
    return;
  }

  dom.clientIdInput.value = data.client_id || "";
  dom.clientSecretInput.value = data.client_secret || "";
  dom.usernamesInput.value = data.usernames || "";

  dom.includeMatureInput.checked = Boolean(data.include_mature);
  dom.allowPreviewInput.checked = Boolean(data.allow_preview);
  dom.seedOnlyInput.checked = Boolean(data.seed_only);
  dom.verboseInput.checked = Boolean(data.verbose);

  dom.startPageInput.value = toInt(data.start_page, 1, 1);
  dom.endPageInput.value = toInt(data.end_page, 3, 1);
  dom.pageSizeInput.value = toInt(data.page_size, 24, 1, 24);
}

async function loadGallery(searchQuery = currentSearchQuery, favoritesOnly = showFavoritesOnly, options = {}) {
  const searching = Boolean(options.searching);
  currentSearchQuery = (searchQuery || "").trim();
  showFavoritesOnly = Boolean(favoritesOnly);
  refreshFavoritesButton();

  if (searching) {
    galleryRenderer.setGallerySearching(true);
  }

  try {
    const data = await fetchGallery(currentSearchQuery, showFavoritesOnly);
    galleryRenderer.render(data.groups || [], data.count || 0, { animateResults: searching });
  } finally {
    if (searching) {
      galleryRenderer.setGallerySearching(false);
    }
  }
}

async function deleteImage(relativePath, cardElement = null) {
  const confirmed = window.confirm(`Delete image?\n${relativePath}`);
  if (!confirmed) {
    return;
  }

  if (cardElement) {
    cardElement.classList.add("is-deleting");
    await wait(220);
  }

  jobController.setTransientLoading(true);
  jobController.setStatus("Deleting image...", "");
  try {
    const { response, data } = await postJson("/api/delete/image", { relative_path: relativePath }, "POST");
    if (!response.ok || !data.ok) {
      if (cardElement) {
        cardElement.classList.remove("is-deleting");
      }
      jobController.setStatus(data.message || "Failed to delete image.", "error");
      return;
    }

    jobController.setStatus("Image deleted.", "success");
    lightboxController.close();
    await loadGallery(currentSearchQuery, showFavoritesOnly);
  } catch (error) {
    if (cardElement) {
      cardElement.classList.remove("is-deleting");
    }
    jobController.setStatus(error.message || "Failed to delete image.", "error");
  } finally {
    jobController.setTransientLoading(false);
  }
}

async function deleteArtist(artist) {
  const confirmed = window.confirm(`Delete all images for artist "${artist}"?`);
  if (!confirmed) {
    return;
  }

  jobController.setTransientLoading(true);
  jobController.setStatus(`Deleting all images for ${artist}...`, "");
  try {
    const { response, data } = await postJson("/api/delete/artist", { artist }, "POST");
    if (!response.ok || !data.ok) {
      jobController.setStatus(data.message || "Failed to delete artist images.", "error");
      return;
    }

    jobController.setStatus(`Deleted images for ${artist}.`, "success");
    lightboxController.close();
    await loadGallery(currentSearchQuery, showFavoritesOnly);
  } catch (error) {
    jobController.setStatus(error.message || "Failed to delete artist images.", "error");
  } finally {
    jobController.setTransientLoading(false);
  }
}

async function toggleFavorite(relativePath, isFavorite, triggerButton = null) {
  const cardElement = triggerButton ? triggerButton.closest(".card") : null;
  const previousFavoriteState = triggerButton ? triggerButton.classList.contains("is-favorite") : false;

  if (triggerButton) {
    triggerButton.classList.add("is-toggling");
    triggerButton.classList.toggle("is-favorite", isFavorite);
  }

  jobController.setTransientLoading(true);
  jobController.setStatus(isFavorite ? "Marking favorite..." : "Removing favorite...", "");
  try {
    const { response, data } = await postJson(
      "/api/favorite/image",
      { relative_path: relativePath, is_favorite: isFavorite },
      "PATCH"
    );

    if (!response.ok || !data.ok) {
      if (triggerButton) {
        triggerButton.classList.toggle("is-favorite", previousFavoriteState);
      }
      jobController.setStatus(data.message || "Failed to update favorite.", "error");
      return;
    }

    if (cardElement) {
      cardElement.classList.add("favorite-flash");
      await wait(220);
      cardElement.classList.remove("favorite-flash");
    }

    jobController.setStatus(isFavorite ? "Marked as favorite." : "Removed from favorites.", "success");
    await loadGallery(currentSearchQuery, showFavoritesOnly);
  } catch (error) {
    if (triggerButton) {
      triggerButton.classList.toggle("is-favorite", previousFavoriteState);
    }
    jobController.setStatus(error.message || "Failed to update favorite.", "error");
  } finally {
    if (triggerButton) {
      triggerButton.classList.remove("is-toggling");
    }
    jobController.setTransientLoading(false);
  }
}

dom.form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const client_id = dom.clientIdInput.value.trim();
  const client_secret = dom.clientSecretInput.value.trim();
  const usernames = dom.usernamesInput.value.trim();

  const start_page = toInt(dom.startPageInput.value, 1, 1);
  const end_page = toInt(dom.endPageInput.value, start_page, 1);
  const page_size = toInt(dom.pageSizeInput.value, 24, 1, 24);

  if (!client_id || !client_secret || !usernames) {
    jobController.setStatus("Please fill all fields before starting.", "error");
    return;
  }

  if (end_page < start_page) {
    jobController.setStatus("End page must be greater than or equal to start page.", "error");
    return;
  }

  jobController.setStartRequestLoading(true);
  jobController.setStatus("Starting download job...", "");

  try {
    const { response, data } = await postJson("/api/run", {
      client_id,
      client_secret,
      usernames,
      include_mature: dom.includeMatureInput.checked,
      allow_preview: dom.allowPreviewInput.checked,
      seed_only: dom.seedOnlyInput.checked,
      verbose: dom.verboseInput.checked,
      start_page,
      end_page,
      page_size,
    });

    if (response.status === 202 && data.ok) {
      jobController.onJobStarted(data.job);
      return;
    }

    if (response.status === 409) {
      jobController.onRunConflict(data.job, data.message);
      return;
    }

    const message = data.message || (data.errors && data.errors[0]) || "Download job failed.";
    jobController.setStatus(message, "error");
  } catch (error) {
    jobController.setStatus(error.message || "Unexpected error.", "error");
  } finally {
    jobController.setStartRequestLoading(false);
  }
});

if (dom.searchInput) {
  dom.searchInput.addEventListener("input", () => {
    if (searchDebounceTimer) {
      window.clearTimeout(searchDebounceTimer);
    }

    searchDebounceTimer = window.setTimeout(async () => {
      try {
        await loadGallery(dom.searchInput.value, showFavoritesOnly, { searching: true });
      } catch (error) {
        jobController.setStatus(error.message || "Failed to load gallery.", "error");
      }
    }, 240);
  });
}

if (dom.favoritesOnlyButton) {
  dom.favoritesOnlyButton.addEventListener("click", async () => {
    showFavoritesOnly = !showFavoritesOnly;
    refreshFavoritesButton();
    try {
      await loadGallery(currentSearchQuery, showFavoritesOnly, { searching: true });
    } catch (error) {
      jobController.setStatus(error.message || "Failed to load gallery.", "error");
    }
  });
}

dom.themeToggle.addEventListener("click", () => toggleTheme(dom.themeToggle));

dom.lightboxClose.addEventListener("click", () => lightboxController.close());
dom.lightboxPrev.addEventListener("click", () => lightboxController.step(-1));
dom.lightboxNext.addEventListener("click", () => lightboxController.step(1));
dom.lightbox.addEventListener("click", lightboxController.onOverlayClick);
document.addEventListener("keydown", lightboxController.onKeyDown);

async function initializePage() {
  initializeTheme(dom.themeToggle);
  refreshFavoritesButton();

  try {
    await loadDefaults();
  } catch (_error) {
    // If defaults fail, user can still type credentials manually.
  }

  await jobController.syncStatus({ refreshGalleryOnFinish: false, allowFinishedStatus: false });

  try {
    await loadGallery();
  } catch (error) {
    jobController.setStatus(error.message || "Failed to load gallery.", "error");
  }
}

window.addEventListener("beforeunload", () => {
  jobController.dispose();
});

initializePage();
