# UniFi Network Setup Guide
## Secure VLAN Segmentation for Apple-Centric Environments

**Applies to:** Any compatible UniFi products using UniFi Network 10.0 and later\
**Audience:** IT administrators\
**Last updated:** August 2026

---

## Overview

This guide covers designing and configuring a segmented UniFi network using zone-based firewall policies. The architecture separates devices by function and trust level, enforces traffic isolation between segments, and supports Apple services including AirPlay, AirPrint, and mobile device management (MDM).

The configuration uses eight VLANs organized into two firewall zones. Policies are applied at the zone level rather than per-interface, which simplifies management as the network scales.

---

## Prerequisites

- UniFi Network application 10.0 or later
- A UniFi gateway (UCG-Max, UDM, or UDR7 recommended)
- Optional UniFi managed switch
- Optional UniFi access point with Wi-Fi 6 or Wi-Fi 7 support
- Admin access at [unifi.ui.com](https://unifi.ui.com)

> **Note:** This guide assumes all devices are adopted and running current stable firmware before configuration begins.

---

## Network architecture

### Design principles

The architecture in this guide follows three principles:

1. **Least privilege** — devices can only communicate with the resources they need.
2. **Zone-based enforcement** — firewall rules apply to zones, not individual interfaces, reducing rule complexity.
3. **Explicit exceptions** — all inter-VLAN traffic is blocked by default. Permitted flows are individually defined.

### VLAN structure

The following table describes the recommended VLAN layout. The IP addressing scheme uses a third-octet value that matches the VLAN ID, making subnets easy to derive at a glance.

> **Note 1:** Any private IP addressing scheme in 10.0.0.0/8, 172.16.0.0/12, or 192.168.0.0/16 is valid. VLAN names used here are examples only.
>
> **Note 2:** All VLANs are optional if no existing devices apply.

| VLAN ID | Name | Subnet | Gateway | Zone | Purpose |
|---|---|---|---|---|---|
| 1 | Management | 10.0.1.0/24 | 10.0.1.1 | Internal | UniFi device management |
| 10 | Home | 10.0.10.0/24 | 10.0.10.1 | Internal | Personal devices |
| 20 | Work | 10.0.20.0/24 | 10.0.20.1 | Internal | Employee computers and mobile devices |
| 30 | Server | 10.0.30.0/24 | 10.0.30.1 | Internal | NAS, file servers, internal services |
| 40 | Media | 10.0.40.0/24 | 10.0.40.1 | Internal | Apple TV, speakers, shared displays |
| 50 | Security | 10.0.50.0/24 | 10.0.50.1 | Internal | Cameras, access control systems |
| 60 | IoT | 10.0.60.0/24 | 10.0.60.1 | Isolated | Smart devices, thermostats, printers |
| 70 | Guest | 10.0.70.0/24 | 10.0.70.1 | Isolated | Visitor internet access |

### Firewall zones

UniFi Network 10.0 uses a zone-based firewall model. Each VLAN is assigned to a zone, and policies are defined between zones rather than between individual networks.

| Zone | Assigned VLANs | Default behavior |
|---|---|---|
| **Internal** | Management, Home, Work, Server, Media, Security | Controlled — requires explicit policies |
| **Isolated** | IoT, Guest | Blocked from all Internal, VPN, DMZ, and other Isolated zones by default |
| **External** | WAN | Internet-facing |
| **Gateway** | Gateway device itself | Management interfaces |

Placing IoT and Guest in the Isolated zone provides automatic blocking from all trusted VLANs with no additional rules required. Exceptions — such as printer access — are added explicitly.

#### Why printers belong on IoT

Network printers are embedded systems with web servers, multiple print protocols, and infrequent firmware updates. Major vendors, including HP, Canon, Ricoh, and Brother, have documented CVEs affecting devices that appear fully up to date. Treating a printer like a server because it has a web interface underestimates its attack surface.

Placing a printer on the Isolated zone means it cannot initiate connections to any Internal VLAN device. If a printer is compromised, the attacker gains outbound internet access but cannot reach computers, servers, or other internal resources without an explicit firewall rule permitting it.

Printing still works normally — computers initiate the connection to the printer (Internal → Isolated), and return traffic is automatically permitted. See [Firewall policies](#firewall-policies).

---

## VLAN configuration

Create each VLAN under **Settings → Networks → Create New**. Key settings for each network:

| Setting | Recommended value |
|---|---|
| Router | Your gateway device |
| DHCP Mode | DHCP Server |
| Auto-Scale Network | Enabled |
| Isolate Network | **Disabled** — use zone assignment instead |
| Allow Internet Access | Enabled |
| IPv6 | Disabled (simplifies firewall management for most deployments) |

> **Important:** Do not use the **Isolate Network** toggle on individual VLANs. Use zone assignment in the Zone-Based Firewall section instead. Combining both creates overlapping auto-generated rules that are difficult to manage.

---

## Zone-Based Firewall configuration

### Network objects

Before creating firewall policies, define reusable objects. This allows policies to reference named objects rather than raw IP addresses, making rules easier to read and update.

#### IP lists

Create under **Settings → Profiles → Port/IP Groups**.

> **Note:** Before creating groups, connect each device and assign your desired static IP via a DHCP reservation in UniFi Client Devices.

| Name | VLAN | Example IP | Notes |
|---|---|---|---|
| Office Printer | IoT (60) | 10.0.60.x | Assign a DHCP reservation first |
| NAS | Server (30) | 10.0.30.x | Your file server address |
| Apple TV | Media (40) | 10.0.40.x | Create one object per device |

#### Port groups

| Name | Ports | Protocol | Purpose |
|---|---|---|---|
| Print Services | 631, 9100 | TCP | IPP/AirPrint and RAW printing |
| Gateway Mgmt Ports | 80, 443, 22 | TCP | Web UI and SSH |

### Zone assignments

Assign VLANs to zones under **Settings → Firewall & Security → Zone-Based Firewall → [Zone] → Edit**.

- Set **IoT** and **Guest** to **Isolated**.
- All other VLANs default to **Internal**.

### Firewall policies

Policies are evaluated top to bottom. The first matching rule wins. The order in the table below is significant.

Create each policy under **Firewall & Security → Firewall Policies → Create New Entry**.

#### Recommended policy order

| # | Name | Source zone | Source | Destination zone | Destination | Port | Action | Conn. state |
|---|---|---|---|---|---|---|---|---|
| 1 | Allow Printing | Internal | Any | Isolated | Office Printer | Print Services | Allow | New |
| 2 | Block Inter-VLAN | Internal | Any | Internal | Any | Any | Block | New |
| 3 | Block Gateway Mgmt — Internal | Internal | Any | Gateway | Any | Gateway Mgmt Ports | Block | All |
| 4 | Block Gateway Mgmt — Isolated | Isolated | Any | Gateway | Any | Gateway Mgmt Ports | Block | All |

#### Policy notes

**Allow Printing (rule 1)** must appear above the inter-VLAN block rule. Policy evaluation stops at the first match. Because the printer is on the IoT VLAN (Isolated zone), this rule crosses from Internal to Isolated — it is not affected by the Block Inter-VLAN rule, which operates only within the Internal zone.

Enable **Auto Allow Return Traffic** on this rule. This creates a companion rule that permits the printer to send job status responses back to the client without requiring a separate explicit rule.

**Block Inter-VLAN (rule 2)** enforces RFC 1918 separation between all Internal zone VLANs. Set **Connection State** to **New** (not All). This ensures the rule only blocks new connection attempts. Established connections — such as a print job already in progress — are handled by the system **Allow Return Traffic** rule and are not interrupted.

> **Important:** Blocking inter-VLAN communication is a security best practice. If a device with weaker security is compromised, this prevents an attacker from moving laterally to more critical devices on other VLANs.

> **Caution:** Setting Block Inter-VLAN to **All** connection states will break return traffic for every allow rule above it. Always use **New** state on inter-VLAN block rules.

**Block Gateway Mgmt rules (3 and 4)** prevent devices on any VLAN from accessing the gateway's local management interface. Administrators should use the cloud-hosted interface at [unifi.ui.com](https://unifi.ui.com) instead of the local web UI. This reduces the attack surface if a device on any VLAN is compromised.

> **Note:** Do not block all ports to the Gateway zone. DNS (port 53) and DHCP (ports 67–68) must remain accessible or devices will lose name resolution. Scoping the block to ports 80, 443, and 22 is sufficient.

> **Note:** If local web access to the gateway is desired for specific devices, add an allow rule positioned above the block rules. For example:
>
> | Allow Local Gateway Access | Internal | Home network | Gateway | Any | Gateway Mgmt Ports | Allow | New |
>
> Scope the source to the specific network or device group that requires local access. All other VLANs remain blocked.

**Printer management access** — to update printer firmware or access the printer's web admin from a computer, add an optional rule:

| Name | Source zone | Source | Destination zone | Destination | Port | Action | Conn. state |
|---|---|---|---|---|---|---|---|
| Allow Printer Management | Internal | Work network | Isolated | Office Printer | 443 | Allow | New |

Scope this to the Work or Home network only. Do not allow all Internal VLANs to reach the printer admin interface.

**Internet access** for all VLANs is handled by the zone matrix defaults. Confirm that **Internal → External** and **Isolated → External** both show **Allow All** in the zone matrix view.

---

## Wi-Fi configuration

### SSID design

Rather than creating a separate SSID for each VLAN, a simpler approach works well for managed-device environments: one SSID for all organization-owned devices, one SSID for guests.

| SSID | Default network | Who connects |
|---|---|---|
| YourOrgNetwork | Work (VLAN 20) | All organization-owned devices |
| YourOrgGuest | Guest (VLAN 70) | Visitors |

Devices that belong on non-Work VLANs (shared displays, smart devices, printers) connect to the main SSID and are moved to the correct VLAN via a fixed assignment in UniFi **Client Devices**. See [Client VLAN assignment](#client-vlan-assignment).

### Security protocols

#### macOS and iOS environments (recommended)

| Setting | Value | Notes |
|---|---|---|
| Security Protocol | WPA3 Personal | Supported on Apple devices with iOS 13+, macOS 10.15+ |
| PMF (Protected Management Frames) | Required | Mandatory for WPA3 |
| Client Isolation | Off | Required for AirDrop and local device communication |
| 802.11r Fast Roaming | On | Reduces roaming latency when multiple APs are present |
| 802.11k/v | On | Client steering and BSS transition hints |
| UAPSD | Off | Known to cause connectivity issues with Apple devices on some AP firmware |
| Multicast Enhancement | On | Improves AirPlay and AirPrint multicast performance |

#### Mixed OS environments (Windows, Android, Linux)

Older devices and non-Apple operating systems may not support WPA3. In mixed environments, use transition mode instead.

| Setting | macOS/iOS primary | Mixed OS |
|---|---|---|
| Security Protocol | WPA3 Personal | WPA2/WPA3 Transition |
| PMF | Required | **Optional** (Required breaks WPA2-only devices) |

> **Important:** When using WPA2/WPA3 Transition, PMF must be set to **Optional**. Setting it to Required prevents WPA2-only devices from associating.

#### Guest SSID settings

| Setting | Value | Notes |
|---|---|---|
| Security Protocol | WPA2/WPA3 Transition | Guest devices may be any OS or age |
| PMF | Optional | |
| Client Isolation | **On** | Prevents guest devices from communicating with each other |
| 802.11r | Off | Not needed for transient guest sessions; can cause issues on older clients |
| Bandwidth Limit | 25 Mbps down / 10 Mbps up | Prevents a single guest from saturating the WAN connection |

### Band configuration

The U7 Pro supports 2.4 GHz, 5 GHz, and 6 GHz simultaneously. Leave all bands enabled and allow UniFi's band steering to assign clients. Older IoT devices such as smart thermostats typically only support 2.4 GHz — if these connect to the main SSID, they will associate on 2.4 GHz automatically.

---

## mDNS proxy

AirPlay and AirPrint use mDNS for service discovery. mDNS is link-local (it doesn't cross VLANs by default), so UniFi's mDNS proxy must be enabled on each VLAN that needs to discover or advertise services.

Enable per network under **Settings → Networks → [Network] → Advanced → Multicast DNS**.

| VLAN | Enable mDNS | Reason |
|---|---|---|
| Management | No | No user devices |
| Home | **Yes** | MacBooks and iPhones need to discover printers and displays |
| Work | **Yes** | MacBooks and iPhones need to discover printers and displays |
| Server | No | Servers don't initiate media discovery |
| Media | **Yes** | Apple TV and speakers advertise here |
| Security | No | Cameras don't use mDNS |
| IoT | **Yes** | Printers advertise AirPrint here; required for cross-VLAN discovery |
| Guest | **Yes** | Optional — enable if guests should AirPlay to shared displays |

> **Note:** Because the printer is on the IoT VLAN, that VLAN must be included in the mDNS proxy for AirPrint discovery to work across VLANs. Both the source VLAN (Home, Work) and the destination VLAN (IoT) must be enabled for discovery to function.

Configure mDNS under **Settings → Networks → Gateway mDNS Proxy → Custom**. Select only the networks that need cross-VLAN service discovery. Enabling it network-wide is unnecessary and increases broadcast traffic.

#### Recommended service exclusions

In the mDNS proxy settings, disable services that are not in use:

- FTP Servers
- SSH Servers
- Time Capsule (discontinued)
- Windows File Sharing (unless required)
- Roku (if no Roku devices)

---

## Security settings

### Intrusion Prevention System

UniFi's IPS (available with a CyberSecure subscription) inspects traffic against signature-based threat intelligence updated daily.

| Setting | Recommended value |
|---|---|
| Intrusion Prevention | On |
| Selected Networks | All |
| Detection Mode | **Notify** during initial deployment; change to **Notify and Block** after one week of stable operation |
| Memory Optimized | On |

> **Note:** Use **Notify** mode for the first week after going live. This allows you to review the IPS event log and confirm no legitimate business traffic is being flagged before enabling blocking. After reviewing, switch to **Notify and Block**.

### Encrypted DNS

Encrypting DNS queries prevents ISP-level inspection of domain lookups.

| Setting | Recommended value |
|---|---|
| Encrypted DNS | Auto or Predefined |
| Provider | Cloudflare (1.1.1.1) or Cloudflare for Families (1.1.1.3) |

Cloudflare for Families (1.0.0.3 / 1.1.1.3) adds malware and adult content blocking at the DNS level with no additional configuration. Suitable for most organizational deployments.

### Region blocking

Region blocking restricts traffic by geographic origin. **Disable outbound region blocking** — even US-based SaaS services route traffic through international CDN infrastructure. "Allow outgoing: United States only" will break Apple services, Google Workspace, and most major SaaS platforms.

If you want to use region blocking, configure it as:

- **Mode:** Block
- **Direction:** Incoming
- **Countries:** High-risk source countries only

However, with IPS enabled at full signature coverage, region blocking adds minimal security value. IPS detects threats by behavior, not geography.

### Backup schedule

Configure automated backups under **Settings → System → Backups**.

| Setting | Value |
|---|---|
| Auto Backup | On |
| Frequency | Daily |
| Retention | 7 copies minimum |

---

## Client VLAN assignment

### Manual assignment

By default, all devices connecting to the main SSID land on the default VLAN (Work). To move a device to a different VLAN permanently:

1. In UniFi, go to **Client Devices**.
2. Find the device by hostname or MAC address.
3. Select **Configuration → Fixed IP/VLAN → Override VLAN**.
4. Choose the target VLAN.
5. On the device, toggle Wi-Fi off and back on to trigger reassociation and receive a new DHCP lease on the correct VLAN.

#### Target VLAN reference

| Device type | Target VLAN |
|---|---|
| Work computers, iPhones, iPads | Work (20) — stays on default |
| Personal devices | Home (10) |
| File server, NAS | Server (30) |
| Apple TV, speakers, shared displays | Media (40) |
| Security cameras, access control | Security (50) |
| Printers | IoT (60) |
| Smart thermostats, smart home devices | IoT (60) |

### MAC address randomization

macOS 14+ and iOS 14+ use randomized MAC addresses for Wi-Fi connections by default. Because VLAN assignment is based on MAC address, MAC randomization prevents fixed assignments from working — the device connects with a different MAC each time, and UniFi doesn't recognize it.

**Resolution for macOS:**

Go to **System Settings → Wi-Fi → [YourOrgNetwork] → Details** and disable **Private Wi-Fi Address** for the organization's SSID.

**At scale with MDM:**

Deploy a Wi-Fi configuration profile via your MDM platform (for example, Jamf Pro at `yourdomain.jamfcloud.com`) with MAC address randomization disabled for the organization SSID. This applies automatically to all enrolled devices.

```xml
<key>DisableAssociationMACRandomization</key>
<true/>
```

Include this key in the Wi-Fi payload of your MDM configuration profile scoped to all managed devices.

> **Note:** Private Wi-Fi Address should remain enabled on **Guest** networks where fixed VLAN assignment is not needed and privacy is appropriate.

### Advanced: Dynamic VLAN assignment with RADIUS

For larger deployments or higher-security requirements, RADIUS-based dynamic VLAN assignment removes the need for manual per-device configuration. The RADIUS server authenticates each device and returns the appropriate VLAN as part of the authentication response.

Required RADIUS attributes:

| Attribute | Value |
|---|---|
| `Tunnel-Type` | VLAN (13) |
| `Tunnel-Medium-Type` | IEEE-802 (6) |
| `Tunnel-Private-Group-ID` | VLAN ID as string (for example, `"20"`) |

For Apple device fleets managed with Jamf Pro, machine certificate–based 802.1X authentication is the recommended approach. Jamf can deploy the Wi-Fi profile and certificates silently. IoT and non-802.1X devices fall back to MAC Authentication Bypass (MAB).

---

## Zone matrix reference

The zone matrix in **Firewall & Security → Zone-Based Firewall** provides a summary of effective policy between each zone pair. Use this view to verify configuration after making changes.

| Source \ Destination | Internal | Isolated | External | Gateway |
|---|---|---|---|---|
| **Internal** | Custom rules (inter-VLAN block) | Custom rules (printing allow) | Allow All | Custom (mgmt ports blocked) |
| **Isolated** | Block All | Block All | Allow All | Custom (mgmt ports blocked) |
| **External** | Allow Return | — | Allow Return | Allow (system rules) |

Key outcomes:
- All Internal VLANs can reach the internet ✓
- All Isolated VLANs can reach the internet ✓
- Isolated VLANs cannot initiate connections to Internal VLANs ✓
- Internal VLANs can print to the printer on IoT (Isolated) ✓
- No VLAN can access the gateway management interface on HTTP, HTTPS, or SSH ✓
- A compromised printer cannot initiate connections to Internal devices ✓

---

## Appendix: Firewall configuration notes

- **Allow Printing** targets the printer by named IP object in the Isolated zone. The rule structure supports future changes to the printer's IP or migration to a different Isolated VLAN without rewriting the policy — only the IP object needs to be updated.
- **Block Inter-VLAN** uses Connection State: New. This is intentional — it blocks new connection initiations only, allowing established return traffic to flow through the system Allow Return Traffic rule.
- **mDNS on IoT** is required when printers are on that VLAN. Both the source VLAN (where clients live) and the destination VLAN (where the printer lives) must be included in the mDNS proxy for AirPrint discovery to work.
- Rows marked **System** in the firewall policy table are UniFi-generated and should not be manually edited or deleted.
- The **Allow Return Traffic** system rule must remain positioned above any broad block rules that use All connection states. Reordering it below a catch-all block will break return traffic network-wide.
