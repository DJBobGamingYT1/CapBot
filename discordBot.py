import os
import re
import time
import subprocess
import shutil
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import main  # your AI file (ai_online.py renamed to main.py, or whatever you import as `main`)
import discordTools

import logging

# Voice goes to the Discord voice channel, not out of the PC speakers
main.PLAY_LOCALLY = True

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print(f"discord.py {discord.__version__}")
    for mod in ("nacl", "davey"):
        try:
            __import__(mod)
            print(f"{mod}: installed")
        except ImportError:
            print(f"{mod}: MISSING  (pip install -U discord.py[voice] davey)")

    main.tools.extend([
        discordTools.add_reaction_to_message, discordTools.change_bot_status, discordTools.create_text_channel, discordTools.delete_discord_message,
        discordTools.get_recent_discord_messages, discordTools.list_server_channels, discordTools.list_server_members, discordTools.reply_to_discord_message,
        discordTools.send_discord_message, discordTools.set_default_channel, discordTools.set_member_nickname, discordTools.timeout_member
    ]) # inject discord tools (DiscordTools.py) into the bot
    main.updateTools()


@bot.command(name="beep")
async def beep(ctx):
    """Plays a 2s test tone that does NOT use main.py/output.mp3. If you can't hear this, the problem is Discord/voice-side, not the TTS file."""
    vc = ctx.guild.voice_client if ctx.guild else None
    if not vc or not vc.is_connected():
        await ctx.send("join a vc first (ping me with 'join vc')")
        return
    if vc.is_playing():
        vc.stop()
    vc.play(
        discord.FFmpegPCMAudio(
            "sine=frequency=440:duration=2",
            before_options="-f lavfi",
            options="-af volume=2",
        ),
        after=lambda e: print(f"beep done, error={e}"),
    )
    await ctx.send("beep (440 Hz tone for 2s)")


def ask_ai_blocking(user: str, message: str, uploads) -> str:
    """Runs in a worker thread so the bot doesn't freeze (and Discord doesn't drop the connection) while the AI thinks."""
    result = {"text": ""}

    def on_responded(response):
        result["text"] = getattr(response, "text", response) or ""

    main.talk_to_ai(
        f"user: \"{user}\" sent this from discord: \"{message}\", answer this message and reply to them",
        on_responded,
        uploads
    )
    return str(result["text"]).strip()

async def upload_attachments_to_ai(message, save_dir: str = "DiscordUploadsTemp"):
	os.makedirs(save_dir, exist_ok=True)
	results = []

	for attachment in message.attachments:
		safe_name = os.path.basename(attachment.filename)
		file_path = os.path.join(save_dir, safe_name)
		await attachment.save(file_path)

		results.append(file_path)

	return results

async def botTalkToAI(user, message, channel, guild, discordMessageObject):
    started = time.time()
    user_uploads = await upload_attachments_to_ai(discordMessageObject)
    text = await asyncio.to_thread(ask_ai_blocking, user, message, user_uploads)

    if not text:
        text = "my brain returned nothing, check the bot console"

    # Discord messages max out at 2000 characters
    for i in range(0, len(text), 1900):
        await channel.send(text[i:i + 1900])

    # Speak ONCE per answer, and look up the voice client NOW (it may have just been created by "join vc")
    # Play in EVERY voice channel the bot is currently connected to (all servers)
    voice_clients = [v for v in bot.voice_clients if v.is_connected()]
    if voice_clients:
        # TTS may still be written AFTER the text callback fires, so wait for a fresh, finished file
        ok = await wait_for_fresh_file("output.mp3", started)
        if not ok:
            print("TTS: output.mp3 never got (re)written after this request. Check where main.py saves its audio.")
            return
        await asyncio.gather(*(play_tts_file(v, "output.mp3") for v in voice_clients))

        audio_file = discord.File("output.mp3", filename="output.mp3")
        await channel.send(
            file=audio_file,
        )


async def join_vc(message):
    if not message.guild:
        return
    if not message.author.voice or not message.author.voice.channel:
        await message.channel.send("join a voice channel first bro")
        return

    channel = message.author.voice.channel
    vc = message.guild.voice_client

    if vc and vc.is_connected():
        await vc.move_to(channel)
    else:
        await channel.connect()


async def leave_vc(message):
    if not message.guild:
        return

    vc = message.guild.voice_client
    if vc and vc.is_connected():
        await vc.disconnect()


async def wait_for_fresh_file(path: str, since: float, timeout: float = 25.0) -> bool:
    """True once `path` was modified after `since` and its size has stopped changing."""
    deadline = time.monotonic() + timeout
    last_size = -1
    while time.monotonic() < deadline:
        if os.path.exists(path) and os.path.getmtime(path) >= since:
            size = os.path.getsize(path)
            if size > 0 and size == last_size:
                return True
            last_size = size
        await asyncio.sleep(0.4)
    return False


def mean_volume_db(path: str):
    """Debug helper: returns mean volume in dB (about -91 means the file is pure silence)."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
        m = re.search(r"mean_volume:\s*(-?[\d.]+|-inf) dB", r.stderr)
        return m.group(1) if m else None
    except Exception as e:
        return f"error: {e}"


async def play_tts_file(vc: discord.VoiceClient, file_path: str):
    if not vc or not vc.is_connected() or not os.path.exists(file_path):
        return

    if vc.is_playing():
        vc.stop()

    copy_path = f"tts_{time.time_ns()}.mp3"
    shutil.copyfile(file_path, copy_path)

    def cleanup(error):
        if error:
            print(f"Voice playback error: {error}")
        try:
            os.remove(copy_path)
        except OSError:
            pass

    source = discord.FFmpegPCMAudio(
        copy_path
    )

    vc.play(source)

    while vc.is_playing():
        await asyncio.sleep(0.1)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if bot.user and bot.user in message.mentions:
        prompt: str = (
            message.content.replace(f"<@!{bot.user.id}>", "")
            .replace(f"<@{bot.user.id}>", "")
            .strip()
        )

        if not prompt:
            await message.channel.send("u pinged me and said nothing bro")
            await bot.process_commands(message)
            return

        try:
            if "join vc" in prompt.lower():
                await join_vc(message)

            if "leave vc" in prompt.lower():
                await leave_vc(message)
            
        except Exception as e:
            print(f"Voice channel error: {e}")
            await message.channel.send(f"couldn't do the vc thing: {str(e)[:200]}")

        async with message.channel.typing():
            await botTalkToAI(message.author.name, prompt, message.channel, message.guild, message)

    await bot.process_commands(message)

@bot.command(name="diag")
async def diag(ctx):
    vc = ctx.guild.voice_client if ctx.guild else None
    lines = [
        f"discord.py {discord.__version__}",
        f"opus loaded: {discord.opus.is_loaded()}",
        f"connected: {bool(vc and vc.is_connected())}",
        f"mode: {getattr(vc, 'mode', None)}",
        f"endpoint: {getattr(vc, 'endpoint', None)}",
        f"latency: {getattr(vc, 'latency', None)}",
    ]
    for mod in ("nacl", "davey"):
        try:
            m = __import__(mod)
            lines.append(f"{mod}: {getattr(m, '__version__', 'installed')}")
        except ImportError:
            lines.append(f"{mod}: MISSING")
    print("\n".join(lines))
    await ctx.send("```\n" + "\n".join(lines) + "\n```")


bot.run(os.environ["DISCORD_BOT_TOKEN"])
main.save_chat_history()