GO ?= go

.PHONY: build check

build:
	mkdir -p bin
	CGO_ENABLED=0 $(GO) build -trimpath -o bin/mc-admin-e2e ./cmd/mc-admin-e2e

check:
	$(GO) vet ./...
	$(GO) test -race -count=1 ./...
