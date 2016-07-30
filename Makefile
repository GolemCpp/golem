WAF=./scripts/waf

all: debug

configure:
	$(WAF) configure

debug:
	$(WAF)

release:
	$(WAF) --variant=release

clean:
	$(WAF) clean

distclean:
	$(WAF) distclean

install:
	$(WAF) install
