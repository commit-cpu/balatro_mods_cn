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
    "filters.aiStatus": "AI 汉化",
    "table.mod": "模组",
    "table.repo": "仓库",
    "table.stars": "星标",
    "table.categories": "分类",
    "table.requires": "依赖",
    "table.l10n": "当前汉化状态",
    "table.ai": "AI 汉化状态",
    "table.workflow": "流程",
    "table.originalPage": "原始仓库",
    "table.aiRepo": "AI 翻译仓库",
    "table.openOriginal": "仓库",
    "table.openAiRepo": "AI 仓库",
    "table.noLink": "无链接",
    "table.notReady": "未创建",
    "home.collected": "已经收录",
    "home.localized": "已有汉化",
    "home.aiTranslated": "AI 汉化",
    "home.mods": "mods",
    "home.lastUpdated": "上次更新时间",
    "l10n.unknown": "未探测",
    "l10n.unknownShort": "未探测",
    "l10n.none": "无汉化",
    "l10n.partialShort": "部分",
    "l10n.complete": "完全汉化",
    "ai.not_started": "未开始",
    "ai.notStartedShort": "未开始",
    "ai.unknown": "未开始",
    "ai.unknownShort": "未开始",
    "ai.skippedShort": "未开始",
    "ai.runningShort": "汉化中",
    "ai.reviewShort": "待审核",
    "ai.completeShort": "已汉化",
    "ai.mergedShort": "已发布",
    "ai.skipped": "未开始",
    "ai.running": "汉化中",
    "ai.translated_needs_review": "待审核",
    "ai.complete": "已汉化",
    "ai.merged_upstream": "已发布",
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
    "admin.back": "返回模组",
    "admin.entries": "组",
    "admin.items": "条",
    "admin.openReview": "进入审核",
    "admin.groupApprove": "整组通过",
    "admin.field": "字段",
    "admin.pipelineMod": "模组",
    "admin.modSearchPlaceholder": "搜索模组 / 仓库",
    "admin.startTranslation": "启动翻译",
    "admin.applyApproved": "应用已通过",
    "admin.publishFork": "提交到 Fork",
    "admin.probeGithub": "探测 GitHub",
    "admin.verifyForks": "验证/创建 Fork",
    "admin.translationStarted": "翻译任务已启动",
    "admin.translationStatus": "翻译任务",
    "admin.githubProbeStarted": "GitHub 探测任务已启动",
    "admin.githubForkStarted": "Fork 验证任务已启动",
    "admin.githubStatus": "GitHub 任务",
    "admin.preparingSource": "正在下载 localization 文件",
    "admin.elapsed": "已运行",
    "admin.round": "轮次",
    "admin.progress": "进度",
    "admin.total": "总数",
    "admin.applyDone": "已写入 zh_CN.lua",
    "admin.publishDone": "已提交到 Fork",
    "admin.notLocal": "该模组还没有本地翻译源，启动翻译时会先下载 localization 文件",
    "admin.selectModFirst": "请先选择一个模组",
    "admin.localOnly": "本地可翻译",
    "admin.autoTranslate": "自动翻译",
    "admin.intervalHours": "间隔小时",
    "admin.saveSettings": "保存设置",
    "admin.tabTodo": "待翻译",
    "admin.tabQueue": "队列",
    "admin.tabRunning": "翻译中",
    "admin.tabReview": "待审核",
    "admin.tabApplied": "已应用",
    "admin.tabCommitted": "已提交 Fork",
    "admin.queueAdd": "加入队列",
    "admin.queueStart": "立即启动",
    "admin.queueRetry": "重试",
    "admin.queueRemove": "移除",
    "admin.queueUp": "上移",
    "admin.queueDown": "下移",
    "admin.branch": "分支",
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
    "filters.aiStatus": "AI localization",
    "table.mod": "Mod",
    "table.repo": "Repository",
    "table.stars": "Stars",
    "table.categories": "Categories",
    "table.requires": "Requires",
    "table.l10n": "Localization",
    "table.ai": "AI localization",
    "table.workflow": "Workflow",
    "table.originalPage": "Original repo",
    "table.aiRepo": "AI translation repo",
    "table.openOriginal": "Repo",
    "table.openAiRepo": "AI repo",
    "table.noLink": "No link",
    "table.notReady": "Not created",
    "home.collected": "Collected",
    "home.localized": "Localized",
    "home.aiTranslated": "AI translated",
    "home.mods": "mods",
    "home.lastUpdated": "Last updated",
    "l10n.unknown": "Unprobed",
    "l10n.unknownShort": "Unprobed",
    "l10n.none": "No Chinese",
    "l10n.partialShort": "Partial",
    "l10n.complete": "Complete",
    "ai.not_started": "Not started",
    "ai.notStartedShort": "Not started",
    "ai.unknown": "Not started",
    "ai.unknownShort": "Not started",
    "ai.skippedShort": "Not started",
    "ai.runningShort": "Translating",
    "ai.reviewShort": "Review",
    "ai.completeShort": "Translated",
    "ai.mergedShort": "Published",
    "ai.skipped": "Not started",
    "ai.running": "Translating",
    "ai.translated_needs_review": "Review",
    "ai.complete": "Translated",
    "ai.merged_upstream": "Published",
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
    "admin.back": "Back to mods",
    "admin.entries": "entries",
    "admin.items": "items",
    "admin.openReview": "Review",
    "admin.groupApprove": "Approve group",
    "admin.field": "Field",
    "admin.pipelineMod": "Mod",
    "admin.modSearchPlaceholder": "Search mod / repository",
    "admin.startTranslation": "Start translation",
    "admin.applyApproved": "Apply approved",
    "admin.publishFork": "Commit to fork",
    "admin.probeGithub": "Probe GitHub",
    "admin.verifyForks": "Verify/create forks",
    "admin.translationStarted": "Translation job started",
    "admin.translationStatus": "Translation job",
    "admin.githubProbeStarted": "GitHub probe job started",
    "admin.githubForkStarted": "Fork verification job started",
    "admin.githubStatus": "GitHub job",
    "admin.preparingSource": "Downloading localization files",
    "admin.elapsed": "elapsed",
    "admin.round": "round",
    "admin.progress": "progress",
    "admin.total": "total",
    "admin.applyDone": "zh_CN.lua written",
    "admin.publishDone": "Committed to fork",
    "admin.notLocal": "This mod has no local source yet; translation will download localization files first",
    "admin.selectModFirst": "Select a mod first",
    "admin.localOnly": "local",
    "admin.autoTranslate": "Auto translate",
    "admin.intervalHours": "Interval hours",
    "admin.saveSettings": "Save settings",
    "admin.tabTodo": "To translate",
    "admin.tabQueue": "Queue",
    "admin.tabRunning": "Running",
    "admin.tabReview": "Review",
    "admin.tabApplied": "Applied",
    "admin.tabCommitted": "Fork committed",
    "admin.queueAdd": "Queue",
    "admin.queueStart": "Start now",
    "admin.queueRetry": "Retry",
    "admin.queueRemove": "Remove",
    "admin.queueUp": "Up",
    "admin.queueDown": "Down",
    "admin.branch": "Branch",
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

const JOB_EVENT_LABELS = {
  zh: {
    "translation.loop.start": "循环开始",
    "translation.round.start": "轮次开始",
    "translation.preview.start": "准备条目",
    "translation.entry.prepare": "准备引用",
    "translation.entry.queued": "等待翻译",
    "translation.name_glossary.start": "翻译名称",
    "translation.name.done": "名称完成",
    "translation.name.failed": "名称失败",
    "translation.name_glossary.complete": "名称表完成",
    "translation.name_glossary.reused": "复用名称",
    "translation.llm.start": "提交 LLM",
    "translation.llm.waiting": "等待 LLM",
    "translation.entry.done": "条目完成",
    "translation.entry.failed": "条目失败",
    "translation.preview.written": "预览写入",
    "translation.preview.merge.start": "合并预览",
    "translation.apply.start": "应用翻译",
    "translation.audit.start": "审计开始",
    "translation.audit.complete": "审计完成",
    "translation.review_items.imported": "Review 导入",
    "translation.loop.resumed": "复用进度",
    "translation.loop.complete": "循环完成",
    "translation.loop.failed": "循环失败",
    "github.probe.start": "GitHub 探测",
    "github.probe.complete": "探测完成",
    "github.probe.failed": "探测失败",
    "github.localization.missing_target": "缺少目标",
    "github.forks.start": "Fork 验证",
    "github.forks.complete": "Fork 完成",
    "github.forks.failed": "Fork 失败",
    "github.localization_source.start": "下载源文件",
    "github.localization_source.complete": "源文件就绪",
    "publish.fork.start": "提交 Fork",
    "publish.fork.complete": "提交完成",
    "publish.fork.failed": "提交失败",
  },
  en: {
    "translation.loop.start": "Loop start",
    "translation.round.start": "Round start",
    "translation.preview.start": "Prepare entries",
    "translation.entry.prepare": "Prepare refs",
    "translation.entry.queued": "Queued",
    "translation.name_glossary.start": "Translate names",
    "translation.name.done": "Name done",
    "translation.name.failed": "Name failed",
    "translation.name_glossary.complete": "Names ready",
    "translation.name_glossary.reused": "Names reused",
    "translation.llm.start": "Submit LLM",
    "translation.llm.waiting": "Waiting LLM",
    "translation.entry.done": "Entry done",
    "translation.entry.failed": "Entry failed",
    "translation.preview.written": "Preview written",
    "translation.preview.merge.start": "Merge preview",
    "translation.apply.start": "Apply",
    "translation.audit.start": "Audit start",
    "translation.audit.complete": "Audit done",
    "translation.review_items.imported": "Review imported",
    "translation.loop.resumed": "Resumed",
    "translation.loop.complete": "Loop done",
    "translation.loop.failed": "Loop failed",
    "github.probe.start": "GitHub probe",
    "github.probe.complete": "Probe done",
    "github.probe.failed": "Probe failed",
    "github.localization.missing_target": "Missing target",
    "github.forks.start": "Verify forks",
    "github.forks.complete": "Forks done",
    "github.forks.failed": "Forks failed",
    "github.localization_source.start": "Download source",
    "github.localization_source.complete": "Source ready",
    "publish.fork.start": "Commit fork",
    "publish.fork.complete": "Commit done",
    "publish.fork.failed": "Commit failed",
  },
};

const REVIEW_REASON_LABELS = {
  zh: {
    translation_failed: "翻译失败",
    ai_translation_blocked: "无法自动应用",
    ai_translation_needs_review: "需要人工审核",
    ai_translation_review: "AI 翻译建议",
  },
  en: {
    translation_failed: "Translation failed",
    ai_translation_blocked: "Cannot auto-apply",
    ai_translation_needs_review: "Needs human review",
    ai_translation_review: "AI suggestion",
  },
};

const state = {
  route: "home",
  lang: localStorage.getItem("balatro-cn-lang") || "zh",
  auth: {
    checked: false,
    isAdmin: false,
  },
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
    modId: null,
  },
  workflow: {
    modsLoaded: false,
    modItems: [],
    jobPollTimer: null,
    adminMods: [],
    queueItems: [],
    adminFilter: "todo",
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
  if (pathname === "/about") return "about";
  if (pathname === "/mods") return "mods";
  if (pathname === "/") return "home";
  return "admin";
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

async function refreshSession() {
  const response = await fetch("/api/session", {
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    state.auth.checked = true;
    state.auth.isAdmin = false;
    document.body.classList.remove("is-admin");
    return;
  }
  const payload = await response.json();
  state.auth.checked = true;
  state.auth.isAdmin = Boolean(payload.is_admin);
  document.body.classList.toggle("is-admin", state.auth.isAdmin);
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
  const path = route === "home" ? "/" : route === "admin" ? window.location.pathname : `/${route}`;
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
  if (Number(item.localization_progress || 0) >= 100) return t("l10n.complete");
  if (item.localization_status === "partial") {
    return state.lang === "zh"
      ? `汉化部分（${item.localization_progress}%）`
      : `Partial (${item.localization_progress}%)`;
  }
  if (item.localization_status === "unknown") return t("l10n.unknown");
  if (item.localization_status === "complete") return t("l10n.complete");
  return t("l10n.none");
}

function l10nPillStatus(item) {
  return Number(item.localization_progress || 0) >= 100
    ? "complete"
    : item.localization_status;
}

function aiLabel(item) {
  return t(`ai.${item.ai_translation_status}`);
}

function workflowLabel(item) {
  const status = item.workflow_status_label || item.workflow_status || "-";
  const action = item.next_action_label || item.next_action || "-";
  if (item.next_action === "none") return status;
  return `${status} · ${action}`;
}

function pageButton(url, label, emptyLabel) {
  if (!url) {
    return `<span class="table-action disabled">${escapeHtml(emptyLabel)}</span>`;
  }
  return `<a class="table-action" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
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

function renderModsTableChrome() {
  const cols = [
    "col-mod",
    "col-stars",
    "col-categories",
    "col-requires",
    "col-l10n",
    "col-ai",
    ...(state.auth.isAdmin ? ["col-workflow"] : []),
    "col-link",
    "col-link",
  ];
  const headers = [
    ["table.mod", ""],
    ["table.stars", ""],
    ["table.categories", ""],
    ["table.requires", ""],
    ["table.l10n", ""],
    ["table.ai", ""],
    ...(state.auth.isAdmin ? [["table.workflow", "data-admin-only"]] : []),
    ["table.originalPage", ""],
    ["table.aiRepo", ""],
  ];
  document.querySelector("#mods-colgroup").innerHTML = cols
    .map((className) => `<col class="${className}" />`)
    .join("");
  document.querySelector("#mods-head-row").innerHTML = headers
    .map(
      ([key, attrs]) =>
        `<th ${attrs} data-i18n="${key}">${escapeHtml(t(key))}</th>`,
    )
    .join("");
}

function renderMods(payload) {
  state.mods.total = payload.total;
  renderCategoryOptions(payload.categories);
  renderModsTableChrome();
  document.querySelector("#mod-count").textContent = payload.total;
  const workflowCell = (item) =>
    state.auth.isAdmin
      ? `
            <td data-admin-only data-label="${escapeHtml(t("table.workflow"))}">
              <span class="workflow-pill ${escapeHtml(item.workflow_status || "unprobed")}">
                ${escapeHtml(workflowLabel(item))}
              </span>
            </td>`
      : "";
  const emptyColspan = state.auth.isAdmin ? 9 : 8;
  document.querySelector("#mod-list").innerHTML =
    payload.items
      .map(
        (item) => `
          <tr>
            <td class="mod-name-cell" data-label="${escapeHtml(t("table.mod"))}">${escapeHtml(item.name)}</td>
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
              <span class="status-pill ${escapeHtml(l10nPillStatus(item))}">
                ${escapeHtml(l10nLabel(item))}
              </span>
            </td>
            <td data-label="${escapeHtml(t("table.ai"))}">
              <span class="status-pill ai-pill ${escapeHtml(item.ai_translation_status)}">
                ${escapeHtml(aiLabel(item))}
              </span>
            </td>
            ${workflowCell(item)}
            <td data-label="${escapeHtml(t("table.originalPage"))}">
              ${pageButton(item.original_page_url || item.repo_url, t("table.openOriginal"), t("table.noLink"))}
            </td>
            <td data-label="${escapeHtml(t("table.aiRepo"))}">
              ${pageButton(item.ai_translation_repo_url, t("table.openAiRepo"), t("table.notReady"))}
            </td>
          </tr>
        `,
      )
      .join("") || `<tr><td colspan="${emptyColspan}" class="empty">${t("empty.mods")}</td></tr>`;
  renderPager("#mod-pager", state.mods.page, state.mods.pageSize, payload.total, "mods");
}

async function loadMods() {
  await refreshSession();
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

function renderReviewMods(payload) {
  state.reviews.total = payload.items.length;
  document.querySelector("#review-back").hidden = true;
  document.querySelector("#review-count").textContent =
    `${payload.items.length} mods · ${state.reviews.status}`;
  document.querySelector("#review-list").innerHTML =
    payload.items
      .map(
        (item) => `
          <article class="review-mod-card panel" data-review-mod="${escapeHtml(item.mod_id)}">
            <div class="review-head">
              <div>
                <div class="review-title">${escapeHtml(item.mod_id)}</div>
                <div class="review-meta">${escapeHtml(text(item.latest_updated_at))}</div>
              </div>
              <button type="button" data-review-mod-open="${escapeHtml(item.mod_id)}">${t("admin.openReview")}</button>
            </div>
            <div class="review-mod-stats">
              <span>${item.entry_groups} ${t("admin.entries")}</span>
              <span>${item.pending_items} ${t("admin.items")}</span>
            </div>
          </article>
        `,
      )
      .join("") || `<div class="panel empty">${t("empty.reviews")}</div>`;
  document.querySelector("#review-pager").innerHTML = "";
}

function renderReviewGroups(payload) {
  state.reviews.total = payload.total;
  document.querySelector("#review-back").hidden = false;
  document.querySelector("#review-count").textContent =
    `${escapeHtml(state.reviews.modId)} · ${payload.total} ${t("admin.entries")} · ${state.reviews.status}`;
  document.querySelector("#review-list").innerHTML =
    payload.items
      .map(
        (group) => `
          <article class="review-group panel" data-entry-key="${escapeHtml(group.entry_key)}">
            <div class="review-head">
              <div>
                <div class="review-title">${escapeHtml(entryName(group.entry_key))}</div>
                <div class="review-meta">${escapeHtml(group.entry_key)}</div>
              </div>
              <span class="status-pill ${escapeHtml(group.status)}">${group.item_count} ${t("admin.items")}</span>
            </div>
            <div class="review-lines">
              ${group.items
                .map(
                  (item) => `
                    <section class="review-line ${hasCurrentTarget(item) ? "" : "current-empty"}" data-item-id="${item.id}">
                      <div class="review-field">
                        <span>${escapeHtml(item.field)}</span>
                      </div>
                      <div class="review-cell">
                        <div class="review-label">EN</div>
                        <div>${escapeHtml(item.source_text)}</div>
                      </div>
                      <div class="review-cell review-current ${hasCurrentTarget(item) ? "" : "is-empty"}">
                        <div class="review-label">${t("admin.current")}</div>
                        <div>${escapeHtml(text(item.current_target_text))}</div>
                      </div>
                      <div class="review-cell">
                        <div class="review-label">${t("admin.suggested")}</div>
                        <textarea data-edit-item="${item.id}">${escapeHtml(
                          item.edited_target_text ||
                            item.suggested_target_text ||
                            item.current_target_text ||
                            "",
                        )}</textarea>
                        ${renderReviewReason(item.reason)}
                      </div>
                    </section>
                  `,
                )
                .join("")}
            </div>
            ${
              ["pending", "needs_changes"].includes(state.reviews.status)
                ? `<div class="review-actions">
                    <button type="button" data-group-approve>${t("admin.groupApprove")}</button>
                  </div>`
                : ""
            }
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

function renderReviewReason(reason) {
  const lines = String(reason || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return "";
  return `
    <div class="review-reason">
      ${lines.map((line) => `<div>${escapeHtml(reviewReasonText(line))}</div>`).join("")}
    </div>
  `;
}

function reviewReasonText(line) {
  return REVIEW_REASON_LABELS[state.lang]?.[line] || line;
}

async function loadReviews() {
  await loadWorkflowMods();
  await loadAdminManagement();
  if (!state.reviews.modId) {
    const params = new URLSearchParams({ status: state.reviews.status });
    renderReviewMods(await api(`/api/review-mods?${params.toString()}`));
    return;
  }
  const params = new URLSearchParams({
    status: state.reviews.status,
    mod_id: state.reviews.modId,
    page: String(state.reviews.page),
    page_size: String(state.reviews.pageSize),
  });
  renderReviewGroups(await api(`/api/review-groups?${params.toString()}`));
}

async function loadAdminManagement() {
  const [settings, mods, queue] = await Promise.all([
    api("/api/admin/settings"),
    api("/api/admin/mods"),
    api("/api/translation-queue"),
  ]);
  renderAdminSettings(settings);
  state.workflow.adminMods = mods.items || [];
  state.workflow.queueItems = queue.items || [];
  renderAdminTabs();
  renderAdminModList();
}

function renderAdminSettings(settings) {
  document.querySelector("#auto-translate-enabled").checked = Boolean(
    settings.auto_translate_enabled,
  );
  document.querySelector("#auto-translate-hours").value =
    settings.auto_translate_interval_hours || 5;
}

function renderAdminTabs() {
  const tabs = [
    ["todo", t("admin.tabTodo")],
    ["queue", t("admin.tabQueue")],
    ["running", t("admin.tabRunning")],
    ["review", t("admin.tabReview")],
    ["applied", t("admin.tabApplied")],
    ["committed", t("admin.tabCommitted")],
  ];
  document.querySelector("#admin-mod-tabs").innerHTML = tabs
    .map(
      ([key, label]) => `
        <button type="button" class="${state.workflow.adminFilter === key ? "active" : ""}" data-admin-filter="${escapeHtml(key)}">
          ${escapeHtml(label)}
        </button>
      `,
    )
    .join("");
}

function renderAdminModList() {
  const items = state.workflow.adminMods.filter(adminModMatchesFilter).slice(0, 80);
  document.querySelector("#admin-mod-list").innerHTML =
    items
      .map(
        (item) => `
          <article class="admin-mod-row">
            <div class="admin-mod-main">
              <strong>${escapeHtml(item.name)}</strong>
              <span>${escapeHtml(item.translation_mod_id || item.repo_url || "-")}</span>
            </div>
            <span class="status-pill ${escapeHtml(item.localization_status)}">${escapeHtml(item.localization_status_label)}</span>
            <span class="workflow-pill ${escapeHtml(item.workflow_status || "unprobed")}">${escapeHtml(item.workflow_status_label || item.workflow_status)}</span>
            <div class="admin-mod-meta">
              <span>${escapeHtml(item.pending_review_items || 0)} ${t("admin.items")}</span>
              <span>${escapeHtml(item.queue_status || "-")}</span>
              ${item.latest_fork_branch_url ? `<a href="${escapeHtml(item.latest_fork_branch_url)}" target="_blank" rel="noreferrer">${t("admin.branch")}</a>` : ""}
            </div>
            <div class="admin-mod-actions">
              ${renderAdminModActions(item)}
            </div>
          </article>
        `,
      )
      .join("") || `<div class="empty">${t("empty.mods")}</div>`;
}

function renderAdminModActions(item) {
  const attrs = [
    `data-mod-id="${escapeHtml(item.translation_mod_id || item.name)}"`,
    `data-source-name="${escapeHtml(item.name)}"`,
    `data-repo-url="${escapeHtml(item.repo_url || "")}"`,
    item.queue_id ? `data-queue-id="${escapeHtml(item.queue_id)}"` : "",
  ]
    .filter(Boolean)
    .join(" ");
  if (item.queue_status === "queued") {
    return `
      <button type="button" data-admin-action="queue-start" ${attrs}>${t("admin.queueStart")}</button>
      <button type="button" data-admin-action="queue-up" ${attrs}>${t("admin.queueUp")}</button>
      <button type="button" data-admin-action="queue-down" ${attrs}>${t("admin.queueDown")}</button>
      <button type="button" data-admin-action="queue-remove" ${attrs}>${t("admin.queueRemove")}</button>
    `;
  }
  if (item.queue_status === "failed") {
    return `
      <button type="button" data-admin-action="queue-retry" ${attrs}>${t("admin.queueRetry")}</button>
      <button type="button" data-admin-action="queue-remove" ${attrs}>${t("admin.queueRemove")}</button>
    `;
  }
  if (item.queue_status === "running") {
    return `<button type="button" disabled>${t("admin.tabRunning")}</button>`;
  }
  return `<button type="button" data-admin-action="queue-add" ${attrs}>${t("admin.queueAdd")}</button>`;
}

function adminModMatchesFilter(item) {
  if (state.workflow.adminFilter === "queue") return Boolean(item.queue_status);
  if (state.workflow.adminFilter === "running") {
    return item.latest_job_status === "running" || item.queue_status === "running";
  }
  if (state.workflow.adminFilter === "review") return item.pending_review_items > 0;
  if (state.workflow.adminFilter === "applied") {
    return item.ai_translation_status === "complete" && item.workflow_status !== "committed";
  }
  if (state.workflow.adminFilter === "committed") {
    return item.workflow_status === "committed" || Boolean(item.latest_fork_branch_url);
  }
  return item.next_action === "translate" || item.translation_available || Boolean(item.repo_url);
}

async function loadWorkflowMods() {
  if (state.workflow.modsLoaded) return;
  state.workflow.modItems = await loadAllModIndexItems();
  renderWorkflowModOptions();
  state.workflow.modsLoaded = true;
  updateWorkflowModSelection();
  updateWorkflowActions();
}

async function loadAllModIndexItems() {
  const pageSize = 200;
  let page = 1;
  const items = [];
  while (true) {
    const payload = await api(`/api/mod-index?page=${page}&page_size=${pageSize}`);
    items.push(...payload.items);
    if (items.length >= payload.total || payload.items.length === 0) break;
    page += 1;
  }
  return items;
}

function workflowModLabel(item) {
  const status = l10nLabel(item);
  const local = item.translation_available ? ` · ${t("admin.localOnly")}` : "";
  return `${item.name} · ${status}${local}`;
}

function workflowSearchText(item) {
  return [
    item.name,
    item.repo_url,
    item.translation_mod_id,
    item.workflow_status_label,
    item.next_action_label,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function renderWorkflowModOptions() {
  const select = document.querySelector("#workflow-mod");
  const query = document.querySelector("#workflow-mod-search").value.trim().toLowerCase();
  const items = state.workflow.modItems
    .filter((item) => !query || workflowSearchText(item).includes(query))
    .slice(0, 200);
  select.innerHTML = items
    .map(
      (item) => `
        <option
          value="${escapeHtml(item.name)}"
          data-repo-url="${escapeHtml(item.repo_url || "")}"
          data-translation-mod-id="${escapeHtml(item.translation_mod_id || "")}"
          data-translation-available="${item.translation_available ? "1" : "0"}"
        >${escapeHtml(workflowModLabel(item))}</option>
      `,
    )
    .join("");
  updateWorkflowActions();
}

function selectedWorkflowMod() {
  if (state.reviews.modId) return state.reviews.modId;
  const option = document.querySelector("#workflow-mod").selectedOptions[0];
  return option?.dataset.translationModId || "";
}

function selectedWorkflowOption() {
  return document.querySelector("#workflow-mod").selectedOptions[0] || null;
}

function selectedGithubPayload() {
  const option = selectedWorkflowOption();
  if (!option) return null;
  return {
    limit: 1,
    mod_name: option.value,
    repo_url: option.dataset.repoUrl || null,
  };
}

function updateWorkflowModSelection() {
  const select = document.querySelector("#workflow-mod");
  if (!state.reviews.modId) return;
  const option = [...select.options].find(
    (item) => item.dataset.translationModId === state.reviews.modId || item.value === state.reviews.modId,
  );
  if (option) {
    select.value = option.value;
  }
  updateWorkflowActions();
}

function setWorkflowStatus(message) {
  document.querySelector("#workflow-status").textContent = message;
}

function updateWorkflowActions() {
  const option = selectedWorkflowOption();
  const canTranslate = Boolean(
    state.reviews.modId ||
      option?.dataset.translationAvailable === "1" ||
      option?.dataset.repoUrl,
  );
  const canApply = Boolean(state.reviews.modId || option?.dataset.translationAvailable === "1");
  document.querySelector("#start-translation").disabled = !canTranslate;
  document.querySelector("#apply-approved").disabled = !canApply;
  document.querySelector("#publish-fork").disabled = !canApply;
  if (!canApply && option) {
    setWorkflowStatus(t("admin.notLocal"));
  } else if (document.querySelector("#workflow-status").textContent === t("admin.notLocal")) {
    setWorkflowStatus("");
  }
}

function clearJobPolling() {
  if (!state.workflow.jobPollTimer) return;
  window.clearTimeout(state.workflow.jobPollTimer);
  state.workflow.jobPollTimer = null;
}

async function pollTranslationJob(jobId) {
  clearJobPolling();
  const job = await api(`/api/jobs/${jobId}`);
  const events = await fetchJobEvents(job);
  setWorkflowJobStatus(t("admin.translationStatus"), job, events);
  if (["pending", "running"].includes(job.status)) {
    state.workflow.jobPollTimer = window.setTimeout(() => {
      pollTranslationJob(jobId).catch(showError);
    }, 3000);
    return;
  }
  state.workflow.modsLoaded = false;
  await loadCurrent();
}

async function pollGithubJob(jobId) {
  clearJobPolling();
  const job = await api(`/api/jobs/${jobId}`);
  const events = await fetchJobEvents(job);
  setWorkflowJobStatus(t("admin.githubStatus"), job, events);
  if (["pending", "running"].includes(job.status)) {
    state.workflow.jobPollTimer = window.setTimeout(() => {
      pollGithubJob(jobId).catch(showError);
    }, 3000);
    return;
  }
  state.workflow.modsLoaded = false;
  await loadCurrent();
}

async function fetchJobEvents(job) {
  const payload = await api(`/api/jobs/${job.id}/events?limit=100`);
  return payload.items || [];
}

function setWorkflowJobStatus(label, job, events) {
  const latest = events.at(-1);
  const elapsed = jobElapsedText(job);
  const progress = latest ? jobEventProgressText(latest) : "";
  const phase = latest ? jobEventLabel(latest) : "";
  const summary = [
    `${label} #${job.id}`,
    job.status,
    elapsed,
    phase,
    progress,
  ].filter(Boolean);
  const title = latest ? jobEventDetailText(latest) : summary.join(" · ");
  document.querySelector("#workflow-status").innerHTML = `
    <span class="job-status-line" title="${escapeHtml(title)}">
      ${escapeHtml(summary.join(" · "))}
    </span>
    ${renderJobEventChips(events)}
  `;
}

function renderJobEventChips(events) {
  const recent = events.slice(-5).reverse();
  if (!recent.length) return "";
  return `
    <span class="job-event-stack" aria-label="Job log">
      ${recent
        .map((event) => {
          const progress = jobEventProgressText(event);
          const brief = [jobEventLabel(event), progress].filter(Boolean).join(" ");
          return `
            <span class="job-event-chip" title="${escapeHtml(jobEventDetailText(event))}">
              ${escapeHtml(brief || event.event)}
            </span>
          `;
        })
        .join("")}
    </span>
  `;
}

function jobEventLabel(event) {
  return JOB_EVENT_LABELS[state.lang]?.[event.event] || event.event;
}

function jobEventDetailText(event) {
  const payload = event.payload && Object.keys(event.payload).length
    ? `\n${JSON.stringify(event.payload, null, 2)}`
    : "";
  return `${jobEventLabel(event)}\n${event.message || event.event}${payload}`;
}

function jobElapsedText(job) {
  const started = job.started_at || job.created_at;
  if (!started) return "";
  const startedAt = new Date(`${started.replace(" ", "T")}Z`);
  if (Number.isNaN(startedAt.getTime())) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - startedAt.getTime()) / 1000));
  return `${t("admin.elapsed")} ${formatDuration(seconds)}`;
}

function jobEventProgressText(event) {
  const payload = event.payload || {};
  const pieces = [];
  if (payload.round && payload.max_rounds) {
    pieces.push(`${t("admin.round")} ${payload.round}/${payload.max_rounds}`);
  }
  if (payload.current && payload.total) {
    pieces.push(`${t("admin.progress")} ${payload.current}/${payload.total}`);
  } else if (payload.written && payload.total_entries) {
    pieces.push(`${t("admin.progress")} ${payload.written}/${payload.total_entries}`);
  } else if (payload.total_entries) {
    pieces.push(`${t("admin.total")} ${payload.total_entries}`);
  }
  return pieces.join(" · ");
}

function formatDuration(seconds) {
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  if (minutes <= 0) return `${remaining}s`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hours <= 0) return `${minutes}m ${remaining}s`;
  return `${hours}h ${mins}m`;
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
  state.reviews.modId = null;
  loadReviews().catch(showError);
});

document.querySelector("#review-back").addEventListener("click", () => {
  state.reviews.modId = null;
  state.reviews.page = 1;
  loadReviews().catch(showError);
});

document.querySelector("#workflow-mod-search").addEventListener("input", () => {
  renderWorkflowModOptions();
});

document.querySelector("#workflow-mod").addEventListener("change", () => {
  updateWorkflowActions();
});

document.querySelector("#save-admin-settings").addEventListener("click", async () => {
  const enabled = document.querySelector("#auto-translate-enabled").checked;
  const hours = Number(document.querySelector("#auto-translate-hours").value || 5);
  const settings = await api("/api/admin/settings", {
    method: "PATCH",
    body: JSON.stringify({
      auto_translate_enabled: enabled,
      auto_translate_interval_hours: Math.max(1, hours),
    }),
  });
  renderAdminSettings(settings);
});

document.body.addEventListener("click", async (event) => {
  const adminFilter = event.target.closest("button[data-admin-filter]");
  if (adminFilter) {
    state.workflow.adminFilter = adminFilter.dataset.adminFilter;
    renderAdminTabs();
    renderAdminModList();
    return;
  }

  const adminAction = event.target.closest("button[data-admin-action]");
  if (adminAction) {
    await handleAdminAction(adminAction);
    return;
  }

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

  const reviewModButton = event.target.closest("button[data-review-mod-open]");
  if (reviewModButton) {
    state.reviews.modId = reviewModButton.dataset.reviewModOpen;
    state.reviews.page = 1;
    updateWorkflowModSelection();
    await loadReviews();
    return;
  }

  const groupApproveButton = event.target.closest("button[data-group-approve]");
  if (groupApproveButton) {
    const group = groupApproveButton.closest(".review-group");
    const textareas = [...group.querySelectorAll("textarea[data-edit-item]")];
    const itemIds = textareas.map((input) => Number(input.dataset.editItem));
    const editedTargetTexts = Object.fromEntries(
      textareas.map((input) => [input.dataset.editItem, input.value]),
    );
    await api("/api/review-groups/approve", {
      method: "PATCH",
      body: JSON.stringify({
        item_ids: itemIds,
        edited_target_texts: editedTargetTexts,
        reviewer: "web",
        comment: "group approved",
      }),
    });
    await loadReviews();
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

async function handleAdminAction(button) {
  const action = button.dataset.adminAction;
  const queueId = button.dataset.queueId;
  let job = null;
  if (action === "queue-add") {
    await api("/api/translation-queue", {
      method: "POST",
      body: JSON.stringify({
        mod_id: button.dataset.modId,
        source_name: button.dataset.sourceName || null,
        repo_url: button.dataset.repoUrl || null,
      }),
    });
  } else if (action === "queue-start") {
    job = await api(`/api/translation-queue/${encodeURIComponent(queueId)}/start`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  } else if (action === "queue-retry") {
    await api(`/api/translation-queue/${encodeURIComponent(queueId)}/retry`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  } else if (action === "queue-remove") {
    await api(`/api/translation-queue/${encodeURIComponent(queueId)}`, {
      method: "DELETE",
    });
  } else if (action === "queue-up" || action === "queue-down") {
    await api(`/api/translation-queue/${encodeURIComponent(queueId)}`, {
      method: "PATCH",
      body: JSON.stringify({ direction: action === "queue-up" ? "up" : "down" }),
    });
  }
  await loadAdminManagement();
  if (job) {
    setWorkflowStatus(`${t("admin.translationStarted")} #${job.id}`);
    pollTranslationJob(job.id).catch(showError);
  }
}

document.querySelector("#start-translation").addEventListener("click", async () => {
  let modId = selectedWorkflowMod();
  if (!modId) {
    const payload = selectedGithubPayload();
    if (!payload) {
      setWorkflowStatus(t("admin.selectModFirst"));
      return;
    }
    setWorkflowStatus(t("admin.preparingSource"));
    const mod = await api("/api/github/localization-source", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    modId = mod.mod_id;
    state.workflow.modsLoaded = false;
  }
  const job = await api(`/api/mods/${encodeURIComponent(modId)}/translate`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  setWorkflowStatus(`${t("admin.translationStarted")} #${job.id}`);
  pollTranslationJob(job.id).catch(showError);
  await loadCurrent();
});

document.querySelector("#apply-approved").addEventListener("click", async () => {
  const modId = selectedWorkflowMod();
  if (!modId) {
    setWorkflowStatus(t("admin.notLocal"));
    return;
  }
  const result = await api(`/api/mods/${encodeURIComponent(modId)}/apply-approved`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  setWorkflowStatus(`${t("admin.applyDone")} · ${result.applied_items} ${t("admin.items")}`);
  state.workflow.modsLoaded = false;
  await loadCurrent();
});

document.querySelector("#publish-fork").addEventListener("click", async () => {
  const modId = selectedWorkflowMod();
  if (!modId) {
    setWorkflowStatus(t("admin.notLocal"));
    return;
  }
  const result = await api(`/api/mods/${encodeURIComponent(modId)}/publish-fork`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  setWorkflowStatus(
    `${t("admin.publishDone")} · ${result.repo_slug}:${result.branch} · ${result.commit_sha.slice(0, 7)}`,
  );
  state.workflow.modsLoaded = false;
  await loadCurrent();
});

document.querySelector("#probe-github").addEventListener("click", async () => {
  const payload = selectedGithubPayload();
  if (!payload) {
    setWorkflowStatus(t("admin.selectModFirst"));
    return;
  }
  const job = await api("/api/github/probe", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setWorkflowStatus(`${t("admin.githubProbeStarted")} #${job.id}`);
  pollGithubJob(job.id).catch(showError);
});

document.querySelector("#verify-forks").addEventListener("click", async () => {
  const payload = selectedGithubPayload();
  if (!payload) {
    setWorkflowStatus(t("admin.selectModFirst"));
    return;
  }
  const job = await api("/api/github/forks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setWorkflowStatus(`${t("admin.githubForkStarted")} #${job.id}`);
  pollGithubJob(job.id).catch(showError);
});

window.addEventListener("popstate", () => {
  setRoute(routeFromPath(window.location.pathname), false);
});

setRoute(routeFromPath(window.location.pathname), false);

function entryName(entryKey) {
  return String(entryKey || "").split(".").at(-1) || entryKey;
}

function hasCurrentTarget(item) {
  return item.current_target_text !== null &&
    item.current_target_text !== undefined &&
    item.current_target_text !== "";
}
