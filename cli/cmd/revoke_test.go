package cmd

import (
	"bytes"
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/require"
)

// proposeLocalUnit proposes a unit through the CLI and returns its ID.
func proposeLocalUnit(t *testing.T, summary string) string {
	t.Helper()

	propose := NewProposeCmd()
	var out bytes.Buffer
	propose.SetOut(&out)
	propose.SetArgs([]string{
		"--summary", summary,
		"--detail", "d",
		"--action", "a",
		"--domain", "test",
		"--format", "json",
	})
	require.NoError(t, propose.Execute())

	var ku map[string]any
	require.NoError(t, json.Unmarshal(out.Bytes(), &ku))
	id, ok := ku["id"].(string)
	require.True(t, ok, "propose output should carry an id")

	return id
}

func TestRevokeLocalUnitReportsRemoval(t *testing.T) {
	testSetup(t)

	unitID := proposeLocalUnit(t, "revocable")

	revoke := NewRevokeCmd()
	var out bytes.Buffer
	revoke.SetOut(&out)
	revoke.SetArgs([]string{unitID})
	require.NoError(t, revoke.Execute())

	// A local unit is deleted rather than marked, so the output must say so.
	require.Contains(t, out.String(), unitID)
	require.Contains(t, out.String(), "removed")
}

func TestRevokeLocalUnitIsGoneAfterwards(t *testing.T) {
	testSetup(t)

	unitID := proposeLocalUnit(t, "gone after revoke")

	revoke := NewRevokeCmd()
	revoke.SetOut(&bytes.Buffer{})
	revoke.SetArgs([]string{unitID})
	require.NoError(t, revoke.Execute())

	again := NewRevokeCmd()
	again.SetOut(&bytes.Buffer{})
	again.SetArgs([]string{unitID})
	require.Error(t, again.Execute(), "revoking a unit twice should fail the second time")
}

func TestRevokeRequiresExactlyOneArg(t *testing.T) {
	testSetup(t)

	for _, args := range [][]string{{}, {"ku_00000000000000000000000000000001", "extra"}} {
		cmd := NewRevokeCmd()
		cmd.SetOut(&bytes.Buffer{})
		cmd.SetErr(&bytes.Buffer{})
		cmd.SetArgs(args)
		require.Error(t, cmd.Execute(), "args %v should be rejected", args)
	}
}

func TestRevokeRejectsMalformedUnitID(t *testing.T) {
	testSetup(t)

	cmd := NewRevokeCmd()
	cmd.SetOut(&bytes.Buffer{})
	cmd.SetArgs([]string{"not-a-ku-id"})
	require.Error(t, cmd.Execute())
}

func TestCLIVerbsIncludesRevokeAfterFlag(t *testing.T) {
	t.Parallel()

	names := make([]string, 0, len(cliVerbs()))
	for _, v := range cliVerbs() {
		names = append(names, v.Name)
	}

	// cliVerbs follows the cq workflow order, not alphabetical order.
	require.Equal(t, []string{"query", "propose", "confirm", "flag", "revoke", "status"}, names)
}
