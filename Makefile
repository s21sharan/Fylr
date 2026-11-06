.PHONY: test eval-organize eval-search

test:
	python -m pytest

eval-search:
	python3 eval/run_search_eval.py

eval-organize:
	python3 eval/run_organize_eval.py
