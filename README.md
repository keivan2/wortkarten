# Wortkarten 🐮📷🔊

A German word-learning helper for kids on a Raspberry Pi. Hold a picture card in front of
the camera and the Pi says what is on it, in German, with the article:

> „Super!" … „Das ist **die Kuh**. Die Kuh!"

The Pi recognises the card online with Google Gemini, so you don't need a list of words on
the device. Any card works: animals, fruit, vehicles, toys, and so on.

---

## How it works

```
camera ──► motion check ──► card held still? ──► photo ──► Gemini ──► "die Kuh"
                                                                         │
                         speaker ◄── mpg123 ◄── cached MP3 ◄── edge-tts ◄┘
```

1. **`camera.py`** compares small grey preview frames with an empty background. When something
   new appears and holds still for about 0.6 s, it takes a 1024×768 photo. It then waits until
   the card is removed, so each card is read only once.
2. **`recognizer.py`** sends the photo to Gemini. Gemini returns JSON such as
   `{"wort": "Kuh", "artikel": "die", "englisch": "cow"}`. If one model is busy, the next one
   in the list is tried.
3. **`speaker.py`** turns the text into German speech with Microsoft Edge's free online voices
   (`edge-tts`). It saves each phrase as an MP3 in `cache/`, so repeated words play instantly.
4. **`main.py`** runs the loop, says „Super!" right away as feedback, and appends every
   recognised word to `gelernte_woerter.jsonl`. That log can feed a quiz mode later.

| File | Purpose |
|---|---|
| `main.py` | Entry point and main loop; `--image` test mode |
| `camera.py` | Card detection and photo capture (Picamera2) |
| `recognizer.py` | Gemini image recognition |
| `speaker.py` | German TTS with an MP3 cache |
| `config.py` | All settings, read from `.env` or environment variables |
| `deploy/wortkarten.service` | systemd unit that starts the app on boot |

---

## Hardware

- **Raspberry Pi 3B+.** Other Pis should work too.
- **OV5647 camera** on the CSI ribbon. Ours is a third-party 5 MP IR-CUT night-vision model.
- **Speaker** on the 3.5 mm headphone jack. Bluetooth is planned.
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
# WK_VOICE=de-DE-KatjaNeural
# WK_VOICE_RATE=-15%
# WK_AUDIO_DEVICE=
# WK_CAMERA_TUNING=ov5647_noir.json
# WK_MOTION_THRESHOLD=12
# WK_STILL_THRESHOLD=4
# WK_STILL_FRAMES=4
```

### 5. Test it

Test the speaker:

```bash
./venv/bin/edge-tts --voice de-DE-KatjaNeural --text "Hallo!" --write-media /tmp/t.mp3 && mpg123 /tmp/t.mp3
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

**Tips for your child:** hold the card 20–40 cm from the camera, in good light, and keep it
still for about a second. Take it away before showing the next one.

---

## Settings

You can set all of these in `.env`. Restart the service after changing them.

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | – | **Required.** Google AI Studio key |
| `GEMINI_MODELS` | `gemini-3.5-flash-lite,gemini-3.5-flash` | Models to try, in order |
| `GEMINI_TIMEOUT_MS` | `15000` | Give up on a model after this many ms |
| `WK_VOICE` | `de-DE-KatjaNeural` | German voice. List them with `./venv/bin/edge-tts --list-voices \| grep de-DE` |
| `WK_VOICE_RATE` | `-15%` | Speaking speed; slightly slower suits kids |
| `WK_AUDIO_DEVICE` | *(system default)* | ALSA device for mpg123, e.g. `hw:0,0` |
| `WK_CAMERA_TUNING` | `ov5647_noir.json` | Camera colour tuning. Leave it empty for a standard (non-IR) camera |
| `WK_MOTION_THRESHOLD` | `12` | How different from the empty scene counts as "a card is there". Raise it if the reader triggers by itself |
| `WK_STILL_THRESHOLD` | `4` | How steady the card must be held. Raise it if it never triggers |
| `WK_STILL_FRAMES` | `4` | Number of steady frames (about 0.15 s each) before the photo is taken |

---

## Troubleshooting

| Problem | Cause and fix |
|---|---|
| `No cameras available!` | Run `sudo dmesg \| grep ov5647`. An `i2c read error … -5` means the camera doesn't respond, which is a cable problem: check the direction, check it's pushed fully in, and check the small lens ribbon. If there's no ov5647 line at all, the `dtoverlay=ov5647` line is missing from the boot config. |
| Pictures look **pink** | IR-CUT/NoIR cameras need `WK_CAMERA_TUNING=ov5647_noir.json` (the default). |
| It hangs or says „keine Verbindung" | No internet, or every Gemini model is busy (HTTP 503). Check `journalctl -u wortkarten`. Calls time out after 15 s. |
| `404 … no longer available` | Google retired a model. List the current ones and update `GEMINI_MODELS`. |
| It says the wrong word | Improve the light, hold the card closer and flatter, and avoid a busy background. |
| It triggers with no card | Lighting is changing (sun, lamps). Raise `WK_MOTION_THRESHOLD`. |
| No sound | `alsamixer` (volume), `aplay -l` (devices), `WK_AUDIO_DEVICE`. |

---

## Costs and privacy

- **Gemini:** each card is one small image request, which is well within the free tier for
  home use. Photos are sent to Google, so point the camera at the card rather than at your
  child's face where you can.
- **edge-tts:** free and needs no account. Only the text being spoken is sent, never images.

## Roadmap

- [ ] Bluetooth speaker
- [ ] Quiz mode („Wie macht die Kuh?") using the words in `gelernte_woerter.jsonl`
- [ ] Listening to the child's spoken answer (speech-to-text)
