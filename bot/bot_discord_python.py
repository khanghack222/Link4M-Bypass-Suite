#!/usr/bin/env python3
"""Modern, High-Performance Discord Bot for Link4M Bypass Suite.
Interfaces with engine-rs HTTP daemon, manages caching, and provides live status.
"""
import os
import re
import time
import asyncio
from typing import Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    import discord
    from discord import app_commands
    from discord.ext import commands
except ImportError:
    discord = None
    app_commands = None
    commands = None

from cache import LinkCache

DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN") or os.environ.get("DISCORD_TOKEN", "")
ENGINE_API_URL = os.environ.get("L4M_ENGINE_URL", "http://127.0.0.1:8080").rstrip("/")
LINK4M_REGEX = re.compile(r"https?://(?:www\.)?link4m\.(?:net|app|co|xyz|com|org)/go/([a-zA-Z0-9_-]+)")

cache = LinkCache(db_path=os.path.join(os.path.dirname(__file__), "cache.db"))

if discord and commands:
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)
else:
    bot = None

def parse_bypass_response(result: dict) -> Tuple[bool, Optional[str], Optional[str]]:
    """Parse engine-rs bypass response.
    Returns: (is_success, destination_url, error_message)
    """
    if not isinstance(result, dict):
        return False, None, "Invalid response payload"
    status = result.get("status")
    dest = result.get("destination_url") or result.get("destination") or result.get("final_url")
    if (status in ("success", "ok")) and dest:
        return True, dest, None
    err = result.get("error") or f"Bypass failed with status: {status}"
    return False, None, err

def format_embed_error(err: any, max_len: int = 1000) -> str:
    """Format and truncate error strings safely for Discord embed limits (<= 1000 chars)."""
    text = str(err or "").strip()
    if not text:
        return "Unknown error"
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text

async def call_engine_bypass(alias: str, url: str) -> dict:
    """Call engine-rs HTTP daemon with timeout and error handling."""
    if not url or not str(url).strip():
        return {"status": "failed", "error": "URL cannot be empty"}
    if aiohttp is None:
        return {"status": "failed", "error": "aiohttp not installed"}
    api_endpoint = f"{ENGINE_API_URL}/api/v1/bypass"
    payload = {"url": url.strip(), "alias": alias.strip() if alias else "", "wait": True}
    timeout_sec = float(os.environ.get("L4M_BYPASS_TIMEOUT", "480"))
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("L4M_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(api_endpoint, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    try:
                        return await resp.json()
                    except Exception as json_err:
                        raw_body = await resp.text()
                        return {"status": "failed", "error": f"Invalid JSON response: {raw_body[:500]}"}
                error_body = await resp.text()
                return {"status": "failed", "error": f"HTTP {resp.status}: {error_body[:500]}"}
    except asyncio.TimeoutError:
        return {"status": "failed", "error": f"Request to engine daemon timed out after {timeout_sec:.0f}s"}
    except Exception as e:
        return {"status": "failed", "error": f"Connection error: {str(e)}"}

async def safe_edit_or_send(interaction, embed):
    """Safely edit response, falling back to channel.send if interaction token expired."""
    try:
        await interaction.edit_original_response(embed=embed)
    except Exception:
        try:
            if getattr(interaction, "channel", None):
                await interaction.channel.send(embed=embed)
        except Exception:
            pass

if bot:
    @bot.event
    async def on_ready():
        print(f"[*] Discord Bot logged in as {bot.user} (ID: {bot.user.id})")
        try:
            synced = await bot.tree.sync()
            print(f"[*] Synced {len(synced)} application (/) commands")
        except Exception as e:
            print(f"[!] Failed to sync slash commands: {e}")

    @bot.tree.command(name="bypass", description="Bypass a Link4M shortlink to get the target URL")
    @app_commands.describe(url="The Link4M URL to bypass (e.g. https://link4m.net/go/...)")
    async def slash_bypass(interaction: discord.Interaction, url: str):
        await interaction.response.defer(ephemeral=False)
        
        match = LINK4M_REGEX.search(url)
        if not match:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Link không hợp lệ",
                    description="Vui lòng cung cấp link dạng `https://link4m.net/go/<alias>`",
                    color=discord.Color.red()
                )
            )
            return

        alias = match.group(1)
        
        # Check cache first for sub-10ms response
        cached_dest = cache.get(alias)
        if cached_dest:
            embed = discord.Embed(
                title="⚡ Link Đã Được Giải (Cache)",
                description=f"**Link gốc**: `{url}`\n**Link đích**: [Nhấn để mở]({cached_dest})\n`{cached_dest}`",
                color=discord.Color.green()
            )
            embed.set_footer(text="Phản hồi tức thì từ Cache | Link4M Bypass Suite")
            await interaction.followup.send(embed=embed)
            return

        # Call engine
        embed_processing = discord.Embed(
            title="⏳ Đang giải link...",
            description=f"Đang bóc tách và giải captcha cho `{alias}`\nVui lòng chờ trong giây lát...",
            color=discord.Color.blue()
        )
        msg = await interaction.followup.send(embed=embed_processing)

        start_time = time.time()
        try:
            result = await call_engine_bypass(alias, url)
            elapsed = time.time() - start_time
            
            success, dest, err_msg = parse_bypass_response(result)
            if success and dest:
                cache.set(alias, dest)
                
                embed_success = discord.Embed(
                    title="✅ Vượt Link Thành Công!",
                    description=f"**Link gốc**: `{url}`\n**Link đích**: [Nhấn vào đây để tải]({dest})\n`{dest}`",
                    color=discord.Color.green()
                )
                embed_success.add_field(name="Thời gian xử lý", value=f"{elapsed:.2f}s", inline=True)
                embed_success.add_field(name="Mã Alias", value=alias, inline=True)
                embed_success.set_footer(text="Powered by Link4M Bypass Suite & AI Dual-Node")
                await safe_edit_or_send(interaction, embed_success)
            else:
                formatted_err = format_embed_error(err_msg, max_len=1000)
                embed_fail = discord.Embed(
                    title="❌ Vượt Link Thất Bại",
                    description=f"Không thể giải `{alias}`: {formatted_err}",
                    color=discord.Color.red()
                )
                await safe_edit_or_send(interaction, embed_fail)
        except Exception as e:
            formatted_e = format_embed_error(e, max_len=1000)
            embed_err = discord.Embed(
                title="⚠️ Lỗi kết nối Engine",
                description=f"Không thể kết nối tới daemon `engine-rs`: {formatted_e}",
                color=discord.Color.orange()
            )
            await safe_edit_or_send(interaction, embed_err)

if __name__ == "__main__":
    if bot is None:
        print("[!] aiohttp or discord.py not installed. Run: pip install discord.py aiohttp python-dotenv")
    elif not DISCORD_TOKEN:
        print("[!] DISCORD_BOT_TOKEN not configured. Please set the environment variable.")
    else:
        bot.run(DISCORD_TOKEN)
