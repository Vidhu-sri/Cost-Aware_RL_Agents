PYTHON ?= python
export PYTHONPATH := $(CURDIR)/src
.PHONY: test audit dry-run dpo grpo graph

test:
	$(PYTHON) -m unittest discover -s tests -v

audit:
	$(PYTHON) -m costagent.traces

dry-run: dpo grpo graph

dpo:
	$(PYTHON) scripts/train_dpo.py --dry-run

grpo:
	$(PYTHON) scripts/train_grpo.py --dry-run --smoke

graph:
	$(PYTHON) scripts/train_graph.py --dry-run --smoke
