module camoucrome/cdpfootprint

go 1.27

require (
	github.com/mafredri/cdp v0.35.0
	tdp v0.0.0
)

require github.com/gorilla/websocket v1.5.3 // indirect

// Placeholder: build.sh points this at $TDP_SRC for a build and restores it.
replace tdp => ../../../tdp

replace github.com/mafredri/cdp => github.com/mafredri/cdp v0.35.1-0.20251207231248-2468c63cb3a7
