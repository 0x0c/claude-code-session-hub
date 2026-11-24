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

    def test_an_automatic_review_skips_drafts_and_bots(self):
        condition = re.search(r"\(github\.event_name == 'pull_request' && (.*)\) \|\|", self.text).group(1)
        self.assertEqual(set(condition.split(" && ")),
                         {"!github.event.pull_request.draft", "github.event.sender.type != 'Bot'"})

    def test_the_job_keeps_the_name_that_the_ruleset_requires(self):
        self.assertRegex(self.text, r"(?m)^    name: claude review$")


if __name__ == "__main__":
    unittest.main()
