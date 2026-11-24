import os
import re
import hashlib
import json
import time
import base64
import asyncio
import inspect
import typing
from types import SimpleNamespace

from openai import OpenAI          # pip install openai   (used for ALL providers, they're OpenAI-compatible)
import edge_tts
from pygame import mixer
from dotenv import load_dotenv

# tools for the AI
import youtubeTool
import computerAccessTool

# ---------------------------------------------------------------------------
# Providers: only services with a real free tier (no credit card, no trial credits that run out)
# ---------------------------------------------------------------------------
# Put keys in your .env file (every key is optional, add as many as you want):
#   GROQ_API_KEY=...          console.groq.com/keys
#   GEMINI_API_KEY=...        aistudio.google.com/apikey          (also sees images)
#   CLOUDFLARE_API_KEY=...    dash.cloudflare.com -> AI -> Workers AI -> "Use REST API" (token with Workers AI permission)
#   CLOUDFLARE_ACCOUNT_ID=... same page. 10,000 free "neurons"/day, many models, some see images
#   MISTRAL_API_KEY=...       console.mistral.ai  (Experiment plan: phone verification, free usage may be used for training)
#   NVIDIA_API_KEY=...        build.nvidia.com/settings/api-keys  (free developer tier, ~40 requests/min) # removed cuz of needing to verify my account on nvidia by contacting them manually and its annoying
#   ZAI_API_KEY=...           z.ai  (GLM Flash models)
#   OPENROUTER_API_KEY=...    openrouter.ai/keys   (LAST resort: all :free models share ONE pool of 50 requests/day)
#   OLLAMA_MODEL=qwen3:8b     runs on YOUR pc through Ollama (ollama.com): no account, no limits, never "freemium"
#
# Removed on purpose: Cerebras (no permanent free tier any more, needs a payment method) and SambaNova (credits that run out).
#
# The bot walks the lists top to bottom and uses the first model that works.
#  - rate limited (429)            -> that model is skipped for 60 seconds
#  - daily limit hit (429 "per day") -> skipped until midnight UTC (OpenRouter: ALL its models, they share one pool)
#  - paid / not found / no access  -> that model is skipped for the rest of the session
# Model IDs change often, so a dead one just gets skipped, it never crashes the bot.
GROQ = ("groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY")
GOOGLE = ("google", "https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY")
CLOUDFLARE = ("cloudflare", "https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/v1", "CLOUDFLARE_API_KEY")
MISTRAL = ("mistral", "https://api.mistral.ai/v1", "MISTRAL_API_KEY")
NVIDIA = ("nvidia", "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY")
ZAI = ("zai", "https://api.z.ai/api/paas/v4/", "ZAI_API_KEY")
OPENROUTER = ("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY")
OLLAMA = ("ollama", "http://localhost:11434/v1", "OLLAMA_API_KEY")  # key is auto-set when OLLAMA_MODEL exists

OPENROUTER_MAX_AUTO = 3  # every failed OpenRouter try burns the shared 50/day, so only auto-add a few


def P(provider, model):
    name, base_url, key = provider
    return {"name": name, "base_url": base_url, "key": key, "model": model}


# Smartest first, providers interleaved so one provider's limit doesn't block everything. Normal chat + tools.
TEXT_PROVIDERS = [
    P(GROQ, "openai/gpt-oss-120b"),
    P(GOOGLE, "gemini-3.8-flash"),
    P(CLOUDFLARE, "@cf/openai/gpt-oss-120b"),
    P(MISTRAL, "mistral-large-latest"),
    P(NVIDIA, "openai/gpt-oss-120b"),
    P(GOOGLE, "gemini-3.6-flash"),
    P(GROQ, "qwen/qwen3.6-27b"),
    P(CLOUDFLARE, "@cf/qwen/qwen3.8-27b"),
    P(MISTRAL, "mistral-medium-latest"),
    P(NVIDIA, "meta/llama-3.3-70b-instruct"),
    P(CLOUDFLARE, "@cf/nvidia/nemotron-3-120b-a12b"),
    P(GOOGLE, "gemini-3.5-flash-lite"),
    P(ZAI, "glm-4.7-flash"),
    P(GROQ, "openai/gpt-oss-20b"),
    P(CLOUDFLARE, "@cf/zai-org/glm-4.7-flash"),
    P(MISTRAL, "mistral-small-latest"),
    P(CLOUDFLARE, "@cf/mistralai/mistral-small-3.1-24b-instruct"),
    P(GOOGLE, "gemini-3.1-flash-lite"),
    P(ZAI, "glm-4.5-flash"),
    #P(OPENROUTER, "openai/gpt-oss-120b:free"),
    # + a few free tool-capable OpenRouter models auto-added at startup
    # + your local Ollama model last (added at startup when OLLAMA_MODEL is set)
]

# Only used when a screenshot / YouTube frames are in the conversation.
# (Mistral is left out: it rejects the "user message right after a tool result" that screenshots need.)
VISION_PROVIDERS = [
    P(GOOGLE, "gemini-3.8-flash"),
    P(CLOUDFLARE, "@cf/qwen/qwen3.8-27b"),
    P(GOOGLE, "gemini-3.6-flash"),
    P(CLOUDFLARE, "@cf/google/gemma-4-26b-a4b-it"),
    P(GOOGLE, "gemini-3.5-flash-lite"),
    P(CLOUDFLARE, "@cf/meta/llama-4-scout-17b-16e-instruct"),
    P(GOOGLE, "gemini-3.1-flash-lite"),
    # + a few free image-capable OpenRouter models auto-added at startup
]

MAX_TOOL_ROUNDS = 30   # safety limit so the model can't loop on tools forever
MAX_HISTORY_MESSAGES = 10  # keeps requests small so you stay inside free token limits
MAX_HISTORY_CHARS = 1200   # each old message is cut to this many characters
MAX_IMAGE_SIDE = 768       # screenshots are shrunk to this size before sending (huge token saver)

clients: dict = {}


# ---------------------------------------------------------------------------
# Web search - runs locally via DuckDuckGo.  pip install ddgs
# ---------------------------------------------------------------------------
def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the internet for current information and return the top results,
    dont use this for inside/personal jokes, if asked by the user for a joke, check your brain first for jokes and if its a personal joke, you should not search it,
    cuz you will get no results on personal jokes

    The best use for this tool is to search for stuff while coding like definitions and whatever, text in the dictionary that you dont understand,
    or something asked by the user

    also if you dont find a result, just admit that you didnt find it and just DO NOT SPAM IT

    Args:
        query: The search query
        max_results: How many results to return (default 5)

    Returns:
        A text list of results with title, link and snippet.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        return "Web search unavailable: run 'pip install ddgs'."

    try:
        results = DDGS().text(query, max_results=max_results)
    except Exception as e:
        return f"Web search failed: {e}"

    if not results:
        return "No results found."

    return "\n\n".join(
        f"{r.get('title', '')}\n{r.get('href', '')}\n{r.get('body', '')}" for r in results
    )


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------
global tools
tools = [
    web_search,  # Search Internet Tool (uses DuckDuckGo)

    youtubeTool.find_yt_urls_in_message, youtubeTool.get_youtube_video_info, youtubeTool.get_youtube_transcript,  # Youtube Tool
    computerAccessTool.see_screen, computerAccessTool.get_app_windows, computerAccessTool.get_app_window_info,  # Computer Access Tool
    computerAccessTool.get_pc_specs_and_stats, computerAccessTool.start_app, computerAccessTool.close_app, computerAccessTool.maximize_app, computerAccessTool.minimize_app,
    computerAccessTool.restore_app, computerAccessTool.resize_app, computerAccessTool.move_app, #computerAccessTool.run_command,
    computerAccessTool.run_input_action_and_screenshot, computerAccessTool.run_window_action_and_screenshot, computerAccessTool.view_file_from_user_computer
]
global tool_map
tool_map = {fn.__name__: fn for fn in tools}

_JSON_TYPES = {int: "integer", float: "number", bool: "boolean", str: "string", list: "array", dict: "object"}


def function_to_schema(fn) -> dict:
    """Build an OpenAI tool schema from a Python function's signature + docstring."""
    sig = inspect.signature(fn)
    props, required = {}, []
    for name, p in sig.parameters.items():
        ann = p.annotation if p.annotation is not inspect.Parameter.empty else str
        ann = typing.get_origin(ann) or ann
        props[name] = {"type": _JSON_TYPES.get(ann, "string")}
        if p.default is inspect.Parameter.empty:
            required.append(name)
    doc = inspect.getdoc(fn) or fn.__name__
    return {"type": "function", "function": {
        "name": fn.__name__,
        "description": " ".join(doc.split("\n\nArgs:")[0].split())[:200],
        "parameters": {"type": "object", "properties": props, "required": required},
    }}


global tool_schemas
tool_schemas = [function_to_schema(fn) for fn in tools]

with open("behaviour.txt", "r", encoding="utf-8") as f:
    rules = f.read().strip()

# ---------------------------------------------------------------------------
# Chat history (plain {"role": "user"|"assistant", "content": str} dicts)
# ---------------------------------------------------------------------------
history = []


def load_chat_history():
    if not os.path.exists("chatHistory.json"):
        return
    with open("chatHistory.json", "r", encoding="utf-8") as f:
        contents = json.load(f)

    for message in contents:
        role = "user" if message["role"] == "user" else "assistant"
        history.append({"role": role, "content": message["text"]})


def add_to_chat_history(message, userOrModel):
    # userOrModel: False = user, True = model (same as before)
    history.append({"role": "assistant" if userOrModel else "user", "content": message})


def history_to_lines(history):
    return [
        {"role": "user" if m["role"] == "user" else "model", "text": m["content"]}
        for m in history
        if m.get("content")
    ]


def save_chat_history():
    with open("chatHistory.json", "w", encoding="utf-8") as f:
        json.dump(history_to_lines(history), f, indent=2, ensure_ascii=False)


_ready = False


def __init__():
    global _ready
    if _ready:  # safe to call more than once (history would get duplicated otherwise)
        return
    _ready = True

    load_dotenv()
    load_chat_history()

    if os.environ.get("OLLAMA_MODEL"):  # local model, no key needed (any string works)
        os.environ.setdefault("OLLAMA_API_KEY", "ollama")
        TEXT_PROVIDERS.append(P(OLLAMA, os.environ["OLLAMA_MODEL"]))

    for p in TEXT_PROVIDERS + VISION_PROVIDERS:
        key = os.environ.get(p["key"])
        if key and p["name"] not in clients:
            try:
                base_url = p["base_url"].format_map(os.environ)  # fills in {CLOUDFLARE_ACCOUNT_ID}
            except KeyError as e:
                print(f"{p['name']}: skipped, missing {e} in .env")
                continue
            clients[p["name"]] = OpenAI(base_url=base_url, api_key=key, timeout=300 if p["name"] == "ollama" else 60)
    print("Providers with a key loaded:", ", ".join(clients) or "NONE")
    if not clients:
        print("No API keys found! Add GROQ_API_KEY / GEMINI_API_KEY / CLOUDFLARE_API_KEY + CLOUDFLARE_ACCOUNT_ID / MISTRAL_API_KEY / NVIDIA_API_KEY ... to your .env")
    discover_openrouter_free()

    print(history)
    mixer.init()

def updateTools():
    tool_map = {fn.__name__: fn for fn in tools}
    tool_schemas = [function_to_schema(fn) for fn in tools]

# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------
def clean_for_tts(text):
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    cleaned = re.sub(r"[*_`#~>]+", " ", cleaned)

    # strip common emoji ranges + variation selectors
    emoji_pattern = re.compile(
        "["
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA70-\U0001FAFF"
        "\U00002600-\U000027BF"
        "\U0000FE00-\U0000FE0F"
        "\U0000200D"
        "]+",
        flags=re.UNICODE,
    )
    cleaned = emoji_pattern.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


tts_voice = "en-HK-SamNeural"


async def save_voice_mp3(text, voice="en-US-GuyNeural", out_file="output.mp3"):
    tts = edge_tts.Communicate(text, voice=voice)  # rate="+10%")
    await tts.save(out_file)


async def save_voice_with_timeout(text, voice, out_file="output.mp3"):
    coro = save_voice_mp3(text, voice=voice, out_file=out_file)
    await asyncio.wait_for(coro, timeout=10)


# ---------------------------------------------------------------------------
# Talking to the model (with a tool-calling loop + provider failover)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Free-model discovery + dead-model tracking
# ---------------------------------------------------------------------------
dead_until: dict = {}  # (provider, model) -> time.time() when it may be tried again


def discover_openrouter_free():
    """Ask OpenRouter which models are $0 right now, and add the tool-capable / image-capable ones."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return
    try:
        import urllib.request
        req = urllib.request.Request("https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            models = json.loads(resp.read().decode("utf-8"))["data"]
    except Exception as e:
        print(f"OpenRouter discovery failed: {e}")
        return

    def free(m):
        pr = m.get("pricing", {})
        return all(float(pr.get(k, 1) or 0) == 0 for k in ("prompt", "completion", "image", "request") if k in pr)

    # biggest context first = usually the bigger/smarter models
    models = sorted((m for m in models if free(m)), key=lambda m: m.get("context_length") or 0, reverse=True)
    have_t = {p["model"] for p in TEXT_PROVIDERS if p["name"] == "openrouter"}
    have_v = {p["model"] for p in VISION_PROVIDERS if p["name"] == "openrouter"}
    added_t = added_v = 0
    for m in models:
        mid = m["id"]
        tools_ok = "tools" in (m.get("supported_parameters") or [])
        if tools_ok and mid not in have_t and added_t < OPENROUTER_MAX_AUTO:
            TEXT_PROVIDERS.append(P(OPENROUTER, mid))
            added_t += 1
        if tools_ok and "image" in (m.get("architecture", {}).get("input_modalities") or []) \
                and mid not in have_v and added_v < OPENROUTER_MAX_AUTO:
            VISION_PROVIDERS.append(P(OPENROUTER, mid))
            added_v += 1
    print(f"OpenRouter: {len(TEXT_PROVIDERS)} text / {len(VISION_PROVIDERS)} vision models in the chain")


provider_dead_until: dict = {}  # provider -> time when ALL its models may be tried again


def next_utc_midnight() -> float:
    now = time.time()
    return now - (now % 86400) + 86400


def mark_failed(p, error):
    text = str(error).lower()
    status = getattr(error, "status_code", None)
    key = (p["name"], p["model"])
    if status == 429 or "rate limit" in text or "quota" in text:
        if re.search(r"per[ _-]?day|daily", text):
            # daily limit: waiting 60 s is pointless, and every extra try can count against the quota
            if p["name"] == "openrouter":  # all :free models share one daily pool
                provider_dead_until["openrouter"] = next_utc_midnight()
            dead_until[key] = next_utc_midnight()
        else:
            dead_until[key] = time.time() + 60
    elif status == 400:
        dead_until[key] = time.time() + 30  # usually 'too long' for this one request, not a dead model
    elif status in (401, 402, 403, 404, 410) or any(w in text for w in ("payment", "paid", "credit", "not found", "decommission", "does not exist", "no access")):
        dead_until[key] = float("inf")  # paid / gone: never try again this session
    else:
        dead_until[key] = time.time() + 15  # temporary hiccup


def image_to_data_url(path: str) -> str:
    """Shrink the image first: a full-size screenshot can cost 10x more tokens than a 768px one."""
    try:
        from PIL import Image  # pip install pillow
        import io
        img = Image.open(path).convert("RGB")
        img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        with open(path, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def _short_id(tool_id) -> str:
    """Mistral only accepts 9-character alphanumeric tool-call ids; this is valid everywhere."""
    return hashlib.md5(str(tool_id).encode()).hexdigest()[:9]


def to_api_messages(messages):
    """Turn our messages (with optional 'images': [file paths]) into clean OpenAI format (base64 image parts).
    Our private 'images' key is never sent: strict providers (Mistral, NVIDIA, Cloudflare) reject unknown fields."""
    out = []
    last_img = max((i for i, m in enumerate(messages) if m.get("images")), default=-1)
    for i, m in enumerate(messages):
        msg = {k: v for k, v in m.items() if k != "images"}
        if m.get("role") in ("user", "assistant") and isinstance(msg.get("content"), str) \
                and len(msg["content"]) > MAX_HISTORY_CHARS:
            msg["content"] = msg["content"][:MAX_HISTORY_CHARS] + "..."
        if msg.get("tool_calls"):
            msg["tool_calls"] = [{**c, "id": _short_id(c["id"])} for c in msg["tool_calls"]]
        if msg.get("tool_call_id"):
            msg["tool_call_id"] = _short_id(msg["tool_call_id"])
        if m.get("images") and i == last_img:
            parts = [{"type": "text", "text": m["content"]}]
            for path in m["images"]:
                parts.append({"type": "image_url", "image_url": {"url": image_to_data_url(path)}})
            msg["content"] = parts
        out.append(msg)
    return out


def has_images(messages) -> bool:
    return any(m.get("images") for m in messages)


def create_completion(messages, use_tools=True):
    """Try each model in order until one works (handles rate limits + paid models)."""
    providers = VISION_PROVIDERS if has_images(messages) else TEXT_PROVIDERS
    api_messages = to_api_messages(messages)
    last_error = None

    for p in providers:
        client = clients.get(p["name"])
        now = time.time()
        if client is None or provider_dead_until.get(p["name"], 0) > now or dead_until.get((p["name"], p["model"]), 0) > now:
            continue

        if p["name"] == "openrouter":
            continue
        
        try:
            response = client.chat.completions.create(
                model=p["model"],
                messages=api_messages,
                **({"tools": tool_schemas} if use_tools else {}),
            )
            if not response.choices:
                raise RuntimeError("empty response")
            print(f"[model] {p['name']}/{p['model']}")
            return response
        except Exception as e:
            print(f"[{p['name']}/{p['model']}] skipped: {str(e)[:150]}")
            mark_failed(p, e)
            last_error = e

    if not clients:
        raise RuntimeError("No API keys loaded - check your .env file is next to the script and has GROQ_API_KEY=... etc")
    raise RuntimeError(f"All models failed or are rate limited. Last error: {last_error}")


def run_tool(name, args):
    fn = tool_map.get(name)
    if fn is None:
        return f"Error: unknown tool '{name}'."
    try:
        print(f"[tool] {name}({args})")
        return fn(**args)
    except Exception as e:
        return f"Error running {name}: {e}"


IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
MAX_TOOL_RESULT_CHARS = 3000  # a huge tool result (e.g. a PNG read as text/base64) makes EVERY provider reply 400 "too long"


def extract_image_path(result, args=None):
    """Give back an image path if the tool produced/opened one, so it is sent as a real image (not as text)."""
    if isinstance(result, dict):
        for key in ("image_path", "path", "file_path"):
            p = result.get(key)
            if isinstance(p, str) and p.lower().endswith(IMAGE_EXTS) and os.path.exists(p):
                return p
    # tools like view_file_from_user_computer: the argument itself is an image file
    if isinstance(args, dict):
        p = args.get("file_path")
        if isinstance(p, str) and p.lower().endswith(IMAGE_EXTS) and os.path.exists(p):
            return p
    if isinstance(result, str) and result.strip().lower().endswith(IMAGE_EXTS) and os.path.exists(result.strip()):
        return result.strip()
    return None


def tool_result_to_text(result, image_path=None) -> str:
    """Never put giant / binary data into the chat history."""
    if image_path:
        return f"Image loaded: {os.path.basename(image_path)} (shown to you in the next message)."
    if isinstance(result, (bytes, bytearray)):
        return f"[binary data, {len(result)} bytes, not shown]"
    if isinstance(result, dict):
        result = {k: v for k, v in result.items() if k != "image_path"}
    text = str(result)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + f"\n...[truncated, {len(text) - MAX_TOOL_RESULT_CHARS} more characters]"
    return text


def chat_with_tools(messages):
    """Send messages, execute any tool calls the model makes, return final text."""
    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = create_completion(messages)
        except RuntimeError:
            # Last resort so the bot always answers: system prompt + latest user text, no tools, no images
            time.sleep(2)
            user_texts = [m for m in messages if m["role"] == "user" and not m.get("images")]
            lean = [messages[0], {"role": "user", "content": (user_texts[-1]["content"] if user_texts else "hi")[:MAX_HISTORY_CHARS]}]
            dead_until.clear()
            response = create_completion(lean, use_tools=False)
        msg = response.choices[0].message

        if not msg.tool_calls:
            return msg.content or ""

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}}
                for c in msg.tool_calls
            ],
        })

        pending_images = []
        for call in msg.tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = run_tool(call.function.name, args)
            image_path = extract_image_path(result, args)
            if image_path:
                pending_images.append(image_path)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": tool_result_to_text(result, image_path),
            })

        # Models read images from a user message, not from a tool result
        if pending_images:
            messages.append({
                "role": "user",
                "content": "Here is the image from the tool you just used.",
                "images": pending_images,
            })

    return "Sorry, I got stuck using my tools too many times."


def speak(text):
    """Text-to-speech. Never raises, and works even when called from inside a running asyncio loop (discord)."""
    try:
        mixer.music.unload()
        coro = save_voice_with_timeout(clean_for_tts(text), voice=tts_voice)
        try:
            asyncio.get_running_loop()
            in_loop = True
        except RuntimeError:
            in_loop = False

        if in_loop:  # asyncio.run() can't run inside a running loop, so use a throwaway thread
            import threading
            err = []
            t = threading.Thread(target=lambda: _run_safely(coro, err))
            t.start()
            t.join()
            if err:
                raise err[0]
        else:
            asyncio.run(coro)

        mixer.music.load("output.mp3")
        mixer.music.play()
    except Exception as e:
        print(f"TTS failed: {e}")


def _run_safely(coro, err):
    try:
        asyncio.run(coro)
    except Exception as e:
        err.append(e)


def talk_to_ai(message, on_responded_function=None, user_uploads=[]):
    __init__()  # no-op if already initialised, so it also works when imported by the discord bot
    text = ""
    try:
        # Frames extracted from any YouTube links, saved as local image files
        frame_paths = youtubeTool.yt_videos_to_chat(message)

        user_msg = {"role": "user", "content": message, "images": []}
        if frame_paths:
            user_msg["images"] += frame_paths

        if user_uploads and user_uploads != []:
            user_msg["images"] += user_uploads
        
        messages = [{"role": "system", "content": rules}, *history[-MAX_HISTORY_MESSAGES:], user_msg]

        text = chat_with_tools(messages)

        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": text})

        print(text)
        if on_responded_function:
            on_responded_function(SimpleNamespace(text=text))  # keeps the old `response.text` usage working

        speak(text)

    except Exception as e:
        print(e)
        if on_responded_function and not text:
            on_responded_function(SimpleNamespace(text=f"(AI error: {str(e)[:300]})"))


# while True:
#     prompt = input("> ")
#
#     if prompt.lower() == "quit":
#         break
#
#     talk_to_ai(prompt)
#     time.sleep(0.1)

# save_chat_history()