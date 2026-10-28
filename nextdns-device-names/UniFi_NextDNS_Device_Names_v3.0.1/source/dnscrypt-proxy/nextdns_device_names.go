package main

// This optional UniFi integration is enabled only by a fresh local registry.
// EDNS client metadata is accepted only from a loopback forwarder and is removed
// before a NextDNS request is encrypted. Names never live on a shared transport.
import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
	"unicode"
	"unicode/utf8"

	"github.com/miekg/dns"
)

const nextDNSMACOption = 0xfde9 // dnsmasq's binary add-mac option

type nextDNSDevice struct {
	Name string `json:"name"`
	ID   string `json:"id"`
	MAC  string `json:"mac"`
}

type nextDNSRegistryData struct {
	Version  int                            `json:"version"`
	Enabled  bool                           `json:"enabled"`
	Expires  int64                          `json:"expires_unix"`
	ByIP     map[string]nextDNSDevice       `json:"by_ip"`
	ByMAC    map[string]nextDNSDevice       `json:"by_mac"`
	Profiles map[string]nextDNSRegistryData `json:"profiles"`
}

type nextDNSRegistry struct {
	sync.Mutex
	path    string
	checked time.Time
	data    nextDNSRegistryData
}

var nextDNSDevices = &nextDNSRegistry{}
var nextDNSProofLock sync.Mutex

func (r *nextDNSRegistry) file() string {
	if r.path != "" {
		return r.path
	}
	if p := os.Getenv("NEXTDNS_DEVICE_NAMES_FILE"); p != "" {
		return p
	}
	return "/run/nextdns-device-names-v3/devices.json"
}

func (r *nextDNSRegistry) current(now time.Time) nextDNSRegistryData {
	r.Lock()
	defer r.Unlock()
	if now.Sub(r.checked) >= 2*time.Second || r.checked.IsZero() {
		r.checked = now
		r.data = nextDNSRegistryData{}
		if st, err := os.Stat(r.file()); err == nil && st.Size() <= 8*1024*1024 {
			if b, err := os.ReadFile(r.file()); err == nil {
				var data nextDNSRegistryData
				if json.Unmarshal(b, &data) == nil && (data.Version == 1 || data.Version == 2) && data.Enabled {
					r.data = data
				}
			}
		}
	}
	if r.data.Expires <= now.Unix() || r.data.Expires > now.Add(5*time.Minute).Unix() {
		return nextDNSRegistryData{}
	}
	return r.data
}

func nextDNSProfileURL(u *url.URL) string {
	if !isNextDNSURL(u) {
		return ""
	}
	parts := strings.Split(strings.TrimPrefix(u.Path, "/"), "/")
	if len(parts) == 0 || len(parts[0]) != 6 {
		return ""
	}
	profile := strings.ToLower(parts[0])
	for _, c := range profile {
		if !(c >= '0' && c <= '9') && !(c >= 'a' && c <= 'f') {
			return ""
		}
	}
	return profile
}

func isNextDNSURL(u *url.URL) bool {
	if u == nil || u.Scheme != "https" {
		return false
	}
	host := strings.ToLower(u.Hostname())
	return host == "dns.nextdns.io" || strings.HasSuffix(host, ".dns.nextdns.io")
}

func nextDNSLoopback(addr *net.Addr) bool {
	if addr == nil || *addr == nil {
		return false
	}
	switch a := (*addr).(type) {
	case *net.UDPAddr:
		return a.IP.IsLoopback()
	case *net.TCPAddr:
		return a.IP.IsLoopback()
	default:
		return false
	}
}

func validNextDNSName(s string) bool {
	if s == "" || len(s) > 256 || !utf8.ValidString(s) || s != strings.TrimSpace(s) {
		return false
	}
	for _, ch := range s {
		if unicode.IsControl(ch) {
			return false
		}
	}
	return true
}

// collectNextDNSDevice returns whether it changed the DNS message. It strips
// metadata even when the collector has expired, so raw MACs never leak upstream.
func (state *PluginsState) collectNextDNSDevice(msg *dns.Msg) bool {
	if !nextDNSLoopback(state.clientAddr) {
		return false
	}
	var ip, mac string
	var ipCount, macCount int
	invalid, changed := false, false
	for _, rr := range msg.Extra {
		opt, ok := rr.(*dns.OPT)
		if !ok {
			continue
		}
		kept := opt.Option[:0]
		for _, option := range opt.Option {
			switch option.Option() {
			case dns.EDNS0SUBNET:
				ipCount++
				changed = true
				ecs, ok := option.(*dns.EDNS0_SUBNET)
				if !ok || ecs.SourceScope != 0 {
					invalid = true
				} else if ecs.Family == 1 && ecs.SourceNetmask == 32 && ecs.Address.To4() != nil {
					ip = ecs.Address.To4().String()
				} else if ecs.Family == 2 && ecs.SourceNetmask == 128 && ecs.Address.To16() != nil && ecs.Address.To4() == nil {
					ip = ecs.Address.String()
				} else {
					invalid = true
				}
			case nextDNSMACOption:
				macCount++
				changed = true
				local, ok := option.(*dns.EDNS0_LOCAL)
				if !ok || len(local.Data) != 6 {
					invalid = true
				} else {
					mac = net.HardwareAddr(local.Data).String()
				}
			default:
				kept = append(kept, option)
			}
		}
		opt.Option = kept
	}
	if !state.nextDNSTarget || invalid || ipCount > 1 || macCount > 1 || ipCount+macCount == 0 {
		return changed
	}
	data := nextDNSDevices.current(time.Now())
	if data.Version == 2 {
		var ok bool
		data, ok = data.Profiles[state.nextDNSProfile]
		if !ok {
			return changed
		}
	}
	device, found := data.ByIP[ip]
	if macDevice, ok := data.ByMAC[mac]; mac != "" && ok {
		if found && device.MAC != "" && device.MAC != mac {
			return changed // conflicting IP and MAC mappings: omit the label
		}
		device, found = macDevice, true
	} else if found && mac != "" && device.MAC != "" && device.MAC != mac {
		return changed
	}
	if found && validNextDNSName(device.Name) {
		state.nextDNSDevice = device
	}
	return changed
}

func (state *PluginsState) nextDNSHeaders() http.Header {
	if !state.nextDNSTarget || !validNextDNSName(state.nextDNSDevice.Name) {
		return nil
	}
	h := make(http.Header)
	h.Set("X-Device-Name", state.nextDNSDevice.Name)
	if id := state.nextDNSDevice.ID; len(id) > 0 && len(id) <= 32 && strings.IndexFunc(id, func(c rune) bool {
		return !(c >= 'A' && c <= 'Z') && !(c >= '2' && c <= '7')
	}) == -1 {
		h.Set("X-Device-Id", id)
	}
	return h
}

// Only explicit integration probes produce a proof record. Ordinary browsing
// does not write query names or device names to a new diagnostic log.
func (state *PluginsState) recordNextDNSProof() {
	name := strings.TrimSuffix(strings.ToLower(state.qName), ".")
	if !strings.HasPrefix(name, "ndn-check-") || !strings.HasSuffix(name, ".example.com") || len(state.nextDNSHeaders()) == 0 {
		return
	}
	nextDNSProofLock.Lock()
	defer nextDNSProofLock.Unlock()
	digest := sha256.Sum256([]byte(name))
	record := map[string]interface{}{
		"at_unix": time.Now().Unix(), "query_sha256": hex.EncodeToString(digest[:]),
		"device_name": state.nextDNSDevice.Name, "device_id": state.nextDNSDevice.ID,
		"profile": state.nextDNSProfile,
	}
	b, err := json.Marshal(record)
	if err != nil {
		return
	}
	file := filepath.Join(filepath.Dir(nextDNSDevices.file()), "proof.json")
	f, err := os.CreateTemp(filepath.Dir(file), ".proof-*")
	if err != nil {
		return
	}
	tmp := f.Name()
	defer os.Remove(tmp)
	if _, err = f.Write(b); err != nil {
		f.Close()
		return
	}
	if f.Close() == nil {
		os.Rename(tmp, file)
	}
}
