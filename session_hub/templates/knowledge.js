  // ---- Knowledge summary (added by session_hub/knowledge.py, inside the dashboard's script) ----
  const knRoot = el("div", { class: "kn-main" });
  const knHeader = document.querySelector("header");
  // The dashboard's code looks its elements up by id, so hide the ones this page has no use for
  for (const n of [$("main"), ...knHeader.querySelectorAll(".conn, .kpis, #notifyBtn")]) n.hidden = true;
  knHeader.querySelector("h1").replaceChildren(el("a", { class: "kn-home", href: "./" }, "Session Hub"));
  $("guideLink").hidden = $("knowledgeLink").hidden = $("playbookLink").hidden = false;
  $("knowledgeLink").setAttribute("aria-current", "page");
  knHeader.after(knRoot);

  const KN_LISTED = { issues: 10, shared: 10, latest: 10, tags: 20 };
  let knCol = null; // the knowledge collection of the last snapshot, or null before the first one

  const knTitle = (it) => it.title || it.summary || it.key;
  const knLink = (it) => el("a", { href: "./#col:knowledge", title: t("kn.open") }, knTitle(it));
  const knSection = (id, lead, ...body) => el("section", { class: "panel", id, "aria-label": t("kn.sec." + id) },
    el("h2", {}, t("kn.sec." + id)), lead ? el("p", { class: "gd-lead kn-meta" }, lead) : null, ...body);
  const knItems = (items, extra) => items.length
    ? el("ul", { class: "kn-list" }, items.map((it) => el("li", {}, knLink(it), extra(it))))
    : el("div", { class: "kn-empty" }, t("kn.none"));

  function knSummarize(col) {
    const active = col.items.filter((it) => (it.status || "active") === "active");
    const view = col.view || {};
    const kinds = new Map();
    for (const it of active) kinds.set(it.kind, (kinds.get(it.kind) || 0) + 1);
    const order = [...(view.order || []), ...[...kinds.keys()].filter((k) => !(view.order || []).includes(k))];
    const tags = new Map();
    for (const it of active) for (const tag of it.tags || []) tags.set(tag, (tags.get(tag) || 0) + 1);
    const byTime = (a, b) => String(b.last_ts).localeCompare(String(a.last_ts));
    return {
      active, kinds, order, groups: view.groups || {},
      reporters: new Set(active.flatMap((it) => it.reporters || [])).size,
      issues: active.filter((it) => it.kind === "issue").sort(byTime).slice(0, KN_LISTED.issues),
      shared: active.filter((it) => (it.reporters || []).length > 1)
        .sort((a, b) => b.reporters.length - a.reporters.length || byTime(a, b)).slice(0, KN_LISTED.shared),
      latest: [...active].sort(byTime).slice(0, KN_LISTED.latest),
      tags: [...tags].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, KN_LISTED.tags),
    };
  }

  function knRender() {
    document.title = `${t("kn.title")} - Session Hub`;
    const head = [el("h2", {}, t("kn.title")), el("p", {}, t("kn.intro"))];
    if (!knCol) return knRoot.replaceChildren(...head, el("div", { class: "empty" }, t("kn.loading")));
    const s = knSummarize(knCol);
    if (!s.active.length) return knRoot.replaceChildren(...head, el("div", { class: "empty" }, t("col.empty")));
    const when = (it) => el("span", { class: "kn-meta", "data-ago": it.last_ts }, ago(it.last_ts));
    knRoot.replaceChildren(...head,
      knSection("totals", null, el("div", { class: "kn-totals" },
        el("div", { class: "kn-total" }, el("b", {}, String(s.active.length)), el("span", {}, t("kn.active"))),
        el("div", { class: "kn-total" }, el("b", {}, String(s.reporters)), el("span", {}, t("kn.reporters"))),
        ...s.order.map((k) => el("div", { class: "kn-total", style: { "--kn-c": `var(${GROUP_COLOR[k] || "--s-queue"})` } },
          el("b", {}, String(s.kinds.get(k) || 0)), el("span", {}, L(s.groups[k]) || k))))),
      knSection("issues", null, knItems(s.issues, when)),
      knSection("shared", t("kn.sharedLead"), knItems(s.shared, (it) =>
        el("span", { class: "kn-meta" }, t("k.reported", { s: it.reporters.length, n: it.count })))),
      knSection("latest", null, knItems(s.latest, (it) => el("span", { class: "kn-meta" }, `${L(s.groups[it.kind]) || it.kind} · `, when(it)))),
      knSection("tags", null, s.tags.length
        ? el("div", { class: "kn-tags" }, s.tags.map(([tag, n]) => el("span", { class: "chip" }, `#${tag} ${n}`)))
        : el("div", { class: "kn-empty" }, t("kn.none"))));
  }

  async function knLoad() {
    try {
      const r = await fetch("api/snapshot", { cache: "no-store" });
      if (!r.ok) return;
      const snap = await r.json();
      knCol = (snap.collections || {}).knowledge || { items: [] };
      knRender();
    } catch (_) {} // keep the last page; the next tick tries again
  }
  $("langBtn").addEventListener("click", knRender); // after the dashboard's handler, which switches the language
  knRender();
  knLoad();
  setInterval(knLoad, 15000);
