/* Favorites stay in this browser. Archived paper content remains server-rendered. */
(function () {
  "use strict";

  const ID_PATTERN = /^(?:\d{4}\.\d{4,5}|[A-Za-z][A-Za-z.\-]*\/\d{7})$/;
  const BUTTON_SELECTOR = "button.favorite-toggle[data-favorite-id]";

  function storagePrefix(scriptURL) {
    return "math-ds-favorites:v1:" + new URL("../", scriptURL).href + ":";
  }

  function createStore(storage, prefix) {
    function keyFor(id) {
      if (!ID_PATTERN.test(id)) throw new TypeError("Invalid arXiv identifier");
      return prefix + encodeURIComponent(id);
    }

    return {
      read() {
        const favorites = new Map();
        let corrupt = false;
        for (let index = 0; index < storage.length; index += 1) {
          const key = storage.key(index);
          if (typeof key !== "string" || !key.startsWith(prefix)) continue;
          let id;
          try {
            id = decodeURIComponent(key.slice(prefix.length));
          } catch (_) {
            corrupt = true;
            continue;
          }
          if (!ID_PATTERN.test(id) || keyFor(id) !== key) {
            corrupt = true;
            continue;
          }
          const raw = storage.getItem(key);
          if (raw === null) continue; // Another tab may have removed this key.
          const timestamp = Number(raw);
          if (!/^[1-9]\d*$/.test(raw) || !Number.isSafeInteger(timestamp)) {
            corrupt = true;
            continue;
          }
          favorites.set(id, timestamp);
        }
        return { favorites, corrupt };
      },
      add(id, timestamp) {
        if (!Number.isSafeInteger(timestamp) || timestamp <= 0) {
          throw new TypeError("Invalid favorite timestamp");
        }
        storage.setItem(keyFor(id), String(timestamp));
      },
      remove(id) {
        storage.removeItem(keyFor(id));
      },
      owns(key) {
        return key === null || (typeof key === "string" && key.startsWith(prefix));
      },
    };
  }

  function initializeFavorites(win, doc, scriptURL) {
    const list = doc.querySelector("[data-favorites-list]");
    const empty = doc.querySelector("[data-favorites-empty]");
    const count = doc.querySelector("[data-favorites-count]");
    const loading = doc.querySelector("[data-favorites-loading]");
    const status = doc.querySelector(".favorites-status[role=status]");
    const catalog = doc.getElementById("favorites-catalog");
    const catalogItems = new Map();
    if (catalog && catalog.content) {
      for (const item of catalog.content.querySelectorAll(".favorite-item[data-favorite-id]")) {
        const id = item.dataset.favoriteId;
        if (ID_PATTERN.test(id) && !catalogItems.has(id)) catalogItems.set(id, item);
      }
    }

    let storage;
    let store;
    let favorites = new Map();

    function announce(message) {
      if (status) status.textContent = message;
    }

    function updateButtons(unavailable) {
      for (const button of doc.querySelectorAll(BUTTON_SELECTOR)) {
        const id = button.dataset.favoriteId;
        const saved = favorites.has(id);
        button.hidden = false;
        button.disabled = unavailable || !ID_PATTERN.test(id);
        button.setAttribute("aria-pressed", String(saved));
        button.setAttribute("title", saved ? "Remove from favorites" : "Add to favorites");
        const icon = button.querySelector("[data-favorite-icon]");
        if (icon) icon.textContent = saved ? "★" : "☆";
      }
    }

    function focusedRow(button) {
      if (!list || !button || !list.contains(button)) return null;
      const rows = Array.from(list.querySelectorAll(".favorite-item[data-favorite-id]"));
      const index = rows.findIndex((row) => row.contains(button));
      if (index < 0) return null;
      const path = [];
      for (let child = button; child !== rows[index]; child = child.parentElement) {
        path.unshift(Array.from(child.parentElement.children).indexOf(child));
      }
      return { id: rows[index].dataset.favoriteId, index, path };
    }

    function renderHome(focus) {
      if (!list) return 0;
      const sorted = Array.from(favorites).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
      const rows = sorted.filter(([id]) => catalogItems.has(id)).map(([id]) => catalogItems.get(id).cloneNode(true));
      list.replaceChildren(...rows);
      if (empty) empty.hidden = rows.length !== 0;
      if (count) {
        count.hidden = false;
        count.textContent = rows.length + " saved paper" + (rows.length === 1 ? "" : "s");
      }
      if (focus) {
        const sameRow = rows.find((item) => item.dataset.favoriteId === focus.id);
        const row = sameRow || rows[Math.min(focus.index, rows.length - 1)];
        const target = sameRow ? focus.path.reduce((node, index) => node.children[index], sameRow)
          : row ? row.querySelector(BUTTON_SELECTOR) : doc.getElementById("favorites-heading");
        // Controls must be visible before focus can move to a newly cloned row.
        if (target) {
          target.hidden = false;
          target.focus();
        }
      }
      return favorites.size - rows.length;
    }

    function unavailable(message) {
      if (loading) loading.hidden = true;
      if (empty) empty.hidden = true;
      updateButtons(true);
      announce(message);
    }

    function refresh(message, focus) {
      try {
        const snapshot = store.read();
        favorites = snapshot.favorites;
        const missing = renderHome(focus || focusedRow(doc.activeElement));
        updateButtons(false);
        if (loading) loading.hidden = true;
        const notices = [];
        if (message) notices.push(message);
        if (snapshot.corrupt) notices.push("Some saved favorites could not be read. Other favorites remain available.");
        if (missing) notices.push("Some saved papers are not in this archive yet. Reload to check for them.");
        announce(notices.join(" "));
        return true;
      } catch (_) {
        unavailable("Favorites are unavailable because this browser could not read local storage.");
        return false;
      }
    }

    try {
      storage = win.localStorage;
      store = createStore(storage, storagePrefix(scriptURL));
    } catch (_) {
      unavailable("Favorites are unavailable because this browser is blocking local storage.");
      return;
    }

    doc.addEventListener("click", function (event) {
      const button = event.target && event.target.closest ? event.target.closest(BUTTON_SELECTOR) : null;
      if (!button || button.disabled) return;
      const id = button.dataset.favoriteId;
      const focus = focusedRow(button);
      try {
        const saved = store.read().favorites.has(id);
        if (saved) store.remove(id);
        else store.add(id, Date.now());
        refresh(saved ? "Removed from favorites." : "Saved to favorites.", focus);
      } catch (_) {
        // Refresh from persisted data; never display an optimistic saved state.
        refresh("Could not update favorites. Your browser may be blocking storage or have no space available.", focus);
      }
    });

    win.addEventListener("storage", function (event) {
      if ((!event.storageArea || event.storageArea === storage) && store.owns(event.key)) refresh();
    });
    win.addEventListener("pageshow", function () { refresh(); });
    refresh();
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { storagePrefix, createStore, initializeFavorites };
  }
  if (typeof document !== "undefined" && document.currentScript) {
    initializeFavorites(window, document, document.currentScript.src);
  }
}());
