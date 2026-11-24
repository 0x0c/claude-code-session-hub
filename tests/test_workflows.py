"""The triggers of the Claude review workflow."""

import re
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "claude-review.yml"


class ClaudeReviewTest(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_a_review_starts_when_a_pull_request_leaves_draft_and_not_on_a_push(self):
        types = re.search(r"^  pull_request:\n    types: \[(.*)\]$", self.text, re.M).group(1)
        self.assertEqual({t.strip() for t in types.split(",")}, {"opened", "reopened", "ready_for_review"})

    def test_a_pull_request_run_is_never_skipped(self):
        condition = re.search(r"(?m)^    if: >-\n(.*)$", self.text).group(1)
        self.assertEqual(condition.strip(), "github.event_name == 'pull_request' ||")

    def test_the_first_step_fails_a_draft_or_a_bot_event(self):
        step = self.text.split("    steps:\n", 1)[1].split("\n\n", 1)[0]
        self.assertIn("if: github.event_name == 'pull_request' && "
                      "(github.event.pull_request.draft || github.event.sender.type == 'Bot')", step)
        self.assertRegex(step, r"(?m)^          exit 1$")

    def test_only_a_pull_request_run_reports_under_the_required_name(self):
        self.assertIn("    name: ${{ github.event_name == 'pull_request' && 'claude review' || "
                      "'claude review (requested)' }}\n", self.text)


if __name__ == "__main__":
    unittest.main()
