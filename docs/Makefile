# Minimal Sphinx Makefile for local docs builds.

SPHINXBUILD ?= sphinx-build
SOURCEDIR = .
BUILDDIR = build

.PHONY: help html clean

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)"

html:
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)"
	@echo
	@echo "HTML docs generated at $(BUILDDIR)/html/index.html"

clean:
	@rm -rf "$(BUILDDIR)"
