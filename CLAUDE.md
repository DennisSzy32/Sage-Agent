# CLAUDE.md - Sage Voice Assistant Project
## Complete Context for Claude Code
## Last Updated: February 1, 2026

---

# QUICK REFERENCE

| Item | Value |
|------|-------|
| **GitHub Repo** | https://github.com/DennisSzy32/Sage-Agent |
| **Local Dev** | `C:\Users\dennis\Projects\sage-agent\` (Windows) |
| **Pi Deploy** | `/home/dennis-admin/sage-agent/` |
| **Test URL** | https://agents-playground.livekit.io/ |
| **Admin Panel** | http://sage-livekit.local:5000 |

---

# PROJECT OVERVIEW

Sage is a privacy-focused voice assistant that:
- Runs on a Raspberry Pi 5
- Uses LiveKit Cloud for voice processing (STT/TTS)
- Uses Ollama Cloud for LLM inference (keeps AI processing private)
- Controls Home Assistant smart home devices via REST API

## Owner Requirements (STRICT)

1. **General Purpose AI** - Sage must handle conversations, questions, and tasks - NOT just smart home
2. **Voice-First** - Responses MUST be 1-3 sentences, conversational tone
3. **NO Home Assistant Add-ons** - Sage is standalone, communicates via REST API only
4. **Larger Models Preferred** - Dennis wants quality over cost savings
5. **Privacy** - Using Ollama Cloud keeps LLM inference private (no OpenAI/Anthropic APIs for Sage itself)

---

# HARDWARE ARCHITECTURE

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           SAGE ECOSYSTEM                                  │
├──────────────────────────────────────────────────────────────────────────┤
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
│   │              Hostname: Sage-LiveKit                              │   │
│   │                                                                  │   │
│   │   agent.py          ←── Python LiveKit Agent                    │   │
│   │   admin/app.py      ←── Admin Panel (FastAPI :5000)             │   │
│   │                                                                  │   │
│   │   Deploy: GitHub → git pull → ./deploy.sh                       │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    │  REST API                           │
│                                    ▼                                     │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              Home Assistant (Raspberry Pi 5 #1)                  │   │
│   │              Hostname: homeassistant.local                       │   │
│   │                                                                  │   │
│   │   • HAOS on Argon ONE M.2 case                                  │   │
│   │   • Smart home device control                                   │   │
│   │   • ESPHome add-on (for future ESP32 satellite)                 │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              ESP32 Satellite (FUTURE - NOT YET DEPLOYED)         │   │
│   │                                                                  │   │
│   │   • Waveshare ESP32-S3-Touch-AMOLED-1.75                        │   │
│   │   • Physical mic/speaker/display                                │   │
│   │   • Will connect to Sage via LiveKit                            │   │
│   │   • Flashed via HA ESPHome add-on (separate from this repo)     │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Key Points:**
- Two Raspberry Pi 5 devices (NOT one)
- Pi #1 = Home Assistant only
- Pi #2 = Sage agent + Admin panel (this is what we deploy to)
- ESP32 is future hardware, not currently active

---

# CURRENT STATUS

## What Works ✅
- LiveKit Cloud connection
- Speech-to-text (Deepgram Nova-3 via LiveKit Inference)
- Text-to-speech (Cartesia Sonic-2 via LiveKit Inference)
- LLM conversation (Ollama Cloud deepseek-v3.2)
- Initial greeting when user connects
- Systemd services running and auto-start on boot
- Admin panel accessible at http://sage-livekit.local:5000
- GitHub deployment workflow

## What's Broken ❌
- **Smart home control** - Action tags get spoken aloud instead of executed
- **Device discovery** - Not implemented; devices manually hardcoded in prompt
- **Admin panel device exposure** - Feature was never built

---

# THE CORE PROBLEM

## Ollama Cloud Does NOT Support Tool Calling

The Ollama Cloud `/v1` endpoint claims OpenAI compatibility but does NOT properly implement function/tool calling. When you define tools, the model outputs function call syntax as spoken text instead of structured JSON.

## Current Workaround: [ACTION:] Tags

Since tool calling doesn't work, the approach is:
1. Remove all tool definitions from the LLM
2. Instruct LLM to output `[ACTION: domain.service | entity_id=xxx]` tags in its response
3. Override `tts_node()` in the Agent class to intercept text BEFORE it reaches TTS
4. Parse action tags, execute them via HA REST API, strip tags from text
5. Pass cleaned text to TTS

## Why It's Not Working

The LLM is NOT following the exact format specified in the prompt.

**What we told it to output:**
```
[ACTION: automation.trigger | entity_id=automation.watch_tv_lighting]
```

**What it actually outputs:**
```
[scene:turn_on] entity_id=scene.tv
```

The regex in agent.py only matches the exact `[ACTION:` format, so malformed tags pass through and get spoken aloud by TTS.

**User heard:**
> "I'll activate TV watching mode for you. Setting up your entertainment lighting. [scene:turn_on] entity_id=scene.tv There, I've activated your TV watching scene."

---

# DEVELOPMENT WORKFLOW

## GitHub Repository
- **URL:** https://github.com/DennisSzy32/Sage-Agent
- **Visibility:** Private
- **Owner:** Dennis (GitHub: DennisSzy32)

## Local Development (Windows PC)
```
C:\Users\dennis\Projects\sage-agent\
├── admin/
│   ├── __init__.py
│   └── app.py
├── .env.example
├── .gitignore
├── agent.py
├── deploy.sh
├── README.md
├── requirements.txt
├── sage-admin.service
├── sage-agent.service
├── SETUP-GUIDE.md
└── system_prompt.txt
```

## Deployment Target (Sage-LiveKit Pi)
```
/home/dennis-admin/sage-agent/
├── admin/
│   ├── __init__.py
│   └── app.py
├── .env                  ← Contains actual secrets (NOT in git)
├── .env.example
├── .gitignore
├── agent.py
├── deploy.sh
├── README.md
├── requirements.txt
├── sage-admin.service
├── sage-agent.service
├── SETUP-GUIDE.md
├── system_prompt.txt
└── venv/                 ← Python virtual environment (NOT in git)
```

## Deployment Commands

**On Windows (Git Bash) - Push changes:**
```bash
cd /c/Users/dennis/Projects/sage-agent
git add .
git commit -m "Description of changes"
git push
```

**On Sage-LiveKit Pi - Deploy:**
```bash
cd ~/sage-agent
./deploy.sh
```

The `deploy.sh` script:
1. Pulls latest from GitHub
2. Installs any new dependencies
3. Restarts sage-agent service
4. Verifies it's running

---

# CREDENTIALS

## LiveKit Cloud
```
LIVEKIT_URL=wss://sage-eah2h8hc.livekit.cloud
LIVEKIT_API_KEY=API5j7purnGDjQb
LIVEKIT_API_SECRET=ZTfCg8sMxsFAexYtsKu3ekUTwPyencdEPhVtchGHZLTB
```
- Playground: https://agents-playground.livekit.io/
- Plan: Build (free tier, $2.50 credits)

## Ollama Cloud
```
OLLAMA_API_KEY=c0ed591408a24b89a10e39e3f8f4736e.7RmMzoZbQqKLiNAeXl3qS8b2
```
- API URL: https://ollama.com/v1 (NOT api.ollama.com!)
- Current Model: deepseek-v3.2 (671B parameters)
- Available models: deepseek-v3.2, gpt-oss:120b, qwen3-next:80b, gemma3:27b, gemma3:4b

## Home Assistant
```
HOME_ASSISTANT_URL=http://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI2ZDNkOTQ0YWVlY2U0MjI5YTZiNmY2ZDQwOGY5NmVjMSIsImlhdCI6MTc2OTg0MDgxMSwiZXhwIjoyMDg1MjAwODExfQ.aCxrG0J-h_n3_GphlcT4L3TeshmfdybcZq7YrEfR5Xw
```

## Admin Panel
```
SAGE_ADMIN_USER=admin
SAGE_ADMIN_PASS=changeme
```
- URL: http://sage-livekit.local:5000

---

# SAGE-LIVEKIT PI CONFIGURATION

| Item | Value |
|------|-------|
| Hostname | Sage-LiveKit |
| User | dennis-admin |
| OS | Raspberry Pi OS Lite (64-bit, headless) |
| Storage | 128GB SD card |
| Access | Raspberry Pi Connect (remote console) |
| Python | 3.13 in venv |

## Useful Commands
```bash
# Check service status
sudo systemctl status sage-agent sage-admin

# Restart agent after code changes
sudo systemctl restart sage-agent

# View logs (follow mode)
sudo journalctl -u sage-agent -f

# View last 100 log lines
sudo journalctl -u sage-agent -n 100

# After editing systemd services
sudo systemctl daemon-reload
```

---

# WHAT NEEDS TO BE FIXED

## Priority 1: Fix Action Tag Parsing

The LLM outputs things like `[scene:turn_on] entity_id=scene.tv` instead of `[ACTION: automation.trigger | entity_id=automation.watch_tv_lighting]`.

**Option A: More Flexible Regex**
Create a regex that catches multiple formats:
- `[ACTION: domain.service | entity_id=xxx]` (intended format)
- `[domain:service] entity_id=xxx` (what LLM actually outputs)
- `[domain.service | entity_id=xxx]` (another variation)

**Option B: Strict Few-Shot Prompting**
Add explicit examples in the system prompt showing the EXACT format, with multiple examples of correct usage.

**Option C: Different Parsing Strategy**
Instead of regex, look for any text that contains a valid domain (light, switch, automation, etc.) followed by a valid service and entity_id pattern.

## Priority 2: Implement Device Discovery

The system should fetch devices from Home Assistant at startup:

```python
async def fetch_ha_devices():
    """Fetch all entities from Home Assistant."""
    url = f"{HA_URL}/api/states"
    headers = {"Authorization": f"Bearer {HA_TOKEN}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
    return []

def build_device_list(entities):
    """Build formatted device list for system prompt."""
    devices = {"light": [], "switch": [], "automation": [], ...}
    for entity in entities:
        entity_id = entity["entity_id"]
        domain = entity_id.split(".")[0]
        friendly_name = entity["attributes"].get("friendly_name", entity_id)
        state = entity["state"]
        if domain in devices:
            devices[domain].append(f"- {friendly_name}: {entity_id} ({state})")
    return devices
```

Then inject into system prompt dynamically.

## Priority 3: Admin Panel Device Exposure

Build a UI in the admin panel that:
1. Fetches all HA entities
2. Lets user check/uncheck which ones Sage can control
3. Saves selection to a config file
4. Agent reads config and only includes selected devices in prompt

---

# CURRENT CODE (v4.2)

## agent.py

The current agent uses `tts_node` override to intercept LLM output before it reaches TTS. This is the correct architecture, but the regex is too strict.

Key components:
- `ALLOWED_SERVICES` - Dictionary of domain → allowed services
- `ACTION_PATTERN` - Regex to match action tags (currently too strict)
- `parse_actions()` - Extract actions from text
- `clean_for_tts()` - Remove action tags before speaking
- `execute_action()` - Call Home Assistant REST API
- `SageAgent.tts_node()` - Override that intercepts text, executes actions, cleans text

## system_prompt.txt

Current prompt instructs LLM to use `[ACTION: domain.service | entity_id=xxx]` format, but LLM doesn't follow it consistently.

---

# TESTING

## Test via LiveKit Playground
1. Open https://agents-playground.livekit.io/
2. Connect to "Sage" project
3. Allow microphone access
4. Sage should greet you automatically

## Test Commands
- General: "What's the weather like?" or "Tell me a joke"
- Smart home: "Turn on watch TV mode" or "Activate sleep mode"

## Check Logs
```bash
sudo journalctl -u sage-agent -f
```

Look for:
- `TTS Node: Found X action(s) to execute` - means parsing worked
- `Executing: domain.service -> entity_id` - means action is being sent to HA
- `SUCCESS` or `FAILED` - result of HA API call

---

# KNOWN GOTCHAS

1. **Ollama URL**: Must be `https://ollama.com/v1` - NOT `api.ollama.com`
2. **Ollama models**: Only "cloud" models work, not the full Ollama library
3. **LiveKit Inference**: STT/TTS included free - just use string identifiers
4. **Tool calling**: Does NOT work with Ollama Cloud - must use text-based action tags
5. **Service restart**: After code changes, must run `sudo systemctl restart sage-agent`
6. **GitHub auth**: Uses browser-based authentication, not passwords

---

# PYTHON DEPENDENCIES

```
livekit-agents[silero]>=1.3.0
livekit-plugins-openai>=1.0.0
python-dotenv>=1.0.0
aiohttp>=3.9.0
fastapi>=0.109.0
uvicorn>=0.27.0
```

---

# REFERENCE LINKS

- LiveKit Agents Docs: https://docs.livekit.io/agents/
- LiveKit Python SDK: https://github.com/livekit/agents
- LiveKit Playground: https://agents-playground.livekit.io/
- Ollama Cloud: https://ollama.com/
- Ollama Cloud Models: https://ollama.com/search?c=cloud
- Cartesia Voices: https://play.cartesia.ai/
- Home Assistant REST API: https://developers.home-assistant.io/docs/api/rest/

---

# VERSION HISTORY

| Version | Change | Status |
|---------|--------|--------|
| v1-v2 | LiveKit tool calling with Ollama Cloud | Failed - Ollama doesn't support it |
| v3 | Text-based action tags with event handler | Failed - tags spoken aloud |
| v4.1 | `conversation_item_added` event interception | Failed - wrong interception point |
| v4.2 | `tts_node` override interception | **Current** - right architecture, wrong regex |

---

# WHAT SUCCESS LOOKS LIKE

When working correctly:

**User says:** "Turn on watch TV mode"

**LLM outputs:** "I'll activate TV mode for you. [ACTION: automation.trigger | entity_id=automation.watch_tv_lighting]"

**tts_node does:**
1. Buffers full text
2. Regex finds the [ACTION:] tag
3. Extracts: domain=automation, service=trigger, entity_id=automation.watch_tv_lighting
4. Calls HA REST API: POST /api/services/automation/trigger with entity_id
5. Strips tag from text
6. Passes "I'll activate TV mode for you." to TTS

**User hears:** "I'll activate TV mode for you."

**User does NOT hear:** Any mention of ACTION, automation.trigger, entity_id, etc.

---

# DENNIS'S PREFERENCES

- Prefers larger AI models for quality over cost savings
- Voice-first interaction patterns (1-3 sentences)
- Privacy-focused - no cloud LLM dependencies on OpenAI/Anthropic for the assistant
- Uses Raspberry Pi Connect for remote Pi access
- Prefers heredoc commands in downloadable documents for Pi file transfers
- New to GitHub - just set up the workflow today (Feb 1, 2026)
- Windows PC for development, Git Bash for commands

---

# ESP32 SATELLITE (FUTURE)

The Waveshare ESP32-S3-Touch-AMOLED-1.75 device is planned as a future voice satellite. Current status:

- Testing microphone configuration (ES7210 ADC)
- `mic_gain` format issue with ESPHome 2026.1.3
- Will be flashed via Home Assistant's ESPHome add-on
- Separate from this repository

See `session-consolidation-2026-02-01.md` for ESP32 mic testing details.
