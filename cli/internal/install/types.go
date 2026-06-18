package install

// Action is the kind of change a primitive applied, or would apply in dry-run.
type Action string

const (
	// ActionCreated reports that a new file or config entry was written.
	ActionCreated Action = "created"

	// ActionRemoved reports that a file or config entry was deleted.
	ActionRemoved Action = "removed"

	// ActionSkipped reports that a user-modified target was left in place.
	ActionSkipped Action = "skipped"

	// ActionUnchanged reports that the target already matched; nothing was written.
	ActionUnchanged Action = "unchanged"

	// ActionUpdated reports that an existing file or config entry was changed.
	ActionUpdated Action = "updated"
)

// Change is the outcome of a single primitive call.
type Change struct {
	// Action is the kind of change applied, or planned in dry-run.
	Action Action

	// Path is the file or directory the change targeted.
	Path string

	// Detail optionally explains the outcome, e.g. why a target was skipped.
	Detail string
}

// CLIVerb describes one cq CLI verb for hosts that embed CLI invocation
// instructions instead of MCP config.
type CLIVerb struct {
	// Name is the verb (e.g. "query", "propose").
	Name string

	// UseLine is the cobra Use string (e.g. "query", "confirm <unit_id>").
	UseLine string

	// FlagUsages is the rendered flag table from cobra (may be empty for
	// commands with no flags, like confirm).
	FlagUsages string
}

// Context carries the resolved per-host paths for one install or uninstall.
type Context struct {
	// Target is the host's configuration directory.
	Target string

	// SkillsDir is the shared skills commons the skill is written into.
	SkillsDir string

	// BinaryPath is the absolute cq binary path written into host config.
	BinaryPath string

	// DryRun reports the planned changes without writing.
	DryRun bool

	// CLIVerbs lists the cq CLI verbs and their argument templates.
	//
	// Populated by the install command from the cobra command definitions;
	// consumed by hosts that embed CLI instructions (e.g. Pi) instead of MCP
	// config.
	// Nil for MCP-capable hosts.
	CLIVerbs []CLIVerb
}

// Host installs and removes cq for one agent host.
//
// NOTE: implementations must be idempotent and must leave user-modified
// files in place rather than clobbering them.
// NOTE: the five methods are intentionally combined because every host adapter
// must satisfy all of them; splitting into smaller interfaces would force every
// call site to compose them back together with no benefit.
type Host interface {
	// GlobalTarget returns the host's global config dir for the given home.
	GlobalTarget(home string) string

	// Install writes cq into the host and reports per-step changes.
	Install(ctx Context) ([]Change, error)

	// Name is the host's stable identifier.
	Name() Target

	// SupportsProject reports whether the host can be installed per-project.
	SupportsProject() bool

	// Uninstall removes cq from the host and reports per-step changes.
	Uninstall(ctx Context) ([]Change, error)
}
