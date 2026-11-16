const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");
const vm = require("node:vm");
const { webcrypto } = require("node:crypto");

const publisherHtml = fs.readFileSync("publisher.html", "utf8");
const publisherScript = publisherHtml.match(/<script>([\s\S]*?)<\/script>/)[1];
const storedArticles = JSON.parse(fs.readFileSync("news.json", "utf8"));

class FakeElement {
  constructor(value = "") {
    this.value = value;
    this.listeners = {};
    this.textContent = "";
    this.disabled = false;
  }

  addEventListener(type, handler) {
    (this.listeners[type] ||= []).push(handler);
  }

  select() {}
}

function loadPublisher() {
  const ids = [
    "title", "category", "description", "source", "newsForm",
    "previewTitle", "previewCategory", "previewDescription", "previewDate",
    "output", "status", "copyButton"
  ];
  const elements = Object.fromEntries(ids.map(id => [
    id,
    new FakeElement(id === "category" ? "AI" : "")
  ]));
  const context = vm.createContext({
    document: { getElementById: id => elements[id] },
    fetch: async () => ({ ok: true, json: async () => storedArticles }),
    URL,
    Date,
    Set,
    Object,
    JSON,
    Math,
    crypto: webcrypto,
    console
  });
  vm.runInContext(publisherScript, context);
  return { context, elements };
}

function validArticle(overrides = {}) {
  return {
    id: "valid-story-1",
    title: "A headline",
    category: "AI",
    description: "An article description",
    date: "2026-11-16",
    source: "https://example.com/story",
    ...overrides
  };
}

test("publisher accepts a valid article and validates the existing database", async () => {
  const { context } = loadPublisher();
  await vm.runInContext("databaseCheck", context);
  assert.equal(context.validateArticle(validArticle()), "");
  assert.equal(vm.runInContext("databaseAvailable", context), true);
});

test("publisher rejects malformed IDs, dates, fields, categories, and URLs", () => {
  const { context } = loadPublisher();
  const invalidArticles = [
    validArticle({ id: "Upper_Case" }),
    validArticle({ title: " " }),
    validArticle({ category: "Unknown" }),
    validArticle({ date: "2026-02-30" }),
    validArticle({ date: "0000-01-01" }),
    validArticle({ source: "javascript:alert(1)" }),
    validArticle({ source: "https://name:password@example.com/" }),
    validArticle({ source: "https://:@example.com/" }),
    validArticle({ source: "https://example.com\\@example.org/" })
  ];
  for (const article of invalidArticles) {
    assert.notEqual(context.validateArticle(article), "", JSON.stringify(article));
  }
});

test("publisher checks article IDs against news.json", async () => {
  const { context } = loadPublisher();
  await vm.runInContext("databaseCheck", context);
  const existingIds = vm.runInContext("existingIds", context);
  assert.match(context.validateArticle(validArticle({ id: "welcome" }), existingIds), /already exists/);
});
