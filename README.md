# MOVA Custom Voice Pack — Home Assistant add-on

Build and install **custom voice packs** for MOVA / Dreame robot vacuums, right
from Home Assistant. For each trigger you either **type what the robot should
say** (spoken by [Piper](https://github.com/rhasspy/piper) neural TTS, offline)
or **upload your own audio**. The add-on builds the pack and tells the robot to
fetch it over your LAN.

Works from your phone with your PC off — everything runs inside Home Assistant.

## Triggers you can customise
- **Returning to dock**
- **Start cleaning**
- **Finished cleaning**
- **Play now** — a button that makes the robot speak on demand (uses *locate*)

Any trigger you leave alone keeps the robot's original sound.

## Install
1. Home Assistant → **Settings → Add-ons → Add-on Store**.
2. Top-right **⋮ → Repositories** → paste this repo URL → **Add**:
   `https://github.com/agentemes/ha-mova-voicepack`
3. The **MOVA Custom Voice Pack** add-on appears in the store → **Install**.
4. (Optional) **Configuration** tab — set your `vacuum_entity` and `ha_base_url`
   if they differ from the defaults.
5. **Start** the add-on, then **Open Web UI**.

## First run
The robot's **base pack** (the full set of original clips) is **not** shipped
with this add-on — it is the manufacturer's proprietary audio. Upload it once in
the Web UI ("Upload base pack"). It is stored only inside your Home Assistant
and never leaves the box. After that, just type/upload per trigger → **Build** →
**Install to robot**.

## How it works
- Typed text → Piper TTS → Ogg Vorbis, mono, 16 kHz (the format the robot wants).
- Uploaded audio → converted to the same format with ffmpeg.
- Your clips replace the matching sound IDs in a copy of the base pack; a flat
  `.tar.gz` is written to `www/voicepack/` (served at `/local/voicepack/`), and
  `dreame_vacuum.vacuum_install_voice_pack` is called so the robot downloads it
  over the LAN.

## Privacy / licensing
This repository contains **only the builder code** (MIT). It ships **no**
manufacturer audio. The base pack you upload stays on your Home Assistant.

## Requirements
- Home Assistant OS / Supervised (add-ons), `amd64` or `aarch64`.
- The [`dreame_vacuum`](https://github.com/Tasshack/dreame-vacuum) integration,
  with your robot exposing `vacuum_install_voice_pack`.
