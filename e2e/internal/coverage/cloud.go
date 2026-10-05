package coverage

type cloudCleanup struct {
	Version     int    `json:"version"`
	Provider    string `json:"provider"`
	Environment string `json:"environment"`
	RunID       string `json:"run_id"`
	Armed       bool   `json:"armed"`
	Cleaned     bool   `json:"cleaned"`
}
