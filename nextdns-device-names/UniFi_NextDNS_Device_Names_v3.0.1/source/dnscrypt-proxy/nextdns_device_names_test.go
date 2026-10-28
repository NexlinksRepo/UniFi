package main

import (
	"crypto/tls"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/miekg/dns"
)

func installTestRegistry(t *testing.T) {
	t.Helper()
	previous := nextDNSDevices
	file := filepath.Join(t.TempDir(), "devices.json")
	data := nextDNSRegistryData{Version: 1, Enabled: true, Expires: time.Now().Add(time.Minute).Unix(),
		ByIP:  map[string]nextDNSDevice{"192.168.1.20": {Name: "DHCP laptop", ID: "ABCDEFG2", MAC: "00:11:22:33:44:55"}},
		ByMAC: map[string]nextDNSDevice{"00:11:22:33:44:55": {Name: "Office laptop", ID: "ABCDEFG2", MAC: "00:11:22:33:44:55"}}}
	b, _ := json.Marshal(data)
	if err := os.WriteFile(file, b, 0600); err != nil {
		t.Fatal(err)
	}
	nextDNSDevices = &nextDNSRegistry{path: file}
	t.Cleanup(func() { nextDNSDevices = previous })
}

func metadataMessage() *dns.Msg {
	m := &dns.Msg{}
	m.SetQuestion("example.com.", dns.TypeA)
	m.SetEdns0(1232, true)
	m.IsEdns0().Option = []dns.EDNS0{
		&dns.EDNS0_SUBNET{Code: dns.EDNS0SUBNET, Family: 1, SourceNetmask: 32, Address: net.ParseIP("192.168.1.20")},
		&dns.EDNS0_LOCAL{Code: nextDNSMACOption, Data: []byte{0, 0x11, 0x22, 0x33, 0x44, 0x55}},
		&dns.EDNS0_PADDING{Padding: []byte{0, 0, 0}},
	}
	return m
}

func metadataState(ip string) PluginsState {
	var addr net.Addr = &net.UDPAddr{IP: net.ParseIP(ip), Port: 23456}
	return PluginsState{nextDNSTarget: true, clientAddr: &addr}
}

func TestNextDNSExtractAndStrip(t *testing.T) {
	installTestRegistry(t)
	m, s := metadataMessage(), metadataState("127.0.0.1")
	if !s.collectNextDNSDevice(m) {
		t.Fatal("metadata was not stripped")
	}
	if got := s.nextDNSHeaders().Get("X-Device-Name"); got != "Office laptop" {
		t.Fatalf("name = %q", got)
	}
	if got := s.nextDNSHeaders().Get("X-Device-Id"); got != "ABCDEFG2" {
		t.Fatalf("id = %q", got)
	}
	if !m.IsEdns0().Do() || len(m.IsEdns0().Option) != 1 || m.IsEdns0().Option[0].Option() != dns.EDNS0PADDING {
		t.Fatal("stripping damaged DNSSEC/padding or retained client metadata")
	}
	if _, err := m.Pack(); err != nil {
		t.Fatal(err)
	}
}

func TestNextDNSTrustAndMalformedMetadata(t *testing.T) {
	installTestRegistry(t)
	cases := []struct {
		name     string
		change   func(*dns.Msg, *PluginsState)
		stripped bool
	}{
		{"untrusted peer", func(m *dns.Msg, s *PluginsState) { *s = metadataState("192.168.1.100") }, false},
		{"other provider", func(m *dns.Msg, s *PluginsState) { s.nextDNSTarget = false }, true},
		{"nil peer", func(m *dns.Msg, s *PluginsState) { s.clientAddr = nil }, false},
		{"duplicate ecs", func(m *dns.Msg, s *PluginsState) {
			m.IsEdns0().Option = append(m.IsEdns0().Option, m.IsEdns0().Option[0])
		}, true},
		{"duplicate mac", func(m *dns.Msg, s *PluginsState) {
			m.IsEdns0().Option = append(m.IsEdns0().Option, m.IsEdns0().Option[1])
		}, true},
		{"subnet not host", func(m *dns.Msg, s *PluginsState) { m.IsEdns0().Option[0].(*dns.EDNS0_SUBNET).SourceNetmask = 24 }, true},
		{"bad mac", func(m *dns.Msg, s *PluginsState) { m.IsEdns0().Option[1].(*dns.EDNS0_LOCAL).Data = []byte{1} }, true},
		{"ip mac mismatch", func(m *dns.Msg, s *PluginsState) { m.IsEdns0().Option[1].(*dns.EDNS0_LOCAL).Data[5] = 0x56 }, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			m, s := metadataMessage(), metadataState("127.0.0.1")
			tc.change(m, &s)
			if got := s.collectNextDNSDevice(m); got != tc.stripped {
				t.Fatalf("stripped=%v", got)
			}
			if len(s.nextDNSHeaders()) != 0 {
				t.Fatal("unexpected device identity")
			}
		})
	}
}

func TestNextDNSExpiredOrInvalidRegistry(t *testing.T) {
	installTestRegistry(t)
	for _, body := range []string{
		`{}`, `{broken`,
		`{"version":1,"enabled":true,"expires_unix":1,"by_mac":{"00:11:22:33:44:55":{"name":"Old"}}}`,
		fmt.Sprintf(`{"version":1,"enabled":false,"expires_unix":%d}`, time.Now().Add(time.Minute).Unix()),
	} {
		os.WriteFile(nextDNSDevices.file(), []byte(body), 0600)
		nextDNSDevices.checked = time.Time{}
		m, s := metadataMessage(), metadataState("127.0.0.1")
		if !s.collectNextDNSDevice(m) || len(s.nextDNSHeaders()) != 0 {
			t.Fatal("registry did not fail closed")
		}
	}
}

func TestNextDNSIPv6AndTCPClientMetadata(t *testing.T) {
	installTestRegistry(t)
	m := metadataMessage()
	m.IsEdns0().Option[0] = &dns.EDNS0_SUBNET{Code: dns.EDNS0SUBNET, Family: 2, SourceNetmask: 128, Address: net.ParseIP("fd00::20")}
	var peer net.Addr = &net.TCPAddr{IP: net.ParseIP("::1"), Port: 1234}
	s := PluginsState{nextDNSTarget: true, clientAddr: &peer}
	if !s.collectNextDNSDevice(m) || s.nextDNSHeaders().Get("X-Device-Name") != "Office laptop" {
		t.Fatal("IPv6 metadata or TCP loopback client was not identified")
	}
}

func TestNextDNSIPOnlyFallback(t *testing.T) {
	installTestRegistry(t)
	m, s := metadataMessage(), metadataState("127.0.0.1")
	m.IsEdns0().Option = m.IsEdns0().Option[:1]
	if !s.collectNextDNSDevice(m) || s.nextDNSHeaders().Get("X-Device-Name") != "DHCP laptop" {
		t.Fatal("IP-only lookup failed")
	}
}

func TestNextDNSProviderAndHeaderValidation(t *testing.T) {
	for raw, expected := range map[string]bool{
		"https://dns.nextdns.io/abcdef": true, "https://doh1.dns.nextdns.io/abcdef": true,
		"http://dns.nextdns.io/abcdef": false, "https://dns.nextdns.io.evil.example/": false,
		"https://evilnextdns.io/": false, "https://example.com/dns.nextdns.io": false,
	} {
		u, _ := url.Parse(raw)
		if isNextDNSURL(u) != expected {
			t.Fatal(raw)
		}
	}
	for _, name := range []string{"", "bad\r\nX-Evil: yes", "bad\x00", strings.Repeat("a", 257), " padded "} {
		s := PluginsState{nextDNSTarget: true, nextDNSDevice: nextDNSDevice{Name: name}}
		if len(s.nextDNSHeaders()) != 0 {
			t.Fatalf("unsafe header: %q", name)
		}
	}
	if !validNextDNSName("Phil's iPhone") || !validNextDNSName("Büro laptop") {
		t.Fatal("valid names rejected")
	}
}

func TestNextDNSNoPluginFastPathStillStrips(t *testing.T) {
	installTestRegistry(t)
	m := metadataMessage()
	packet, _ := m.Pack()
	s := metadataState("::1")
	s.maxPayloadSize = 1232
	queries, logs := []Plugin{}, []Plugin{}
	g := PluginsGlobals{queryPlugins: &queries, loggingPlugins: &logs}
	out, err := s.ApplyQueryPlugins(&g, packet, false)
	if err != nil {
		t.Fatal(err)
	}
	var unpacked dns.Msg
	if err := unpacked.Unpack(out); err != nil {
		t.Fatal(err)
	}
	if len(unpacked.IsEdns0().Option) != 1 || s.nextDNSHeaders().Get("X-Device-Name") != "Office laptop" {
		t.Fatal("fast path lost metadata changes")
	}
}

func TestNextDNSConcurrentHTTPHeaders(t *testing.T) {
	var mu sync.Mutex
	seen := make(map[string]int)
	server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		name := r.Header.Get("X-Device-Name")
		var body []byte
		if r.Method == "GET" {
			body, _ = base64.RawURLEncoding.DecodeString(r.URL.Query().Get("dns"))
		} else {
			body, _ = io.ReadAll(r.Body)
		}
		var msg dns.Msg
		if err := msg.Unpack(body); err != nil {
			t.Error(err)
			w.WriteHeader(400)
			return
		}
		expected := strings.TrimSuffix(msg.Question[0].Name, ".example.com.")
		if name != expected {
			t.Errorf("header %q, query identity %q", name, expected)
		}
		mu.Lock()
		seen[name]++
		mu.Unlock()
		msg.Response = true
		response, _ := msg.Pack()
		w.Header().Set("Content-Type", "application/dns-message")
		w.Write(response)
	}))
	server.EnableHTTP2 = true
	server.StartTLS()
	defer server.Close()
	x := NewXTransport()
	x.transport = server.Client().Transport.(*http.Transport).Clone()
	x.transport.TLSClientConfig = &tls.Config{InsecureSkipVerify: true} // isolated test server only
	x.transport.DialContext = (&net.Dialer{}).DialContext
	u, _ := url.Parse(server.URL)
	defer x.transport.CloseIdleConnections()
	var wg sync.WaitGroup
	for i := 0; i < 60; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			name := fmt.Sprintf("device-%d", i)
			msg := &dns.Msg{}
			msg.SetQuestion(name+".example.com.", dns.TypeA)
			body, _ := msg.Pack()
			s := PluginsState{nextDNSTarget: true, nextDNSDevice: nextDNSDevice{Name: name, ID: "ABCDEFG2"}}
			_, _, _, _, err := x.DoHQuery(i%2 == 0, u, body, 5*time.Second, s.nextDNSHeaders())
			if err != nil {
				t.Error(err)
			}
		}(i)
	}
	wg.Wait()
	if len(seen) != 60 {
		t.Fatalf("received %d identities", len(seen))
	}
}

func TestNextDNSRedirectDoesNotLeakHeaders(t *testing.T) {
	arrived := false
	target := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { arrived = true }))
	defer target.Close()
	origin := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { http.Redirect(w, r, target.URL, 302) }))
	defer origin.Close()
	x := NewXTransport()
	x.transport = origin.Client().Transport.(*http.Transport).Clone()
	x.transport.TLSClientConfig = &tls.Config{InsecureSkipVerify: true} // isolated test server only
	u, _ := url.Parse(origin.URL)
	_, _, _, _, err := x.DoHQuery(true, u, []byte{0, 1}, time.Second, http.Header{"X-Device-Name": {"Private device"}})
	if err == nil || arrived {
		t.Fatal("device headers followed a cross-origin redirect")
	}
}
