
  // ---- Playbook (added by session_hub/playbook.py, inside the dashboard's script) ----
  // A story returns the nodes to show. Stories call the dashboard's own render functions, so they
  // change with it. Sample text is an {en, ja} map; L() picks the current language.
  const PB_NOW = Date.now();
  const pbAt = (min) => new Date(PB_NOW - min * 60000).toISOString();
  const PB_TEXT = {
    title: { en: "Rate limiting for the auth API", ja: "認証APIのレート制限" },
    other: { en: "Structured log output", ja: "ログ出力の構造化" },
    long: { en: "A session whose title is far too long to fit on one line of a narrow card", ja: "狭いカードの1行にはとても収まりきらないほど長いタイトルを持つセッション" },
    summary: { en: "Started a Redis sliding-window implementation", ja: "Redis のスライディングウィンドウ方式で実装開始" },
    question: { en: "Requests per minute limit?", ja: "1分あたりのリクエスト上限は?" },
    error: { en: "npm ci fails with ERESOLVE", ja: "npm ci が ERESOLVE で失敗" },
    finding: { en: "Use a sliding window for rate limits", ja: "レート制限はスライディングウィンドウ方式にする" },
    body: { en: "A fixed window lets twice the limit through at its edge.", ja: "固定ウィンドウでは境界で倍の要求が通ります。" },
  };
  const pbText = (k) => L(PB_TEXT[k]);
  const PB_OPTIONS = ["60", "120", "300"];
  const pbAsk = (blocking) => ({ qid: 4, kind: "decision", blocking, question: pbText("question"), options: PB_OPTIONS, default: "120" });
  // A sample session in a given state
  const pbSession = (state, more = {}) => ({
    session_id: "pb-" + state, title: pbText("title"), state, phase: "implement", task_ref: "#128",
    summary: pbText("summary"), progress: { done: 1, total: 4, remaining: 7 }, usage: { input: 90000, output: 9000, cost_usd: 0.8 },
    heartbeat: pbAt(30), needs_action: false, ...more,
  });
  const pbEvent = (type, more = {}) => ({
    id: "pb-" + type, type, session_id: "pb-working", ts: pbAt(20), state_after: "working", summary: pbText("summary"), ...more,
  });
  const PB_EVENTS = {
    ask: () => ({ state_after: "needs_human", attention: pbAsk(true) }),
    answer: () => ({ writer: "parent", qid: 4, value: "120" }),
    command: () => ({ writer: "parent" }),
    pr: () => ({ state_after: "waiting_ci", pr: { number: 45, ci: "pending", unresolved_threads: 2 } }),
    ready: () => ({ state_after: "review_ready" }),
    done: () => ({ state_after: "done" }),
    fail: () => ({ state_after: "failed", last_error: pbText("error") }),
    finding: () => ({ finding: { title: pbText("finding") } }),
    heartbeat: () => ({ usage: { input: 90000, output: 9000, context_pct: 42 } }),
  };
  const pbItem = (kind, more = {}) => ({
    key: "pb-" + kind, title: pbText("finding"), body: pbText("body"), kind, tags: ["redis"], scopes: ["api"], status: "active",
    reporters: ["pb-working"], sources: [{ session_id: "pb-working", event_id: "pb-finding" }], count: 1, last_ts: pbAt(40), ...more,
  });
  const pbCollection = (view, items) => ({ description: PB_TEXT.body, label: { en: "Knowledge", ja: "ナレッジ" }, active: items.length, items, view });

  // Run a dashboard renderer against sample data and take what it drew out of its container
  function pbCapture(id, data, draw, settings = {}) {
    const saved = { ...db }, state = { view: ui.view, session: ui.session, byProject: ui.byProject, collapsed: ui.collapsed, lane: ui.lane };
    Object.assign(db, data);
    Object.assign(ui, { byProject: false, collapsed: new Set(), lane: { span: null, end: null } }, settings);
    try { draw(); return [...$(id).childNodes]; }
    finally { Object.assign(db, saved); Object.assign(ui, state); }
  }
  const pbEvents = (list) => new Map(list.map((e) => [e.id, e]));
  const pbProjects = () => [pbSession("needs_human", { needs_action: true, attention: pbAsk(true) }), pbSession("planning", { repo: "api" }), pbSession("working")];
  const pbKnown = () => [pbSession("working"), { ...pbSession("done"), title: pbText("other") }];
  const pbWith = (data, make) => { const saved = { ...db }; Object.assign(db, data); try { return make(); } finally { Object.assign(db, saved); } };

  const pbTokens = () => {
    for (const sheet of document.styleSheets)
      for (const rule of sheet.cssRules)
        if (rule.selectorText === ":root") return [...rule.style].filter((n) => n.startsWith("--") && n !== "--glow-ms");
    return [];
  };
  const pbTokenRows = (match, sample) => pbTokens().filter((n) => match.test(n)).map((n) =>
    el("div", { class: "pb-token" }, el("code", {}, n), el("code", {}, css(n)), sample(n)));

  const PB = [
    ["Tokens", [
      ["Color", () => pbTokenRows(/^--(bg|panel|ink|muted|line|hover|accent|flash|on-fill|s-.+|g-.+)$/,
        (n) => el("div", { class: "pb-swatch", style: { background: `var(${n})` } }))],
      ["Type", () => pbTokenRows(/^--fs-/, (n) => el("div", { class: "pb-sample", style: { fontSize: `var(${n})` } }, pbText("title")))],
      ["Weight", () => pbTokenRows(/^--fw-/, (n) => el("div", { class: "pb-sample", style: { fontWeight: `var(${n})` } }, pbText("title")))],
      ["Spacing", () => pbTokenRows(/^--space-/, (n) => el("div", { class: "pb-bar", style: { width: `var(${n})` } }))],
      ["Corners", () => pbTokenRows(/^--radius-/, (n) => el("div", { class: "pb-box", style: { borderRadius: `var(${n})` } }))],
    ]],
    ["GroupHeading", [
      ["All groups, with cards", () => pbCapture("sessions", { sessions: [
        pbSession("needs_human", { needs_action: true, attention: pbAsk(true) }), pbSession("working"), pbSession("done"),
        pbSession("abandoned", { archived: { since: pbAt(60) } })] }, renderSessions), "narrow"],
      ["Grid layout", () => el("main", { class: "grid", style: { padding: "0" } }, pbCapture("sessions", { sessions: [
        pbSession("needs_human", { needs_action: true, attention: pbAsk(true) }), pbSession("failed", { needs_action: true }), pbSession("working")] }, renderSessions))],
      ["No sessions", () => pbCapture("sessions", { sessions: [] }, renderSessions), "narrow"],
    ]],
    ["ProjectHeading", [
      ["Expanded", () => pbCapture("sessions", { sessions: pbProjects() }, renderSessions, { byProject: true }), "narrow"],
      ["Collapsed", () => pbCapture("sessions", { sessions: pbProjects() }, () => {
        ui.collapsed = new Set(sessionGroups(db.sessions).map(([key]) => key));
        renderSessions();
      }, { byProject: true }), "narrow"],
      ["Status group collapsed", () => pbCapture("sessions", { sessions: [pbSession("working", { repo: "acme/app" }), pbSession("done", { repo: "acme/app" })] }, () => {
        ui.collapsed = new Set([subKey("acme/app", "done")]);
        renderSessions();
      }, { byProject: true }), "narrow"],
      ["Grid layout", () => el("main", { class: "grid", style: { padding: "0" } }, pbCapture("sessions", { sessions: [
        pbSession("working", { repo: "acme/app" }), pbSession("done", { repo: "acme/app" })] }, renderSessions, { byProject: true }))],
    ]],
    ["SessionCard", [
      ...Object.keys(STATE_COLORS).filter((s) => !["stale", "review_pending", "archived"].includes(s)).map((s) =>
        [s, () => sessionCard(pbSession(s, s === "failed" ? { last_error: pbText("error") } : {})), "narrow"]),
      ["archived", () => sessionCard(pbSession("done", { archived: { since: pbAt(60) } })), "narrow"],
      ["stale", () => sessionCard(pbSession("working", { stale: true })), "narrow"],
      ["review_pending (gate not met)", () => sessionCard(pbSession("review_ready", {
        gate: ["ci"], gate_codes: [{ code: "ci", value: "unknown" }] })), "narrow"],
      ["Blocking question", () => sessionCard(pbSession("needs_human", { attention: pbAsk(true) })), "narrow"],
      ["Non-blocking question", () => sessionCard(pbSession("working", { attention: pbAsk(false) })), "narrow"],
      // The static page omits the delete button, so the story adds it
      ["Delete button", () => {
        const wrap = sessionCard(pbSession("working"));
        wrap.classList.add("deletable");
        wrap.append(el("button", { class: "carddel", type: "button", "aria-label": t("sessions.delete") }, "×"));
        return wrap;
      }, "narrow"],
      ["Pull request", () => sessionCard(pbSession("waiting_ci", { pr: { number: 45, url: "https://example.com/pull/45", ci: "pending", unresolved_threads: 2 } })), "narrow"],
      ["Long title", () => sessionCard(pbSession("working", { title: pbText("long") })), "narrow"],
      ["Minimal", () => sessionCard({ session_id: "pb-minimal", state: "queued", heartbeat: pbAt(1) }), "narrow"],
      ["Selected", () => { const s = ui.session; ui.session = "pb-working"; const n = sessionCard(pbSession("working")); ui.session = s; return n; }, "narrow"],
    ]],
    ["StateBadge", [
      ["Every state", () => el("div", { class: "pb-row" }, Object.keys(STATE_COLORS).map(badge))],
    ]],
    ["EventRow", [
      ...TYPE_KEYS.map((type) => [type, () => pbWith({ sessions: pbKnown() }, () => eventRow(pbEvent(type, (PB_EVENTS[type] || (() => ({})))())))]),
      ["Every change chip", () => pbWith({ sessions: pbKnown() }, () => eventRow(pbEvent("report", { id: "pb-chips", phase: "test", diff: {
        state: { from: "working", to: "review_ready" }, phase: { from: "implement", to: "test" },
        progress: { from: { done: 1, total: 4 }, to: { done: 2, total: 4 } }, attention: { from: { qid: 4 }, to: null },
        ready: true, confidence: { from: "low", to: "high" } } })))],
      ["Phase chip", () => pbWith({ sessions: pbKnown() }, () => eventRow(pbEvent("report", { id: "pb-phase", phase: "implement" })))],
    ]],
    ["Feed", [
      ["Days and collapsed heartbeats", () => { const hb = ui.heartbeat; ui.heartbeat = true; try { return pbCapture("feedView", { sessions: pbKnown(), events: pbEvents([
        pbEvent("report", { id: "pb-f1" }), pbEvent("heartbeat", { id: "pb-f2", ts: pbAt(25) }), pbEvent("heartbeat", { id: "pb-f3", ts: pbAt(26) }),
        pbEvent("start", { id: "pb-f4", ts: pbAt(2000) })]) }, renderFeed); } finally { ui.heartbeat = hb; } }],
      ["Empty", () => pbCapture("feedView", { events: new Map() }, renderFeed)],
      ["Highlighted row", () => pbWith({ sessions: pbKnown() }, () => {
        const row = eventRow(pbEvent("report", { id: "pb-flash" }));
        row.classList.add("flash");
        return el("div", { class: "feed" }, row);
      })],
      ["New events bar", () => el("button", { class: "newbar show" }, t("newbar", { n: 3 }) + " ↑")],
    ]],
    ["Overview", [
      ["Every session on one axis", () => {
        const sess = [pbSession("working"), { ...pbSession("done"), session_id: "pb-done", title: pbText("other") }];
        const list = [["start", 180, "working"], ["ask", 90, "needs_human"], ["answer", 60, "working"]].map(([type, min, after], i) =>
          pbEvent(type, { id: "pb-o" + i, ts: pbAt(min), ...(PB_EVENTS[type] || (() => ({})))(), state_after: after }));
        const nodes = pbCapture("overview", { sessions: sess, events: pbEvents(list) }, renderOverview, { session: "pb-done" });
        return [el("div", { class: "overview" }, nodes), el("div", { class: "legend" }, [...$("ovLegend").childNodes])];
      }],
    ]],
    ["Swimlanes", [
      ["States over time", () => {
        const list = [["start", 120, "working"], ["ask", 80, "needs_human"], ["answer", 60, "working"], ["ready", 20, "review_ready"]].map(([type, min, after], i) =>
          pbEvent(type, { id: "pb-l" + i, ts: pbAt(min), state_after: after, ...(PB_EVENTS[type] || (() => ({})))(), ...{ state_after: after } }));
        const nodes = pbCapture("lanes", { sessions: [pbSession("working")], events: pbEvents(list) }, renderLanes);
        return [el("div", { class: "lanes" }, nodes), el("div", { class: "legend" }, [...$("legend").childNodes])];
      }],
      ["Zoom controls", () => pbClone("#lanebar")],
      ["Zoomed in, with the details of the shown period", () => {
        const list = [["start", 120, "working"], ["ask", 80, "needs_human"], ["answer", 60, "working"], ["ready", 20, "review_ready"]].map(([type, min, after], i) =>
          pbEvent(type, { id: "pb-z" + i, ts: pbAt(min), ...(PB_EVENTS[type] || (() => ({})))(), state_after: after }));
        const lane = { span: 60 * 60000, end: PB_NOW - 40 * 60000 };
        const nodes = pbCapture("lanes", { sessions: [pbSession("working")], events: pbEvents(list) }, renderLanes, { lane });
        return [el("div", { class: "lanes zoomed" }, nodes), ...$("laneTable").childNodes];
      }],
      ["While dragging", () => el("div", { class: "lanes zoomed dragging" }, pbCapture("lanes", { sessions: [pbSession("working")],
        events: pbEvents([pbEvent("start")]) }, renderLanes))],
      ["Period without events", () => {
        const lane = { span: 60000, end: PB_NOW };
        pbCapture("lanes", { sessions: [pbSession("working")], events: pbEvents([pbEvent("heartbeat", { ts: pbAt(60) })]) }, renderLanes, { lane });
        return [...$("laneTable").childNodes];
      }],
      ["Lane that received a message", () => {
        markGlow(glowKey.session("pb-lane"), css("--s-needs"));
        return el("div", { class: "lanes" }, pbCapture("lanes", { sessions: [pbSession("working", { session_id: "pb-lane" })],
          events: pbEvents([pbEvent("start", { session_id: "pb-lane" })]) }, renderLanes));
      }],
      ["Empty", () => pbCapture("lanes", { sessions: [], events: new Map() }, renderLanes)],
    ]],
    ["Collection", [
      ["Cards by kind", () => pbCapture("colView", { sessions: pbKnown(), collections: { pb: pbCollection(
        { type: "cards", group_by: "kind" }, [...Object.keys(GROUP_COLOR).map((k) => pbItem(k)),
          pbItem("caveat", { key: "pb-2", count: 3, reporters: ["pb-working", "pb-done"] })]) } }, () => renderCollection("pb"))],
      ["Obsolete card", () => pbWith({ sessions: pbKnown() }, () => knowledgeCard(pbItem("howto", { status: "obsolete" }), "var(--s-review)"))],
      ["Table", () => pbCapture("colView", { sessions: pbKnown(), collections: { pb: pbCollection(
        { type: "table", columns: ["title", "kind", "reporters", "last_ts"] }, [pbItem("howto"), pbItem("issue")]) } }, () => renderCollection("pb"))],
      ["Every item filtered out", () => pbCapture("colView", { collections: { pb: pbCollection({ type: "cards" },
        [pbItem("howto", { status: "obsolete" })]) } }, () => renderCollection("pb"))],
      ["Empty", () => pbCapture("colView", { collections: { pb: pbCollection({ type: "cards" }, []) } }, () => renderCollection("pb"))],
    ]],
    ["Connection", [
      ["Every state", () => el("div", { class: "pb-row" }, [["", "conn.connecting"], ["live", "conn.live"], ["retry", "conn.retry"], ["retry", "conn.polling"], ["", "conn.down"], ["", "conn.static"]]
        .map(([kind, key]) => el("span", { class: "conn " + kind }, el("span", { class: "dot" }), el("span", {}, t(key, { ts: new Date(PB_NOW).toLocaleString(LOCALE) })))))],
    ]],
    ["Panel", [
      ["Heading with a scope and a button", () => el("section", { class: "panel" }, el("h2", {}, t("tl.title"), " ",
        el("span", { class: "chip" }, t("tl.all")), el("button", { class: "iconbtn danger" }, t("sessions.delete"))))],
    ]],
    ["Controls", [
      ["Buttons", () => el("div", { class: "pb-row" }, el("button", { class: "iconbtn" }, t("btn.theme")),
        el("button", { class: "iconbtn", "aria-pressed": "true" }, t("btn.notify")),
        el("button", { class: "iconbtn danger" }, t("sessions.delete")), el("button", { class: "iconbtn danger", disabled: true }, t("sessions.delete")))],
      ["Layout toggle", () => pbClone(".seg")],
      ["Toolbar and tabs", () => pbClone(".toolbar")],
      ["Event type filter", () => pbClone("#fTypes")],
      ["Header", () => pbClone("header")],
      ["Chips", () => el("div", { class: "pb-row" }, el("span", { class: "chip" }, "implement"), el("span", { class: "chip" }, "#redis"))],
      ["Tooltip", () => el("div", { class: "tip", style: { position: "static", display: "inline-block" } }, t("state.working"))],
    ]],
    ["Glow", [
      ["On a card (restarts when the page redraws)", () => {
        const card = sessionCard(pbSession("needs_human"));
        const body = card.querySelector(".card");
        body.classList.add("glow");
        body.style.setProperty("--glow", css("--s-needs"));
        return card;
      }, "narrow"],
      ["On a timeline row", () => pbWith({ sessions: pbKnown() }, () => {
        const row = eventRow(pbEvent("ready", { id: "pb-g" }));
        row.classList.add("glow");
        row.style.setProperty("--glow", css("--s-review"));
        return row;
      })],
    ]],
  ];

  // A copy of a static part of the page. Ids are dropped so that the original stays unique.
  function pbClone(selector) {
    const copy = pbPage.querySelector(selector).cloneNode(true);
    for (const n of [copy, ...copy.querySelectorAll("[id]")]) n.removeAttribute("id");
    if (selector === "header") { copy.style.position = "static"; copy.querySelector("a.iconbtn").hidden = false; }
    return copy;
  }

  // Keep the dashboard's own markup in the document, hidden: its renderers look containers up by id
  const pbPage = el("div", { hidden: true });
  pbPage.append(...[...document.body.children].filter((n) => n.tagName !== "SCRIPT" && n.id !== "tip"));
  const pbRoot = el("div", { class: "pb-layout" });
  // A story's group heading would toggle and persist the dashboard's own collapsed groups (hub.collapsed)
  pbRoot.addEventListener("click", (e) => { if (e.target.closest(".project")) e.stopPropagation(); }, true);
  document.body.prepend(pbPage, pbRoot);

  // Page layout, not components: the window-high split, its connector, and the grid's fixed detail panel
  const PB_LAYOUT = new Set(["open", "slide", "gridlayout", "scroll", "linked", "off"]);
  // The dashboard's classes that no story shows
  function pbMissing() {
    const own = [...document.styleSheets][0], names = new Set();
    const walk = (rules) => { for (const r of rules) { if (r.selectorText) for (const m of r.selectorText.matchAll(/\.([a-z][\w-]*)/gi)) names.add(m[1]); if (r.cssRules) walk(r.cssRules); } };
    walk(own.cssRules);
    return [...names].filter((n) => !PB_LAYOUT.has(n) && !pbRoot.querySelector("." + n)).sort();
  }

  // A story that throws shows its error in its own frame, so that the rest of the page still draws
  function pbDraw(id, make) {
    try { return [].concat(make()); }
    catch (err) {
      console.error(id, err);
      return el("pre", { class: "pb-failed" }, `Story failed: ${err}`);
    }
  }

  function pbRender() {
    document.title = "Session Hub playbook";
    // A click in a story may have filtered or selected something; start each redraw from a clean slate
    Object.assign(ui, { session: "", text: "", showObsolete: false, colGroups: {} });
    const button = (label, act) => el("button", { class: "iconbtn", onclick: act }, label);
    const nav = el("nav", { class: "pb-nav" }, el("b", {}, "Session Hub playbook"),
      location.protocol === "file:" ? null : el("a", { href: "./" }, "← Session Hub"),
      el("div", { class: "pb-tools" }, button(t("btn.theme"), () => { $("themeBtn").click(); pbRender(); }),
        button(t("btn.lang"), () => { $("langBtn").click(); pbRender(); })),
      PB.map(([name]) => el("a", { href: "#" + name }, name)));
    const main = el("div", { class: "pb-main" }, PB.map(([name, stories]) => el("section", { id: name }, el("h2", {}, name),
      stories.map(([story, make, width]) => el("div", { class: "pb-story", "data-story": `${name}/${story}` },
        el("div", { class: "pb-name" }, story),
        el("div", { class: "pb-frame" + (width ? " pb-" + width : "") }, pbDraw(`${name}/${story}`, make)))))));
    pbRoot.replaceChildren(nav, main);
    const missing = pbMissing();
    main.append(el("section", { id: "Coverage" }, el("h2", {}, "Coverage"),
      el("div", { class: "pb-name", id: "pbMissing" }, missing.length ? "No story shows: " + missing.join(", ") : "Every class of the dashboard appears in a story.")));
  }
  pbRender();
