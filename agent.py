"""
Sage Voice Assistant Agent v4.7
Manual action parsing via llm_node interception
Actions are parsed and executed BEFORE text reaches TTS
- Multi-pattern regex for LLM output variations
- Startup validation for required config
- Dynamic device loading from exposed_devices.json
- Fixed: Intercept at llm_node instead of tts_node to prevent parallel TTS path bypass
"""

import os
import re
import json
import logging
import asyncio
import aiohttp
from pathlib import Path
from typing import AsyncIterable
from dotenv import load_dotenv

from livekit.agents import (
    Agent, AgentSession, AutoSubscribe, JobContext, WorkerOptions, cli, room_io, llm,
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
EXPOSED_DEVICES_FILE = Path(__file__).parent / "exposed_devices.json"

# Domain labels for prompt generation
DOMAIN_LABELS = {
    "automation": "AUTOMATIONS",
    "light": "LIGHTS",
    "switch": "SWITCHES",
    "button": "BUTTONS",
    "scene": "SCENES",
    "script": "SCRIPTS",
    "lock": "LOCKS",
    "cover": "COVERS",
    "fan": "FANS",
    "climate": "CLIMATE",
    "media_player": "MEDIA PLAYERS",
    "input_boolean": "INPUT BOOLEANS",
}


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


def load_exposed_devices() -> list:
    """Load list of exposed device entity_ids from config file."""
    if EXPOSED_DEVICES_FILE.exists():
        try:
            devices = json.loads(EXPOSED_DEVICES_FILE.read_text())
            logger.info(f"Loaded {len(devices)} exposed devices from config")
            return devices
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse exposed_devices.json: {e}")
            return []
    logger.info("No exposed_devices.json found, using empty device list")
    return []


async def fetch_device_details(entity_ids: list) -> dict:
    """Fetch device details from Home Assistant for the given entity_ids.

    Returns a dict mapping entity_id to {friendly_name, state, domain}.
    """
    if not HA_TOKEN or not entity_ids:
        return {}

    details = {}
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {HA_TOKEN}"}
            async with session.get(f"{HA_URL}/api/states", headers=headers) as resp:
                if resp.status == 200:
                    states = await resp.json()
                    for entity in states:
                        entity_id = entity.get("entity_id", "")
                        if entity_id in entity_ids:
                            details[entity_id] = {
                                "friendly_name": entity.get("attributes", {}).get("friendly_name", entity_id),
                                "state": entity.get("state", "unknown"),
                                "domain": entity_id.split(".")[0] if "." in entity_id else ""
                            }
                    logger.info(f"Fetched details for {len(details)}/{len(entity_ids)} devices from HA")
                else:
                    logger.error(f"Failed to fetch from HA: status {resp.status}")
    except Exception as e:
        logger.error(f"Error fetching device details from HA: {e}")

    return details


def build_device_list_section(device_details: dict) -> str:
    """Build the '### Available Devices' section content from device details."""
    if not device_details:
        return "### Available Devices\nNo devices configured. Use the Admin Panel to expose devices."

    # Group devices by domain
    by_domain = {}
    for entity_id, info in device_details.items():
        domain = info["domain"]
        if domain not in by_domain:
            by_domain[domain] = []
        by_domain[domain].append((entity_id, info["friendly_name"]))

    # Build section content
    lines = ["### Available Devices"]

    # Sort domains by priority (automations first, then lights, etc.)
    domain_order = ["automation", "light", "switch", "button", "scene", "script",
                    "lock", "cover", "fan", "climate", "media_player", "input_boolean"]
    sorted_domains = sorted(by_domain.keys(),
                           key=lambda d: domain_order.index(d) if d in domain_order else 999)

    for domain in sorted_domains:
        devices = by_domain[domain]
        label = DOMAIN_LABELS.get(domain, domain.upper())
        lines.append(f"{label}:")
        for entity_id, friendly_name in sorted(devices, key=lambda x: x[1]):
            lines.append(f"- {friendly_name}: {entity_id}")
        lines.append("")  # Blank line between groups

    return "\n".join(lines).strip()


def load_system_prompt(device_section: str = None) -> str:
    """Load system prompt and optionally inject dynamic device list."""
    if not PROMPT_FILE.exists():
        logger.warning(f"No prompt file at {PROMPT_FILE}, using default")
        return "You are Sage, a helpful AI assistant."

    prompt = PROMPT_FILE.read_text().strip()

    # If we have a device section, replace the existing one
    if device_section:
        # Pattern to match the entire "### Available Devices" section until next "###" or "## " or end
        pattern = r'### Available Devices.*?(?=###|## |\Z)'
        if re.search(pattern, prompt, re.DOTALL):
            prompt = re.sub(pattern, device_section + "\n\n", prompt, flags=re.DOTALL)
            logger.info("Injected dynamic device list into system prompt")
        else:
            # No existing section, append before "### Rules" if it exists
            rules_pattern = r'(### Rules)'
            if re.search(rules_pattern, prompt):
                prompt = re.sub(rules_pattern, device_section + "\n\n\\1", prompt)
                logger.info("Added device list section before Rules")
            else:
                # Just append at end
                prompt = prompt + "\n\n" + device_section
                logger.info("Appended device list section to prompt")

    logger.info(f"Loaded system prompt ({len(prompt)} chars)")
    return prompt


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
    "shopping_list": ["add_item", "remove_item", "complete_item"],
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

# Pattern 5: Generic ACTION without entity_id (e.g. shopping_list)
# Matches [ACTION: domain.service | key=value | key=value]
PATTERN_ACTION_GENERIC = re.compile(
    r'\[ACTION:\s*([a-z_]+)\.([a-z_]+)\s*\|\s*([^\]]+)\]',
    re.IGNORECASE
)

VALID_DOMAINS = {'light', 'switch', 'automation', 'button', 'scene', 'script',
                 'lock', 'cover', 'fan', 'climate', 'media_player', 'input_boolean',
                 'shopping_list'}


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

    # Pattern 5: Generic ACTION (for services without entity_id, e.g. shopping_list)
    for match in PATTERN_ACTION_GENERIC.finditer(text):
        domain, service, params_str = match.groups()
        params = parse_params(params_str)
        # Skip if this was already matched by Pattern 1 (which also matches this format)
        entity_id = params.pop("entity_id", None)
        if entity_id:
            key = (domain.lower(), service.lower(), entity_id.lower())
        else:
            # Use a key based on all params for dedup (e.g. shopping_list items)
            key = (domain.lower(), service.lower(), str(sorted(params.items())))
        if key not in seen and domain.lower() in VALID_DOMAINS:
            seen.add(key)
            action = {
                "domain": domain.lower(),
                "service": service.lower(),
                "entity_id": entity_id,
                "data": params
            }
            actions.append(action)
            logger.debug(f"Pattern GENERIC matched: {domain}.{service} with params {params}")

    return actions

def clean_for_tts(text: str) -> str:
    """Remove all action tag variations and technical artifacts from text before TTS."""
    cleaned = text

    # Remove Pattern 1: [ACTION: domain.service | entity_id=xxx | params]
    cleaned = PATTERN_ACTION.sub("", cleaned)

    # Remove Pattern 5: [ACTION: domain.service | key=value] (generic, e.g. shopping_list)
    cleaned = PATTERN_ACTION_GENERIC.sub("", cleaned)

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
    cleaned = re.sub(r'\b(light|switch|automation|button|scene|script|lock|cover|fan|climate|media_player|input_boolean|shopping_list)\.[a-z0-9_]+\b', '', cleaned, flags=re.IGNORECASE)

    # Clean up extra whitespace and punctuation artifacts
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = re.sub(r'\s+([.,!?])', r'\1', cleaned)  # Fix space before punctuation
    cleaned = re.sub(r'([.,!?])\s*\1+', r'\1', cleaned)  # Fix repeated punctuation
    cleaned = cleaned.strip()

    return cleaned

async def execute_action(action: dict) -> bool:
    domain = action["domain"]
    service = action["service"]
    entity_id = action.get("entity_id")
    data = action.get("data", {})
    if domain not in ALLOWED_SERVICES:
        logger.warning(f"Domain not allowed: {domain}")
        return False
    if service not in ALLOWED_SERVICES[domain]:
        logger.warning(f"Service not allowed: {domain}.{service}")
        return False
    url = f"{HA_URL}/api/services/{domain}/{service}"
    headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
    payload = {}
    if entity_id:
        payload["entity_id"] = entity_id
    payload.update(data)
    logger.info(f"Executing: {domain}.{service} -> {entity_id or 'no entity'} with {data}")
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
    def __init__(self, instructions: str):
        super().__init__(instructions=instructions)

    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list,
        model_settings,
    ):
        """
        Override llm_node to intercept LLM output, parse action tags,
        execute Home Assistant commands, and clean text before TTS.

        This is the correct interception point because it modifies the text
        stream BEFORE it reaches the TTS pipeline, avoiding race conditions
        with parallel audio synthesis.
        """
        # Get the default LLM response stream
        llm_stream = Agent.default.llm_node(self, chat_ctx, tools, model_settings)

        # Handle if llm_stream is a coroutine (needs await)
        if asyncio.iscoroutine(llm_stream):
            llm_stream = await llm_stream

        # Buffer to accumulate text for action parsing
        text_buffer = []

        async for chunk in llm_stream:
            # Handle string chunks directly
            if isinstance(chunk, str):
                text_buffer.append(chunk)
                # We'll process and yield cleaned text at the end
                continue

            # Handle ChatChunk objects (structured LLM responses)
            if hasattr(chunk, 'delta') and hasattr(chunk.delta, 'content'):
                content = chunk.delta.content
                if content:
                    text_buffer.append(content)
                    # Continue buffering - we process at the end
                    continue

            # For any other chunk types, yield as-is
            yield chunk

        # Now we have the complete text - parse and clean it
        full_text = "".join(text_buffer)

        if full_text:
            logger.info(f"LLM Node INPUT: {full_text[:200]}...")

            # Parse and execute any actions found
            actions = parse_actions(full_text)
            if actions:
                logger.info(f"LLM Node: Found {len(actions)} action(s) to execute")
                for action in actions:
                    logger.info(f"  -> {action['domain']}.{action['service']} | {action['entity_id']}")
                    asyncio.create_task(execute_action(action))

            # Clean the text (remove action tags)
            cleaned_text = clean_for_tts(full_text)
            logger.info(f"LLM Node CLEANED: {cleaned_text[:200]}...")

            if cleaned_text:
                # Yield the cleaned text as a single string
                yield cleaned_text

async def entrypoint(ctx: JobContext):
    logger.info("Sage agent starting...")

    # Validate configuration before proceeding
    if not validate_config():
        logger.error("Configuration validation failed - check your .env file")
        return

    # Load exposed devices and fetch their details from HA
    exposed_ids = load_exposed_devices()
    device_details = await fetch_device_details(exposed_ids)
    device_section = build_device_list_section(device_details)

    # Load system prompt with dynamic device list
    system_prompt = load_system_prompt(device_section)

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info(f"Connected to room: {ctx.room.name}")

    agent = SageAgent(instructions=system_prompt)

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
