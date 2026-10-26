package main

import (
	"encoding/json"
	"net/url"
	"os"
	"testing"
	"time"
)

func TestNextDNSV2ProfilesNeverCross(t *testing.T) {
	installTestRegistry(t)
	data := nextDNSRegistryData{Version: 2, Enabled: true, Expires: time.Now().Add(time.Minute).Unix(), Profiles: map[string]nextDNSRegistryData{
		"abcdef": {ByMAC: map[string]nextDNSDevice{"00:11:22:33:44:55": {Name: "Office", ID: "AAAAAAA2"}}},
		"123456": {ByMAC: map[string]nextDNSDevice{"00:11:22:33:44:55": {Name: "Other profile", ID: "BBBBBBB2"}}},
	}}
	b, _ := json.Marshal(data)
	if err := os.WriteFile(nextDNSDevices.file(), b, 0600); err != nil {
		t.Fatal(err)
	}
	nextDNSDevices.checked = time.Time{}
	for profile, wanted := range map[string]string{"abcdef": "Office", "123456": "Other profile", "bad": ""} {
		m, s := metadataMessage(), metadataState("127.0.0.1")
		s.nextDNSProfile = profile
		s.collectNextDNSDevice(m)
		if got := s.nextDNSHeaders().Get("X-Device-Name"); got != wanted {
			t.Fatalf("profile %s got %s", profile, got)
		}
	}
}

func TestNextDNSV2ProfileURL(t *testing.T) {
	for raw, wanted := range map[string]string{
		"https://dns.nextdns.io/ABCDEF":        "abcdef",
		"https://dns.nextdns.io/abcdef/device": "abcdef",
		"https://dns.nextdns.io/abcdefg":       "",
		"https://example.com/abcdef":           "",
		"https://dns.nextdns.io/xyzxyz":        "",
	} {
		u, _ := url.Parse(raw)
		if nextDNSProfileURL(u) != wanted {
			t.Fatal(raw)
		}
	}
}
