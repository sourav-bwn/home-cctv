# Home CCTV

Turn any old Android phone into a CCTV camera you control from your phone via Telegram and a web dashboard.

## What you get

- **Telegram bot** — send commands from anywhere in the world
- **Web dashboard** — view live feed and control from your browser
- **RTSP stream** — watch in VLC or any video player
- **Zero config** — paste one command and you're done

## What you need

| Item | Details |
|---|---|
| Old Android phone | Any Android 8+ phone lying around |
| WiFi | Both phones on the same network (for setup) |
| ~5 minutes | That's it |

## Setup

### Step 1: Install F-Droid on the old phone

1. Open the old phone's browser
2. Go to **https://f-droid.org**
3. Tap the download button → install the APK
4. Open F-Droid

### Step 2: Install Termux + Termux:API

1. In F-Droid, tap the search icon (🔍)
2. Search for **Termux** → tap Install
3. Search for **Termux:API** → tap Install
4. Open the **Termux** app

### Step 3: Create a Telegram bot (on your main phone)

1. Open Telegram on your main phone
2. Search for **@BotFather** → start a chat
3. Send: `/newbot`
4. Pick a name (e.g. `Home Camera`)
5. Pick a username ending in `_bot` (e.g. `home_camera_bot`)
6. **Copy the token** BotFather gives you — it looks like `123456:ABCdef...`

### Step 4: Get your Telegram User ID (on your main phone)

1. Search for **@userinfobot** on Telegram
2. Send: `/start`
3. **Copy the number** it replies with — that's your User ID

### Step 5: Run the one-command setup (on the old phone)

In the Termux app, paste this and press enter:

```bash
curl -sL https://raw.githubusercontent.com/sourav-bwn/home-cctv/main/install.sh | bash
```

The script will ask you for three things:
- **BotFather token** — paste from Step 3
- **Telegram User ID** — paste from Step 4
- **Web password** — pick any password (for the web dashboard)

That's it. The bot starts automatically.

## Usage

### From Telegram

Open your bot's chat and send:

| Command | What it does |
|---|---|
| `/start` | Show all commands |
| `/photo` | Take a photo and send it |
| `/torch` | Toggle flashlight on/off |
| `/stream` | Start/stop RTSP video stream |
| `/lock` | Turn off old phone's screen |
| `/battery` | Show battery level and temperature |
| `/sensors` | Read all sensors (proximity, light, etc.) |
| `/reboot` | Reboot the old phone |
| `/speak hello` | Make the old phone speak out loud |
| `/ping` | Check if bot is alive |

### From Web Dashboard

Open your main phone's browser and go to:

```
http://192.168.x.x:5000
```

(The exact IP is shown when setup completes)

Enter the web password you chose during setup. You'll see:
- Live camera feed
- Photo, Torch, Stream, Lock buttons
- Battery and sensor status

### In VLC (for RTSP stream)

Open VLC → Open Network Stream → enter:

```
rtsp://192.168.x.x:8554/live
```

## Troubleshooting

| Problem | Fix |
|---|---|
| Bot doesn't respond | Make sure old phone is on WiFi and Termux is running |
| Camera doesn't work | Settings → Apps → Termux → Permissions → enable Camera |
| App killed by Android | Settings → Battery → Termux → set to Unrestricted |
| WiFi disconnects | Settings → WiFi → Advanced → disable WiFi optimization |
| Screen locks and stops | Developer options → Keep screen on while charging |

## Commands reference

```
/photo      — capture & send photo
/torch      — toggle flashlight
/stream     — start/stop RTSP stream
/lock       — turn screen off
/battery    — battery level & temp
/sensors    — read proximity, light, accel
/reboot     — reboot the phone
/speak txt  — text-to-speech
/ping       — health check
```

## License

MIT
