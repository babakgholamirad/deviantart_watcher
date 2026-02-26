const THEME_STORAGE_KEY = "da_watcher_theme";

const form = document.getElementById("downloadForm");
const startButton = document.getElementById("startButton");
const spinner = document.getElementById("loadingSpinner");
const statusText = document.getElementById("statusText");
const emptyText = document.getElementById("emptyText");
const galleryCount = document.getElementById("galleryCount");
const artistGroups = document.getElementById("artistGroups");

const themeToggle = document.getElementById("themeToggle");

const clientIdInput = document.getElementById("clientId");
const clientSecretInput = document.getElementById("clientSecret");
const usernamesInput = document.getElementById("usernames");

const startPageInput = document.getElementById("startPage");
const endPageInput = document.getElementById("endPage");
const pageSizeInput = document.getElementById("pageSize");

const includeMatureInput = document.getElementById("includeMature");
const allowPreviewInput = document.getElementById("allowPreview");
const seedOnlyInput = document.getElementById("seedOnly");
const verboseInput = document.getElementById("verbose");

const lightbox = document.getElementById("lightbox");
const lightboxImage = document.getElementById("lightboxImage");
const lightboxCaption = document.getElementById("lightboxCaption");
const lightboxClose = document.getElementById("lightboxClose");
const lightboxPrev = document.getElementById("lightboxPrev");
const lightboxNext = document.getElementById("lightboxNext");

let lightboxItems = [];
let currentLightboxIndex = -1;

function toInt(value, fallback, minValue, maxValue = null) {
  const parsed = Number.parseInt(String(value), 10);
  let result = Number.isNaN(parsed) ? fallback : parsed;

  if (result < minValue) {
    result = minValue;
  }
  if (maxValue !== null && result > maxValue) {
    result = maxValue;
  }
  return result;
}

function getSystemTheme() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme) {
  const resolved = theme === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", resolved);
  themeToggle.textContent = resolved === "dark" ? "Light" : "Dark";
}

function initializeTheme() {
  const saved = localStorage.getItem(THEME_STORAGE_KEY);
  if (saved === "dark" || saved === "light") {
    applyTheme(saved);
    return;
  }
  applyTheme(getSystemTheme());
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  const next = current === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_STORAGE_KEY, next);
  applyTheme(next);
}

function setLoading(isLoading) {
  startButton.disabled = isLoading;
  spinner.classList.toggle("show", isLoading);
}

function setStatus(message, type = "") {
  statusText.textContent = message;
  statusText.classList.remove("error", "success");
  if (type) {
    statusText.classList.add(type);
  }
}

function updateLightboxNavState() {
  const atStart = currentLightboxIndex <= 0;
  const atEnd = currentLightboxIndex >= lightboxItems.length - 1;
  lightboxPrev.disabled = atStart;
  lightboxNext.disabled = atEnd;
}

function openLightboxAt(index) {
  if (!lightboxItems.length || index < 0 || index >= lightboxItems.length) {
    return;
  }

  currentLightboxIndex = index;
  const item = lightboxItems[currentLightboxIndex];
  lightboxImage.src = item.url;
  lightboxCaption.textContent = item.caption;
  updateLightboxNavState();

  lightbox.classList.add("show");
  lightbox.setAttribute("aria-hidden", "false");
}

function stepLightbox(delta) {
  if (!lightbox.classList.contains("show")) {
    return;
  }

  const nextIndex = currentLightboxIndex + delta;
  if (nextIndex < 0 || nextIndex >= lightboxItems.length) {
    return;
  }
  openLightboxAt(nextIndex);
}

function closeLightbox() {
  lightbox.classList.remove("show");
  lightbox.setAttribute("aria-hidden", "true");
  lightboxImage.src = "";
  lightboxCaption.textContent = "";
  currentLightboxIndex = -1;
  lightboxPrev.disabled = true;
  lightboxNext.disabled = true;
}

function renderGallery(groups, totalCount) {
  artistGroups.innerHTML = "";
  lightboxItems = [];
  galleryCount.textContent = `${totalCount} image(s)`;

  if (!totalCount) {
    emptyText.style.display = "block";
    return;
  }

  emptyText.style.display = "none";

  groups.forEach((group) => {
    const details = document.createElement("details");
    details.className = "artist-group";
    details.open = true;

    const summary = document.createElement("summary");
    summary.innerHTML = `<span>${group.artist}</span><span class="artist-count">${group.count} image(s)</span>`;

    const grid = document.createElement("div");
    grid.className = "artist-grid";

    group.images.forEach((image) => {
      const card = document.createElement("article");
      card.className = "card";

      const img = document.createElement("img");
      const src = `${image.url}?v=${encodeURIComponent(image.mtime)}`;
      img.src = src;
      img.alt = image.name;
      img.loading = "lazy";

      const meta = document.createElement("div");
      meta.className = "card-meta";
      meta.textContent = image.relative_path;

      const itemIndex = lightboxItems.length;
      lightboxItems.push({
        url: src,
        caption: image.relative_path,
      });

      card.addEventListener("click", () => {
        openLightboxAt(itemIndex);
      });

      card.appendChild(img);
      card.appendChild(meta);
      grid.appendChild(card);
    });

    details.appendChild(summary);
    details.appendChild(grid);
    artistGroups.appendChild(details);
  });
}

async function loadDefaults() {
  const response = await fetch("/api/defaults", { cache: "no-store" });
  if (!response.ok) {
    return;
  }

  const data = await response.json();
  clientIdInput.value = data.client_id || "";
  clientSecretInput.value = data.client_secret || "";
  usernamesInput.value = data.usernames || "";

  includeMatureInput.checked = Boolean(data.include_mature);
  allowPreviewInput.checked = Boolean(data.allow_preview);
  seedOnlyInput.checked = Boolean(data.seed_only);
  verboseInput.checked = Boolean(data.verbose);

  startPageInput.value = toInt(data.start_page, 1, 1);
  endPageInput.value = toInt(data.end_page, 3, 1);
  pageSizeInput.value = toInt(data.page_size, 24, 1, 24);
}

async function loadGallery() {
  const response = await fetch("/api/gallery", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to load gallery.");
  }
  const data = await response.json();
  renderGallery(data.groups || [], data.count || 0);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const client_id = clientIdInput.value.trim();
  const client_secret = clientSecretInput.value.trim();
  const usernames = usernamesInput.value.trim();

  const start_page = toInt(startPageInput.value, 1, 1);
  const end_page = toInt(endPageInput.value, start_page, 1);
  const page_size = toInt(pageSizeInput.value, 24, 1, 24);

  if (!client_id || !client_secret || !usernames) {
    setStatus("Please fill all fields before starting.", "error");
    return;
  }

  if (end_page < start_page) {
    setStatus("End page must be greater than or equal to start page.", "error");
    return;
  }

  setLoading(true);
  setStatus("Downloading...", "");

  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_id,
        client_secret,
        usernames,
        include_mature: includeMatureInput.checked,
        allow_preview: allowPreviewInput.checked,
        seed_only: seedOnlyInput.checked,
        verbose: verboseInput.checked,
        start_page,
        end_page,
        page_size,
      }),
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
      const message = data.message || (data.errors && data.errors[0]) || "Download job failed.";
      setStatus(message, "error");
    } else {
      const stats = data.stats || {};
      const pagination = data.pagination || {};
      setStatus(
        `Completed. downloaded=${stats.downloaded ?? 0}, new=${stats.new_items ?? 0}, skipped=${stats.skipped ?? 0}, pages=${pagination.start_page ?? start_page}-${pagination.end_page ?? end_page}`,
        "success"
      );
    }

    await loadGallery();
  } catch (error) {
    setStatus(error.message || "Unexpected error.", "error");
  } finally {
    setLoading(false);
  }
});

themeToggle.addEventListener("click", toggleTheme);

lightboxClose.addEventListener("click", closeLightbox);
lightboxPrev.addEventListener("click", () => stepLightbox(-1));
lightboxNext.addEventListener("click", () => stepLightbox(1));

lightbox.addEventListener("click", (event) => {
  if (event.target === lightbox) {
    closeLightbox();
  }
});

document.addEventListener("keydown", (event) => {
  if (!lightbox.classList.contains("show")) {
    return;
  }

  if (event.key === "Escape") {
    closeLightbox();
  } else if (event.key === "ArrowLeft") {
    stepLightbox(-1);
  } else if (event.key === "ArrowRight") {
    stepLightbox(1);
  }
});

async function initializePage() {
  initializeTheme();

  try {
    await loadDefaults();
  } catch (_error) {
    // If defaults fail, user can still type credentials manually.
  }

  try {
    await loadGallery();
  } catch (error) {
    setStatus(error.message || "Failed to load gallery.", "error");
  }
}

initializePage();
