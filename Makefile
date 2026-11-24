# Shortcuts for developing this repository; each target runs one script.
.DEFAULT_GOAL := help
.PHONY: help setup check check-secrets

help: ## List the targets
	@awk -F ':.*## ' '/^[a-z-]+:.*## / { printf "  %-14s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

setup: ## Prepare the clone: everything needed before you start work
	@scripts/setup.sh

check: setup ## Run the gate
	@scripts/check.sh

check-secrets: setup ## Scan the history for secrets
	@scripts/check_secrets.sh
