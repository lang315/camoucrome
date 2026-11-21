module camoucrome/cdpfootprint

go 1.27

require (
	github.com/lang315/camoucrome/client/go v0.0.0
	github.com/lang315/camoucrome/client/go/core v0.0.0
	github.com/lang315/camoucrome/client/go/rodclient v0.0.0
	github.com/mafredri/cdp v0.35.0
	tdp v0.0.0
)

require (
	github.com/deckarep/golang-set/v2 v2.8.0 // indirect
	github.com/go-rod/rod v0.116.2 // indirect
	github.com/go-stack/stack v1.8.1 // indirect
	github.com/gorilla/websocket v1.5.3 // indirect
	github.com/mxschmitt/playwright-go v0.6201.1 // indirect
	github.com/ysmood/fetchup v0.2.3 // indirect
	github.com/ysmood/goob v0.4.0 // indirect
	github.com/ysmood/got v0.40.0 // indirect
	github.com/ysmood/gson v0.7.3 // indirect
	github.com/ysmood/leakless v0.9.0 // indirect
)

replace github.com/lang315/camoucrome/client/go/rodclient => ../../client/go/rodclient

replace github.com/lang315/camoucrome/client/go => ../../client/go

replace github.com/lang315/camoucrome/client/go/core => ../../client/go/core

// Placeholder: build.sh points this at $TDP_SRC for a build and restores it.
replace tdp => ../../../tdp

replace github.com/mafredri/cdp => github.com/mafredri/cdp v0.35.1-0.20251207231248-2468c63cb3a7
