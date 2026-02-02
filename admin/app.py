"""
Sage Admin Panel
FastAPI web interface for managing Sage voice assistant
"""

import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
import secrets

app = FastAPI(title="Sage Admin Panel")
security = HTTPBasic()

ADMIN_USER = os.environ.get("SAGE_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("SAGE_ADMIN_PASS", "changeme")


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_user = secrets.compare_digest(credentials.username, ADMIN_USER)
    correct_pass = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (correct_user and correct_pass):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return credentials.username


@app.get("/", response_class=HTMLResponse)
async def root(username: str = Depends(verify_credentials)):
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sage Admin Panel</title>
        <style>
            body { font-family: system-ui; max-width: 800px; margin: 50px auto; padding: 20px; }
            h1 { color: #333; }
            .status { padding: 10px; background: #e8f5e9; border-radius: 5px; }
        </style>
    </head>
    <body>
        <h1>🌿 Sage Admin Panel</h1>
        <div class="status">
            <p><strong>Status:</strong> Running</p>
            <p><strong>Version:</strong> 4.2</p>
        </div>
        <h2>Quick Links</h2>
        <ul>
            <li><a href="/health">Health Check</a></li>
        </ul>
        <h2>TODO</h2>
        <ul>
            <li>Device exposure management</li>
            <li>System prompt editor</li>
            <li>Log viewer</li>
        </ul>
    </body>
    </html>
    """


@app.get("/health")
async def health():
    return {"status": "ok", "version": "4.2"}
