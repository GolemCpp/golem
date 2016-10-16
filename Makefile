WAF=./waf

dir=$(PWD)
runtime=shared
link=shared
arch=$(shell uname -m)
variant=debug
test=--test
bump=

.PHONY: about
about:
	@echo "=== Golem C++ Build System ==="

.PHONY: configure
configure: about
	$(WAF) configure --dir=$(dir)

.PHONY: everything
everything: about
	$(WAF) everything --dir=$(dir)

.PHONY: all
all: about
	$(WAF) build --dir=$(dir) --runtime=$(runtime) --link=$(link) --arch=$(arch) --variant=$(variant) $(test)

.PHONY: clean
clean: about
	$(WAF) clean --dir=$(dir)

.PHONY: distclean
distclean: about
	$(WAF) distclean --dir=$(dir)

.PHONY: rebuild
rebuild: about distclean configure build

.PHONY: release
release: about
	$(WAF) release --dir=$(dir) --$(bump)

.DEFAULT: about
	$(WAF) $(MAKECMDGOALS) --dir=$(dir)
