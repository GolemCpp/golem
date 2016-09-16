GOLEM=./golem

dir=$(PWD)
runtime=shared
link=shared
arch=$(shell uname -m)
variant=debug
test=--test
bump=

all:
	$(GOLEM) all --dir=$(dir)

build:
	$(GOLEM) build --dir=$(dir) --runtime=$(runtime) --link=$(link) --arch=$(arch) --variant=$(variant) $(test)

debug:
	$(GOLEM) clean --dir=$(dir)
	$(GOLEM) build --dir=$(dir) --runtime=$(runtime) --link=$(link) --arch=$(arch) --variant=$(variant) $(test)

clean:
	$(GOLEM) clean --dir=$(dir)

release:
	$(GOLEM) release --dir=$(dir) --$(bump)

.DEFAULT:
	$(GOLEM) $(MAKECMDGOALS) --dir=$(dir)
