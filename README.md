<p align="center">
  <img src="logo.svg" alt="CAN Do Logo" width="180">
</p>

<h1 align="center">CAN Do for Home Assistant</h1>

<p align="center">
  <b>The bidirectional vehicle automation and telematics platform for Home Assistant.</b><br>
  Powered by the <a href="https://github.com/SuperSuave/can-do-message-catalog">CAN Do Message Catalog</a> and CAN Do firmware.
</p>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge" alt="HACS Custom"></a>
  <a href="https://github.com/SuperSuave/ha-can-do/releases"><img src="https://img.shields.io/github/v/release/SuperSuave/ha-can-do?style=for-the-badge&color=0284c7" alt="Release"></a>
  <a href="https://github.com/SuperSuave/ha-can-do/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License"></a>
</p>

---

## Overview

**CAN Do for Home Assistant** transforms your WiCAN and ESP32 CAN adapters from passive OBD loggers into a **full-featured, bidirectional vehicle control plane**. 

Control climate preconditioning, heated seats, door locks, charge limits, and power tailgates directly from your Home Assistant dashboards, voice assistants, and automations—both at home on local Wi-Fi and remotely anywhere in the world.

---

## Key Features

* 🚗 **Bidirectional Vehicle Controls:** Over 58 vehicle actions supported out of the box via the [CAN Do Message Catalog](https://github.com/SuperSuave/can-do-message-catalog).
* 🌡️ **Cabin Preconditioning:** One-tap remote preconditioning with target temperature configuration and automatic vehicle keep-alive states.
* ⚡ **Dual-Transport Architecture:**
  * **Direct Local / HTTPS:** Sub-second command dispatch over local HTTP or secure HTTPS tunnel when reachable.
  * **Zero-NAT Remote MQTT Fallback:** When your vehicle is away from home behind cellular or hotspot NAT, commands automatically route through Home Assistant's MQTT broker (`can_do/<device_id>/cmd`).
* 📊 **Live Telematics & State Tracking:** Real-time CAN bus telemetry, high-voltage battery SOC, 12V auxiliary battery health, door/window states, and odometer tracking delivered via secure HTTPS webhooks.
* 🧩 **Rich Multi-Domain Entity Generation:**
  * `climate`: Cabin HVAC, preconditioning controls, and target temperatures.
  * `select`: Multi-level driver & passenger heated/cooled seat comfort, DC charge limits, and drive modes.
  * `button`: Horn, hazard flashes, preconditioning toggles, and trunk release.
  * `switch`: Defrosters, steering wheel heaters, and utility modes.
  * `lock`: Door lock and unlock controls.
  * `cover`: Windows, sunshades, and motorized charge port doors.
  * `sensor` & `binary_sensor`: Battery voltage, speed, tire pressure, and condition triggers.
  * `event`: Steering wheel buttons and vehicle CAN Do automation triggers.

---

## Prerequisites

1. **Hardware & Firmware:** WiCAN OBD adapter or supported ESP32 CAN device running **CAN Do firmware** ([wicant-i-automate](https://github.com/SuperSuave/wicant-i-automate)).
2. **Home Assistant:** Version `2024.1.0` or newer.
3. **(Optional for Remote Control):** Home Assistant **MQTT Integration** (e.g. Mosquitto Broker) with external access configured (MQTTS/port 8883 or VPN/Cloudflare).

---

## Installation

### Via HACS (Recommended)

1. Open **HACS** in Home Assistant.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Enter the repository details:
   * **Repository:** `https://github.com/SuperSuave/ha-can-do`
   * **Type:** `Integration`
4. Click **Add**, then find and install **CAN Do**.
5. Restart Home Assistant.

---

## Configuration

### 1. Adding the Integration
1. In Home Assistant, navigate to **Settings → Devices & Services → Integrations**.
2. Click **Add Integration**, search for **CAN Do**, and select it.
3. Enter the hostname (e.g., `can_do_xxxx.local`) or local IP address of your device.
4. Set your preferred telemetry **Post Interval** (default is 15 seconds).

### 2. Device Webhook Pairing
When the integration finishes initial setup, it automatically registers its primary (and external HTTPS / Nabu Casa fallback) webhook URLs directly onto the CAN Do device.
* You can verify the registered webhook in your device's web dashboard under **Settings → Automation → Webhooks**.

### 3. Remote Control via MQTT (Away from Home)
To enable instant remote vehicle control outside your home network:
1. In the CAN Do device web interface, go to **Settings → MQTT**.
2. Enter your Home Assistant MQTT broker host, port, and credentials.
3. Enable MQTT.
4. That's it! When away from home, `ha-can-do` automatically routes commands via `can_do/<device_id>/cmd`.

---

## Troubleshooting

### Device unreachable during setup
* Verify your device is connected to the same Wi-Fi network and powered via the vehicle OBD port or USB bench supply.
* Check that mDNS resolution is functioning on your local network or configure via direct IP.

### Commands work at home but fail away from home
* Ensure your Home Assistant MQTT integration is configured and running.
* Verify the CAN Do device displays "MQTT Online" in its dashboard status.

---

## Contributing & Catalog
New vehicle models and CAN commands are actively maintained in the [CAN Do Message Catalog](https://github.com/SuperSuave/can-do-message-catalog). Contributions and captures are welcome!

---

## License
MIT License. See [LICENSE](LICENSE) for details.
