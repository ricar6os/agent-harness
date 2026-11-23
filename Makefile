# Shortcuts for working with the meta workspace. Every target is a thin wrapper
# around scripts/ or a CLI; keep the logic in the scripts, not here.
#
#   make            show this list
#   make sync       clone/update repos (ONLY=a,b or PRODUCT=slug to restrict)

SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

ONLY ?=
PRODUCT ?=
NAME ?=
REPO ?=

.PHONY: help sync skills status list repo-check doctor check test

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

sync: ## Clone/update repos from repos.json (ONLY=a,b or PRODUCT=slug to restrict)
	@scripts/init.sh $(if $(ONLY),--only $(ONLY)) $(if $(PRODUCT),--product $(PRODUCT))

skills: ## Relink repo skills into .claude/skills/ and .agents/skills/ (sync does it too)
	@scripts/link-skills.sh

status: ## Branch, local changes and ahead/behind for each cloned repo
	@scripts/status.sh

list: ## Print the repos manifest
	@scripts/init.sh --list

repo-check: ## Run the check command repos.json declares for a repo (REPO=name)
	@scripts/repo-check.sh $(REPO)

doctor: ## Check required tools: git, jq, gh (authenticated), python3, openspec
	@ok=1; \
	for t in git jq gh python3 openspec; do \
	  if command -v $$t >/dev/null 2>&1; then printf '  \033[32m✓\033[0m %s\n' "$$t"; \
	  else printf '  \033[31m✗\033[0m %s (missing)\n' "$$t"; ok=0; fi; \
	done; \
	if command -v gh >/dev/null 2>&1; then \
	  if gh auth status >/dev/null 2>&1; then printf '  \033[32m✓\033[0m gh auth\n'; \
	  else printf '  \033[31m✗\033[0m gh auth (run: gh auth login)\n'; ok=0; fi; \
	fi; \
	if command -v openspec >/dev/null 2>&1; then \
	  if python3 scripts/check.py --openspec-ok; then printf '  \033[32m✓\033[0m openspec version\n'; \
	  else printf '  \033[31m✗\033[0m openspec version\n'; ok=0; fi; \
	fi; \
	[[ $$ok -eq 1 ]] || { echo; echo "Install openspec with: npm i -g @fission-ai/openspec@$$(python3 scripts/check.py --openspec-version)"; exit 1; }

check: ## Check the workspace conventions (rules: scripts/check.py --list)
	@python3 scripts/check.py

test: ## Run the tests of the checker and the guardrails
	@python3 -m unittest discover -s tests
