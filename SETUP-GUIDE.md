# Sage Agent - GitHub Setup Guide

## Overview

This guide sets up a GitHub workflow for developing Sage:
1. Edit code locally (with Claude Code or any editor)
2. Push to GitHub
3. Pull on Sage-LiveKit Pi and restart

## Part 1: Create GitHub Repository

1. Go to https://github.com → **New repository**
2. Name: `sage-agent`
3. Visibility: **Private**
4. **DO NOT** initialize with README
5. Click **Create repository**

## Part 2: Set Up Your Development Machine

On your Mac/PC where you'll use Claude Code:

```bash
mkdir -p ~/Projects/sage-agent
cd ~/Projects/sage-agent
git init
git config user.name "Dennis"
git config user.email "your-email@example.com"
git remote add origin https://github.com/YOUR_USERNAME/sage-agent.git
```

Copy all repo files into this folder, then:

```bash
git add .
git commit -m "Initial commit"
git push -u origin main
```

**Note:** GitHub requires a Personal Access Token instead of password:
- GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
- Generate with `repo` scope
- Use as password when pushing

## Part 3: Set Up Sage-LiveKit Pi

Connect via Raspberry Pi Connect, then run these commands.

### 3.1 Install Git

```bash
sudo apt update && sudo apt install -y git
```

### 3.2 Backup Existing Files

```bash
mkdir -p ~/sage-backup
cp ~/sage-agent/agent.py ~/sage-backup/ 2>/dev/null || true
cp ~/sage-agent/.env ~/sage-backup/ 2>/dev/null || true
cp ~/sage-agent/system_prompt.txt ~/sage-backup/ 2>/dev/null || true
```

### 3.3 Clone Repository

```bash
cd /home/dennis-admin
rm -rf sage-agent
git clone https://github.com/YOUR_USERNAME/sage-agent.git
cd sage-agent
```

### 3.4 Restore .env File

```bash
cp ~/sage-backup/.env ~/sage-agent/.env
```

Or create new .env (fill in your actual values):

```bash
cat > ~/sage-agent/.env << 'EOF'
LIVEKIT_URL=wss://sage-eah2h8hc.livekit.cloud
LIVEKIT_API_KEY=API5j7purnGDjQb
LIVEKIT_API_SECRET=ZTfCg8sMxsFAexYtsKu3ekUTwPyencdEPhVtchGHZLTB
OLLAMA_API_KEY=c0ed591408a24b89a10e39e3f8f4736e.7RmMzoZbQqKLiNAeXl3qS8b2
HOME_ASSISTANT_URL=http://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI2ZDNkOTQ0YWVlY2U0MjI5YTZiNmY2ZDQwOGY5NmVjMSIsImlhdCI6MTc2OTg0MDgxMSwiZXhwIjoyMDg1MjAwODExfQ.aCxrG0J-h_n3_GphlcT4L3TeshmfdybcZq7YrEfR5Xw
SAGE_ADMIN_USER=admin
SAGE_ADMIN_PASS=changeme
EOF
```

### 3.5 Set Up Python Environment

```bash
cd ~/sage-agent
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3.6 Make Deploy Script Executable

```bash
chmod +x deploy.sh
```

### 3.7 Install Systemd Services

```bash
sudo cp sage-agent.service sage-admin.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sage-agent sage-admin
sudo systemctl restart sage-agent sage-admin
```

### 3.8 Verify Services

```bash
sudo systemctl status sage-agent sage-admin
```

## Part 4: Daily Workflow

### On Development Machine

```bash
cd ~/Projects/sage-agent

# Make changes (or use Claude Code)
# ...

# Commit and push
git add .
git commit -m "Description of changes"
git push origin main
```

### On Sage-LiveKit Pi

```bash
cd ~/sage-agent
./deploy.sh
```

## Quick Reference

### Development Machine

| Command | Purpose |
|---------|---------|
| `git status` | See changes |
| `git add .` | Stage all |
| `git commit -m "msg"` | Commit |
| `git push origin main` | Push to GitHub |

### Sage-LiveKit Pi

| Command | Purpose |
|---------|---------|
| `./deploy.sh` | Pull + restart |
| `sudo systemctl status sage-agent` | Check status |
| `sudo journalctl -u sage-agent -f` | View logs |
| `sudo systemctl restart sage-agent` | Restart agent |

## File Locations

```
Development Machine:
~/Projects/sage-agent/
├── agent.py
├── system_prompt.txt
├── admin/app.py
├── .env.example        ← Template (committed)
└── ...

Sage-LiveKit Pi:
/home/dennis-admin/sage-agent/
├── agent.py
├── system_prompt.txt
├── admin/app.py
├── .env                ← Actual secrets (NOT committed)
├── venv/               ← Python environment
└── ...
```
