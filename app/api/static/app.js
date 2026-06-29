const I18N = {
  zh: {
    "nav.home": "首页",
    "nav.mods": "列表",
    "nav.about": "关于",
    "filters.search": "搜索",
    "filters.searchPlaceholder": "mod 名称 / 仓库",
    "filters.category": "分类",
    "filters.all": "全部",
    "filters.l10nStatus": "汉化状态",
    "filters.aiStatus": "AI 状态",
    "table.mod": "模组",
    "table.repo": "仓库",
    "table.stars": "星标",
    "table.categories": "分类",
    "table.requires": "依赖",
    "table.l10n": "当前汉化状态",
    "table.ai": "AI 翻译状态",
    "home.collected": "已经收录",
    "home.localized": "已有汉化",
    "home.aiTranslated": "AI 汉化",
    "home.mods": "mods",
    "home.lastUpdated": "上次更新时间",
    "l10n.none": "无汉化",
    "l10n.partialShort": "部分",
    "l10n.complete": "完全汉化",
    "ai.skippedShort": "跳过",
    "ai.runningShort": "进行中",
    "ai.reviewShort": "待 review",
    "ai.completeShort": "已完成",
    "ai.mergedShort": "已合并",
    "ai.skipped": "跳过",
    "ai.running": "正在汉化",
    "ai.translated_needs_review": "已经汉化（未review）",
    "ai.complete": "完全汉化",
    "ai.merged_upstream": "完全汉化并且 merge到官方仓库",
    "deps.steamodded": "Steamodded",
    "deps.talisman": "Talisman",
    "deps.none": "无",
    "pager.prev": "上一页",
    "pager.next": "下一页",
    "empty.mods": "没有匹配项",
    "empty.reviews": "没有 review 项",
    "admin.review": "审核",
    "admin.current": "当前",
    "admin.suggested": "建议",
    "admin.approve": "通过",
    "admin.reject": "拒绝",
    "background.toggle": "动态背景",
    "about.kicker": "Balatro 模组汉化",
    "about.lead": "一个面向 Balatro 模组的中文汉化索引、自动补全和人工 review 工作台。",
    "about.whatTitle": "Balatro CN 是什么？",
    "about.whatText": "Balatro CN 用来追踪模组仓库、分析本地化状态，并把 AI 生成后仍需要人工判断的翻译集中到一个工作台。",
    "about.featuresTitle": "核心功能",
    "about.featureIndexTitle": "模组索引",
    "about.featureIndexText": "从 balatro-mod-index 读取名称、仓库、星标、分类和依赖信息。",
    "about.featureStatusTitle": "汉化状态",
    "about.featureStatusText": "对比 en/default 与 zh_CN，显示无汉化、部分汉化和完全汉化。",
    "about.featureAiTitle": "AI 流水线",
    "about.featureAiText": "只补缺失 keys，减少重复 API 调用，并把未 review 的结果留给人工确认。",
    "about.featureGithubTitle": "GitHub 流程",
    "about.featureGithubText": "后续可 fork 仓库、提交 zh_CN.lua、发起 PR，并跟踪上游 merge 状态。",
    "about.projectTitle": "项目定位",
    "about.projectText": "这个页面不是模组管理器，而是围绕“中文汉化覆盖率”和“翻译 review”建立的索引与流水线前端。",
    "about.faqTitle": "FAQ",
    "about.faqText": "状态数据来自本地探测报告和数据库。未探测的仓库不会假装已经完成，会保守显示为跳过或无汉化。",
    "about.creditsTitle": "鸣谢",
    "about.creditsText": "视觉方向参考 Balatro 的像素质感；工作流基于本仓库里的翻译、探测、GitHub 和 review 脚本。",
  },
  en: {
    "nav.home": "Home",
    "nav.mods": "Mods",
    "nav.about": "About",
    "filters.search": "Search",
    "filters.searchPlaceholder": "mod name / repository",
    "filters.category": "Category",
    "filters.all": "All",
    "filters.l10nStatus": "Localization",
    "filters.aiStatus": "AI status",
    "table.mod": "Mod",
    "table.repo": "Repository",
    "table.stars": "Stars",
    "table.categories": "Categories",
    "table.requires": "Requires",
    "table.l10n": "Localization",
    "table.ai": "AI translation",
    "home.collected": "Collected",
    "home.localized": "Localized",
    "home.aiTranslated": "AI translated",
    "home.mods": "mods",
    "home.lastUpdated": "Last updated",
    "l10n.none": "No Chinese",
    "l10n.partialShort": "Partial",
    "l10n.complete": "Complete",
    "ai.skippedShort": "Skipped",
    "ai.runningShort": "Running",
    "ai.reviewShort": "Review",
    "ai.completeShort": "Complete",
    "ai.mergedShort": "Merged",
    "ai.skipped": "Skipped",
    "ai.running": "Translating",
    "ai.translated_needs_review": "Translated, needs review",
    "ai.complete": "Complete",
    "ai.merged_upstream": "Complete and merged upstream",
    "deps.steamodded": "Steamodded",
    "deps.talisman": "Talisman",
    "deps.none": "None",
    "pager.prev": "Prev",
    "pager.next": "Next",
    "empty.mods": "No matching mods",
    "empty.reviews": "No review items",
    "admin.review": "Review",
    "admin.current": "Current",
    "admin.suggested": "Suggested",
    "admin.approve": "Approve",
    "admin.reject": "Reject",
    "background.toggle": "Animated BG",
    "about.kicker": "Balatro Mod Localization",
    "about.lead": "A Chinese localization index, AI-assisted updater, and human review workbench for Balatro mods.",
    "about.whatTitle": "What is Balatro CN?",
    "about.whatText": "Balatro CN tracks mod repositories, analyzes localization status, and centralizes AI translations that still need human review.",
    "about.featuresTitle": "Key Features",
    "about.featureIndexTitle": "Mod Index",
    "about.featureIndexText": "Reads names, repositories, stars, categories, and dependency flags from balatro-mod-index.",
    "about.featureStatusTitle": "Localization Status",
    "about.featureStatusText": "Compares en/default with zh_CN and reports no Chinese, partial, or complete coverage.",
    "about.featureAiTitle": "AI Pipeline",
    "about.featureAiText": "Fills only missing keys, reduces repeated API calls, and keeps unreviewed results in a human queue.",
    "about.featureGithubTitle": "GitHub Workflow",
    "about.featureGithubText": "Can grow into fork, zh_CN.lua commit, pull request, and upstream merge tracking.",
    "about.projectTitle": "Project",
    "about.projectText": "This is not a mod manager. It is an index and pipeline UI focused on Chinese localization coverage and review.",
    "about.faqTitle": "FAQ",
    "about.faqText": "Status data comes from local probe reports and the database. Unprobed repositories are not treated as complete.",
    "about.creditsTitle": "Acknowledgements",
    "about.creditsText": "The visual direction follows Balatro's pixel feel; the workflow is built around translation, probe, GitHub, and review scripts in this repo.",
  },
};

const state = {
  route: "home",
  lang: localStorage.getItem("balatro-cn-lang") || "zh",
  mods: {
    page: 1,
    pageSize: 50,
    total: 0,
  },
  reviews: {
    page: 1,
    pageSize: 20,
    total: 0,
    status: "pending",
  },
};

async function api(path, options) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${await response.text()}`);
  }
  return response.json();
}

function t(key) {
  return I18N[state.lang][key] || I18N.zh[key] || key;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function text(value) {
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

function routeFromPath(pathname) {
  if (pathname === "/admin") return "admin";
  if (pathname === "/about") return "about";
  if (pathname === "/mods") return "mods";
  return "home";
}

function applyLanguage() {
  document.documentElement.lang = state.lang === "zh" ? "zh-CN" : "en";
  document.documentElement.dataset.lang = state.lang;
  document.querySelector("#language-select").value = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.placeholder = t(node.dataset.i18nPlaceholder);
  });
}

function setRoute(route, push = true) {
  state.route = route;
  document.body.dataset.route = route;
  document.querySelectorAll(".page").forEach((page) => {
    page.classList.toggle("active", page.dataset.route === route);
  });
  document.querySelectorAll("[data-link]").forEach((link) => {
    link.classList.toggle("active", link.dataset.page === route);
  });
  const path = route === "home" ? "/" : `/${route}`;
  if (push && window.location.pathname !== path) {
    history.pushState({ route }, "", path);
  }
  window.BalatroBackground?.refresh();
  loadCurrent().catch(showError);
}

function showError(error) {
  alert(error.message);
}

function formatDate(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return value;
  return parsed.toLocaleString(state.lang === "zh" ? "zh-CN" : "en-US", { hour12: false });
}

function l10nLabel(item) {
  if (item.localization_status === "partial") {
    return state.lang === "zh"
      ? `汉化部分（${item.localization_progress}%）`
      : `Partial (${item.localization_progress}%)`;
  }
  if (item.localization_status === "complete") return t("l10n.complete");
  return t("l10n.none");
}

function aiLabel(item) {
  return t(`ai.${item.ai_translation_status}`);
}

function repoLabel(url) {
  if (!url) return "-";
  try {
    const parsed = new URL(url);
    return parsed.pathname.replace(/^\/+/, "") || url;
  } catch {
    return url;
  }
}

function dependencyTags(item) {
  const tags = [];
  if (item.requires_steamodded) tags.push(t("deps.steamodded"));
  if (item.requires_talisman) tags.push(t("deps.talisman"));
  if (tags.length === 0) tags.push(t("deps.none"));
  return tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
}

function renderDashboard(payload) {
  document.querySelector("#dashboard").innerHTML = [
    [t("home.collected"), payload.collected_mods, t("home.mods")],
    [t("home.localized"), payload.localized_mods, t("home.mods")],
    [t("home.aiTranslated"), payload.ai_translated_mods, t("home.mods")],
  ]
    .map(
      ([label, value, suffix]) => `
        <article class="score-card">
          <span>${label}</span>
          <strong>${escapeHtml(value)}</strong>
          <span>${suffix}</span>
        </article>
      `,
    )
    .join("");

  document.querySelector("#dashboard").insertAdjacentHTML(
    "beforeend",
    `<article class="score-card">
      <span>${t("home.lastUpdated")}</span>
      <time>${escapeHtml(formatDate(payload.last_updated_at))}</time>
    </article>`,
  );
}

async function loadDashboard() {
  renderDashboard(await api("/api/dashboard"));
}

function filterParams() {
  const form = new FormData(document.querySelector("#mod-filters"));
  const params = new URLSearchParams({
    page: String(state.mods.page),
    page_size: String(state.mods.pageSize),
  });
  for (const [key, value] of form.entries()) {
    if (value) params.set(key, value);
  }
  return params;
}

function renderCategoryOptions(categories) {
  const select = document.querySelector("#category-filter");
  const current = select.value;
  select.innerHTML = [
    `<option value="">${t("filters.all")}</option>`,
    ...categories.map(
      (category) =>
        `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`,
    ),
  ].join("");
  select.value = categories.includes(current) ? current : "";
}

function renderMods(payload) {
  state.mods.total = payload.total;
  renderCategoryOptions(payload.categories);
  document.querySelector("#mod-count").textContent = payload.total;
  document.querySelector("#mod-list").innerHTML =
    payload.items
      .map(
        (item) => `
          <tr>
            <td data-label="${escapeHtml(t("table.mod"))}">${escapeHtml(item.name)}</td>
            <td data-label="${escapeHtml(t("table.repo"))}">
              ${
                item.repo_url
                  ? `<a href="${escapeHtml(item.repo_url)}" target="_blank" rel="noreferrer">${escapeHtml(repoLabel(item.repo_url))}</a>`
                  : "-"
              }
            </td>
            <td data-label="${escapeHtml(t("table.stars"))}">${escapeHtml(item.stars)}</td>
            <td data-label="${escapeHtml(t("table.categories"))}">
              <div class="tag-row">
                ${item.categories.map((category) => `<span class="tag">${escapeHtml(category)}</span>`).join("")}
              </div>
            </td>
            <td data-label="${escapeHtml(t("table.requires"))}">
              <div class="tag-row">${dependencyTags(item)}</div>
            </td>
            <td data-label="${escapeHtml(t("table.l10n"))}">
              <span class="status-pill ${escapeHtml(item.localization_status)}">
                ${escapeHtml(l10nLabel(item))}
              </span>
            </td>
            <td data-label="${escapeHtml(t("table.ai"))}">
              <span class="status-pill ai-pill ${escapeHtml(item.ai_translation_status)}">
                ${escapeHtml(aiLabel(item))}
              </span>
            </td>
          </tr>
        `,
      )
      .join("") || `<tr><td colspan="7" class="empty">${t("empty.mods")}</td></tr>`;
  renderPager("#mod-pager", state.mods.page, state.mods.pageSize, payload.total, "mods");
}

async function loadMods() {
  renderMods(await api(`/api/mod-index?${filterParams().toString()}`));
}

function renderPager(selector, page, pageSize, total, target) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  document.querySelector(selector).innerHTML = `
    <button type="button" data-pager="${target}" data-dir="-1" ${page <= 1 ? "disabled" : ""}>${t("pager.prev")}</button>
    <span>${page} / ${pages}</span>
    <button type="button" data-pager="${target}" data-dir="1" ${page >= pages ? "disabled" : ""}>${t("pager.next")}</button>
  `;
}

function renderReviews(payload) {
  state.reviews.total = payload.total;
  document.querySelector("#review-count").textContent = `${payload.total} ${state.reviews.status}`;
  document.querySelector("#review-list").innerHTML =
    payload.items
      .map(
        (item) => `
          <article class="review-item" data-id="${item.id}">
            <div class="review-head">
              <div>
                <div class="review-title">${escapeHtml(item.mod_id)}</div>
                <div class="review-meta">${escapeHtml(item.unit_key)}</div>
              </div>
              <span class="status-pill ${escapeHtml(item.status)}">${escapeHtml(item.reason)}</span>
            </div>
            <div class="review-grid">
              <div class="review-box">
                <div class="review-label">EN</div>
                ${escapeHtml(item.source_text)}
              </div>
              <div class="review-box">
                <div class="review-label">${t("admin.current")}</div>
                ${escapeHtml(text(item.current_target_text))}
              </div>
              <div class="review-box">
                <div class="review-label">${t("admin.suggested")}</div>
                ${escapeHtml(text(item.suggested_target_text))}
              </div>
            </div>
            <div class="review-actions">
              <input value="${escapeHtml(item.edited_target_text || item.suggested_target_text || item.current_target_text || "")}" />
              <button type="button" data-action="approved">${t("admin.approve")}</button>
              <button type="button" data-action="rejected">${t("admin.reject")}</button>
            </div>
          </article>
        `,
      )
      .join("") || `<div class="panel empty">${t("empty.reviews")}</div>`;
  renderPager(
    "#review-pager",
    state.reviews.page,
    state.reviews.pageSize,
    payload.total,
    "reviews",
  );
}

async function loadReviews() {
  const params = new URLSearchParams({
    status: state.reviews.status,
    page: String(state.reviews.page),
    page_size: String(state.reviews.pageSize),
  });
  renderReviews(await api(`/api/review-items?${params.toString()}`));
}

async function loadCurrent() {
  applyLanguage();
  if (state.route === "mods") return loadMods();
  if (state.route === "admin") return loadReviews();
  if (state.route === "about") return undefined;
  return loadDashboard();
}

document.querySelectorAll("[data-link]").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    setRoute(link.dataset.page);
  });
});

document.querySelector("#language-select").addEventListener("change", (event) => {
  state.lang = event.target.value;
  localStorage.setItem("balatro-cn-lang", state.lang);
  loadCurrent().catch(showError);
});

document.querySelector("#mod-filters").addEventListener("input", () => {
  state.mods.page = 1;
  loadMods().catch(showError);
});

document.querySelector("#review-status").addEventListener("change", (event) => {
  state.reviews.status = event.target.value;
  state.reviews.page = 1;
  loadReviews().catch(showError);
});

document.body.addEventListener("click", async (event) => {
  const pagerButton = event.target.closest("button[data-pager]");
  if (pagerButton) {
    const dir = Number(pagerButton.dataset.dir);
    if (pagerButton.dataset.pager === "mods") {
      state.mods.page += dir;
      await loadMods();
    } else {
      state.reviews.page += dir;
      await loadReviews();
    }
    return;
  }

  const reviewButton = event.target.closest("button[data-action]");
  if (!reviewButton) return;
  const item = reviewButton.closest(".review-item");
  const edited = item.querySelector("input").value;
  await api(`/api/review-items/${item.dataset.id}`, {
    method: "PATCH",
    body: JSON.stringify({
      status: reviewButton.dataset.action,
      edited_target_text: edited,
      reviewer: "web",
    }),
  });
  await loadReviews();
});

window.addEventListener("popstate", () => {
  setRoute(routeFromPath(window.location.pathname), false);
});

setRoute(routeFromPath(window.location.pathname), false);
