"""
Sage Admin Panel
FastAPI web interface for managing Sage voice assistant
"""

import os
import json
import asyncio
import aiohttp
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import secrets

app = FastAPI(title="Sage Admin Panel")
security = HTTPBasic()

# Configuration
ADMIN_USER = os.environ.get("SAGE_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("SAGE_ADMIN_PASS", "changeme")
BASE_DIR = Path(__file__).parent.parent
PROMPT_FILE = BASE_DIR / "system_prompt.txt"
EXPOSED_DEVICES_FILE = BASE_DIR / "exposed_devices.json"
DEVICE_DESCRIPTIONS_FILE = BASE_DIR / "device_descriptions.json"
HA_URL = os.environ.get("HOME_ASSISTANT_URL", "http://homeassistant.local:8123")
HA_TOKEN = os.environ.get("HOME_ASSISTANT_TOKEN", "")

# Domain categories for grouping devices
DOMAIN_LABELS = {
    "light": "Lights",
    "switch": "Switches",
    "automation": "Automations",
    "button": "Buttons",
    "scene": "Scenes",
    "script": "Scripts",
    "lock": "Locks",
    "cover": "Covers",
    "fan": "Fans",
    "climate": "Climate",
    "media_player": "Media Players",
    "input_boolean": "Input Booleans",
    "sensor": "Sensors",
    "binary_sensor": "Binary Sensors",
}


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_user = secrets.compare_digest(credentials.username, ADMIN_USER)
    correct_pass = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (correct_user and correct_pass):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return credentials.username


def load_exposed_devices() -> list:
    """Load list of exposed device entity_ids."""
    if EXPOSED_DEVICES_FILE.exists():
        try:
            return json.loads(EXPOSED_DEVICES_FILE.read_text())
        except json.JSONDecodeError:
            return []
    return []


def save_exposed_devices(devices: list):
    """Save list of exposed device entity_ids."""
    EXPOSED_DEVICES_FILE.write_text(json.dumps(devices, indent=2))


def load_device_descriptions() -> dict:
    """Load device descriptions mapping entity_id -> description."""
    if DEVICE_DESCRIPTIONS_FILE.exists():
        try:
            return json.loads(DEVICE_DESCRIPTIONS_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_device_descriptions(descriptions: dict):
    """Save device descriptions mapping."""
    DEVICE_DESCRIPTIONS_FILE.write_text(json.dumps(descriptions, indent=2))


async def get_service_status(service_name: str) -> dict:
    """Get the status of a systemd service."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "is-active", service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        is_active = stdout.decode().strip() == "active"

        # Get more details if active
        status = "running" if is_active else "stopped"

        return {"service": service_name, "status": status, "active": is_active}
    except Exception as e:
        return {"service": service_name, "status": "unknown", "active": False, "error": str(e)}


async def restart_service(service_name: str) -> dict:
    """Restart a systemd service using sudo."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo", "systemctl", "restart", service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        if proc.returncode == 0:
            return {"success": True, "message": f"{service_name} restarted successfully"}
        else:
            error = stderr.decode().strip()
            return {"success": False, "message": f"Failed to restart: {error}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


async def get_git_info() -> dict:
    """Get current git commit info."""
    try:
        # Get current commit hash (short)
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "--short", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=BASE_DIR
        )
        stdout, _ = await proc.communicate()
        commit = stdout.decode().strip() if proc.returncode == 0 else "unknown"

        # Get current branch
        proc = await asyncio.create_subprocess_exec(
            "git", "branch", "--show-current",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=BASE_DIR
        )
        stdout, _ = await proc.communicate()
        branch = stdout.decode().strip() if proc.returncode == 0 else "unknown"

        return {"commit": commit, "branch": branch}
    except Exception as e:
        return {"commit": "error", "branch": "error", "error": str(e)}


async def git_pull() -> dict:
    """Pull latest changes from git."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "pull",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=BASE_DIR
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode().strip()
        error = stderr.decode().strip()

        if proc.returncode == 0:
            if "Already up to date" in output:
                return {"success": True, "message": "Already up to date", "updated": False}
            else:
                return {"success": True, "message": output, "updated": True}
        else:
            return {"success": False, "message": error or output}
    except Exception as e:
        return {"success": False, "message": str(e)}


# Pydantic models for API
class SystemPromptUpdate(BaseModel):
    content: str


class ExposedDevicesUpdate(BaseModel):
    devices: list[str]
    descriptions: dict[str, str] = {}


# HTML Templates
def get_base_html(active_tab: str, content: str) -> str:
    """Generate base HTML with navigation tabs."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sage Admin Panel</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                margin: 0;
                padding: 0;
                background: #f5f5f5;
                color: #333;
            }}
            .header {{
                background: linear-gradient(135deg, #2e7d32, #4caf50);
                color: white;
                padding: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
            }}
            .header p {{
                margin: 5px 0 0;
                opacity: 0.9;
                font-size: 14px;
            }}
            .tabs {{
                display: flex;
                background: white;
                border-bottom: 1px solid #ddd;
                padding: 0 20px;
            }}
            .tab {{
                padding: 15px 25px;
                text-decoration: none;
                color: #666;
                border-bottom: 3px solid transparent;
                transition: all 0.2s;
            }}
            .tab:hover {{
                color: #2e7d32;
                background: #f9f9f9;
            }}
            .tab.active {{
                color: #2e7d32;
                border-bottom-color: #4caf50;
                font-weight: 500;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }}
            .card {{
                background: white;
                border-radius: 8px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                padding: 20px;
                margin-bottom: 20px;
            }}
            .card h2 {{
                margin-top: 0;
                color: #2e7d32;
                font-size: 18px;
                border-bottom: 1px solid #eee;
                padding-bottom: 10px;
            }}
            textarea {{
                width: 100%;
                min-height: 400px;
                font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
                font-size: 13px;
                padding: 15px;
                border: 1px solid #ddd;
                border-radius: 4px;
                resize: vertical;
                line-height: 1.5;
            }}
            textarea:focus {{
                outline: none;
                border-color: #4caf50;
                box-shadow: 0 0 0 2px rgba(76,175,80,0.2);
            }}
            .btn {{
                display: inline-block;
                padding: 10px 20px;
                background: #4caf50;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                transition: background 0.2s;
            }}
            .btn:hover {{
                background: #388e3c;
            }}
            .btn:disabled {{
                background: #ccc;
                cursor: not-allowed;
            }}
            .btn-secondary {{
                background: #757575;
            }}
            .btn-secondary:hover {{
                background: #616161;
            }}
            .status {{
                display: inline-block;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
            }}
            .status-ok {{
                background: #e8f5e9;
                color: #2e7d32;
            }}
            .status-error {{
                background: #ffebee;
                color: #c62828;
            }}
            .message {{
                padding: 12px 15px;
                border-radius: 4px;
                margin-bottom: 15px;
                display: none;
            }}
            .message.success {{
                background: #e8f5e9;
                color: #2e7d32;
                border: 1px solid #a5d6a7;
            }}
            .message.error {{
                background: #ffebee;
                color: #c62828;
                border: 1px solid #ef9a9a;
            }}
            .device-group {{
                margin-bottom: 25px;
            }}
            .device-group h3 {{
                margin: 0 0 10px;
                font-size: 16px;
                color: #555;
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            .device-group h3 .count {{
                font-size: 12px;
                background: #e0e0e0;
                padding: 2px 8px;
                border-radius: 10px;
                font-weight: normal;
            }}
            .device-list {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 8px;
            }}
            .device-item {{
                display: flex;
                align-items: center;
                padding: 8px 12px;
                background: #fafafa;
                border-radius: 4px;
                border: 1px solid #eee;
            }}
            .device-item:hover {{
                background: #f0f0f0;
            }}
            .device-item input[type="checkbox"] {{
                margin-right: 10px;
                width: 18px;
                height: 18px;
                cursor: pointer;
            }}
            .device-item label {{
                flex: 1;
                cursor: pointer;
                font-size: 14px;
            }}
            .device-item .entity-id {{
                font-size: 11px;
                color: #888;
                font-family: monospace;
            }}
            .device-item .state {{
                font-size: 11px;
                padding: 2px 6px;
                border-radius: 3px;
                background: #e0e0e0;
                color: #666;
            }}
            .toolbar {{
                display: flex;
                gap: 10px;
                margin-bottom: 15px;
                flex-wrap: wrap;
                align-items: center;
            }}
            .toolbar .spacer {{
                flex: 1;
            }}
            .search-box {{
                padding: 8px 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                width: 250px;
            }}
            .loading {{
                text-align: center;
                padding: 40px;
                color: #888;
            }}
            .stats {{
                display: flex;
                gap: 20px;
                flex-wrap: wrap;
            }}
            .stat-box {{
                flex: 1;
                min-width: 150px;
                padding: 15px;
                background: #f9f9f9;
                border-radius: 6px;
                text-align: center;
            }}
            .stat-box .value {{
                font-size: 28px;
                font-weight: bold;
                color: #2e7d32;
            }}
            .stat-box .label {{
                font-size: 12px;
                color: #888;
                margin-top: 5px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Sage Admin Panel</h1>
            <p>Voice Assistant Configuration</p>
        </div>
        <div class="tabs">
            <a href="/" class="tab {'active' if active_tab == 'dashboard' else ''}">Dashboard</a>
            <a href="/prompt" class="tab {'active' if active_tab == 'prompt' else ''}">System Prompt</a>
            <a href="/devices" class="tab {'active' if active_tab == 'devices' else ''}">Devices</a>
        </div>
        <div class="container">
            {content}
        </div>
    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
async def dashboard(username: str = Depends(verify_credentials)):
    """Dashboard with status overview."""
    exposed_count = len(load_exposed_devices())
    prompt_size = PROMPT_FILE.stat().st_size if PROMPT_FILE.exists() else 0

    # Get service statuses
    agent_status = await get_service_status("sage-agent")
    admin_status = await get_service_status("sage-admin")
    git_info = await get_git_info()

    agent_status_class = "status-ok" if agent_status["active"] else "status-error"
    admin_status_class = "status-ok" if admin_status["active"] else "status-error"

    content = f"""
    <div class="card">
        <h2>Status Overview</h2>
        <div id="message" class="message"></div>
        <div class="stats">
            <div class="stat-box">
                <div class="value">4.6</div>
                <div class="label">Agent Version</div>
            </div>
            <div class="stat-box">
                <div class="value">{exposed_count}</div>
                <div class="label">Exposed Devices</div>
            </div>
            <div class="stat-box">
                <div class="value">{prompt_size:,}</div>
                <div class="label">Prompt Size (bytes)</div>
            </div>
            <div class="stat-box">
                <div class="value" style="font-size: 16px;">{git_info["commit"]}</div>
                <div class="label">Git Commit ({git_info["branch"]})</div>
            </div>
        </div>
        <div style="margin-top: 20px;">
            <h3 style="margin-bottom: 10px; font-size: 14px; color: #555;">Deployment</h3>
            <div style="display: flex; gap: 15px; flex-wrap: wrap; align-items: center;">
                <button class="btn" onclick="pullUpdates()" style="background: #7b1fa2;">Pull Updates from GitHub</button>
                <span id="pull-status" style="font-size: 13px; color: #666;"></span>
            </div>
        </div>
        <div style="margin-top: 20px;">
            <h3 style="margin-bottom: 10px; font-size: 14px; color: #555;">Services</h3>
            <div style="display: flex; gap: 15px; flex-wrap: wrap;">
                <div style="display: flex; align-items: center; gap: 10px; padding: 10px 15px; background: #fafafa; border-radius: 6px; border: 1px solid #eee;">
                    <span>sage-agent</span>
                    <span class="status {agent_status_class}" id="agent-status">{agent_status["status"]}</span>
                    <button class="btn" onclick="restartService('sage-agent')" style="padding: 5px 10px; font-size: 12px;">Restart</button>
                </div>
                <div style="display: flex; align-items: center; gap: 10px; padding: 10px 15px; background: #fafafa; border-radius: 6px; border: 1px solid #eee;">
                    <span>sage-admin</span>
                    <span class="status {admin_status_class}" id="admin-status">{admin_status["status"]}</span>
                    <button class="btn btn-secondary" onclick="restartService('sage-admin')" style="padding: 5px 10px; font-size: 12px;">Restart</button>
                </div>
            </div>
        </div>
    </div>
    <div class="card">
        <h2>Quick Actions</h2>
        <p>Use the tabs above to:</p>
        <ul>
            <li><strong>System Prompt</strong> - Edit Sage's personality and instructions</li>
            <li><strong>Devices</strong> - Choose which Home Assistant devices Sage can control</li>
        </ul>
        <p style="color: #888; font-size: 13px;">
            <strong>Workflow:</strong> Pull Updates → Restart sage-admin (if admin changed) → Restart sage-agent (to apply config)
        </p>
    </div>
    <script>
        async function restartService(serviceName) {{
            const messageEl = document.getElementById('message');
            messageEl.textContent = 'Restarting ' + serviceName + '...';
            messageEl.className = 'message';
            messageEl.style.display = 'block';
            messageEl.style.background = '#fff3e0';
            messageEl.style.color = '#e65100';
            messageEl.style.border = '1px solid #ffcc80';

            try {{
                const response = await fetch('/api/service/' + serviceName + '/restart', {{
                    method: 'POST'
                }});
                const data = await response.json();

                if (data.success) {{
                    messageEl.textContent = data.message;
                    messageEl.className = 'message success';
                    messageEl.style.background = '';
                    messageEl.style.border = '';

                    // Refresh status after a short delay
                    if (serviceName !== 'sage-admin') {{
                        setTimeout(() => location.reload(), 1500);
                    }} else {{
                        messageEl.textContent = data.message + ' Page will reload...';
                        setTimeout(() => location.reload(), 3000);
                    }}
                }} else {{
                    messageEl.textContent = 'Error: ' + data.message;
                    messageEl.className = 'message error';
                    messageEl.style.background = '';
                    messageEl.style.border = '';
                }}
            }} catch (e) {{
                messageEl.textContent = 'Error: ' + e.message;
                messageEl.className = 'message error';
                messageEl.style.background = '';
                messageEl.style.border = '';
            }}
        }}

        async function pullUpdates() {{
            const messageEl = document.getElementById('message');
            const pullStatus = document.getElementById('pull-status');

            pullStatus.textContent = 'Pulling...';
            messageEl.style.display = 'none';

            try {{
                const response = await fetch('/api/git/pull', {{ method: 'POST' }});
                const data = await response.json();

                if (data.success) {{
                    pullStatus.textContent = '';
                    if (data.updated) {{
                        messageEl.textContent = 'Updates pulled successfully! Restart services to apply changes.';
                        messageEl.className = 'message success';
                        messageEl.style.display = 'block';
                        // Reload to show new commit
                        setTimeout(() => location.reload(), 2000);
                    }} else {{
                        messageEl.textContent = data.message;
                        messageEl.className = 'message success';
                        messageEl.style.display = 'block';
                    }}
                }} else {{
                    pullStatus.textContent = '';
                    messageEl.textContent = 'Pull failed: ' + data.message;
                    messageEl.className = 'message error';
                    messageEl.style.display = 'block';
                }}
            }} catch (e) {{
                pullStatus.textContent = '';
                messageEl.textContent = 'Error: ' + e.message;
                messageEl.className = 'message error';
                messageEl.style.display = 'block';
            }}
        }}
    </script>
    """
    return HTMLResponse(get_base_html("dashboard", content))


@app.get("/prompt", response_class=HTMLResponse)
async def prompt_page(username: str = Depends(verify_credentials)):
    """System prompt editor page."""
    prompt_content = ""
    if PROMPT_FILE.exists():
        prompt_content = PROMPT_FILE.read_text()

    # Escape HTML entities in prompt content
    prompt_content = prompt_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    content = f"""
    <div class="card">
        <h2>System Prompt Editor</h2>
        <div id="message" class="message"></div>
        <p style="color: #666; font-size: 13px; margin-bottom: 15px;">
            Edit Sage's system prompt below. This defines the AI's personality, capabilities, and available devices.
        </p>
        <textarea id="prompt-editor">{prompt_content}</textarea>
        <div style="margin-top: 15px; display: flex; gap: 10px; flex-wrap: wrap;">
            <button class="btn" onclick="savePrompt(false)">Save Changes</button>
            <button class="btn" onclick="savePrompt(true)" style="background: #1976d2;">Save & Restart Agent</button>
            <button class="btn btn-secondary" onclick="reloadPrompt()">Reload</button>
        </div>
    </div>
    <script>
        async function savePrompt(restart) {{
            const content = document.getElementById('prompt-editor').value;
            const messageEl = document.getElementById('message');

            try {{
                const response = await fetch('/api/prompt', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ content }})
                }});

                if (response.ok) {{
                    if (restart) {{
                        messageEl.textContent = 'Saved! Restarting sage-agent...';
                        messageEl.className = 'message';
                        messageEl.style.display = 'block';
                        messageEl.style.background = '#fff3e0';
                        messageEl.style.color = '#e65100';
                        messageEl.style.border = '1px solid #ffcc80';

                        const restartResp = await fetch('/api/service/sage-agent/restart', {{ method: 'POST' }});
                        const restartData = await restartResp.json();

                        if (restartData.success) {{
                            messageEl.textContent = 'System prompt saved and agent restarted successfully!';
                            messageEl.className = 'message success';
                            messageEl.style.background = '';
                            messageEl.style.border = '';
                        }} else {{
                            messageEl.textContent = 'Saved, but restart failed: ' + restartData.message;
                            messageEl.className = 'message error';
                            messageEl.style.background = '';
                            messageEl.style.border = '';
                        }}
                    }} else {{
                        messageEl.textContent = 'System prompt saved successfully! Restart sage-agent to apply changes.';
                        messageEl.className = 'message success';
                        messageEl.style.display = 'block';
                    }}
                }} else {{
                    const data = await response.json();
                    messageEl.textContent = 'Error: ' + (data.detail || 'Failed to save');
                    messageEl.className = 'message error';
                    messageEl.style.display = 'block';
                }}
            }} catch (e) {{
                messageEl.textContent = 'Error: ' + e.message;
                messageEl.className = 'message error';
                messageEl.style.display = 'block';
            }}
        }}

        function reloadPrompt() {{
            location.reload();
        }}
    </script>
    """
    return HTMLResponse(get_base_html("prompt", content))


@app.get("/devices", response_class=HTMLResponse)
async def devices_page(username: str = Depends(verify_credentials)):
    """Device exposure management page."""
    content = """
    <div class="card">
        <h2>Device Exposure</h2>
        <div id="message" class="message"></div>
        <p style="color: #666; font-size: 13px; margin-bottom: 15px;">
            Select which Home Assistant devices Sage can control. Only checked devices will be included in the system prompt.
        </p>
        <div class="toolbar">
            <input type="text" class="search-box" id="search" placeholder="Search devices..." oninput="filterDevices()">
            <div class="spacer"></div>
            <button class="btn btn-secondary" onclick="selectAll()">Select All</button>
            <button class="btn btn-secondary" onclick="selectNone()">Select None</button>
            <button class="btn" onclick="saveDevices(false)">Save Selection</button>
            <button class="btn" onclick="saveDevices(true)" style="background: #1976d2;">Save & Restart Agent</button>
        </div>
        <div id="device-list">
            <div class="loading">Loading devices from Home Assistant...</div>
        </div>
    </div>
    <script>
        let allDevices = [];
        let exposedDevices = [];
        let deviceDescriptions = {};

        async function loadDevices() {
            try {
                const response = await fetch('/api/devices');
                const data = await response.json();
                allDevices = data.devices || [];
                exposedDevices = data.exposed || [];
                deviceDescriptions = data.descriptions || {};
                renderDevices();
            } catch (e) {
                document.getElementById('device-list').innerHTML =
                    '<div class="message error" style="display:block;">Failed to load devices: ' + e.message + '</div>';
            }
        }

        function renderDevices() {
            const container = document.getElementById('device-list');
            const searchTerm = document.getElementById('search').value.toLowerCase();

            // Group by domain
            const groups = {};
            const domainLabels = {
                'light': 'Lights', 'switch': 'Switches', 'automation': 'Automations',
                'button': 'Buttons', 'scene': 'Scenes', 'script': 'Scripts',
                'lock': 'Locks', 'cover': 'Covers', 'fan': 'Fans',
                'climate': 'Climate', 'media_player': 'Media Players',
                'input_boolean': 'Input Booleans', 'sensor': 'Sensors',
                'binary_sensor': 'Binary Sensors'
            };

            allDevices.forEach(device => {
                const domain = device.entity_id.split('.')[0];
                if (!groups[domain]) groups[domain] = [];

                // Filter by search
                const matchesSearch = !searchTerm ||
                    device.entity_id.toLowerCase().includes(searchTerm) ||
                    (device.friendly_name && device.friendly_name.toLowerCase().includes(searchTerm));

                if (matchesSearch) {
                    groups[domain].push(device);
                }
            });

            // Sort domains
            const sortedDomains = Object.keys(groups).sort((a, b) => {
                const order = ['automation', 'light', 'switch', 'button', 'scene', 'script', 'lock', 'cover', 'fan', 'climate', 'media_player'];
                const aIdx = order.indexOf(a);
                const bIdx = order.indexOf(b);
                if (aIdx === -1 && bIdx === -1) return a.localeCompare(b);
                if (aIdx === -1) return 1;
                if (bIdx === -1) return -1;
                return aIdx - bIdx;
            });

            let html = '';
            sortedDomains.forEach(domain => {
                const devices = groups[domain];
                if (devices.length === 0) return;

                const label = domainLabels[domain] || domain.charAt(0).toUpperCase() + domain.slice(1);
                const checkedCount = devices.filter(d => exposedDevices.includes(d.entity_id)).length;

                html += `<div class="device-group">
                    <h3>${label} <span class="count">${checkedCount}/${devices.length} exposed</span></h3>
                    <div class="device-list">`;

                devices.forEach(device => {
                    const checked = exposedDevices.includes(device.entity_id) ? 'checked' : '';
                    const isExposed = exposedDevices.includes(device.entity_id);
                    const name = device.friendly_name || device.entity_id;
                    const desc = deviceDescriptions[device.entity_id] || '';
                    html += `<div class="device-item" style="flex-wrap: wrap;">
                        <input type="checkbox" id="${device.entity_id}" ${checked} onchange="toggleDevice('${device.entity_id}')">
                        <label for="${device.entity_id}">
                            ${name}<br>
                            <span class="entity-id">${device.entity_id}</span>
                        </label>
                        <span class="state">${device.state}</span>
                        ${isExposed ? `<input type="text" class="desc-input" placeholder="Description (e.g. what this device does)..." value="${desc.replace(/"/g, '&quot;')}" onchange="updateDescription('${device.entity_id}', this.value)" style="width: 100%; margin-top: 6px; padding: 5px 8px; font-size: 12px; border: 1px solid #ddd; border-radius: 3px; color: #555;">` : ''}
                    </div>`;
                });

                html += '</div></div>';
            });

            container.innerHTML = html || '<p>No devices found matching your search.</p>';
        }

        function toggleDevice(entityId) {
            const idx = exposedDevices.indexOf(entityId);
            if (idx === -1) {
                exposedDevices.push(entityId);
            } else {
                exposedDevices.splice(idx, 1);
            }
            renderDevices();
        }

        function selectAll() {
            const searchTerm = document.getElementById('search').value.toLowerCase();
            allDevices.forEach(device => {
                const matchesSearch = !searchTerm ||
                    device.entity_id.toLowerCase().includes(searchTerm) ||
                    (device.friendly_name && device.friendly_name.toLowerCase().includes(searchTerm));
                if (matchesSearch && !exposedDevices.includes(device.entity_id)) {
                    exposedDevices.push(device.entity_id);
                }
            });
            renderDevices();
        }

        function selectNone() {
            const searchTerm = document.getElementById('search').value.toLowerCase();
            allDevices.forEach(device => {
                const matchesSearch = !searchTerm ||
                    device.entity_id.toLowerCase().includes(searchTerm) ||
                    (device.friendly_name && device.friendly_name.toLowerCase().includes(searchTerm));
                if (matchesSearch) {
                    const idx = exposedDevices.indexOf(device.entity_id);
                    if (idx !== -1) exposedDevices.splice(idx, 1);
                }
            });
            renderDevices();
        }

        function filterDevices() {
            renderDevices();
        }

        function updateDescription(entityId, value) {
            deviceDescriptions[entityId] = value;
        }

        async function saveDevices(restart) {
            const messageEl = document.getElementById('message');
            try {
                const response = await fetch('/api/devices', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ devices: exposedDevices, descriptions: deviceDescriptions })
                });

                if (response.ok) {
                    if (restart) {
                        messageEl.textContent = 'Saved! Restarting sage-agent...';
                        messageEl.className = 'message';
                        messageEl.style.display = 'block';
                        messageEl.style.background = '#fff3e0';
                        messageEl.style.color = '#e65100';
                        messageEl.style.border = '1px solid #ffcc80';

                        const restartResp = await fetch('/api/service/sage-agent/restart', { method: 'POST' });
                        const restartData = await restartResp.json();

                        if (restartData.success) {
                            messageEl.textContent = 'Device selection saved and agent restarted successfully!';
                            messageEl.className = 'message success';
                            messageEl.style.background = '';
                            messageEl.style.border = '';
                        } else {
                            messageEl.textContent = 'Saved, but restart failed: ' + restartData.message;
                            messageEl.className = 'message error';
                            messageEl.style.background = '';
                            messageEl.style.border = '';
                        }
                    } else {
                        messageEl.textContent = 'Device selection saved! Restart sage-agent to apply changes.';
                        messageEl.className = 'message success';
                        messageEl.style.display = 'block';
                    }
                } else {
                    const data = await response.json();
                    messageEl.textContent = 'Error: ' + (data.detail || 'Failed to save');
                    messageEl.className = 'message error';
                    messageEl.style.display = 'block';
                }
            } catch (e) {
                messageEl.textContent = 'Error: ' + e.message;
                messageEl.className = 'message error';
                messageEl.style.display = 'block';
            }
        }

        // Load on page load
        loadDevices();
    </script>
    """
    return HTMLResponse(get_base_html("devices", content))


@app.post("/api/prompt")
async def save_prompt(data: SystemPromptUpdate, username: str = Depends(verify_credentials)):
    """Save the system prompt."""
    try:
        PROMPT_FILE.write_text(data.content)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/prompt")
async def get_prompt(username: str = Depends(verify_credentials)):
    """Get the current system prompt."""
    if PROMPT_FILE.exists():
        return {"content": PROMPT_FILE.read_text()}
    return {"content": ""}


@app.get("/api/devices")
async def get_devices(username: str = Depends(verify_credentials)):
    """Fetch all devices from Home Assistant and return with exposure status."""
    if not HA_TOKEN:
        raise HTTPException(status_code=500, detail="HOME_ASSISTANT_TOKEN not configured")

    devices = []
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {HA_TOKEN}"}
            async with session.get(f"{HA_URL}/api/states", headers=headers) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=resp.status, detail="Failed to fetch from Home Assistant")
                states = await resp.json()

                for entity in states:
                    entity_id = entity.get("entity_id", "")
                    domain = entity_id.split(".")[0] if "." in entity_id else ""

                    # Only include controllable domains
                    if domain in DOMAIN_LABELS:
                        devices.append({
                            "entity_id": entity_id,
                            "friendly_name": entity.get("attributes", {}).get("friendly_name", ""),
                            "state": entity.get("state", "unknown"),
                            "domain": domain
                        })
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to Home Assistant: {str(e)}")

    # Sort by domain then name
    devices.sort(key=lambda d: (d["domain"], d["friendly_name"] or d["entity_id"]))

    return {
        "devices": devices,
        "exposed": load_exposed_devices(),
        "descriptions": load_device_descriptions()
    }


@app.post("/api/devices")
async def save_devices(data: ExposedDevicesUpdate, username: str = Depends(verify_credentials)):
    """Save the exposed devices list and descriptions."""
    try:
        save_exposed_devices(data.devices)
        if data.descriptions:
            # Only save descriptions for devices that are exposed
            filtered = {k: v for k, v in data.descriptions.items() if k in data.devices and v.strip()}
            save_device_descriptions(filtered)
        return {"status": "ok", "count": len(data.devices)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/service/{service_name}/status")
async def service_status(service_name: str, username: str = Depends(verify_credentials)):
    """Get status of a service."""
    if service_name not in ["sage-agent", "sage-admin"]:
        raise HTTPException(status_code=400, detail="Invalid service name")
    return await get_service_status(service_name)


@app.post("/api/service/{service_name}/restart")
async def service_restart(service_name: str, username: str = Depends(verify_credentials)):
    """Restart a service."""
    if service_name not in ["sage-agent", "sage-admin"]:
        raise HTTPException(status_code=400, detail="Invalid service name")
    return await restart_service(service_name)


@app.get("/api/git/info")
async def git_info_endpoint(username: str = Depends(verify_credentials)):
    """Get current git info."""
    return await get_git_info()


@app.post("/api/git/pull")
async def git_pull_endpoint(username: str = Depends(verify_credentials)):
    """Pull latest changes from git."""
    return await git_pull()


@app.get("/health")
async def health():
    """Health check endpoint (no auth required)."""
    return {"status": "ok", "version": "4.6"}
