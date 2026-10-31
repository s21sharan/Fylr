.PHONY: test eval-organize eval-search

test:
	python -m pytest

eval-organize:
	python eval/run_organize_eval.py

eval-search:
	python eval/run_search_eval.py
