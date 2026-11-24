import pywinctl
import pyautogui
import platform
import os
import time
import psutil
import subprocess
import mimetypes
import base64

SCREENSHOT_DIR = "ScreenshotTemp"


def _cleanup_old_screenshots(keep: int = 10):
    try:
        files = sorted(
            (os.path.join(SCREENSHOT_DIR, f) for f in os.listdir(SCREENSHOT_DIR) if f.endswith(".png")),
            key=os.path.getmtime,
        )
        for old in files[:-keep]:
            os.remove(old)
    except OSError:
        pass


def see_screen(max_width: int, regionX: int, regionY: int, regionWidth: int, regionHeight: int):
    """
        Function to get a screenshot from the users computer (if a region axis is 0, or at their default value, it screenshots the whole screen)
        Set a text-visible non-blur text max screenshot width but not so big that your tokens choke, use 600px max_width unless you need something important af
        The screenshot is attached as an image in the next message after you call this.
    """
    try:
        if regionX == 0 or regionY == 0 or regionWidth == 0 or regionHeight == 0:
            screenshot = pyautogui.screenshot()
        else:
            screenshot = pyautogui.screenshot(region=(regionX, regionY, regionWidth, regionHeight))

        if screenshot.width > max_width:
            ratio = max_width / screenshot.width
            new_height = int(screenshot.height * ratio)
            screenshot = screenshot.resize((max_width, new_height))

        # Local model reads the image from a file path instead of an uploaded part
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        path = os.path.abspath(os.path.join(SCREENSHOT_DIR, f"screen_{time.time_ns()}.png"))
        screenshot.save(path, format="PNG")
        _cleanup_old_screenshots()

        return {
            "image_path": path,
            "width": screenshot.width,
            "height": screenshot.height,
        }
    except Exception as e:
        return {
            "error": str(e)
        }

def get_app_windows():
    """
    Function to get a list of the app windows running on the users computer
    """
    windows = pywinctl.getAllWindows()

    appWindows = []

    if windows == None:
        return []

    for window in windows:
        if window.title != "" or window.isVisible == True:
            appWindows.append(window.title)

    return appWindows

def get_app_window_info(windowTitle : str):
    """
    Get info about a window like position, size and more (needs window title, it gets the windowTitle you input and gets the first window with that title and its case-sensitive, also consider using the get_app_windows function if you wanna see for an app)
    This Function can return None if no open window with that title is found
    """

    window = pywinctl.getWindowsWithTitle(windowTitle)[0]
    return {
        "title": str(window.title),
        "x": int(window.left),
        "y": int(window.top),
        "width": int(window.width),
        "height": int(window.height),
        "is_visible": bool(window.isVisible),
        "is_minimized": bool(window.isMinimized),
        "is_maximized": bool(window.isMaximized),
        "is_active": bool(window.isActive),
    }

def start_app(appName: str):
    """
    Start an app on the users computer (it uses the start command in the command prompt, Windows only)
    """
    subprocess.Popen(['cmd', '/c' ,'start', appName])
    return "action started"

def close_app(appName: str):
    """
    Close an app on the users computer (can trigger "are you sure do you want to save this file?" dialogs on windows and its not force-closing)
    """
    window = pywinctl.getWindowsWithTitle(appName)[0]
    window.close()
    return "app closed successfully"

def maximize_app(appName: str):
    """Maximize the first window whose title matches appName."""
    window = pywinctl.getWindowsWithTitle(appName)[0]
    window.maximize()
    return "maximized app successfully"

def minimize_app(appName: str):
    """Minimize the first window whose title matches appName."""
    window = pywinctl.getWindowsWithTitle(appName)[0]
    window.minimize()
    return "minimized app successfully"

def restore_app(appName: str):
    """Restore the first window whose title matches appName from minimized/maximized."""
    window = pywinctl.getWindowsWithTitle(appName)[0]
    window.restore()
    return "restored app successfully"

def resize_app(appName: str, width: int, height: int):
    """Resize the first window whose title matches appName to width x height pixels."""
    window = pywinctl.getWindowsWithTitle(appName)[0]
    window.resizeTo(width, height)
    return "resized app successfully"

def move_app(appName: str, x: int, y: int):
    """Move the first window whose title matches appName to screen position x, y."""
    window = pywinctl.getWindowsWithTitle(appName)[0]
    window.moveTo(x, y)
    return "moved app successfully"

def run_command(command: str): # removed from the ai
    #cuz the ai wouldnt have enough tokes to know and memorize the windows,linux and macOS commands anyway, replaced with functions that run the commands (even better and supports cross-platform)
    """Run a command in the Windows command prompt (5 second timeout) and return its exit code and output."""
    res = subprocess.run(
        ["cmd.exe", "/c", *command.split(" ")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
        executable=os.environ.get("COMSPEC", "C:\\Windows\\System32\\cmd.exe"),
        stdin=subprocess.DEVNULL
    )

    output_text = res.stdout.strip()
    error_text = res.stderr.strip()
    code = res.returncode
    return {"errorCode": code, "outputText": output_text}

def move_mouse(x: int, y: int, duration: float = 0):
    print(f"[move_mouse] x={x}, y={y}, duration={duration}")
    pyautogui.moveTo(x, y, duration)

def left_click_mouse():
    pyautogui.leftClick()

def right_click_mouse():
    pyautogui.rightClick()

def middle_click_mouse():
    pyautogui.middleClick()

def scroll_mouse(scroll_amount):
    pyautogui.scroll(scroll_amount)

def press_keyboard_keys(text: str):
    pyautogui.press(text)

def run_input_action_and_screenshot(screenshot_max_width: int, screenshot_x: int, screenshot_y: int, screenshot_width: int, screenshot_height: int, action: str, action_x: int, action_y: int, action_duration: float=0, action_scroll_amount: int = 5, action_text: str = ""):
    """
    Runs a input action and then captures a screenshot of the screen.

    Actions (uses some of the action arguements of this function):
        move_mouse -> takes: x, y and duration, moves the mouse
        left_click_mouse -> takes no arguments, left clicks the mouse
        right_click_mouse -> takes no arguments, right clicks the mouse
        middle_click_mouse -> takes no arguments, middle clicks the mouse
        scroll_mouse -> takes: scroll_amount, scrolls the mouse
        press_keyboard_keys -> takes: text, pressed a keyboard key or multiple

    Args:
        screenshot_max_width (int): Max width limit for resizing the captured screenshot
        screenshot_x (int): Left X coordinate of the screenshot capture region
        screenshot_y (int): Top Y coordinate of the screenshot capture region
        screenshot_width (int): Width of the screenshot capture region
        screenshot_height (int): Height of the screenshot capture region
        action (str): Action to run
        action_x (int): Target X coordinate for mouse movement
        action_y (int): Target Y coordinate for mouse movement
        action_duration (int, optional): Time in seconds for mouse movement (default 0.1)
        action_scroll_amount (int, optional): Scroll steps for scrolling (default 5)
        action_text (string, optional): Keys to press, used only by press_keyboard_keys

    Returns:
        The result from see_screen() after the action runs.
    """
    if action == "move_mouse":
        move_mouse(action_x, action_y)
    elif action == "left_click_mouse":
        left_click_mouse()
    elif action == "right_click_mouse":
        right_click_mouse()
    elif action == "middle_click_mouse":
        middle_click_mouse()
    elif action == "scroll_mouse":
        scroll_mouse(action_scroll_amount)
    elif action == "press_keyboard_keys":
        press_keyboard_keys(action_text)

    return see_screen(screenshot_max_width, screenshot_x, screenshot_y, screenshot_width, screenshot_height)

def run_window_action_and_screenshot(screenshot_max_width: int, screenshot_x: int, screenshot_y: int, screenshot_width: int, screenshot_height: int, action: str, action_x: int, action_y: int, action_text: str = ""):
    """
    Runs a window action and then captures a screenshot of the screen.

    Actions (uses some of the action arguements of this function):
        start_app -> takes appName
        close_app -> takes appName
        maximize_app -> takes appName
        minimize_app -> takes appName
        restore_app -> takes appName
        resize_app -> takes appName, size x and y (using action_x and action_y)
        move_app -> takes appName, position x and y (using action_x and action_y)

    Args:
        screenshot_max_width (int): Max width limit for resizing the captured screenshot
        screenshot_x (int): Left X coordinate of the screenshot capture region
        screenshot_y (int): Top Y coordinate of the screenshot capture region
        screenshot_width (int): Width of the screenshot capture region
        screenshot_height (int): Height of the screenshot capture region
        action (str): Action to run
        action_x (int): Target X coordinate for window movement and resizing
        action_y (int): Target Y coordinate for window movement and resizing
        action_string (string, optional) app to target

    Returns:
        The result from see_screen() after the action runs.
    """
    if action == "start_app":
        start_app(action_text)
    elif action == "close_app":
        close_app(action_text)
    elif action == "maximize_app":
        maximize_app(action_text)
    elif action == "minimize_app":
        minimize_app(action_text)
    elif action == "restore_app":
        restore_app(action_text)
    elif action == "resize_app":
        resize_app(action_text)
    elif action == "move_app":
        move_app(action_text)

    return see_screen(screenshot_max_width, screenshot_x, screenshot_y, screenshot_width, screenshot_height)

def view_file_from_user_computer(file_path: str):
	if not os.path.exists(file_path):
		return {"error": f"file not found: {file_path}"}

	mime_type, _ = mimetypes.guess_type(file_path)
	ext = os.path.splitext(file_path)[1].lower()

	if ext in {".txt", ".md", ".py", ".json", ".log", ".csv"}:
		with open(file_path, "r", encoding="utf-8", errors="replace") as f:
			return {"type": "text", "content": f.read()}

	with open(file_path, "rb") as f:
		raw_bytes = f.read()

	encoded = base64.b64encode(raw_bytes).decode("ascii")
	return {
		"type": "binary",
		"mime_type": mime_type or "application/octet-stream",
		"size_bytes": len(raw_bytes),
		"base64": encoded,
	}

def get_pc_specs_and_stats() -> list[str]:
    """
    Return a list of non-private PC specs and current running stats from the users computer
    """
    items: list[str] = []

    # PC specs (no hostname, IP, network info, or device model)
    items.append(f"OS: {platform.system()}")
    items.append(f"OS release: {platform.release()}")
    items.append(f"OS version: {platform.version()}")
    items.append(f"Architecture: {platform.machine()}")
    if platform.processor():
        items.append(f"Processor: {platform.processor()}")

    logical_cores = psutil.cpu_count(logical=True)
    physical_cores = psutil.cpu_count(logical=False)
    if logical_cores is not None:
        items.append(f"Logical CPU cores: {logical_cores}")
    if physical_cores is not None:
        items.append(f"Physical CPU cores: {physical_cores}")

    vm = psutil.virtual_memory()
    gib = 1024 ** 3
    items.append(f"Total RAM (GiB): {vm.total / gib:.2f}")
    items.append(f"Available RAM (GiB): {vm.available / gib:.2f}")
    items.append(f"Used RAM (GiB): {vm.used / gib:.2f}")
    items.append(f"RAM usage percent: {vm.percent:.1f}%")

    swap = psutil.swap_memory()
    items.append(f"Total swap (GiB): {swap.total / gib:.2f}")
    items.append(f"Used swap (GiB): {swap.used / gib:.2f}")
    items.append(f"Swap usage percent: {swap.percent:.1f}%")

    # Live running stats
    cpu_pct = psutil.cpu_percent(interval=0.2)
    items.append(f"Current CPU usage: {cpu_pct:.1f}%")

    per_core = psutil.cpu_percent(interval=None, percpu=True)
    if per_core:
        formatted_cores = ", ".join(f"C{i}:{val:.0f}%" for i, val in enumerate(per_core))
        items.append(f"Per-core CPU usage: {formatted_cores}")

    cpu_freq = psutil.cpu_freq()
    if cpu_freq and cpu_freq.current:
        items.append(f"Current CPU frequency (MHz): {cpu_freq.current:.0f}")

    if hasattr(os, "getloadavg"):
        try:
            load1, load5, load15 = os.getloadavg()
            items.append(f"Load average (1m / 5m / 15m): {load1:.2f} / {load5:.2f} / {load15:.2f}")
        except OSError:
            pass

    try:
        root_path = "C:\\" if os.name == "nt" else "/"
        disk = psutil.disk_usage(root_path)
        items.append(f"Disk ({root_path}) total (GiB): {disk.total / gib:.2f}")
        items.append(f"Disk ({root_path}) used (GiB): {disk.used / gib:.2f}")
        items.append(f"Disk ({root_path}) free (GiB): {disk.free / gib:.2f}")
        items.append(f"Disk ({root_path}) usage percent: {disk.percent:.1f}%")
    except OSError:
        items.append("Disk usage: unavailable")

    boot_time = psutil.boot_time()
    uptime_mins = int((time.time() - boot_time) // 60)
    items.append(f"Uptime (minutes): {uptime_mins}")

    return items