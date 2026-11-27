# Wortkarten 🐮📷🔊

A German word-learning helper for kids on a Raspberry Pi. Hold a picture card in front of
the camera and the Pi says what is on it, in German, with the article:

> „**Die Kuh!**"

The Pi recognises the card online with Google Gemini, so you don't need a list of words on
the device. Any card works: animals, fruit, vehicles, toys, and so on.

---

## How it works

```
 auto mode:   card held still in the zone ─┐
 button mode: Zigbee button pressed ───────┴─► photo ──► Gemini ──► "die Kuh"
                                                                       │
                       speaker ◄── mpg123 ◄── cached MP3 ◄── edge-tts ◄┘
```

There are two modes (`WK_MODE`):

- **`auto`** (default): the camera reads a card as soon as one is held still in front of it.
- **`button`**: nothing happens until the button is pressed. Then it takes a photo right away
  and says the word. Pressing again cuts off whatever is being said and reads the card that's
  there now. See [Zigbee button](#zigbee-button).

1. **`camera.py`** only watches a **detection zone** in the middle of the picture (`WK_ZONE`).
   In auto mode a card counts when it covers at least 35% of the zone (`WK_MIN_COVER`), which
   means it's held close, and stays still for about 0.6 s. Movement in the background or at
   the edges is ignored. In auto mode the photo sent to Gemini is cropped to the zone, and each
   card is read only once until it's taken away. In button mode Gemini gets the whole picture,
   so a card held close (about 20 cm) isn't cut off. Before every photo the exposure is adjusted
   for the card itself, so a white card doesn't burn out and its text stays readable.
2. **`recognizer.py`** sends the photo to Gemini. Gemini **reads the name printed on the card
   first** and only falls back to the picture when no text is readable. That matters for cards
   that look alike, such as colour blobs labelled "Rot", "Blau", "Grün". Rotated cards work, and
   labels in other languages are translated (a card saying "Yellow" becomes *Gelb*). Gemini
   returns JSON such as
   `{"text": "Kuh", "quelle": "text", "wort": "Kuh", "artikel": "die", "englisch": "cow"}`.
   If one model is busy, the next one in the list is tried.
3. **`tts.py`** turns the text into German speech with **ElevenLabs** (voice "Sarah", model v3),
   which sounds the most human. If there's no ElevenLabs key, or it fails (offline, free
   allowance used up), it uses Microsoft Edge's free voice **Seraphina** (`edge-tts`) instead.
   Each phrase is saved as an MP3 in `cache/`, so repeated words play instantly and cost nothing.
   **`speaker.py`** plays it on the Bluetooth speaker, or on the headphone jack as a fallback.
4. **`main.py`** runs the loop and appends every recognised word to `gelernte_woerter.jsonl`.
   That log can feed a quiz mode later. If Gemini sees **no card** in the photo, the Pi stays
   silent in auto mode, because something else moved in front of the camera. In button mode it
   says „Ich sehe keine Karte …".
   Every photo is also saved to `captures/<date>/` for review (see [Reviewing the photos](#reviewing-the-photos)).

| File | Purpose |
|---|---|
| `main.py` | Entry point, auto and button loops; `--image` and `--snapshot` test modes |
| `camera.py` | Detection zone, card detection, own auto-exposure, photo capture (Picamera2) |
| `livefeed.py` | Live camera view in the browser (MJPEG stream, optional) |
| `button.py` | Listens for button presses over MQTT (from zigbee2mqtt) |
| `recognizer.py` | Gemini image recognition |
| `tts.py` | Text to speech: ElevenLabs, falling back to edge-tts; MP3 cache |
| `speaker.py` | Playback: Bluetooth speaker or wired output, stopping on a button press |
| `config.py` | All settings, read from `.env` or environment variables |
| `deploy/wortkarten.service` | systemd unit that starts the app on boot |

---

## Hardware

- **Raspberry Pi 3B+.** Other Pis should work too.
- **OV5647 camera** on the CSI ribbon. Ours is a third-party 5 MP IR-CUT night-vision model.
- **Speaker:** a Bluetooth speaker (ours is a *Fresh 'n Rebel 1ARB700*). Whenever it's off or out
  of range, the sound goes to the 3.5 mm headphone jack instead.
- **Optional: Zigbee button.** We use a Tuya battery "scene switch" button with a USB Zigbee
  dongle (ours shows up as a CH340 serial device, `/dev/ttyUSB0`).
- **Internet connection** (Wi-Fi or Ethernet).

### Connecting the camera (Pi 3B+)

**Unplug the Pi first.** Connecting the camera while the Pi is on can damage it.

- Use the slot labelled **CAMERA**, between the HDMI and audio jacks. Don't use the one
  labelled DISPLAY.
- At the Pi end, the **silver contacts face the HDMI jack** and the blue strip faces the audio
  jack.
- At the camera end, the silver contacts face the circuit board.
- On the camera board, press down the small ribbon that connects the lens module.
  It often comes loose.

---

## Fresh install

These steps assume Raspberry Pi OS / Debian 13 (trixie), 64-bit, and the user `keivan`.
If your username is different, change the paths in `deploy/wortkarten.service`.

### 1. Enable the camera

Third-party OV5647 boards are not always auto-detected. Edit the boot config:

```bash
sudo nano /boot/firmware/config.txt
```

Change `camera_auto_detect=1` to `camera_auto_detect=0`. Then add this line at the very end,
under `[all]`:

```
dtoverlay=ov5647
```

Reboot, then check:

```bash
sudo reboot
rpicam-hello --list-cameras     # should list: 0 : ov5647 [2592x1944 ...]
```

### 2. Install system packages

```bash
sudo apt update
sudo apt install -y git python3-picamera2 rpicam-apps-lite python3-venv python3-pip mpg123 alsa-utils
```

### 3. Get the code and the Python libraries

```bash
cd ~
git clone https://github.com/keivan2/wortkarten.git
cd wortkarten
python3 -m venv --system-site-packages venv     # system-site-packages is needed for picamera2
./venv/bin/pip install -r requirements.txt
```

### 4. Add your Gemini API key

1. Create a free key at <https://aistudio.google.com/apikey>.
2. Create the `.env` file. It is git-ignored, so the key never ends up on GitHub.

```bash
cd ~/wortkarten
umask 077                       # makes the file readable only by you
nano .env
```

Contents of `.env`. Only the first line is required; the rest show the optional settings
with their default values:

```ini
GEMINI_API_KEY=your-key-here

# Optional settings (defaults shown)
# GEMINI_MODELS=gemini-3.5-flash-lite,gemini-3.5-flash
# GEMINI_TIMEOUT_MS=15000
# ELEVENLABS_API_KEY=
# WK_ELEVENLABS_VOICE=EXAVITQu4vr4xnSDxMaL
# WK_ELEVENLABS_MODEL=eleven_v3
# WK_VOICE=de-DE-SeraphinaMultilingualNeural
# WK_VOICE_RATE=-10%
# WK_AUDIO_DEVICE=
# WK_BT_SPEAKER=
# WK_CAMERA_TUNING=ov5647_noir.json
# WK_TARGET_BRIGHTNESS=110
# WK_SAVE_CAPTURES=1
# WK_CHILD_NAME=
# WK_MODE=auto
# WK_BUTTON_TOPICS=zigbee2mqtt/knopf
# WK_MQTT_HOST=localhost
# WK_MQTT_PORT=1883
# WK_ZONE=0.1,0.05,0.9,0.95
# WK_MIN_COVER=0.35
# WK_PIXEL_DIFF=25
# WK_STILL_THRESHOLD=4
# WK_STILL_FRAMES=4
```

### 5. Test it

Test the speaker:

```bash
./venv/bin/edge-tts --voice de-DE-SeraphinaMultilingualNeural --text "Hallo!" --write-media /tmp/t.mp3 && mpg123 /tmp/t.mp3
```

If you hear nothing, run `alsamixer` and turn up the volume, or set `WK_AUDIO_DEVICE=hw:0,0` in `.env`.

Test recognition with any photo, without the camera:

```bash
./venv/bin/python main.py --image some-photo.jpg
```

Run it with the camera. Press Ctrl+C to stop.

```bash
./venv/bin/python main.py -v
```

### 6. Start automatically on boot

```bash
sudo cp deploy/wortkarten.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wortkarten
```

---

## Everyday use

| What | Command |
|---|---|
| Is it running? | `systemctl status wortkarten` |
| Live log | `journalctl -u wortkarten -f` |
| Restart (e.g. after changing `.env`) | `sudo systemctl restart wortkarten` |
| Stop / start | `sudo systemctl stop wortkarten` / `start` |
| Words learned so far | `cat ~/wortkarten/gelernte_woerter.jsonl` |
| Update the code | `cd ~/wortkarten && git pull && ./venv/bin/pip install -r requirements.txt && sudo systemctl restart wortkarten` |

### Reviewing the photos

Every photo the camera takes of a card is saved on the Pi, named with the time and what was
recognised:

```
~/wortkarten/captures/
└── 2026-11-27/
    ├── 093512_Kuh.jpg
    ├── 093540_Apfel.jpg
    ├── 093611_unbekannt.jpg     ← Gemini couldn't tell what it was
    └── 093702_fehler.jpg        ← no internet / Gemini error
```

Each entry in `gelernte_woerter.jsonl` also has a `"bild"` field pointing to its photo.

Copy the photos to your computer to look through and sort them:

```bash
rsync -av keivan@192.168.50.187:wortkarten/captures/ ~/Pictures/wortkarten-captures/
```

The photos are never uploaded to GitHub (`captures/` is git-ignored). Each one is about
75 KB, so a full card is a long way off. To turn saving off, set `WK_SAVE_CAPTURES=0`.

### Taking a test picture

The service keeps the camera busy, so stop it briefly. The snapshot shows the full camera
view with the **detection zone drawn in red**, which is handy for aiming the camera:

```bash
sudo systemctl stop wortkarten
cd ~/wortkarten && ./venv/bin/python main.py --snapshot ~/snapshot.jpg
sudo systemctl start wortkarten
```

### Live view in the browser

Set `WK_LIVE_PORT=8000` (in `.env` or the service drop-in) and restart the service. Then open
`http://<pi-address>:8000/` on any computer or phone at home to watch the camera live, with
the detection zone in red. `/snapshot.jpg` gives a single picture. It works while the service
runs, so there's no need to stop it. There's **no password**: anyone on your home network can
open it, so leave it off (`0`, the default) if that's not OK. The stream only uses CPU while a
browser is watching.

**Tips for your child:** hold the card 25–35 cm from the camera so it fills most of the red
zone, in good light, and keep it still for about a second. Tilt glossy cards slightly if a
lamp reflects on the text. In auto mode, take each card away before showing the next one.
When the service starts, keep the zone empty: it takes whatever is in view as the empty
background.

### Bluetooth speaker

This uses **bluez-alsa**, a small system service that makes a Bluetooth speaker a normal ALSA
sound output. Unlike PulseAudio/PipeWire, it works for a background service with nobody logged in.

```bash
sudo apt install -y bluez-alsa-utils libasound2-plugin-bluez rfkill
sudo systemctl disable --now bluealsa-aplay   # that one is for using the Pi AS a speaker
sudo rfkill unblock bluetooth                  # Raspberry Pi OS ships with Bluetooth blocked
bluetoothctl power on
```

Put the speaker in pairing mode, then find it and pair it:

```bash
bluetoothctl --timeout 30 scan on
bluetoothctl devices | grep -v -- '-..-..-'    # look for your speaker's name
bluetoothctl pair 52:C5:EC:33:40:58            # use your speaker's address
bluetoothctl trust 52:C5:EC:33:40:58
bluetoothctl connect 52:C5:EC:33:40:58
```

Then add `WK_BT_SPEAKER=52:C5:EC:33:40:58` to `.env` and run `sudo systemctl restart wortkarten`.

- If the speaker is off or out of range, words play on the headphone jack (`WK_AUDIO_DEVICE`)
  straight away, without waiting.
- A background thread retries the connection every 20 s, so switching the speaker back on is
  enough: it's used again within about half a minute.
- On a Pi 3B+, Wi-Fi and Bluetooth share one radio. If the sound stutters, Ethernet or a
  shorter distance to the speaker helps.

### Zigbee button

In button mode (`WK_MODE=button`), the Pi reads the card only when the button is pressed.
The chain is:

```
Zigbee button ──► USB dongle ──► zigbee2mqtt ──► mosquitto (MQTT) ──► button.py
```

zigbee2mqtt publishes each press as `{"action": "single"}` (or `double` / `hold`) on
`zigbee2mqtt/<button name>`. Any message with an `action` counts as a press, while battery
and signal updates are ignored.

Our hardware: a **Tuya TS0041** one-button wireless switch and a **"ZigBee 3.0 USB-Dongle
Plus-E"** (Silicon Labs EFR32MG21, EmberZNet 7.4.5 firmware, CH340 USB chip). The config
files are in `deploy/`.

**1. MQTT broker and Node.js 24.** zigbee2mqtt 2.x needs Node.js 22.13 or newer. Debian 13
only ships Node.js 20, so install Node.js from NodeSource:

```bash
sudo apt install -y mosquitto mosquitto-clients git
sudo apt remove -y nodejs npm            # only if Debian's Node.js 20 is installed
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt install -y nodejs
node --version                           # v24.x
```

**2. Install zigbee2mqtt.** This takes about 5–10 minutes on a Pi 3:

```bash
sudo mkdir -p /opt/zigbee2mqtt && sudo chown $USER: /opt/zigbee2mqtt
git clone --depth 1 https://github.com/Koenkk/zigbee2mqtt.git /opt/zigbee2mqtt
cd /opt/zigbee2mqtt
npx --yes pnpm install --frozen-lockfile
npx --yes pnpm run build
```

**3. Configure and start it.** Check that the `port` in the config matches
`ls /dev/serial/by-id/`. For a TI-based dongle (e.g. "-P"), change `adapter` to `zstack`.

```bash
cp ~/wortkarten/deploy/zigbee2mqtt/configuration.yaml /opt/zigbee2mqtt/data/
sudo cp ~/wortkarten/deploy/zigbee2mqtt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now zigbee2mqtt
mosquitto_sub -t zigbee2mqtt/bridge/state -C 1     # should print {"state":"online"}
```

On first start, zigbee2mqtt writes your network's secret keys into
`/opt/zigbee2mqtt/data/configuration.yaml`. Don't copy that file back into the repo.

**4. Pair the button.** Open pairing for 3 minutes, either in the web page
(http://192.168.50.187:8080, "Permit join") or with:

```bash
mosquitto_pub -t zigbee2mqtt/bridge/request/permit_join -m '{"time": 180}'
```

Hold the button **once for about 5 s**, then let go. The TS0041 has no visible LED, so don't
wait for one. Within a few seconds the log reports *"Tuya Wireless switch with 1 button
(TS0041)"*. Then rename it to `knopf` (replace the address with yours from the log or web page):

```bash
mosquitto_pub -t zigbee2mqtt/bridge/request/device/rename \
  -m '{"from": "0xa4c13857bce16546", "to": "knopf"}'
```

⚠️ **After pairing, only tap the button.** A short hold is fine and counts as a press, but
holding it for about 5 s resets it, and it leaves the network and has to be paired again.

**5. Check presses arrive**, then switch the card reader to button mode:

```bash
mosquitto_sub -t 'zigbee2mqtt/knopf' -v
#   zigbee2mqtt/knopf {"action":"single","battery":100,"linkquality":244,"voltage":3000}
```

Add `WK_MODE=button` to `.env`, then run `sudo systemctl restart wortkarten`.

To test button mode without the button, fake a press:

```bash
mosquitto_pub -t zigbee2mqtt/knopf -m '{"action":"single"}'
```

---

## Settings

You can set all of these in `.env`. Restart the service after changing them.

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | – | **Required.** Google AI Studio key |
| `GEMINI_MODELS` | `gemini-3.5-flash-lite,gemini-3.5-flash` | Models to try, in order |
| `GEMINI_TIMEOUT_MS` | `15000` | Give up on a model after this many ms |
| `ELEVENLABS_API_KEY` | *(empty)* | ElevenLabs key (elevenlabs.io → API keys). Only the text-to-speech permission is needed. Without a key, the free voice is used |
| `WK_ELEVENLABS_VOICE` | `EXAVITQu4vr4xnSDxMaL` ("Sarah") | ElevenLabs voice ID. Free accounts can only use the built-in voices, e.g. Sarah, Laura `FGY2WhTYpPnrIDTdsKH5`, Matilda `XrExE9yKIg1WjnnlVkGX`, George `JBFqnCBsd6RMkjVDRZzb` |
| `WK_ELEVENLABS_MODEL` | `eleven_v3` | `eleven_v3` (most expressive) or `eleven_multilingual_v2` (calmer, very stable) |
| `WK_VOICE` | `de-DE-SeraphinaMultilingualNeural` | Free fallback voice (edge-tts). `KatjaNeural`, `FlorianMultilingualNeural`, `AmalaNeural`, `TanjaNeural` and `ConradNeural` also work, even though `--list-voices` doesn't show all of them |
| `WK_VOICE_RATE` | `-10%` | Speaking speed of the free voice; slightly slower suits kids |
| `WK_AUDIO_DEVICE` | *(system default)* | Wired ALSA device for mpg123, e.g. `hw:0,0`. Also used as the fallback when the Bluetooth speaker is unavailable |
| `WK_BT_SPEAKER` | *(empty)* | MAC address of the paired Bluetooth speaker, e.g. `52:C5:EC:33:40:58` |
| `WK_CAMERA_TUNING` | `ov5647_noir.json` | Camera colour tuning. Leave it empty for a standard (non-IR) camera |
| `WK_TARGET_BRIGHTNESS` | `110` | Average brightness (0–255) that the app's own auto-exposure aims for. Lower it if pictures look washed out |
| `WK_LIVE_PORT` | `0` (off) | Port for the live camera view in the browser, e.g. `8000`. No password, home network only |
| `WK_SAVE_CAPTURES` | `1` | Save every card photo to `captures/`. Set it to `0` to turn this off |
| `WK_CHILD_NAME` | *(empty)* | Your child's name, used in the greeting "Hallo Anna! Zeig mir eine Karte …". Keep it in `.env`, not in the code, because the repo is public |
| `WK_MODE` | `auto` | `auto` reads a card when it's held still; `button` reads only when the button is pressed |
| `WK_BUTTON_TOPICS` | `zigbee2mqtt/knopf` | MQTT topics of the button(s), comma-separated |
| `WK_MQTT_HOST` / `WK_MQTT_PORT` | `localhost` / `1883` | MQTT broker (mosquitto) |
| `WK_ZONE` | `0.1,0.05,0.9,0.95` | Detection zone: left, top, right, bottom as fractions of the picture. Check it with `--snapshot` |
| `WK_MIN_COVER` | `0.35` | How much of the zone a card must cover (auto mode). Raise it if the background still triggers, lower it if cards are ignored. The log shows "Ignored: something covers X%" |
| `WK_PIXEL_DIFF` | `25` | How different from the empty background a pixel must be to count as covered |
| `WK_STILL_THRESHOLD` | `4` | How steady the card must be held. Raise it if it never triggers |
| `WK_STILL_FRAMES` | `4` | Number of steady frames (about 0.15 s each) before the photo is taken |

---

## Troubleshooting

| Problem | Cause and fix |
|---|---|
| `No cameras available!` | Run `sudo dmesg \| grep ov5647`. An `i2c read error … -5` means the camera doesn't respond, which is a cable problem: check the direction, check it's pushed fully in, and check the small lens ribbon. If there's no ov5647 line at all, the `dtoverlay=ov5647` line is missing from the boot config. |
| Pictures look **pink** | IR-CUT/NoIR cameras need `WK_CAMERA_TUNING=ov5647_noir.json` (the default). |
| Pictures are **washed out / almost white** | This camera's built-in auto-exposure overexposes badly (it locks at about 37 ms and 4× gain), so the app sets exposure itself (`camera.py`). If they're still too bright, lower `WK_TARGET_BRIGHTNESS`. Note that `rpicam-still` without `--shutter`/`--gain` still uses the broken built-in mode. |
| Pictures are **hazy / blurry** | Peel off any clear protective film on the lens. On wide-angle/fisheye models, turn the lens barrel gently to focus at the distance where cards are held (20–40 cm). |
| It hangs or says „keine Verbindung" | No internet, or every Gemini model is busy (HTTP 503). Check `journalctl -u wortkarten`. Calls time out after 15 s. |
| `404 … no longer available` | Google retired a model. List the current ones and update `GEMINI_MODELS`. |
| It says the wrong word | Improve the light, hold the card closer and flatter, and avoid a busy background. |
| It triggers with no card | Usually harmless: Gemini sees no card and the Pi stays quiet (the photo is saved as `…_keinekarte.jpg`). If it happens often, raise `WK_MIN_COVER` or shrink `WK_ZONE`. |
| It ignores the card | The card is too far away or not inside the zone. Check with `--snapshot`, look for "Ignored: … covers X%" in the log, and lower `WK_MIN_COVER` if needed. |
| The button does nothing | Run `mosquitto_sub -t 'zigbee2mqtt/#' -v` and press it. If nothing appears, it's a zigbee2mqtt or pairing problem. If messages appear on a different topic, set `WK_BUTTON_TOPICS`. Also check `WK_MODE=button`. |
| No sound | `alsamixer` (volume), `aplay -l` (devices), `WK_AUDIO_DEVICE`. |
| Sound comes from the jack, not the speaker | Is the speaker on? Run `bluetoothctl info <MAC>` and check for `Connected: yes`. The log shows "Bluetooth speaker connected / not available". If `bluetoothctl power on` fails, run `sudo rfkill unblock bluetooth`. |

---

## Costs and privacy

- **Gemini:** each card is one small image request, which is well within the free tier for
  home use. Photos are sent to Google, so point the camera at the card rather than at your
  child's face where you can.
- **ElevenLabs:** the free plan includes 10,000 characters a month. A new word sentence is about
  30 characters, and repeats come from the cache for free, so that's roughly 300 new words a
  month. When the allowance runs out, the free voice takes over automatically.
- **edge-tts:** free and needs no account.
- Only the text being spoken is sent to the voice services, never images.

## Roadmap

- [x] Detection zone, plus staying quiet when there's no card
- [x] Button mode (Zigbee via zigbee2mqtt / MQTT)
- [x] Bluetooth speaker, falling back to the headphone jack
- [ ] Quiz mode („Wie macht die Kuh?") using the words in `gelernte_woerter.jsonl`
- [ ] Listening to the child's spoken answer (speech-to-text)
