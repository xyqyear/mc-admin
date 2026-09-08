GO ?= go
GOFMT ?= gofmt

.PHONY: build check lint test

build:
	mkdir -p bin
	CGO_ENABLED=0 $(GO) build -trimpath -o bin/mc-admin-e2e ./cmd/mc-admin-e2e

lint:
	@unformatted="$$($(GOFMT) -l cmd internal suites)" || exit $$?; \
	if [ -n "$$unformatted" ]; then \
		printf '%s\n' "$$unformatted"; \
		exit 1; \
	fi
	$(GO) vet ./...

test:
	$(GO) test -race -vet=off -count=1 ./...

check: lint test
