package models

import "testing"

func TestNormalizePartyIDs(t *testing.T) {
	r := &CreateJobRequest{
		Config: DagConfig{
			Version:   "2.0",
			Initiator: InitiatorConfig{Role: "guest", NodeID: "alice", PartyID: "10000"},
			Role:      RoleConfig{Guest: []string{"alice"}, Host: []string{"bob"}},
		},
	}
	r.NormalizePartyIDs()
	if got, want := r.Config.Initiator.NodeID, "JG0100001100000010"; got != want {
		t.Fatalf("initiator node id = %q, want %q", got, want)
	}
	if got, want := r.Config.Initiator.PartyID, "JG0100001100000010"; got != want {
		t.Fatalf("initiator party id = %q, want %q", got, want)
	}
	if got, want := r.Config.Role.Host[0], "JG0100001100000000"; got != want {
		t.Fatalf("host party id = %q, want %q", got, want)
	}
}
