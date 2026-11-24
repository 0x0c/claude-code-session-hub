"""Static checks of the dashboard page. The suite has no browser, so these cover its wiring."""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

PAGE = (Path(__file__).resolve().parent.parent / "session_hub/templates/dashboard.html").read_text(encoding="utf-8")

# Custom properties that the script sets on an element at run time
SET_BY_SCRIPT = {"glow", "glow-ms", "kc", "group-color", "header-h"}
SIZED = re.compile(r"(?<![\w-])(font|font-size|border(?:-\w+)*-radius|(?:row-|column-)?gap|(?:padding|margin)(?:-\w+)*):\s*([^;}]+)")
WEIGHT = re.compile(r"font-weight:(?!\s*(?:var\(|inherit))[^;}]+")
COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|hsl)a?\(")
PAINT = re.compile(r"(?<![\w-])(?:color|background(?:-color)?|border(?:-\w+)*-color|outline-color|fill|stroke):\s*([^;}]+)")
OUTLINE = re.compile(r"(?<![\w-])(?:border(?:-(?:top|right|bottom|left))?|outline):\s*([^;}]+)")
PAINT_VALUE = re.compile(r"var\(--|color-mix\(|(?:transparent|inherit|currentColor|none)\s*$")


def tokens(block):
    return dict(re.findall(r"--([\w-]+):\s*([^;]+);", block))


def messages(lang: str) -> set[str]:
    block = re.search(rf"^    {lang}: \{{\n(.*?)^    \}},$", PAGE, re.M | re.S).group(1)
    return set(re.findall(r'"([a-z]\w*\.?[\w.]*)": "', block))


class DashboardTest(unittest.TestCase):
    def test_every_label_exists_in_both_languages(self):
        singular = {k for k in messages("en") if k.endswith("_one")}  # Japanese has no singular form
        self.assertEqual(messages("en") - singular, messages("ja"))

    def test_static_labels_are_defined(self):
        used = set(re.findall(r'data-i18n(?:-title|-aria)?="([^"]+)"', PAGE))
        self.assertLessEqual(used, messages("en"))

    def test_script_ids_exist_in_the_page(self):
        used = set(re.findall(r'\$\("(\w+)"\)', PAGE))
        self.assertLessEqual(used, set(re.findall(r'\bid="(\w+)"', PAGE)))

    @unittest.skipUnless(shutil.which("node"), "needs node")
    def test_families_nest_under_parents_and_survive_loops(self):
        code = re.search(r"  function parentOf\(.*?(?=  // \[key, label, sessions\] of each non-empty group, in)", PAGE, re.S)[0]
        script = """
          const S = (id, parent) => ({ session_id: id, parent_id: parent });
          const db = { sessions: [S("kid", "mom"), S("other"), S("mom"), S("grandkid", "kid"), S("orphan", "gone"),
                                  S("l1", "l2"), S("l2", "l1"), S("tail", "l1")] };
          const shape = (list) => list.map((n) => (n.kids.length ? [n.s.session_id, shape(n.kids)] : n.s.session_id));
          const run = (list) => shape(families(list, sessionsById()));
          console.log(JSON.stringify([run(db.sessions), run(db.sessions.filter((s) => s.session_id !== "kid"))]));
        """
        out = subprocess.run(["node", "-e", code + script], capture_output=True, text=True, check=True).stdout
        tail = ["orphan", ["l1", ["tail"]], "l2"]
        self.assertEqual(json.loads(out), [
            [["mom", [["kid", ["grandkid"]]]], "other", *tail],
            ["other", "mom", "grandkid", *tail]])  # A child whose parent is in another list stands alone

    @unittest.skipUnless(shutil.which("node"), "needs node")
    def test_fold_keys_name_everything_that_hides_a_card(self):
        # The fold state, then the code from the session groups to the family helpers
        code = re.search(r"  const statusOf = .*?(?=  // \[key, label, sessions\] of each non-empty group, in)", PAGE, re.S)[0]
        script = """
          const ui = { byProject: true, collapsed: new Set() };
          const saved = {};
          const localStorage = { setItem: (k, v) => { saved[k] = JSON.parse(v); } };
          const S = (id, parent, more) => ({ session_id: id, parent_id: parent, repo: "app", state: "working", ...more });
          const db = { sessions: [S("mom"), S("kid", "mom"), S("grandkid", "kid"), S("done", "mom", { state: "done" }),
                                  S("under", "done"), S("l1", "l2"), S("l2", "l1"), S("tail", "l1")] };
          const byId = sessionsById();
          const hiders = (id) => foldKeys(byId.get(id), byId).slice(groupKeys(byId.get(id)).length);
          const isFamily = (id) => isCollapsed(familyKey(id));
          const out = [["mom", "kid", "grandkid", "done", "under", "tail"].map((id) => hiders(id).map((k) => JSON.parse(k).family))];
          out.push(isFamily("mom"));
          toggleFold(familyKey("mom"));
          out.push(isFamily("mom"), isFamily("kid"), saved["hub.collapsed"].map((k) => JSON.parse(k)));
          out.push(foldKeys(byId.get("grandkid"), byId).find(isCollapsed) === familyKey("mom"));
          toggleFold(...foldKeys(byId.get("grandkid"), byId).filter(isCollapsed)); // What a link to a session does
          out.push(isFamily("mom"), saved["hub.collapsed"]);
          out.push(families(db.sessions, byId).slice(0, 1).map(descendants)[0].map((s) => s.session_id));
          console.log(JSON.stringify(out));
        """
        out = subprocess.run(["node", "-e", code + script], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), [
            # A parent in another group hides nothing; a session outside the loop sits under its member
            [[], ["mom"], ["mom", "kid"], [], [], ["l1"]],
            False, True, False, [{"family": "mom"}], True, False, [],
            ["kid", "grandkid", "done", "under"]])

    @unittest.skipUnless(shutil.which("node"), "needs node")
    def test_the_toggle_of_a_family_marks_what_it_hides(self):
        code = re.search(r"  function kidsToggle\(.*?\n  \}\n", PAGE, re.S)[0]
        script = """
          const ui = { session: "kid" };
          let open = true;
          const familyKey = (id) => "family " + id, isCollapsed = () => !open, t = (k) => k;
          const calls = [], toggleFold = (k) => calls.push(k), renderSessions = () => calls.push("render"), drawLink = () => calls.push("link");
          const glowKey = { session: (id) => id }, glowProps = (keys, props) => ({ ...props, keys });
          const el = (tag, props, ...kids) => ({ tag, ...props });
          const draw = () => kidsToggle({ session_id: "mom" }, 1, [{ session_id: "kid" }]);
          const shape = (n) => [n.class, n["aria-expanded"], n.keys];
          const out = [shape(draw())];
          open = false;
          out.push(shape(draw()));
          const event = { key: " ", stopPropagation: () => calls.push("stop") };
          draw().onclick(event);
          draw().onkeydown(event);
          draw().onkeydown({ ...event, key: "Escape" });
          console.log(JSON.stringify([...out, calls]));
        """
        out = subprocess.run(["node", "-e", code + script], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), [
            ["kidstoggle", "true", []], ["kidstoggle selected", "false", ["kid"]],
            ["stop", "family mom", "render", "link", "stop"]])  # Neither the click nor the key selects the card

    def test_layout_toggle_offers_list_and_grid(self):
        self.assertEqual(re.findall(r'<button data-layout="(\w+)"', PAGE), ["list", "grid"])
        self.assertIn('localStorage.getItem("hub.layout")', PAGE)

    def test_grid_makes_room_for_the_open_panel(self):
        self.assertIn("main.grid.withpanel { padding-right: calc(var(--detail-w) + var(--space-16)); }", PAGE)
        self.assertRegex(PAGE, r'classList\.toggle\("withpanel", grid && ui\.panelOpen\)')

    def test_panel_resize_handle_is_an_accessible_separator(self):
        handle = re.search(r'<div class="resizer" id="panelResize"[^>]*>', PAGE)[0]
        for attr in ('role="separator"', 'aria-orientation="vertical"', 'aria-controls="detail"', 'tabindex="0"', "data-i18n-aria="):
            self.assertIn(attr, handle)
        for attr in ("aria-valuenow", "aria-valuemin", "aria-valuemax"):
            self.assertIn(f'handle.setAttribute("{attr}"', PAGE)
        # Outside #detail, whose content scrolls
        self.assertLess(PAGE.index(handle), PAGE.index('id="detail"'))

    def test_panel_resize_handle_shows_beside_an_open_grid_panel_alone(self):
        self.assertIn("main > #panelResize { display: none;", PAGE)
        self.assertIn("@media (min-width: 860.02px) { main.grid.withpanel:not(.fullscreen) > #panelResize { display: block; } }", PAGE)

    def test_panel_width_is_remembered_and_recovers_from_a_canceled_drag(self):
        for call in ("getItem", "setItem", "removeItem"):
            self.assertIn(f'localStorage.{call}("hub.panelWidth"', PAGE)
        for event, keep in (("pointerup", "true"), ("pointercancel", "false"), ("lostpointercapture", "false")):
            self.assertIn(f'on("{event}", {keep});', PAGE)
        self.assertIn("--detail-w: min(720px, 55%);", PAGE)  # panelWidth() repeats this default
        self.assertIn("Math.min(720, document.documentElement.clientWidth * 0.55)", PAGE)

    def test_closed_grid_panel_is_inert(self):
        self.assertRegex(PAGE, r'\$\("detail"\)\.inert\s*=\s*grid\s*&&\s*!ui\.panelOpen\b')

    def test_fullscreen_covers_the_window_without_touching_the_panel_width(self):
        rule = re.search(r"main\.grid\.fullscreen #detail \{([^}]*)\}", PAGE)[1]
        self.assertIn("inset: 0; width: auto;", rule)
        z = lambda pattern: int(re.search(pattern + r" \{[^}]*z-index: (\d+)", PAGE, re.M)[1])
        self.assertLess(z(r"^header"), int(re.search(r"z-index: (\d+)", rule)[1]))
        self.assertGreater(z(r"^\.tip"), int(re.search(r"z-index: (\d+)", rule)[1]))
        self.assertNotIn("transition", rule)  # nothing to reduce for prefers-reduced-motion

    def test_fullscreen_ends_with_the_panel_and_hides_what_it_covers(self):
        self.assertIn('on = ui.fullscreen && ui.layout === "grid" && ui.panelOpen;', PAGE)
        self.assertIn('document.querySelector("header").inert = $("sessions").closest("section").inert = on;', PAGE)
        self.assertRegex(PAGE, r'aria-pressed", String\(b\.dataset\.layout === ui\.layout\)\)\);\n    applyFullscreen\(\);\n  \}')
        self.assertLessEqual({"panel.fullscreenOn", "panel.fullscreenOff"}, messages("ja"))

    def test_escape_clears_the_search_then_leaves_fullscreen_then_closes_the_panel(self):
        handler = re.search(r'if \(e\.key !== "Escape" [^\n]*ui\.layout !== "grid".*?\n  \}\);', PAGE, re.S)[0]
        steps = [handler.index(s) for s in ('e.target === $("fText")', "setFullscreen(false)", "closePanel()")]
        self.assertEqual(steps, sorted(steps))
        self.assertIn("return setFullscreen(false);", handler)
        self.assertIn("if (!e.repeat) closePanel();", handler)

    def test_pull_request_link_is_limited_to_web_addresses(self):
        self.assertIn(r'/^https?:\/\//i.test(pr.url || "") ? pr.url : null', PAGE)
        self.assertRegex(PAGE, r'class: "pr", href: prUrl, target: "_blank", rel: "noopener noreferrer"')

    def test_swimlanes_zoom_and_list_the_shown_period(self):
        for button in ("laneIn", "laneOut", "laneFit"):
            self.assertIn(f'$("{button}").addEventListener("click"', PAGE)
        self.assertIn('{ passive: false }', PAGE)  # a passive wheel listener cannot stop the page zoom
        columns = re.search(r'\[([^\]]*)\]\.map\(\(c\) => el\("th", \{ scope: "col" \}', PAGE)[1]
        self.assertLessEqual({"lanes.col." + c for c in re.findall(r'"(\w+)"', columns)}, messages("ja"))
        self.assertLessEqual({"dur.sec", "dur.min", "dur.hour", "dur.day"}, messages("ja"))

    def test_detail_view_opens_the_desktop_app(self):
        self.assertIn('/^local_[A-Za-z0-9-]{1,64}$/.test(s.desktop_id || "")', PAGE)
        self.assertIn('"claude://code/continue?session=" + s.desktop_id', PAGE)
        self.assertIn("open.hidden = !appUrl;", PAGE)
        self.assertIn("@media (max-width: 860px) { #tlTitle { flex-wrap: wrap; } }", PAGE)

    def test_overview_replaces_the_all_sessions_button(self):
        self.assertIn('data-view="overview"', PAGE)
        self.assertRegex(PAGE, r'function renderOverview\(\) \{\n[^\n]*\n\s*tipEl\.style\.display = "none";')
        self.assertNotIn('id="openPanel"', PAGE)
        self.assertNotIn("panel.openAll", PAGE)
        self.assertLessEqual({"tab.overview", "overview.aria", "overview.open", "overview.end"}, messages("ja"))

    def test_feed_rows_name_the_project_and_search_finds_it(self):
        self.assertIn('project ? el("span", { class: "evproject" }, project) : null', PAGE)
        self.assertIn("!sessionProject(e.session_id).toLowerCase().includes(q)", PAGE)

    def test_detail_view_links_the_pull_request(self):
        self.assertRegex(PAGE, r'<a class="pr" id="tlPr" target="_blank" rel="noopener noreferrer" hidden>')
        self.assertIn("link.hidden = !prUrl;", PAGE)
        self.assertIn("const body = eventBody(e);", PAGE)
        self.assertIn('el("div", { class: "text" }, body)', PAGE)
        self.assertIn("p.url || (p.number && p.number === known.number ? known.url : null)", PAGE)
        self.assertIn("if (!prWebUrl(pr)) return text;", PAGE)
        self.assertIn('onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") e.stopPropagation(); }', PAGE)

    def test_selected_session_feed_omits_the_session_title(self):
        row = PAGE[PAGE.index("function eventRow(e)"):PAGE.index("const stripEvent")]
        self.assertRegex(row, r'const who = !ui\.session\s+\? el\("span", \{ class: "who"')
        self.assertIn(': e.writer ? el("span", { class: "writer" }, e.writer) : null;', row)
        self.assertEqual(row.count("sessionName("), 1)

    def test_open_details_survive_an_update(self):
        render = re.search(r"  function renderFeed\(\) \{\n(.*?)\n  \}\n", PAGE, re.S)[1]
        before, rebuild, after = render.partition("rebuildFeed(box);")
        self.assertTrue(rebuild)
        self.assertIn("d.open ? openRows.add(id) : openRows.delete(id);", before)
        self.assertIn("if (!db.events.has(id.slice(3))) openRows.delete(id);", before)
        self.assertIn('if (openRows.has(row.id)) row.querySelector("details").open = true;', after)
        self.assertNotIn("ontoggle", PAGE)  # a toggle event fires late, even for a replaced row

    def test_type_filter_is_a_popover_with_its_own_escape(self):
        self.assertRegex(PAGE, r'id="typesBtn" type="button" aria-expanded="false" aria-controls="fTypes"')
        self.assertRegex(PAGE, r'id="fTypes" popover="manual" role="group" data-i18n-aria="filter.typesAria"')
        self.assertIn('el("input", { type: "checkbox", checked: ui.types.has(type)', PAGE)
        self.assertIn('if (isCol || unfiltered) closeTypes();\n    $("typesBtn").hidden = isCol || unfiltered;', PAGE)
        self.assertIn('if ($("detail").inert) closeTypes();', PAGE)
        escape = re.search(r'!typesOpen\(\)\) return;\n\s+e\.preventDefault\(\);(.*?)\}, true\);', PAGE, re.S)[1]
        for call in ("e.stopPropagation();", "closeTypes();", '$("typesBtn").focus('):
            self.assertIn(call, escape)


class DesignTokenTest(unittest.TestCase):
    def setUp(self):
        style = re.search(r"<style>(.*?)</style>", PAGE, re.S)[1]
        style = re.sub(r"/\*.*?\*/", "", style, flags=re.S)
        token_blocks, marker, rules = style.partition("* { box-sizing")
        self.assertTrue(marker)
        self.rules = marker + rules
        self.light, self.dark_auto, self.dark_chosen = map(tokens, re.findall(r":root[^{]*\{([^{}]*)\}", token_blocks))

    def test_rules_take_their_values_from_tokens(self):
        for prop, value in SIZED.findall(self.rules):
            # A calc() may add layout sizes, such as a column width, to the tokens
            value = re.sub(r"calc\((?=[^;}]*var\(--(?:space|radius)-)(?:[^()]|\([^()]*\))*\)", "", value)
            with self.subTest(prop=prop, value=value):
                self.assertNotRegex(value, r"\d(?:px|rem|em|pt)\b")
                if prop == "font-size":
                    self.assertRegex(value.strip(), r"^var\(--fs-[\w-]+\)$")
        for value in OUTLINE.findall(self.rules):
            with self.subTest(outline=value):
                self.assertRegex(value, r"^(?:0|none)\s*$|var\(--|\btransparent\b")
        for value in PAINT.findall(self.rules):
            with self.subTest(paint=value):
                self.assertRegex(value, r"^(?:" + PAINT_VALUE.pattern + ")")
        self.assertEqual(WEIGHT.findall(self.rules), [])
        self.assertEqual(COLOR.findall(self.rules), [])

    def test_every_used_property_is_defined(self):
        used = set(re.findall(r"var\(--([\w-]+)", self.rules))
        self.assertEqual(used - set(self.light) - SET_BY_SCRIPT, set())

    def test_every_status_group_but_archived_has_a_fill(self):
        groups = set(re.findall(r'\bstatus\("(\w+)"\)', PAGE))
        self.assertLessEqual({"action", "active", "done"}, groups)
        self.assertEqual({f"g-{g}" for g in groups - {"archived"}} - set(self.light), set())

    def test_both_dark_blocks_agree(self):
        self.assertTrue(self.dark_auto)
        self.assertEqual(self.dark_auto, self.dark_chosen)
        self.assertEqual(set(self.dark_auto) - set(self.light), set())


if __name__ == "__main__":
    unittest.main()
