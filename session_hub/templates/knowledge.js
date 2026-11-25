  // ---- Knowledge page (added by session_hub/knowledge.py, inside the dashboard's script) ----
  const knRoot = el("div", { class: "kn-main" });
  const knHeader = document.querySelector("header");
  // The dashboard's code looks its elements up by id, so hide the ones this page has no use for
  for (const n of [$("main"), ...knHeader.querySelectorAll(".conn, .kpis, #notifyBtn")]) n.hidden = true;
  knHeader.querySelector("h1").replaceChildren(el("a", { class: "kn-home", href: "./" }, "Session Hub"));
  $("guideLink").hidden = $("knowledgeLink").hidden = $("playbookLink").hidden = false;
  $("knowledgeLink").setAttribute("aria-current", "page");
  knHeader.after(knRoot);

  // ---- Pure helpers: filtering, sorting, and the address ----
  const KN_PAGE = 50;
  const KN_TAGS = 20;
  const KN_PARAMS = ["kind", "tag", "scope", "q", "sort"];
  const knDefaults = () => ({ kind: "", tag: "", scope: "", q: "", sort: "recent", shared: false, obsolete: false, limit: KN_PAGE });

  // The filters live in the query string, so that a filtered list can be shared
  function knParse(search) {
    const p = new URLSearchParams(search), f = knDefaults();
    for (const k of KN_PARAMS) if (p.get(k)) f[k] = p.get(k);
    if (!["recent", "reporters"].includes(f.sort)) f.sort = "recent";
    f.shared = p.get("shared") === "1";
    f.obsolete = p.get("obsolete") === "1";
    return f;
  }

  function knSerialize(f) {
    const p = new URLSearchParams(), d = knDefaults();
    for (const k of KN_PARAMS) if (f[k] && f[k] !== d[k]) p.set(k, f[k]);
    if (f.shared) p.set("shared", "1");
    if (f.obsolete) p.set("obsolete", "1");
    const s = p.toString();
    return s ? "?" + s : "";
  }

  const knActive = (it) => (it.status || "active") === "active";
  const knTitle = (it) => it.title || it.summary || it.key;

  function knSearchText(it) {
    return [knTitle(it), it.body, ...(it.tags || []), ...(it.scopes || [])].join("\n").toLowerCase();
  }

  // The items that pass every filter, in the chosen order
  function knFilter(items, f) {
    const q = (f.q || "").trim().toLowerCase();
    const out = items.filter((it) => (f.obsolete || knActive(it))
      && (!f.kind || it.kind === f.kind)
      && (!f.tag || (it.tags || []).includes(f.tag))
      && (!f.scope || (it.scopes || []).includes(f.scope))
      && (!f.shared || (it.reporters || []).length > 1)
      && (!q || q.split(/\s+/).every((w) => knSearchText(it).includes(w))));
    const recent = (a, b) => String(b.last_ts).localeCompare(String(a.last_ts));
    return out.sort(f.sort === "reporters"
      ? (a, b) => (b.reporters || []).length - (a.reporters || []).length || recent(a, b) : recent);
  }

  // Counts for the summary row and the filter chips, over the items the current view could show
  function knStats(col, f) {
    const view = col.view || {};
    const pool = col.items.filter((it) => f.obsolete || knActive(it));
    const kinds = new Map(), tags = new Map(), scopes = new Set();
    for (const it of pool) {
      kinds.set(it.kind, (kinds.get(it.kind) || 0) + 1);
      for (const tag of it.tags || []) tags.set(tag, (tags.get(tag) || 0) + 1);
      for (const sc of it.scopes || []) scopes.add(sc);
    }
    const order = [...(view.order || []), ...[...kinds.keys()].filter((k) => !(view.order || []).includes(k))];
    return {
      total: pool.length, kinds, order: order.filter((k) => kinds.has(k)), groups: view.groups || {},
      reporters: new Set(pool.flatMap((it) => it.reporters || [])).size,
      tagCounts: tags,
      tags: [...tags].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, KN_TAGS),
      scopes: [...scopes].sort(),
    };
  }
  // The tag chips and scope options to draw: the stats' own, plus the active tag or scope when the
  // pool does not list it (a rare tag below the top chips, an obsolete item's scope, a shared address),
  // so that a filter that narrows the list always has a control that shows and undoes it
  function knControls(s, f) {
    return {
      kinds: f.kind && !s.order.includes(f.kind) ? [...s.order, f.kind] : s.order,
      tags: f.tag && !s.tags.some(([tag]) => tag === f.tag) ? [...s.tags, [f.tag, s.tagCounts.get(f.tag) || 0]] : s.tags,
      scopes: f.scope && !s.scopes.includes(f.scope) ? [...s.scopes, f.scope] : s.scopes,
    };
  }
  // ---- End of the pure helpers ----

  let knCol = null; // the knowledge collection of the last snapshot, or null before the first one
  let knFailed = null; // why the first read failed (an HTTP status, or 0 for no answer); cleared on success
  let knNames = new Map(); // session id -> title, from the last snapshot
  let knFilters = knParse(location.search);
  // The hash comes from a link that anyone may share, so a malformed one selects nothing
  const knEntry = () => { try { return decodeURIComponent(location.hash.slice(1)); } catch (e) { return ""; } };
  const knName = (sid) => knNames.get(sid) || sid;

  // The search box and the toggles are made once, so a redraw never drops the reader's focus
  const knSearch = el("input", { type: "search", class: "kn-search", value: knFilters.q, oninput: (e) => knSet({ q: e.target.value }) });
  const knSort = el("select", { class: "kn-select", onchange: (e) => knSet({ sort: e.target.value }) });
  const knScope = el("select", { class: "kn-select", onchange: (e) => knSet({ scope: e.target.value }) });
  const knSharedBox = el("input", { type: "checkbox", onchange: (e) => knSet({ shared: e.target.checked }) });
  const knObsoleteBox = el("input", { type: "checkbox", onchange: (e) => knSet({ obsolete: e.target.checked }) });
  const knSharedLabel = el("label", { class: "kn-check" }, knSharedBox, el("span"));
  const knObsoleteLabel = el("label", { class: "kn-check" }, knObsoleteBox, el("span"));
  const knClear = el("button", { class: "iconbtn", onclick: () => knSet({ ...knDefaults() }, true) });
  const knSummary = el("div", { class: "kn-totals" });
  const knKindChips = el("div", { class: "kn-chips" });
  const knTagChips = el("div", { class: "kn-chips" });
  const knCount = el("span", { class: "kn-meta" });
  const knList = el("div", { class: "kn-listcol" });
  const knDetail = el("div", { class: "kn-detail" });
  const knHead = el("div", { class: "kn-head" });
  const knBar = el("div", { class: "kn-bar" },
    knSearch, knScope, knSort, knSharedLabel, knObsoleteLabel, knClear);
  const knSplit = el("div", { class: "kn-split" }, knList, knDetail);
  knRoot.append(knHead, knSummary, knBar, knKindChips, knTagChips, knCount, knSplit);

  function knSet(change, resetBox) {
    knFilters = { ...knFilters, ...change, limit: KN_PAGE };
    if (resetBox) knSearch.value = "";
    history.replaceState(null, "", location.pathname + knSerialize(knFilters) + location.hash);
    knDraw();
  }

  const knKindColor = (k) => `var(${GROUP_COLOR[k] || "--s-queue"})`;
  const knBadge = (it, groups) => el("span", { class: "badge", style: { background: knKindColor(it.kind) } }, L(groups[it.kind]) || it.kind || "-");
  const knExcerpt = (it) => (it.body || "").replace(/\s+/g, " ").trim();

  function knRow(it, groups, selected) {
    return el("a", { class: "kn-row", href: "#" + encodeURIComponent(it.entry), "aria-current": selected ? "true" : null, style: { "--kn-c": knKindColor(it.kind) } },
      el("span", { class: "kn-rowhead" }, knBadge(it, groups), el("b", { class: "kn-rowtitle" }, knTitle(it)),
        knActive(it) ? null : el("span", { class: "chip" }, t("chip.obsolete"))),
      knExcerpt(it) ? el("span", { class: "kn-excerpt" }, knExcerpt(it)) : null,
      el("span", { class: "kn-meta" },
        t("k.reported", { s: (it.reporters || []).length, n: it.count }), " · ",
        el("span", { "data-ago": it.last_ts }, ago(it.last_ts)),
        (it.tags || []).slice(0, 3).map((tag) => ` #${tag}`)));
  }

  function knRevisions(it) {
    const hist = [...(it.history || [])].reverse();
    if (hist.length < 2) return null;
    return el("section", { class: "kn-section" }, el("h4", {}, t("kn.history")),
      hist.map((h, i) => el("details", { class: "kn-rev", ...(i === 0 ? { open: true } : {}) },
        el("summary", {}, t("kn.rev", { n: hist.length - i }), " · ", knName(h.session_id), " · ",
          el("span", { "data-ago": h.ts, title: h.ts }, ago(h.ts)), (h.status || "active") === "active" ? null : ` · ${t("chip.obsolete")}`),
        el("div", { class: "kn-title2" }, h.title), el("div", { class: "kn-body" }, h.body || t("kn.noBody")))));
  }

  function knShow(it, groups) {
    const reporters = (it.reporters || []).map((sid) => knNames.has(sid)
      ? el("a", { class: "src", href: `./#session:${encodeURIComponent(sid)}`, title: t("kn.openSession") }, knName(sid))
      : el("span", { class: "kn-meta" }, sid));
    knDetail.replaceChildren(el("article", { class: "kn-article", style: { "--kn-c": knKindColor(it.kind) } },
      el("a", { class: "iconbtn kn-back", href: "#", onclick: (e) => { e.preventDefault(); history.replaceState(null, "", location.pathname + location.search); knDraw(); } }, t("kn.back")),
      el("div", { class: "kn-rowhead" }, knBadge(it, groups), knActive(it) ? null : el("span", { class: "chip" }, t("chip.obsolete"))),
      el("h3", { class: "kn-heading" }, knTitle(it)),
      el("div", { class: "kn-body" }, it.body || t("kn.noBody")),
      el("div", { class: "kn-chips" },
        (it.tags || []).map((tag) => el("button", { class: "chip kn-chip", title: t("kn.filterTag"), onclick: () => knSet({ tag }) }, "#" + tag)),
        (it.scopes || []).map((scope) => el("button", { class: "chip kn-chip", title: t("kn.filterScope"), onclick: () => knSet({ scope }) }, "@" + scope))),
      el("div", { class: "kn-meta" }, t("kn.reportedBy"), " ", reporters.flatMap((r, i) => (i ? [", ", r] : [r])), " · ", t("k.reported", { s: (it.reporters || []).length, n: it.count }),
        " · ", el("span", { "data-ago": it.last_ts, title: it.last_ts }, ago(it.last_ts))),
      knRevisions(it)));
  }

  function knDraw() {
    document.title = `${t("kn.title")} - Session Hub`;
    knHead.replaceChildren(el("h2", {}, t("kn.title")), el("p", {}, t("kn.intro")));
    if (!knCol || !knCol.items.length) {
      for (const n of [knSummary, knBar, knKindChips, knTagChips, knCount, knSplit]) n.hidden = true;
      return knHead.append(el("div", { class: "empty" }, knCol ? t("col.empty")
        : knFailed === null ? t("kn.loading") : t(knFailed === 401 ? "kn.unauthorized" : "kn.error")));
    }
    for (const n of [knSummary, knBar, knKindChips, knTagChips, knCount, knSplit]) n.hidden = false;
    const f = knFilters, s = knStats(knCol, f);
    const entry = knEntry();
    const items = knFilter(knCol.items, f);
    const picked = knCol.items.find((it) => it.entry === entry);

    knSummary.replaceChildren(
      el("div", { class: "kn-total" }, el("b", {}, String(s.total)), el("span", {}, t("kn.active"))),
      el("div", { class: "kn-total" }, el("b", {}, String(s.reporters)), el("span", {}, t("kn.reporters"))));
    const { kinds: kindList, tags: tagList, scopes: scopeList } = knControls(s, f);
    knKindChips.replaceChildren(el("button", { class: "iconbtn", "aria-pressed": String(!f.kind), onclick: () => knSet({ kind: "" }) }, `${t("kn.allKinds")} ${s.total}`),
      ...kindList.map((k) => el("button", { class: "iconbtn", "aria-pressed": String(f.kind === k), style: { "--kn-c": knKindColor(k) },
        onclick: () => knSet({ kind: f.kind === k ? "" : k }) }, `${L(s.groups[k]) || k} ${s.kinds.get(k) || 0}`)));
    knTagChips.replaceChildren(...tagList.map(([tag, n]) => el("button", { class: "chip kn-chip", "aria-pressed": String(f.tag === tag),
      onclick: () => knSet({ tag: f.tag === tag ? "" : tag }) }, `#${tag} ${n}`)));

    knSearch.placeholder = t("kn.search");
    knSort.replaceChildren(...["recent", "reporters"].map((v) => el("option", { value: v, ...(f.sort === v ? { selected: true } : {}) }, t("kn.sort." + v))));
    knScope.replaceChildren(el("option", { value: "" }, t("kn.allScopes")),
      ...scopeList.map((sc) => el("option", { value: sc, ...(f.scope === sc ? { selected: true } : {}) }, "@" + sc)));
    knSharedBox.checked = f.shared;
    knObsoleteBox.checked = f.obsolete;
    knSharedLabel.lastChild.textContent = t("kn.shared");
    knObsoleteLabel.lastChild.textContent = t("col.showObsolete").trim();
    knClear.textContent = t("kn.clear");
    knCount.textContent = t("kn.count", { n: items.length, m: s.total });

    const shown = items.slice(0, f.limit);
    knList.replaceChildren(
      ...(shown.length ? shown.map((it) => knRow(it, s.groups, it.entry === entry)) : [el("div", { class: "kn-empty" }, t("col.emptyFiltered"))]),
      items.length > shown.length ? el("button", { class: "iconbtn kn-more", onclick: () => { knFilters.limit += KN_PAGE; knDraw(); } },
        t("kn.more", { n: Math.min(KN_PAGE, items.length - shown.length) })) : null);
    knSplit.classList.toggle("kn-has-detail", Boolean(entry));
    if (picked) knShow(picked, s.groups);
    else knDetail.replaceChildren(el("div", { class: "kn-empty" }, entry ? t("kn.notFound") : t("kn.pick")));
  }

  async function knLoad() {
    try {
      const r = await fetch("api/snapshot", { cache: "no-store" });
      if (!r.ok) throw r.status;
      const snap = await r.json();
      const col = (snap.collections || {}).knowledge || { items: [] };
      const names = new Map((snap.sessions || []).map((x) => [x.session_id, x.title || x.session_id]));
      const same = knCol !== null && JSON.stringify([col, [...names]]) === JSON.stringify([knCol, [...knNames]]);
      knCol = col;
      knNames = names;
      knFailed = null;
      if (!same) knDraw(); // a redraw would drop the reader's selection; the ago labels refresh on their own
    } catch (e) { // keep the last page after a first success; the next tick tries again
      if (knCol) return;
      knFailed = typeof e === "number" ? e : 0;
      knDraw();
    }
  }
  window.addEventListener("hashchange", knDraw);
  $("langBtn").addEventListener("click", knDraw); // after the dashboard's handler, which switches the language
  knDraw();
  knLoad();
  setInterval(knLoad, 15000);
