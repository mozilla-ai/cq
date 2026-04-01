cask "cq" do
  version "{{ .Version }}"
{{- range $p := .Platforms }}

  on_{{ $p.Value }} do
{{- range $a := $.Arches }}
{{- with $.Artifact $p.Key $a.Key }}
    on_{{ $a.Value }} do
      url "{{ .URL }}"
      sha256 "{{ .SHA256 }}"
    end
{{- end }}
{{- end }}
  end
{{- end }}

  name "cq"
  desc "cq is a shared knowledge store that helps agents avoid known pitfalls."
  homepage "https://github.com/mozilla-ai/cq"

  livecheck do
    skip "Auto-generated on release."
  end

  binary "cq"

  postflight do
    if OS.mac?
      system_command "/usr/bin/xattr", args: ["-dr", "com.apple.quarantine", "#{staged_path}/cq"]
    end
  end
end
