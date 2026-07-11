.PHONY: test check

test:
	python3 -m unittest discover -s tests -v

check: test
	python3 -m py_compile fantop.py
	bash -n fantop install.sh uninstall.sh
	git diff --check
