package cmd

import (
	"bytes"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestApproveRequiresRemote(t *testing.T) {
	testSetup(t)

	approve := NewApproveCmd()
	var approveBuf bytes.Buffer
	approve.SetOut(&approveBuf)
	approve.SetErr(&approveBuf)
	approve.SetArgs([]string{"test-id"})

	err := approve.Execute()
	require.Error(t, err)
	require.Contains(t, err.Error(), "no remote API configured")
}
