"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { storagePrefix, createStore, initializeFavorites } = require("../static/favorites.js");

const SCRIPT = "https://example.test/daily-math-ds-digest/assets/favorites.js";
const PREFIX = storagePrefix(SCRIPT);
const A = "2609.00001";
const B = "2609.00002";
const C = "math/1234567";

class MemoryStorage {
  constructor() {
    this.values = new Map();
    this.failRead = false;
    this.failWrite = false;
  }
  get length() {
    if (this.failRead) throw new Error("Storage is blocked");
    return this.values.size;
  }
  key(index) { return Array.from(this.values.keys())[index] ?? null; }
  getItem(key) {
    if (this.failRead) throw new Error("Storage is blocked");
    return this.values.get(key) ?? null;
  }
  setItem(key, value) {
    if (this.failWrite) throw new Error("Quota exceeded");
    this.values.set(key, String(value));
  }
  removeItem(key) {
    if (this.failWrite) throw new Error("Storage is blocked");
    this.values.delete(key);
  }
}

// A small DOM contract fixture keeps these tests dependency-free. The real
// browser integration checks the generated HTML, keyboard behavior and layout.
class Element {
  constructor(tag, attrs = {}, children = []) {
    this.tagName = tag.toLowerCase();
    this.attributes = { ...attrs };
    this.dataset = {};
    for (const [name, value] of Object.entries(attrs)) {
      if (name.startsWith("data-")) {
        this.dataset[name.slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase())] = value;
      }
    }
    this.children = [];
    this.hidden = Object.hasOwn(attrs, "hidden");
    this.disabled = false;
    this.textContent = "";
    this.parentElement = null;
    this.ownerDocument = null;
    this.replacements = 0;
    this.replaceChildren(...children);
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  matches(selector) {
    const tag = selector.match(/^[a-z]+/);
    if (tag && this.tagName !== tag[0]) return false;
    for (const [, name] of selector.matchAll(/\.([\w-]+)/g)) {
      if (!(this.attributes.class || "").split(/\s+/).includes(name)) return false;
    }
    for (const [, name, value] of selector.matchAll(/\[([\w-]+)(?:=([^\]]+))?\]/g)) {
      if (!Object.hasOwn(this.attributes, name)) return false;
      if (value !== undefined && this.attributes[name] !== value.replace(/^['"]|['"]$/g, "")) return false;
    }
    return true;
  }
  querySelectorAll(selector) {
    return this.children.flatMap((child) => [
      ...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector),
    ]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; }
  closest(selector) {
    return this.matches(selector) ? this : this.parentElement?.closest(selector) ?? null;
  }
  contains(node) { return this === node || this.children.some((child) => child.contains(node)); }
  attach(doc) {
    this.ownerDocument = doc;
    for (const child of this.children) child.attach(doc);
  }
  replaceChildren(...children) {
    for (const child of this.children) child.parentElement = null;
    this.children = children;
    for (const child of children) {
      child.parentElement = this;
      child.attach(this.ownerDocument);
    }
    this.replacements += 1;
  }
  cloneNode(deep) {
    const clone = new Element(this.tagName, this.attributes,
      deep ? this.children.map((child) => child.cloneNode(true)) : []);
    clone.hidden = this.hidden;
    clone.disabled = this.disabled;
    clone.textContent = this.textContent;
    return clone;
  }
  focus() { this.ownerDocument.activeElement = this; }
}

class TestDocument extends Element {
  constructor(children) {
    super("document", {}, children);
    this.listeners = new Map();
    this.activeElement = null;
    this.attach(this);
  }
  getElementById(id) {
    return this.querySelectorAll("[id]").find((element) => element.getAttribute("id") === id) ?? null;
  }
  addEventListener(type, listener) { this.listeners.set(type, listener); }
  click(target) { this.listeners.get("click")?.({ target }); }
}

function button(id) {
  return new Element("button", {
    class: "favorite-toggle", "data-favorite-id": id, "aria-pressed": "false",
    "aria-label": "Favorite arXiv:" + id, type: "button", hidden: "",
  }, [new Element("span", { "data-favorite-icon": "", "aria-hidden": "true" })]);
}

function catalogRow(id) {
  const title = new Element("a", {
    class: "favorite-title", href: "reports/2026-09-17/#paper-" + encodeURIComponent(id),
  }, [new Element("img", { class: "math-formula", src: "data:image/svg+xml;base64,TRUSTED", alt: "x^2" })]);
  title.textContent = "Trusted title " + id;
  return new Element("li", { class: "favorite-item", "data-favorite-id": id }, [
    new Element("div", { class: "paper-title-row" }, [new Element("h3", {}, [title]), button(id)]),
    new Element("p", { class: "authors" }),
  ]);
}

function setup({ storage = new MemoryStorage(), home = false, ids = [A, B, C], denied = false } = {}) {
  const status = new Element("p", { class: "favorites-status", role: "status" });
  const controls = home ? [] : ids.map(button);
  let list, catalog, heading, empty, count, loading;
  if (home) {
    list = new Element("ol", { "data-favorites-list": "" });
    catalog = new Element("template", { id: "favorites-catalog" });
    catalog.content = new Element("fragment", {}, ids.map(catalogRow));
    heading = new Element("h2", { id: "favorites-heading", tabindex: "-1" });
    empty = new Element("p", { "data-favorites-empty": "", hidden: "" });
    count = new Element("span", { "data-favorites-count": "", hidden: "" });
    loading = new Element("p", { "data-favorites-loading": "" });
    controls.push(heading, catalog, list, empty, count, loading);
  }
  const doc = new TestDocument([...controls, status]);
  const listeners = new Map();
  const win = {
    get localStorage() {
      if (denied) throw new Error("Access denied");
      return storage;
    },
    addEventListener(type, listener) { listeners.set(type, listener); },
    emit(type, detail = {}) { listeners.get(type)?.(detail); },
  };
  initializeFavorites(win, doc, SCRIPT);
  const findButton = (id) => doc.querySelectorAll("button.favorite-toggle[data-favorite-id]")
    .find((element) => element.dataset.favoriteId === id);
  return { storage, doc, win, status, list, catalog, heading, empty, count, loading, findButton };
}

test("storage is scoped to the site root, with independent keys and legacy IDs", () => {
  assert.equal(PREFIX, storagePrefix(SCRIPT + "?v=2"));
  assert.notEqual(PREFIX, storagePrefix("https://example.test/another/assets/favorites.js"));
  const storage = new MemoryStorage();
  storage.setItem("unrelated", "keep this");
  const store = createStore(storage, PREFIX);
  store.add(A, 100);
  store.add(C, 200);
  assert.deepEqual(Array.from(store.read().favorites), [[A, 100], [C, 200]]);
  assert.equal(storage.getItem(PREFIX + "math%2F1234567"), "200");
  store.remove(A);
  assert.equal(storage.getItem("unrelated"), "keep this");
  assert.deepEqual(Array.from(store.read().favorites), [[C, 200]]);
  assert.throws(() => store.add("../../other", 300), /Invalid arXiv/);
  assert.throws(() => store.add(A, Infinity), /Invalid favorite timestamp/);
});

test("corrupt records are ignored without deleting valid or unrelated data", () => {
  const storage = new MemoryStorage();
  const store = createStore(storage, PREFIX);
  store.add(A, 100);
  storage.setItem(PREFIX + B, '{"html":"<script>unsafe</script>"}');
  storage.setItem(PREFIX + "%zz", "200");
  storage.setItem(PREFIX + "math/1234567", "300"); // Not the canonical encoded key.
  storage.setItem("another-project:" + C, "400");
  const before = Array.from(storage.values);
  assert.deepEqual(Array.from(store.read().favorites), [[A, 100]]);
  assert.equal(store.read().corrupt, true);
  assert.deepEqual(Array.from(storage.values), before);
});

test("a report star saves, survives reload, and removes a legacy ID", () => {
  const page = setup();
  const star = page.findButton(C);
  assert.equal(star.hidden, false);
  assert.equal(star.getAttribute("aria-pressed"), "false");
  assert.equal(star.getAttribute("title"), "Add to favorites");
  page.doc.click(star.querySelector("[data-favorite-icon]"));
  assert.equal(star.getAttribute("aria-pressed"), "true");
  assert.equal(star.getAttribute("title"), "Remove from favorites");
  assert.equal(star.querySelector("[data-favorite-icon]").textContent, "★");
  assert.equal(star.getAttribute("aria-label"), "Favorite arXiv:" + C);
  assert.match(page.status.textContent, /Saved to favorites/);
  const reloaded = setup({ storage: page.storage });
  assert.equal(reloaded.findButton(C).getAttribute("aria-pressed"), "true");
  reloaded.doc.click(reloaded.findButton(C));
  assert.equal(reloaded.findButton(C).getAttribute("aria-pressed"), "false");
  assert.equal(createStore(page.storage, PREFIX).read().favorites.size, 0);
});

test("homepage clones trusted math titles newest first and retains unknown saved IDs", () => {
  const storage = new MemoryStorage();
  const store = createStore(storage, PREFIX);
  store.add(A, 100);
  store.add(B, 200);
  store.add("2609.99999", 300);
  const page = setup({ storage, home: true });
  assert.deepEqual(page.list.children.map((row) => row.dataset.favoriteId), [B, A]);
  assert.equal(page.count.textContent, "2 saved papers");
  assert.equal(page.empty.hidden, true);
  assert.equal(page.loading.hidden, true);
  const title = page.list.children[0].querySelector("a.favorite-title");
  assert.equal(title.textContent, "Trusted title " + B);
  assert.equal(title.querySelector("img").getAttribute("src"), "data:image/svg+xml;base64,TRUSTED");
  assert.notEqual(page.list.children[0], page.catalog.content.children[1]);
  assert.match(page.status.textContent, /not in this archive yet/);
  assert.equal(store.read().favorites.has("2609.99999"), true);
});

test("removing a homepage row focuses the next, previous, then the section heading", () => {
  const storage = new MemoryStorage();
  const store = createStore(storage, PREFIX);
  store.add(A, 300);
  store.add(B, 200);
  store.add(C, 100);
  const page = setup({ storage, home: true });
  page.findButton(B).focus();
  page.doc.click(page.findButton(B));
  assert.equal(page.doc.activeElement, page.findButton(C));
  assert.equal(page.doc.activeElement.hidden, false);
  page.doc.click(page.findButton(C));
  assert.equal(page.doc.activeElement, page.findButton(A));
  page.doc.click(page.findButton(A));
  assert.equal(page.doc.activeElement, page.heading);
  assert.equal(page.empty.hidden, false);
  assert.equal(page.count.textContent, "0 saved papers");
});

test("storage events and pageshow refresh tabs without reacting to unrelated keys", () => {
  const storage = new MemoryStorage();
  const report = setup({ storage });
  const home = setup({ storage, home: true });
  report.doc.click(report.findButton(A));
  const before = home.list.replacements;
  home.win.emit("storage", { key: "another-project:favorite", storageArea: storage });
  assert.equal(home.list.replacements, before);
  home.win.emit("storage", { key: PREFIX + A, storageArea: storage });
  assert.equal(home.findButton(A).getAttribute("aria-pressed"), "true");
  home.doc.click(home.findButton(A));
  report.win.emit("pageshow");
  assert.equal(report.findButton(A).getAttribute("aria-pressed"), "false");
  report.doc.click(report.findButton(B));
  home.win.emit("storage", { key: PREFIX + B, storageArea: storage });
  storage.values.clear();
  home.win.emit("storage", { key: null, storageArea: storage });
  assert.equal(home.list.children.length, 0);
  assert.equal(home.empty.hidden, false);
});

test("refresh keeps a focused title link on a row that remains in favorites", () => {
  const storage = new MemoryStorage();
  createStore(storage, PREFIX).add(A, 100);
  const page = setup({ storage, home: true });
  const originalLink = page.list.children[0].querySelector("a.favorite-title");
  originalLink.focus();
  page.win.emit("pageshow");
  const refreshedLink = page.list.children[0].querySelector("a.favorite-title");
  assert.notEqual(refreshedLink, originalLink);
  assert.equal(page.doc.activeElement, refreshedLink);
  createStore(storage, PREFIX).add(B, 200);
  page.win.emit("storage", { key: PREFIX + B, storageArea: storage });
  assert.equal(page.doc.activeElement, page.list.children[1].querySelector("a.favorite-title"));
});

test("different tabs saving different papers do not overwrite each other", () => {
  const storage = new MemoryStorage();
  const first = setup({ storage });
  const second = setup({ storage });
  first.doc.click(first.findButton(A));
  second.doc.click(second.findButton(B));
  assert.deepEqual(Array.from(createStore(storage, PREFIX).read().favorites.keys()).sort(), [A, B]);
});

test("failed writes never display a false save or removal", () => {
  const storage = new MemoryStorage();
  const page = setup({ storage });
  storage.failWrite = true;
  page.doc.click(page.findButton(A));
  assert.equal(page.findButton(A).getAttribute("aria-pressed"), "false");
  assert.match(page.status.textContent, /Could not update favorites/);
  storage.failWrite = false;
  page.doc.click(page.findButton(A));
  storage.failWrite = true;
  page.doc.click(page.findButton(A));
  assert.equal(page.findButton(A).getAttribute("aria-pressed"), "true");
  assert.equal(createStore(storage, PREFIX).read().favorites.has(A), true);
  assert.match(page.status.textContent, /Could not update favorites/);
});

test("denied access and read failures show an error and disable controls", () => {
  const denied = setup({ denied: true });
  assert.equal(denied.findButton(A).disabled, true);
  assert.match(denied.status.textContent, /blocking local storage/);
  const page = setup();
  page.storage.failRead = true;
  page.win.emit("pageshow");
  assert.equal(page.findButton(A).disabled, true);
  assert.match(page.status.textContent, /could not read local storage/);
  page.storage.failRead = false;
  page.win.emit("pageshow");
  assert.equal(page.findButton(A).disabled, false);
});

test("corruption is reported while valid homepage favorites remain usable", () => {
  const storage = new MemoryStorage();
  createStore(storage, PREFIX).add(A, 100);
  storage.setItem(PREFIX + B, '<a href="javascript:unsafe">bad</a>');
  const page = setup({ storage, home: true });
  assert.deepEqual(page.list.children.map((row) => row.dataset.favoriteId), [A]);
  assert.match(page.status.textContent, /Some saved favorites could not be read/);
  assert.equal(page.findButton(A).disabled, false);
  page.doc.click(page.findButton(A));
  assert.equal(page.list.children.length, 0);
  assert.equal(storage.getItem(PREFIX + B), '<a href="javascript:unsafe">bad</a>');
});
