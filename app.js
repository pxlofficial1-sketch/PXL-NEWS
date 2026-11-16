"use strict";

function setupNavigation() {
  const toggle = document.querySelector(".nav-toggle");
  const navigation = document.getElementById("primary-nav");
  if (!toggle || !navigation) return;

  const setOpen = open => {
    toggle.setAttribute("aria-expanded", String(open));
    navigation.dataset.open = String(open);
  };

  toggle.addEventListener("click", () => {
    setOpen(toggle.getAttribute("aria-expanded") !== "true");
  });

  navigation.addEventListener("click", event => {
    if (event.target.closest("a")) setOpen(false);
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
      setOpen(false);
      toggle.focus();
    }
  });

  if (window.matchMedia) {
    const mobileQuery = window.matchMedia("(max-width: 700px)");
    mobileQuery.addEventListener?.("change", event => {
      if (!event.matches) setOpen(false);
    });
  }
}

function formatDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return "Date unavailable";
  }

  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value) {
    return "Date unavailable";
  }

  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric"
  }).format(date);
}

function compareArticlesByDate(a, b) {
  const dateA = Date.parse(`${a.date || ""}T00:00:00`) || 0;
  const dateB = Date.parse(`${b.date || ""}T00:00:00`) || 0;
  return dateB - dateA;
}

function createArticleCard(article, featured = false) {
  const card = document.createElement("article");
  card.className = featured ? "news-card featured-card" : "news-card";

  const meta = document.createElement("div");
  meta.className = "news-card-meta";

  const category = document.createElement("span");
  category.className = "news-category";
  category.textContent = article.category || "General";

  const date = document.createElement("time");
  date.dateTime = article.date || "";
  date.textContent = formatDate(article.date);
  meta.append(category, date);

  const heading = document.createElement("h3");
  const link = document.createElement("a");
  link.href = `article.html?id=${encodeURIComponent(article.id || "")}`;
  link.textContent = article.title || "Untitled article";
  heading.appendChild(link);

  const description = document.createElement("p");
  description.className = "news-card-description";
  description.textContent = article.description || "No description available.";

  card.append(meta, heading, description);
  return card;
}

function showState(container, message, state = "") {
  const notice = document.createElement("p");
  notice.className = `news-state ${state}`.trim();
  notice.textContent = message;
  container.replaceChildren(notice);
  container.setAttribute("aria-busy", "false");
}

async function setupHomepage() {
  const featuredContainer = document.getElementById("featured-news");
  const latestContainer = document.getElementById("latest-news");
  const searchInput = document.getElementById("news-search");
  const filtersContainer = document.getElementById("category-filters");
  const resultCount = document.getElementById("result-count");
  if (!featuredContainer || !latestContainer) return;

  try {
    const response = await fetch("news.json");
    if (!response.ok) throw new Error(`News request failed with status ${response.status}`);

    const data = await response.json();
    if (!Array.isArray(data) || data.some(article => !article || typeof article !== "object" || Array.isArray(article))) {
      throw new Error("News data must be a list of article objects");
    }

    const articles = [...data].sort(compareArticlesByDate);
    if (articles.length === 0) {
      showState(featuredContainer, "No articles published yet.", "empty");
      showState(latestContainer, "No articles published yet.", "empty");
      filtersContainer?.setAttribute("aria-busy", "false");
      if (searchInput) searchInput.disabled = true;
      return;
    }

    const explicitlyFeatured = articles.filter(article => article.featured === true);
    const featuredArticles = explicitlyFeatured.length ? explicitlyFeatured : [articles[0]];
    featuredContainer.replaceChildren(...featuredArticles.map(article => createArticleCard(article, true)));
    featuredContainer.setAttribute("aria-busy", "false");

    const categories = [...new Set(articles.map(article => article.category).filter(category => typeof category === "string" && category.trim()))]
      .sort((a, b) => a.localeCompare(b));
    let activeCategory = "All";

    const renderLatest = () => {
      const query = searchInput?.value.trim().toLocaleLowerCase() || "";
      const filtered = articles.filter(article => {
        const matchesCategory = activeCategory === "All" || article.category === activeCategory;
        const searchableText = [article.title, article.description, article.category]
          .filter(value => typeof value === "string")
          .join(" ")
          .toLocaleLowerCase();
        return matchesCategory && searchableText.includes(query);
      });

      if (resultCount) {
        resultCount.textContent = `${filtered.length} ${filtered.length === 1 ? "article" : "articles"}`;
      }

      if (filtered.length === 0) {
        showState(latestContainer, "No articles match your search and category. Try changing your search or filter.", "empty");
        return;
      }

      latestContainer.replaceChildren(...filtered.map(article => createArticleCard(article)));
      latestContainer.setAttribute("aria-busy", "false");
    };

    if (filtersContainer) {
      const filterButtons = ["All", ...categories].map(category => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "filter-button";
        button.textContent = category;
        button.setAttribute("aria-pressed", String(category === activeCategory));
        button.addEventListener("click", () => {
          activeCategory = category;
          filtersContainer.querySelectorAll(".filter-button").forEach(filter => {
            filter.setAttribute("aria-pressed", String(filter === button));
          });
          renderLatest();
        });
        return button;
      });
      filtersContainer.replaceChildren(...filterButtons);
      filtersContainer.setAttribute("aria-busy", "false");
    }

    if (searchInput) {
      searchInput.disabled = false;
      searchInput.addEventListener("input", renderLatest);
    }
    renderLatest();
  } catch (error) {
    console.error("PXL News error:", error);
    showState(featuredContainer, "Unable to load featured news.", "error");
    showState(latestContainer, "Unable to load news. Please try again later.", "error");
    filtersContainer?.setAttribute("aria-busy", "false");
  }
}

function showArticleState(container, message, state = "error") {
  const notice = document.createElement("p");
  notice.className = `news-state ${state}`;
  notice.textContent = message;
  const homeLink = document.createElement("a");
  homeLink.className = "article-source";
  homeLink.href = "./";
  homeLink.textContent = "Return to all news";
  container.replaceChildren(notice, homeLink);
  container.setAttribute("aria-busy", "false");
}

async function setupArticlePage() {
  const container = document.getElementById("article");
  if (!container) return;

  const articleId = new URLSearchParams(window.location.search).get("id");
  if (!articleId) {
    showArticleState(container, "Article not found. No article ID was provided.", "empty");
    return;
  }

  try {
    const response = await fetch("news.json");
    if (!response.ok) throw new Error(`News request failed with status ${response.status}`);
    const articles = await response.json();
    if (!Array.isArray(articles)) throw new Error("News data must be a list of articles");

    const article = articles.find(item => item && item.id === articleId);
    if (!article) {
      showArticleState(container, "Article not found. It may have been removed or the link may be incorrect.", "empty");
      return;
    }

    document.title = `${article.title || "Article"} | PXL Tech News`;

    const category = document.createElement("p");
    category.className = "news-category";
    category.textContent = article.category || "General";

    const heading = document.createElement("h1");
    heading.textContent = article.title || "Untitled article";

    const meta = document.createElement("div");
    meta.className = "article-meta";
    const date = document.createElement("time");
    date.dateTime = article.date || "";
    date.textContent = formatDate(article.date);
    meta.append(category, date);

    const description = document.createElement("p");
    description.className = "article-description";
    description.textContent = article.description || "No description is available for this article.";

    const content = [heading, meta, description];
    if (typeof article.source === "string" && article.source.trim()) {
      try {
        const sourceUrl = new URL(article.source);
        if (sourceUrl.protocol === "http:" || sourceUrl.protocol === "https:") {
          const source = document.createElement("a");
          source.className = "article-source";
          source.href = sourceUrl.href;
          source.textContent = "Read the original source ↗";
          source.target = "_blank";
          source.rel = "noopener noreferrer";
          content.push(source);
        }
      } catch {
        // Ignore malformed source links while keeping the article readable.
      }
    }

    container.replaceChildren(...content);
    container.setAttribute("aria-busy", "false");
  } catch (error) {
    console.error("PXL article error:", error);
    showArticleState(container, "Unable to load this article right now. Please try again later.");
  }
}

setupNavigation();
setupHomepage();
setupArticlePage();
