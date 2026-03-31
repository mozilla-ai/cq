cq
Copyright 2026 Mozilla AI

This product includes the following third-party software.
{{ range . }}
================================================================================
{{ .Name }}{{ if .Version }} {{ .Version }}{{ end }}
License: {{ .LicenseName }}
================================================================================

{{ .LicenseText }}
{{ end }}
