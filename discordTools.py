import asyncio
import discord


_client = None
_loop = None
_default_channel_id = None


def bind_discord_client(client, loop=None, default_channel_id=None):
	"""Call this in your Discord bot's on_ready() so sync tools can run Discord actions."""
	global _client, _loop, _default_channel_id
	_client = client
	_loop = loop or getattr(client, "loop", None) or asyncio.get_running_loop()
	if default_channel_id is not None:
		_default_channel_id = int(default_channel_id)


def set_default_channel(channel_id: int):
	"""Update the active channel ID whenever a message comes in so tools know where to act."""
	global _default_channel_id
	_default_channel_id = int(channel_id)


def _run_coro(coro, timeout: float = 15.0):
	if _client is None or _loop is None:
		raise RuntimeError("Discord client is not bound yet. Call bind_discord_client(bot) in on_ready().")
	future = asyncio.run_coroutine_threadsafe(coro, _loop)
	return future.result(timeout=timeout)


def _resolve_channel(channel_id: int = 0):
	target_id = int(channel_id) if channel_id else _default_channel_id
	if not target_id:
		return None
	channel = _client.get_channel(target_id)
	return channel


async def _fetch_channel(channel_id: int = 0):
	channel = _resolve_channel(channel_id)
	if channel is not None:
		return channel
	target_id = int(channel_id) if channel_id else _default_channel_id
	if not target_id:
		return None
	return await _client.fetch_channel(target_id)


def send_discord_message(text: str, channel_id: int = 0) -> str:
	"""
	Send a text message to a Discord channel. If channel_id is 0, sends to the current active channel.

	Args:
		text: The message content to send.
		channel_id: Optional target channel ID (defaults to current channel).
	"""
	if not text or not text.strip():
		return "Cannot send an empty message."

	async def _task():
		channel = await _fetch_channel(channel_id)
		if channel is None:
			return "Error: Could not find target Discord channel."
		msg = await channel.send(text[:2000])
		return f"Sent message (ID: {msg.id}) to #{getattr(channel, 'name', channel.id)}."

	try:
		return _run_coro(_task())
	except Exception as e:
		return f"Failed to send message: {e}"


def reply_to_discord_message(message_id: int, text: str, channel_id: int = 0) -> str:
	"""
	Reply directly to a specific message by its ID in a Discord channel.

	Args:
		message_id: The ID of the Discord message to reply to.
		text: The reply content.
		channel_id: Optional channel ID (defaults to current channel).
	"""
	async def _task():
		channel = await _fetch_channel(channel_id)
		if channel is None:
			return "Error: Could not find target Discord channel."
		target_msg = await channel.fetch_message(int(message_id))
		sent = await target_msg.reply(text[:2000], mention_author=False)
		return f"Replied (ID: {sent.id}) to message {message_id}."

	try:
		return _run_coro(_task())
	except Exception as e:
		return f"Failed to reply: {e}"


def add_reaction_to_message(message_id: int, emoji: str, channel_id: int = 0) -> str:
	"""
	React to a Discord message with a Unicode emoji (like '🔥' or '💀') or custom emoji string.

	Args:
		message_id: The ID of the message to react to.
		emoji: The emoji to add.
		channel_id: Optional channel ID (defaults to current channel).
	"""
	async def _task():
		channel = await _fetch_channel(channel_id)
		if channel is None:
			return "Error: Could not find target Discord channel."
		target_msg = await channel.fetch_message(int(message_id))
		await target_msg.add_reaction(emoji.strip())
		return f"Added reaction {emoji} to message {message_id}."

	try:
		return _run_coro(_task())
	except Exception as e:
		return f"Failed to add reaction: {e}"


def get_recent_discord_messages(limit: int = 10, channel_id: int = 0) -> str:
	"""
	Read the most recent messages in a Discord channel so you can see context or get message IDs.

	Args:
		limit: How many recent messages to fetch (clamped between 1 and 25).
		channel_id: Optional channel ID (defaults to current channel).
	"""
	clamped = max(1, min(int(limit), 25))

	async def _task():
		channel = await _fetch_channel(channel_id)
		if channel is None:
			return "Error: Could not find target Discord channel."
		lines = []
		async for m in channel.history(limit=clamped):
			content = m.content or "[attachment/embed]"
			lines.append(f"[{m.id}] {m.author.display_name} ({m.author.id}): {content}")
		lines.reverse()
		return "\n".join(lines) if lines else "No messages found."

	try:
		return _run_coro(_task())
	except Exception as e:
		return f"Failed to read messages: {e}"


def delete_discord_message(message_id: int, channel_id: int = 0) -> str:
	"""
	Delete a message by ID from a Discord channel (requires Manage Messages permission for others' messages).

	Args:
		message_id: The ID of the message to delete.
		channel_id: Optional channel ID (defaults to current channel).
	"""
	async def _task():
		channel = await _fetch_channel(channel_id)
		if channel is None:
			return "Error: Could not find target Discord channel."
		target_msg = await channel.fetch_message(int(message_id))
		await target_msg.delete()
		return f"Deleted message {message_id}."

	try:
		return _run_coro(_task())
	except Exception as e:
		return f"Failed to delete message: {e}"


def list_server_channels(guild_id: int = 0) -> str:
	"""
	List text and voice channels in the Discord server along with their channel IDs.

	Args:
		guild_id: Optional server ID (uses current channel's server if 0).
	"""
	async def _task():
		guild = _client.get_guild(int(guild_id)) if guild_id else None
		if guild is None:
			ch = _resolve_channel(0)
			guild = getattr(ch, "guild", None)
		if guild is None:
			return "Error: Could not determine Discord server."
		rows = [f"Server: {guild.name} (ID: {guild.id})"]
		for ch in guild.channels:
			rows.append(f"- #{ch.name} [{type(ch).__name__}] (ID: {ch.id})")
		return "\n".join(rows)

	try:
		return _run_coro(_task())
	except Exception as e:
		return f"Failed to list channels: {e}"


def list_server_members(limit: int = 25, guild_id: int = 0) -> str:
	"""
	List members in the Discord server with their usernames, display names, IDs, and roles.

	Args:
		limit: Max members to show (clamped between 1 and 50).
		guild_id: Optional server ID (uses current channel's server if 0).
	"""
	clamped = max(1, min(int(limit), 50))

	async def _task():
		guild = _client.get_guild(int(guild_id)) if guild_id else None
		if guild is None:
			ch = _resolve_channel(0)
			guild = getattr(ch, "guild", None)
		if guild is None:
			return "Error: Could not determine Discord server."
		rows = []
		for member in list(guild.members)[:clamped]:
			roles = [r.name for r in member.roles if r.name != "@everyone"]
			rows.append(f"- {member.display_name} (@{member.name}, ID: {member.id}) | Roles: {', '.join(roles) or 'None'}")
		return "\n".join(rows) if rows else "No members cached (enable Server Members Intent)."

	try:
		return _run_coro(_task())
	except Exception as e:
		return f"Failed to list members: {e}"


def create_text_channel(name: str, category_name: str = "", guild_id: int = 0) -> str:
	"""
	Create a new text channel in the Discord server (requires Manage Channels permission).

	Args:
		name: Name for the new text channel.
		category_name: Optional category name to place the channel under.
		guild_id: Optional server ID (uses current channel's server if 0).
	"""
	async def _task():
		guild = _client.get_guild(int(guild_id)) if guild_id else None
		if guild is None:
			ch = _resolve_channel(0)
			guild = getattr(ch, "guild", None)
		if guild is None:
			return "Error: Could not determine Discord server."
		category = None
		if category_name.strip():
			category = discord.utils.find(lambda c: c.name.lower() == category_name.strip().lower(), guild.categories)
		new_ch = await guild.create_text_channel(name=name.strip(), category=category)
		return f"Created channel #{new_ch.name} (ID: {new_ch.id})."

	try:
		return _run_coro(_task())
	except Exception as e:
		return f"Failed to create channel: {e}"


def set_member_nickname(user_id: int, nickname: str, guild_id: int = 0) -> str:
	"""
	Change a server member's nickname (pass empty string to reset it; requires Manage Nicknames permission).

	Args:
		user_id: The Discord user ID of the member.
		nickname: New nickname, or '' to clear.
		guild_id: Optional server ID (uses current channel's server if 0).
	"""
	async def _task():
		guild = _client.get_guild(int(guild_id)) if guild_id else None
		if guild is None:
			ch = _resolve_channel(0)
			guild = getattr(ch, "guild", None)
		if guild is None:
			return "Error: Could not determine Discord server."
		member = guild.get_member(int(user_id)) or await guild.fetch_member(int(user_id))
		await member.edit(nick=nickname.strip() or None)
		return f"Updated nickname for {member.name} to '{nickname.strip() or 'default'}'."

	try:
		return _run_coro(_task())
	except Exception as e:
		return f"Failed to update nickname: {e}"


def timeout_member(user_id: int, minutes: int = 5, reason: str = "Timed out by DJBot", guild_id: int = 0) -> str:
	"""
	Timeout (mute) a server member for a set number of minutes (requires Moderate Members permission).

	Args:
		user_id: The Discord user ID of the member.
		minutes: Duration in minutes (1 to 60).
		reason: Reason shown in the audit log.
		guild_id: Optional server ID (uses current channel's server if 0).
	"""
	from datetime import timedelta
	clamped = max(1, min(int(minutes), 60))

	async def _task():
		guild = _client.get_guild(int(guild_id)) if guild_id else None
		if guild is None:
			ch = _resolve_channel(0)
			guild = getattr(ch, "guild", None)
		if guild is None:
			return "Error: Could not determine Discord server."
		member = guild.get_member(int(user_id)) or await guild.fetch_member(int(user_id))
		await member.timeout(timedelta(minutes=clamped), reason=reason)
		return f"Timed out {member.display_name} for {clamped} minute(s)."

	try:
		return _run_coro(_task())
	except Exception as e:
		return f"Failed to timeout member: {e}"


def change_bot_status(activity_text: str, activity_type: str = "playing") -> str:
	"""
	Update DJBot's Discord status/activity text.

	Args:
		activity_text: The status message to show.
		activity_type: One of 'playing', 'listening', 'watching', or 'competing'.
	"""
	kind = activity_type.strip().lower()
	type_map = {
		"playing": discord.ActivityType.playing,
		"listening": discord.ActivityType.listening,
		"watching": discord.ActivityType.watching,
		"competing": discord.ActivityType.competing,
	}
	chosen = type_map.get(kind, discord.ActivityType.playing)

	async def _task():
		await _client.change_presence(activity=discord.Activity(type=chosen, name=activity_text[:128]))
		return f"Updated bot status to {kind}: {activity_text}"

	try:
		return _run_coro(_task())
	except Exception as e:
		return f"Failed to change status: {e}"