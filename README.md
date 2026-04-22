# Eufy E15 / E18 — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration for the **Eufy E15** and **E18** robotic lawn mowers.

The init version is a copy of https://github.com/jnicolaes/eufy-robomow-ha

Development repository. No final integartion.

---

Some code for the HA Dashboard 

Mardown for the schedule plan:
```
type: markdown
content: >
  ### 📅 Mäh-Wochenplan

  {% set tage_namen = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'] %}

  {% set heute = now().strftime('%a') %}

  {# Wir greifen auf dein Attribut 'plan' zu #}

  {% set plans = state_attr('sensor.eufy_robomow_e15_mah_zeitplan', 'plan') %}


  {% for tag in tage_namen %}

  **{{ '👉 ' if tag == heute }}{{ tag }}{{ ' (HEUTE)' if tag == heute }}**


  {% set hat_plan = namespace(found=false) %}

  {% if plans is iterable %}
    {% for p in plans %}
      {# Da 'day' bei dir eine echte Liste ist, prüfen wir direkt mit 'in' #}
      {% if tag in p.day %}
        {% set hat_plan.found = true %}
        {% set ist_aktiv = p.active == 'Ja' %}
  > {{ '🟢' if ist_aktiv else '⚪' }} **{{ 'AKTIV' if ist_aktiv else 'PAUSE'
  }}**: {{ p.time }} ({{ p.zone }})
      {% endif %}
    {% endfor %}
  {% endif %}


  {% if not hat_plan.found %}

  *Kein Mähvorgang geplant*

  {% endif %}

  ---

  {% endfor %}
```


## Prerequisites

- **Local network access** — the mower and Home Assistant must be on the same LAN (or the mower reachable via IP).
- **Eufy account** — required for cloud-managed settings. The same email/password you use in the Eufy Home app.
- HA **2024.1** or newer.

---

## Installation

### Via HACS

1. Open HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add URL: `https://github.com/xtinos84x/eufy_e15_e18` — category: **Integration**
3. Search for **Eufy e15 e18** and install
4. Restart Home Assistant

---

## Configuration

Go to **Settings → Devices & Services → Add Integration → Eufy Robomow**.

**Step 1 — Sign in:**
Enter your Eufy account email and password. The integration will automatically discover all your devices and fetch their local keys.

**Step 2 — Select mower:**
Pick your mower from the dropdown and enter its local IP address (find it in your router's DHCP table or the Eufy app's device info screen).

That's it — no external tools, no manual key extraction.

---

## How it works

- **Local polling** (every 30 s) via the [Tuya local protocol](https://github.com/jasonacox/tinytuya) for real-time status (battery, activity state, etc.).
- **Cloud polling** (every 5 min) via the Tuya mobile API for settings stored as protobuf blobs in DP154/DP155.
- **Writes** go directly to the cloud API and are immediately reflected in the Eufy app.

---

## Known limitations

- **Zone mowing** — the E15/E18 supports zone-specific settings in the app; this is not yet implemented.
- **Map display** — live GPS map is not yet supported.
- **Pad direction unit** — the app shows a rotary dial; the integration exposes it as 0–359°. Verify the degree → direction mapping matches your app if the direction appears off.

---

## Troubleshooting

- **Entities unavailable** — check that the IP address is correct and the mower is on WiFi (not cellular only).
- **Cloud settings not updating** — cloud data refreshes every 5 minutes; changes made in the Eufy app will appear after the next refresh cycle.

---

## Credits

Authentication and local-key discovery based on [eufy-clean-local-key-grabber](https://github.com/albaintor/eufy-clean-local-key-grabber).
Local protocol via [tinytuya](https://github.com/jasonacox/tinytuya).
