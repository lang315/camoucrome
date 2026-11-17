package core

import "math/rand/v2"

// pcg wraps math/rand/v2's PCG, whose output sequence is part of its contract.
type pcg struct{ *rand.PCG }

func newPCG(seed, stream uint64) pcg { return pcg{rand.NewPCG(seed, stream)} }
