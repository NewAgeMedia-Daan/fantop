.PHONY: test check

test:
	python3 -m unittest discover -s tests -v

check: test
	python3 -m py_compile fan_control.py
	bash -n fan-control install.sh uninstall.sh
	git diff --check
