"""
Sage Voice Assistant Agent v4.2
Manual action parsing via tts_node interception
Actions are parsed and executed BEFORE text reaches TTS
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
PROMPT_FILE = Path(__file__).parent / "system_prompt.txt"

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

# THIS REGEX IS TOO STRICT - only matches exact [ACTION: format
ACTION_PATTERN = re.compile(
    r'\[ACTION:\s*([a-z_]+\.[a-z_]+)\s*\|\s*entity_id=([a-z0-9_.]+)(?:\s*\|\s*([^\]]+))?\]',
    re.IGNORECASE
)

def load_system_prompt() -> str:
    if PROMPT_FILE.exists():
        prompt = PROMPT_FILE.read_text().strip()
        logger.info(f"Loaded system prompt ({len(prompt)} chars)")
        return prompt
    logger.warning(f"No prompt file at {PROMPT_FILE}, using default")
    return "You are Sage, a helpful AI assistant."

def parse_actions(text: str) -> list:
    actions = []
    for match in ACTION_PATTERN.finditer(text):
        service_full = match.group(1)
        entity_id = match.group(2)
        params_str = match.group(3)
        parts = service_full.split(".")
        if len(parts) != 2:
            logger.warning(f"Invalid service format: {service_full}")
            continue
        domain, service = parts
        data = {}
        if params_str:
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
        actions.append({"domain": domain, "service": service, "entity_id": entity_id, "data": data})
    return actions

def clean_for_tts(text: str) -> str:
    cleaned = ACTION_PATTERN.sub("", text)
    cleaned = re.sub(r'<tools>.*?</tools>', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'\b(light|switch|automation|button|scene|script|lock|cover|fan|climate|media_player|input_boolean)\.[a-z0-9_]+\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
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
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info(f"Connected to room: {ctx.room.name}")
    
    agent = SageAgent()
    
    ollama_llm = openai.LLM(
        model="deepseek-v3.2",
        base_url="https://ollama.com/v1",
        api_key=os.environ.get("OLLAMA_API_KEY"),
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
