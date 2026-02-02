# Sage Voice Assistant

A privacy-focused AI voice assistant using LiveKit Agents with Ollama Cloud for LLM inference. Sage provides natural language control of Home Assistant devices while serving as a general-purpose conversational AI.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│   ┌────────────────────┐        ┌─────────────────────────────────────┐  │
│   │  LiveKit Cloud     │        │  Ollama Cloud                       │  │
│   │  (STT/TTS)         │        │  (LLM: deepseek-v3.2)               │  │
│   └─────────┬──────────┘        └──────────────┬──────────────────────┘  │
│             │                                  │                         │
│             │  WebSocket                       │  HTTPS API              │
│             │                                  │                         │
│             ▼                                  ▼                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              Sage-LiveKit (Raspberry Pi 5 #2)                    │   │
│   │                                                                  │   │
│   │   agent.py          ←──  Python LiveKit Agent                   │   │
│   │   admin/app.py      ←──  Admin Panel (FastAPI :5000)            │   │
│   │                                                                  │   │
│   │   Deploy: GitHub → git pull → systemctl restart                 │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    │  REST API                           │
│                                    ▼                                     │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              Home Assistant (Raspberry Pi 5 #1)                  │   │
│   │                                                                  │   │
│   │   • HAOS on Argon ONE M.2 case                                  │   │
│   │   • Smart home device control                                   │   │
│   │   • ESPHome add-on (for future ESP32 satellite)                 │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              ESP32 Satellite (FUTURE)                            │   │
│   │                                                                  │   │
│   │   • Waveshare ESP32-S3-Touch-AMOLED-1.75                        │   │
│   │   • Physical mic/speaker/display                                │   │
│   │   • Will connect to Sage via LiveKit                            │   │
│   │   • Flashed via HA ESPHome add-on (not this repo)               │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

## Repository Structure

```
sage-agent/
├── agent.py              # Main LiveKit agent
├── system_prompt.txt     # LLM system prompt
├── admin/
│   └── app.py            # Admin panel (FastAPI)
├── .env.example          # Environment template (copy to .env)
├── .gitignore            # Excludes .env, venv, __pycache__
├── requirements.txt      # Python dependencies
├── sage-agent.service    # Systemd service for agent
├── sage-admin.service    # Systemd service for admin panel
├── deploy.sh             # One-command deployment script
└── README.md
```

## Deployment

This repo deploys to **one target**: the Sage-LiveKit Raspberry Pi.

### Initial Setup (one time)

```bash
# On Sage-LiveKit Pi
cd /home/dennis-admin
git clone https://github.com/YOUR_USERNAME/sage-agent.git
cd sage-agent

# Create venv and install dependencies
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Fill in your API keys

# Install systemd services
sudo cp sage-agent.service sage-admin.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sage-agent sage-admin
sudo systemctl start sage-agent sage-admin
```

### Ongoing Updates

After pushing changes to GitHub:

```bash
# On Sage-LiveKit Pi
cd /home/dennis-admin/sage-agent
./deploy.sh
```

Or manually:
```bash
git pull origin main
sudo systemctl restart sage-agent
```

## Current Status

### Working ✅
- LiveKit Cloud connection
- Speech-to-text (Deepgram Nova-3 via LiveKit Inference)
- Text-to-speech (Cartesia Sonic-2 via LiveKit Inference)
- LLM conversation (Ollama Cloud deepseek-v3.2)
- Initial greeting on connect
- Systemd services auto-start
- Admin panel at http://sage-livekit.local:5000

### Broken ❌
- **Smart home control** - Action tags spoken aloud instead of executed
- **Device discovery** - Not implemented; devices hardcoded in prompt

## Testing

1. Open https://agents-playground.livekit.io/
2. Connect to "Sage" project
3. Allow microphone access
4. Sage should greet you automatically

## Service Management

```bash
# Check status
sudo systemctl status sage-agent sage-admin

# View agent logs
sudo journalctl -u sage-agent -f

# Restart after code changes
sudo systemctl restart sage-agent
```

## Links

- [LiveKit Agents](https://docs.livekit.io/agents/)
- [LiveKit Playground](https://agents-playground.livekit.io/)
- [Ollama Cloud](https://ollama.com/)
- [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/)
