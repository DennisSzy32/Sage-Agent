"""
Sage Voice Assistant Agent v4.3
Manual action parsing via tts_node interception
Actions are parsed and executed BEFORE text reaches TTS
- Multi-pattern regex for LLM output variations
- Startup validation for required config
"""

import os
import re
import logging
import asyncio
import aiohttp
from pathlib import Path
from typing import AsyncIterable
from dotenv import load_dotenv

from livekit.agents import (
    Agent, AgentSession, AutoSubscribe, JobContext, WorkerOptions, cli, room_io,
)
from livekit.plugins import silero, openai

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sage-agent")

HA_URL = os.environ.get("HOME_ASSISTANT_URL", "http://homeassistant.local:8123")
HA_TOKEN = os.environ.get("HOME_ASSISTANT_TOKEN", "")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com/v1")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
PROMPT_FILE = Path(__file__).parent / "system_prompt.txt"


def validate_config() -> bool:
    """Validate required configuration at startup. Returns True if valid."""
    errors = []
    warnings = []

    # Required: LiveKit credentials
    if not os.environ.get("LIVEKIT_URL"):
        errors.append("LIVEKIT_URL is not set")
    if not os.environ.get("LIVEKIT_API_KEY"):
        errors.append("LIVEKIT_API_KEY is not set")
    if not os.environ.get("LIVEKIT_API_SECRET"):
        errors.append("LIVEKIT_API_SECRET is not set")

    # Required: Ollama API key
    if not OLLAMA_API_KEY:
        errors.append("OLLAMA_API_KEY is not set")

    # Optional but recommended: Home Assistant
    if not HA_TOKEN:
        warnings.append("HOME_ASSISTANT_TOKEN is not set - smart home control will not work")

    # Log warnings
    for warning in warnings:
        logger.warning(f"CONFIG WARNING: {warning}")

    # Log errors and return result
    if errors:
        for error in errors:
            logger.error(f"CONFIG ERROR: {error}")
        return False

    logger.info("Configuration validated successfully")
    return True

ALLOWED_SERVICES = {
    "light": ["turn_on", "turn_off", "toggle"],
    "switch": ["turn_on", "turn_off", "toggle"],
    "automation": ["trigger"],
    "button": ["press"],
    "scene": ["turn_on"],
    "script": ["turn_on", "turn_off", "toggle"],
    "lock": ["lock", "unlock"],
    "cover": ["open_cover", "close_cover", "stop_cover", "toggle"],
    "fan": ["turn_on", "turn_off", "toggle", "set_percentage"],
    "climate": ["set_temperature", "set_hvac_mode", "turn_on", "turn_off"],
    "media_player": ["turn_on", "turn_off", "media_play", "media_pause", "media_stop", "volume_set", "volume_up", "volume_down"],
    "input_boolean": ["turn_on", "turn_off", "toggle"],
}

# Multiple patterns to catch LLM output variations
# Pattern 1: Intended format [ACTION: domain.service | entity_id=xxx]
PATTERN_ACTION = re.compile(
    r'\[ACTION:\s*([a-z_]+)\.([a-z_]+)\s*\|\s*entity_id=([a-z0-9_.]+)(?:\s*\|\s*([^\]]+))?\]',
    re.IGNORECASE
)

# Pattern 2: LLM variation [domain:service] entity_id=xxx
PATTERN_COLON = re.compile(
    r'\[([a-z_]+):([a-z_]+)\]\s*entity_id=([a-z0-9_.]+)',
    re.IGNORECASE
)

# Pattern 3: Without ACTION prefix [domain.service | entity_id=xxx]
PATTERN_SIMPLE = re.compile(
    r'\[([a-z_]+)\.([a-z_]+)\s*\|\s*entity_id=([a-z0-9_.]+)(?:\s*\|\s*([^\]]+))?\]',
    re.IGNORECASE
)

# Pattern 4: Catch-all for any bracketed command with entity_id nearby
PATTERN_CATCHALL = re.compile(
    r'\[([a-z_]+)[:\.]([a-z_]+)\][^\[]*?entity_id[=:\s]+([a-z0-9_.]+)',
    re.IGNORECASE
)

VALID_DOMAINS = {'light', 'switch', 'automation', 'button', 'scene', 'script',
                 'lock', 'cover', 'fan', 'climate', 'media_player', 'input_boolean'}

def load_system_prompt() -> str:
    if PROMPT_FILE.exists():
        prompt = PROMPT_FILE.read_text().strip()
        logger.info(f"Loaded system prompt ({len(prompt)} chars)")
        return prompt
    logger.warning(f"No prompt file at {PROMPT_FILE}, using default")
    return "You are Sage, a helpful AI assistant."

def parse_params(params_str: str) -> dict:
    """Parse pipe-separated parameters like 'brightness_pct=50 | color_name=red'."""
    data = {}
    if not params_str:
        return data
    for param in params_str.split("|"):
        param = param.strip()
        if "=" in param:
            key, value = param.split("=", 1)
            key, value = key.strip(), value.strip()
            if value.isdigit():
                value = int(value)
            elif value.replace(".", "", 1).isdigit():
                value = float(value)
            data[key] = value
    return data

def parse_actions(text: str) -> list:
    """Parse action tags from text using multiple patterns to catch LLM variations."""
    actions = []
    seen = set()  # Avoid duplicate actions

    # Pattern 1: [ACTION: domain.service | entity_id=xxx | params]
    for match in PATTERN_ACTION.finditer(text):
        domain, service, entity_id, params_str = match.groups()
        key = (domain.lower(), service.lower(), entity_id.lower())
        if key not in seen and domain.lower() in VALID_DOMAINS:
            seen.add(key)
            actions.append({
                "domain": domain.lower(),
                "service": service.lower(),
                "entity_id": entity_id,
                "data": parse_params(params_str)
            })
            logger.debug(f"Pattern ACTION matched: {domain}.{service} -> {entity_id}")

    # Pattern 2: [domain:service] entity_id=xxx
    for match in PATTERN_COLON.finditer(text):
        domain, service, entity_id = match.groups()
        key = (domain.lower(), service.lower(), entity_id.lower())
        if key not in seen and domain.lower() in VALID_DOMAINS:
            seen.add(key)
            actions.append({
                "domain": domain.lower(),
                "service": service.lower(),
                "entity_id": entity_id,
                "data": {}
            })
            logger.debug(f"Pattern COLON matched: {domain}.{service} -> {entity_id}")

    # Pattern 3: [domain.service | entity_id=xxx | params]
    for match in PATTERN_SIMPLE.finditer(text):
        domain, service, entity_id, params_str = match.groups()
        key = (domain.lower(), service.lower(), entity_id.lower())
        if key not in seen and domain.lower() in VALID_DOMAINS:
            seen.add(key)
            actions.append({
                "domain": domain.lower(),
                "service": service.lower(),
                "entity_id": entity_id,
                "data": parse_params(params_str)
            })
            logger.debug(f"Pattern SIMPLE matched: {domain}.{service} -> {entity_id}")

    # Pattern 4: Catch-all for malformed tags
    for match in PATTERN_CATCHALL.finditer(text):
        domain, service, entity_id = match.groups()
        key = (domain.lower(), service.lower(), entity_id.lower())
        if key not in seen and domain.lower() in VALID_DOMAINS:
            seen.add(key)
            actions.append({
                "domain": domain.lower(),
                "service": service.lower(),
                "entity_id": entity_id,
                "data": {}
            })
            logger.debug(f"Pattern CATCHALL matched: {domain}.{service} -> {entity_id}")

    return actions

def clean_for_tts(text: str) -> str:
    """Remove all action tag variations and technical artifacts from text before TTS."""
    cleaned = text

    # Remove Pattern 1: [ACTION: domain.service | entity_id=xxx | params]
    cleaned = PATTERN_ACTION.sub("", cleaned)

    # Remove Pattern 2: [domain:service] entity_id=xxx (both parts)
    cleaned = re.sub(r'\[([a-z_]+):([a-z_]+)\]\s*entity_id=[a-z0-9_.]+', '', cleaned, flags=re.IGNORECASE)

    # Remove Pattern 3: [domain.service | entity_id=xxx | params]
    cleaned = PATTERN_SIMPLE.sub("", cleaned)

    # Remove any remaining bracketed domain commands
    cleaned = re.sub(r'\[([a-z_]+)[:\.]([a-z_]+)\]', '', cleaned, flags=re.IGNORECASE)

    # Remove standalone entity_id references
    cleaned = re.sub(r'\bentity_id\s*[=:]\s*[a-z0-9_.]+', '', cleaned, flags=re.IGNORECASE)

    # Remove <tools> blocks
    cleaned = re.sub(r'<tools>.*?</tools>', '', cleaned, flags=re.DOTALL)

    # Remove bare domain.entity_id references (like "scene.tv" or "automation.watch_tv_lighting")
    cleaned = re.sub(r'\b(light|switch|automation|button|scene|script|lock|cover|fan|climate|media_player|input_boolean)\.[a-z0-9_]+\b', '', cleaned, flags=re.IGNORECASE)

    # Clean up extra whitespace and punctuation artifacts
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = re.sub(r'\s+([.,!?])', r'\1', cleaned)  # Fix space before punctuation
    cleaned = re.sub(r'([.,!?])\s*\1+', r'\1', cleaned)  # Fix repeated punctuation
    cleaned = cleaned.strip()

    return cleaned

async def execute_action(action: dict) -> bool:
    domain = action["domain"]
    service = action["service"]
    entity_id = action["entity_id"]
    data = action.get("data", {})
    if domain not in ALLOWED_SERVICES:
        logger.warning(f"Domain not allowed: {domain}")
        return False
    if service not in ALLOWED_SERVICES[domain]:
        logger.warning(f"Service not allowed: {domain}.{service}")
        return False
    url = f"{HA_URL}/api/services/{domain}/{service}"
    headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
    payload = {"entity_id": entity_id}
    payload.update(data)
    logger.info(f"Executing: {domain}.{service} -> {entity_id} with {data}")
    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    logger.info(f"SUCCESS: {domain}.{service} -> {entity_id}")
                    return True
                else:
                    err = await resp.text()
                    logger.error(f"FAILED ({resp.status}): {err}")
                    return False
    except Exception as e:
        logger.error(f"ERROR executing action: {e}")
        return False

class SageAgent(Agent):
    def __init__(self):
        super().__init__(instructions=load_system_prompt())

    async def tts_node(self, text: AsyncIterable, model_settings):
        # Collect all text chunks from the LLM
        chunks = []
        async for chunk in text:
            chunks.append(str(chunk) if not isinstance(chunk, str) else chunk)
        full_text = "".join(chunks)
        logger.debug(f"TTS Node received: {full_text[:100]}...")
        
        # Parse and execute any actions found
        actions = parse_actions(full_text)
        if actions:
            logger.info(f"TTS Node: Found {len(actions)} action(s) to execute")
            for action in actions:
                logger.info(f"  -> {action['domain']}.{action['service']} | {action['entity_id']}")
                asyncio.create_task(execute_action(action))
        
        # Clean the text (remove action tags)
        cleaned_text = clean_for_tts(full_text)
        if not cleaned_text:
            logger.debug("TTS Node: No text to speak after cleaning")
            return
        logger.debug(f"TTS Node: Speaking: {cleaned_text[:50]}...")
        
        # Create async generator for cleaned text
        async def cleaned_generator():
            yield cleaned_text
        
        # Pass cleaned text to the default TTS node
        async for frame in Agent.default.tts_node(self, cleaned_generator(), model_settings):
            yield frame

async def entrypoint(ctx: JobContext):
    logger.info("Sage agent starting...")

    # Validate configuration before proceeding
    if not validate_config():
        logger.error("Configuration validation failed - check your .env file")
        return

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info(f"Connected to room: {ctx.room.name}")

    agent = SageAgent()

    ollama_llm = openai.LLM(
        model="deepseek-v3.2",
        base_url=OLLAMA_BASE_URL,
        api_key=OLLAMA_API_KEY,
    )
    
    session = AgentSession(
        vad=silero.VAD.load(),
        stt="deepgram/nova-3",
        llm=ollama_llm,
        tts="cartesia/sonic-2:6ccbfb76-1fc6-48f7-b71d-91ac6298247b",
    )
    
    await session.start(
        room=ctx.room,
        agent=agent,
        room_options=room_io.RoomOptions(
            text_input=True,
            text_output=True,
        ),
    )
    
    logger.info("Sage is ready!")
    
    await session.generate_reply(
        instructions="Greet the user briefly and ask how you can help them today."
    )

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
