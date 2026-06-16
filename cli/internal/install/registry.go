package install

// Selection records which hosts a single invocation targets.
type Selection struct {
	// Windsurf targets the Windsurf editor.
	Windsurf bool
}

// registry maps a host name to its adapter; populated by each adapter's init().
var registry = map[string]Host{}

// SelectHosts returns the host adapters chosen by sel, in a stable order.
func SelectHosts(sel Selection) []Host {
	var hosts []Host
	if sel.Windsurf {
		if h, ok := registry["windsurf"]; ok {
			hosts = append(hosts, h)
		}
	}
	return hosts
}
