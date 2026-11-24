
  // ---- Status guide (added by session_hub/guide.py, inside the dashboard's script) ----
  const gdRoot = el("div", { class: "gd-main" });
  const gdHeader = document.querySelector("header");
  // The dashboard's code looks its elements up by id, so hide the ones this page has no use for
  for (const n of [$("main"), ...gdHeader.querySelectorAll(".conn, .kpis, #notifyBtn")]) n.hidden = true;
  gdHeader.querySelector("h1").replaceChildren(el("a", { class: "gd-home", href: "./" }, "Session Hub"));
  $("guideLink").hidden = $("playbookLink").hidden = false;
  $("guideLink").setAttribute("aria-current", "page");
  gdHeader.after(gdRoot);

  function gdRender() {
    document.title = `${t("guide.title")} - Session Hub`;
    gdRoot.replaceChildren(
      el("h2", {}, t("guide.title")),
      el("p", {}, t("guide.intro")),
      ...Object.entries(STATUS_STATES).map(([status, states]) => el("section", { class: "panel", id: status, "aria-label": t("group." + status) },
        el("h2", {}, statusLabel(status, t("group." + status))),
        el("p", { class: "gd-lead" }, t("help.group." + status)),
        el("div", { class: "ctable-wrap" }, el("table", { class: "ctable" },
          el("thead", {}, el("tr", {}, ["state", "id", "meaning"].map((c) => el("th", { scope: "col" }, t("guide.col." + c))))),
          el("tbody", {}, states.map((s) => el("tr", {},
            el("td", { class: "nowrap" }, badge(s)),
            el("td", { class: "nowrap" }, el("code", {}, s)),
            el("td", { class: "wide" }, t("help.state." + s))))))))));
  }
  $("langBtn").addEventListener("click", gdRender); // after the dashboard's handler, which switches the language
  gdRender();
