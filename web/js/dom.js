/*
Module: dom.js

Variables exported:
- `dom`: one object with references to all page elements used by the app.

How this module works:
- Queries the DOM once at startup so other modules can import `dom` and avoid
  repeated `document.getElementById` calls.
*/

const dom = {
  form: document.getElementById("downloadForm"),
  startButton: document.getElementById("startButton"),
  spinner: document.getElementById("loadingSpinner"),
  statusText: document.getElementById("statusText"),
  emptyText: document.getElementById("emptyText"),
  galleryCount: document.getElementById("galleryCount"),
  artistGroups: document.getElementById("artistGroups"),
  searchInput: document.getElementById("searchInput"),
  favoritesOnlyButton: document.getElementById("favoritesOnlyButton"),
  themeToggle: document.getElementById("themeToggle"),
  clientIdInput: document.getElementById("clientId"),
  clientSecretInput: document.getElementById("clientSecret"),
  usernamesInput: document.getElementById("usernames"),
  startPageInput: document.getElementById("startPage"),
  endPageInput: document.getElementById("endPage"),
  pageSizeInput: document.getElementById("pageSize"),
  includeMatureInput: document.getElementById("includeMature"),
  allowPreviewInput: document.getElementById("allowPreview"),
  seedOnlyInput: document.getElementById("seedOnly"),
  verboseInput: document.getElementById("verbose"),
  lightbox: document.getElementById("lightbox"),
  lightboxImage: document.getElementById("lightboxImage"),
  lightboxCaption: document.getElementById("lightboxCaption"),
  lightboxClose: document.getElementById("lightboxClose"),
  lightboxPrev: document.getElementById("lightboxPrev"),
  lightboxNext: document.getElementById("lightboxNext"),
};

export default dom;
