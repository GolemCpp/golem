GOLEM=./golem

all:
	$(GOLEM) all

debug:
	$(GOLEM) clean
	$(GOLEM) build --link=shared --arch=x64 --variant=debug --test

clean:
	$(GOLEM) clean