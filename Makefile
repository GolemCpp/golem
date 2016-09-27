WAF=./waf

dir=$(PWD)
runtime=shared
link=shared
arch=$(shell uname -m)
variant=debug
test=--test
bump=

about:
	@echo "=== Golem C++ Build System ==="

all: about
	$(WAF) all --dir=$(dir)

build: about
	$(WAF) build --dir=$(dir) --runtime=$(runtime) --link=$(link) --arch=$(arch) --variant=$(variant) $(test)

debug: about clean
	$(WAF) build --dir=$(dir) --runtime=$(runtime) --link=$(link) --arch=$(arch) --variant=$(variant) $(test)

clean: about
	$(WAF) clean --dir=$(dir)

release: about
	$(WAF) release --dir=$(dir) --$(bump)

.DEFAULT: about
	$(WAF) $(MAKECMDGOALS) --dir=$(dir)
