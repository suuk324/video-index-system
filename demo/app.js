const demoSources = [
  {
    name: "Design Channels",
    category: "Motion / design",
    rhythm: "Every 12h",
    status: "Active",
  },
  {
    name: "Creative Tutorials",
    category: "Workflow / education",
    rhythm: "Manual refresh",
    status: "Read-only demo",
  },
  {
    name: "Reference Clips",
    category: "Archive / indexing",
    rhythm: "Every 24h",
    status: "Active",
  },
  {
    name: "Workflow Notes",
    category: "Pipeline / research",
    rhythm: "Weekly refresh",
    status: "Prototype",
  },
];

const demoItems = [
  {
    title: "Design system breakdown for an editorial landing page",
    source: "Design Channels",
    tags: ["design system", "editorial", "landing"],
    summary: "展示如何把版式、颜色和组件拆成可复用模块，适合作为系统型页面的研究样例。",
    variant: "variant-1",
    label: "design system",
  },
  {
    title: "Ambient workflow sound pack / index sample",
    source: "Reference Clips",
    tags: ["ambient", "audio", "index"],
    summary: "模拟素材索引类条目，强调标题、来源、标签与筛选入口的统一组织方式。",
    variant: "variant-2",
    label: "audio index",
  },
  {
    title: "Motion typography case clip",
    source: "Design Channels",
    tags: ["motion", "type", "case study"],
    summary: "用于验证动态视觉方向的浏览节奏，让索引界面不只像表格，也更像一个可探索的入口。",
    variant: "variant-3",
    label: "motion",
  },
  {
    title: "Product walkthrough / dashboard interaction sample",
    source: "Creative Tutorials",
    tags: ["dashboard", "product", "ui"],
    summary: "模拟系统型产品演示条目，方便检索 dashboard、UI、product 等不同主题。",
    variant: "variant-4",
    label: "dashboard",
  },
  {
    title: "Camera movement reference for short-form video",
    source: "Reference Clips",
    tags: ["camera", "reference", "short-form"],
    summary: "作为镜头调度与节奏参考的样例，体现索引系统对灵感素材库的价值。",
    variant: "variant-5",
    label: "camera",
  },
  {
    title: "Creative coding visual loop / archive sample",
    source: "Design Channels",
    tags: ["creative coding", "visual", "archive"],
    summary: "用于展示带标签归档的视觉条目样式，强调系统对内容聚合的扩展性。",
    variant: "variant-6",
    label: "archive",
  },
  {
    title: "UI onboarding flow review",
    source: "Creative Tutorials",
    tags: ["onboarding", "flow", "ux"],
    summary: "模拟可回看、可收藏的流程评审条目，让列表既像内容库，也像研究工具。",
    variant: "variant-1",
    label: "ux flow",
  },
  {
    title: "Studio interview clip / mood research sample",
    source: "Reference Clips",
    tags: ["studio", "interview", "mood"],
    summary: "体现来源、主题和标签三层维度下的检索方式，适合做灵感收集场景演示。",
    variant: "variant-2",
    label: "mood",
  },
  {
    title: "Rendering pipeline note / capture sample",
    source: "Workflow Notes",
    tags: ["render", "pipeline", "capture"],
    summary: "模拟工作流记录型条目，体现系统既能索引结果，也能索引过程。",
    variant: "variant-3",
    label: "pipeline",
  },
];

const searchInput = document.getElementById("searchInput");
const sourceFilter = document.getElementById("sourceFilter");
const tagFilter = document.getElementById("tagFilter");
const cardGrid = document.getElementById("cardGrid");
const resultsMeta = document.getElementById("resultsMeta");
const sourceTable = document.getElementById("sourceTable");

function unique(values) {
  return [...new Set(values)];
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderFilters() {
  unique(demoItems.map((item) => item.source)).forEach((source) => {
    const option = document.createElement("option");
    option.value = source;
    option.textContent = source;
    sourceFilter.appendChild(option);
  });

  unique(demoItems.flatMap((item) => item.tags))
    .sort((left, right) => left.localeCompare(right))
    .forEach((tag) => {
      const option = document.createElement("option");
      option.value = tag;
      option.textContent = tag;
      tagFilter.appendChild(option);
    });
}

function matches(item) {
  const keyword = searchInput.value.trim().toLowerCase();
  const source = sourceFilter.value;
  const tag = tagFilter.value;
  const haystack = [item.title, item.source, item.summary, item.tags.join(" ")]
    .join(" ")
    .toLowerCase();

  if (keyword && !haystack.includes(keyword)) {
    return false;
  }

  if (source && item.source !== source) {
    return false;
  }

  if (tag && !item.tags.includes(tag)) {
    return false;
  }

  return true;
}

function renderCards() {
  const filtered = demoItems.filter(matches);
  resultsMeta.textContent = `${filtered.length} demo items · sanitized public dataset · local filter logic preserved`;

  if (!filtered.length) {
    cardGrid.innerHTML = `
      <article class="card-item">
        <h4>No matching result</h4>
        <p>试试清空关键词，或切换来源 / 标签进行重新浏览。</p>
      </article>
    `;
    return;
  }

  cardGrid.innerHTML = filtered
    .map((item) => {
      const metaItems = [item.source, ...item.tags]
        .map((value) => `<span>${escapeHtml(value)}</span>`)
        .join("");

      return `
        <article class="card-item">
          <div class="thumb ${escapeHtml(item.variant)}">
            <span class="thumb-label">${escapeHtml(item.label)}</span>
          </div>
          <h4>${escapeHtml(item.title)}</h4>
          <div class="card-meta">${metaItems}</div>
          <p>${escapeHtml(item.summary)}</p>
        </article>
      `;
    })
    .join("");
}

function renderSources() {
  sourceTable.innerHTML = demoSources
    .map((source) => {
      const statusClass =
        source.status === "Active"
          ? "active"
          : source.status === "Prototype"
            ? "prototype"
            : "readonly";

      return `
        <tr class="source-row">
          <td>${escapeHtml(source.name)}</td>
          <td>${escapeHtml(source.category)}</td>
          <td>${escapeHtml(source.rhythm)}</td>
          <td><span class="status ${statusClass}">${escapeHtml(source.status)}</span></td>
        </tr>
      `;
    })
    .join("");
}

[searchInput, sourceFilter, tagFilter].forEach((element) => {
  element.addEventListener("input", renderCards);
  element.addEventListener("change", renderCards);
});

renderFilters();
renderCards();
renderSources();
