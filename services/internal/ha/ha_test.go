package ha

import "testing"

func TestCommandsAreValidated(t *testing.T) {
	b := &Bridge{Node: "pynab_test"}
	for topic, payload := range map[string]string{
		"pynab/pynab_test/sleep/set":     "ON",
		"pynab/pynab_test/volume/set":    "55",
		"pynab/pynab_test/left_ear/set":  "16",
		"pynab/pynab_test/weather/press": "PRESS",
	} {
		if _, ok := b.ParseCommand(topic, []byte(payload)); !ok {
			t.Fatalf("%s %s refused", topic, payload)
		}
	}
	for topic, payload := range map[string]string{
		"pynab/pynab_test/sleep/set":     "maybe",
		"pynab/pynab_test/volume/set":    "250",
		"pynab/pynab_test/right_ear/set": "-1",
		"pynab/other/volume/set":         "10",
		"pynab/pynab_test/reboot/press":  "",
	} {
		if _, ok := b.ParseCommand(topic, []byte(payload)); ok {
			t.Fatalf("%s %s accepted", topic, payload)
		}
	}
	if len(b.Discovery("homeassistant")) != 9 {
		t.Fatal("discovery entities")
	}
}
