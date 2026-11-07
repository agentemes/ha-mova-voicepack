# MOVA Custom Voice Pack

## Configuration
| Option | Default | Meaning |
|---|---|---|
| `vacuum_entity` | `vacuum.p10_pro_ultra` | Your robot's `vacuum.*` entity. |
| `ha_base_url` | `http://192.168.1.136` | How the **robot** reaches Home Assistant on the LAN (used to build the download URL for the pack). |

## Steps
1. Start the add-on, open the Web UI.
2. **Upload base pack** (once). The archive is a flat `.tar.gz` of `<id>.ogg`
   clips plus `tts.json` — the robot's original voice pack. It is stored in the
   add-on's `/data` and never leaves this machine.
3. For each trigger: pick **Type text** or **Upload audio**, **Preview**, **Save**.
4. **Build pack** → **Install to robot**. The robot fetches the pack from
   `http://<ha_base_url>/local/voicepack/pack-XXXXXXXX.tar.gz` and applies it.
5. **Play now** makes the robot speak immediately (via `vacuum.locate`).

## Notes
- The pack is installed under a fixed language id `custom_mova`; each build gets
  a new filename (md5-stamped) so the robot always re-downloads the latest.
- Leaving a trigger unset keeps the robot's original clip for it.
- Audio you upload is converted to Ogg Vorbis, mono, 16 kHz automatically.

## Permissions used
- `homeassistant_api` — to call `dreame_vacuum.vacuum_install_voice_pack` and
  `vacuum.locate` through the Supervisor proxy.
- `homeassistant_config:rw` — to write the built pack into `www/voicepack/` so
  Home Assistant serves it to the robot at `/local/voicepack/`.
