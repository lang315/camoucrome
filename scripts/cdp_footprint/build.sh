#!/usr/bin/env bash
# Build tdpdrive, reddrive and roddrive. TDP_SRC: a checkout of the private tdp at 6e87aca.
set -euo pipefail
cd "$(dirname "$0")"
: "${TDP_SRC:?set TDP_SRC to a tdp checkout at 6e87aca}"
head=$(git -C "$TDP_SRC" rev-parse --short HEAD)
[[ $head == 6e87aca* ]] || { echo "tdp is at $head, not 6e87aca" >&2; exit 2; }
cp go.mod go.mod.placeholder
trap 'mv go.mod.placeholder go.mod' EXIT
go mod edit -replace "tdp=$(cd "$TDP_SRC" && pwd)"
mkdir -p out/darwin
for d in tdpdrive reddrive roddrive; do
  CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -o "out/$d.exe" "./$d"
  CGO_ENABLED=0 go build -o "out/darwin/$d" "./$d"
done
ls -l out out/darwin
