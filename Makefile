GOLEM=./golem

dir=$(PWD)
runtime=shared
link=shared
arch=$(shell uname -m)
variant=debug
test=--test

all:
	$(GOLEM) all

build:
	$(GOLEM) build --dir=$(dir) --runtime=$(runtime) --link=$(link) --arch=$(arch) --variant=$(variant) $(test)

debug:
	$(GOLEM) clean
	$(GOLEM) build --dir=$(dir) --runtime=$(runtime) --link=$(link) --arch=$(arch) --variant=$(variant) $(test)

clean:
	$(GOLEM) clean

.DEFAULT:
	$(GOLEM) $(MAKECMDGOALS) --dir=$(shell pwd)
