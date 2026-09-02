import argparse
from pathlib import Path
import ctypes
from ctypes import wintypes
import shutil
import sys
import tempfile
import time

from pathspec import GitIgnoreSpec
import win32api
import win32con
from pywinauto import Desktop, timings


EXCLUDED_NAMES = {
    ".git", ".hg", ".svn", ".venv", "venv", ".vscode", ".idea",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".nox", "node_modules", "dist", "build", ".DS_Store",
}

CF_HDROP = 15
GMEM_MOVEABLE = 0x0002

CTRL_TO_V_DELAY = 0.010
V_HOLD_DELAY = 0.010
DEFOCUS_OFFSET = 20
DEFOCUS_MOUSE_DELAY = 0.005
REFOCUS_MOUSE_DELAY = 0.010


class DROPFILES(ctypes.Structure):
    _fields_ = [
        ("pFiles", wintypes.DWORD),
        ("pt_x", wintypes.LONG),
        ("pt_y", wintypes.LONG),
        ("fNC", wintypes.BOOL),
        ("fWide", wintypes.BOOL),
    ]


def loadGitignore(project_path):
    gitignore_path = project_path / ".gitignore"
    if not gitignore_path.is_file():
        return GitIgnoreSpec.from_lines([])
    return GitIgnoreSpec.from_lines(
        gitignore_path.read_text(encoding="utf-8-sig").splitlines()
    )


def createExclusionFilter(project_path):
    gitignore = loadGitignore(project_path)

    def shouldExclude(directory, names):
        directory = Path(directory)
        ignored = []
        for name in names:
            path = directory / name
            relative_path = path.relative_to(project_path).as_posix()
            if path.is_dir():
                relative_path += "/"
            if (
                name in EXCLUDED_NAMES
                or name.endswith(".egg-info")
                or gitignore.match_file(relative_path)
            ):
                ignored.append(name)
        return ignored

    return shouldExclude


def buildSnapshot(project_path, snapshot_path):
    project_path = project_path.resolve()
    snapshot_path = snapshot_path.resolve()
    if not project_path.is_dir():
        raise NotADirectoryError(f"Project directory not found: {project_path}")
    if snapshot_path == project_path or project_path in snapshot_path.parents:
        raise ValueError("Snapshot directory must not be inside the source project.")

    if snapshot_path.exists():
        shutil.rmtree(snapshot_path)
    shutil.copytree(
        project_path,
        snapshot_path,
        ignore=createExclusionFilter(project_path),
    )


def createAttachmentQueue(snapshot_path):
    attachment_queue = [
        file for file in snapshot_path.rglob("*") if file.is_file()
    ]
    print(f"\nAttachment queue contains {len(attachment_queue)} files:")
    for number, file in enumerate(attachment_queue, start=1):
        print(f"{number:>3}. {file.relative_to(snapshot_path)}")
    print()
    return attachment_queue


def copyFilesToClipboard(files):
    files = [Path(file).resolve() for file in files]
    for file in files:
        if not file.is_file():
            raise FileNotFoundError(file)

    file_bytes = ("\0".join(str(file) for file in files) + "\0\0").encode(
        "utf-16le"
    )
    dropfiles = DROPFILES()
    dropfiles.pFiles = ctypes.sizeof(DROPFILES)
    dropfiles.pt_x = 0
    dropfiles.pt_y = 0
    dropfiles.fNC = False
    dropfiles.fWide = True

    total_size = ctypes.sizeof(DROPFILES) + len(file_bytes)
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL

    memory = kernel32.GlobalAlloc(GMEM_MOVEABLE, total_size)
    if not memory:
        raise RuntimeError("GlobalAlloc failed")

    pointer = kernel32.GlobalLock(memory)
    if not pointer:
        kernel32.GlobalFree(memory)
        raise RuntimeError("GlobalLock failed")

    try:
        ctypes.memmove(pointer, ctypes.byref(dropfiles), ctypes.sizeof(DROPFILES))
        ctypes.memmove(
            pointer + ctypes.sizeof(DROPFILES), file_bytes, len(file_bytes)
        )
    finally:
        kernel32.GlobalUnlock(memory)

    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(memory)
        raise RuntimeError("Could not open clipboard")

    try:
        if not user32.EmptyClipboard():
            raise RuntimeError("Could not empty clipboard")
        if not user32.SetClipboardData(CF_HDROP, memory):
            raise RuntimeError("SetClipboardData failed")
        # Windows owns the allocation after SetClipboardData succeeds.
        memory = None
    finally:
        user32.CloseClipboard()
        if memory:
            kernel32.GlobalFree(memory)


def sendCtrlV():
    user32 = ctypes.windll.user32
    keyeventf_keyup = 0x0002
    vk_control = 0x11
    vk_v = 0x56
    user32.keybd_event(vk_control, 0, 0, 0)
    time.sleep(CTRL_TO_V_DELAY)
    user32.keybd_event(vk_v, 0, 0, 0)
    time.sleep(V_HOLD_DELAY)
    user32.keybd_event(vk_v, 0, keyeventf_keyup, 0)
    user32.keybd_event(vk_control, 0, keyeventf_keyup, 0)


def fastMouseClick(x, y, settle_delay):
    screen_width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
    screen_height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
    absolute_x = int(float(x) * (65535.0 / float(screen_width - 1)))
    absolute_y = int(float(y) * (65535.0 / float(screen_height - 1)))

    win32api.mouse_event(
        win32con.MOUSEEVENTF_MOVE | win32con.MOUSEEVENTF_ABSOLUTE,
        absolute_x, absolute_y, 0, 0,
    )
    time.sleep(settle_delay)
    win32api.mouse_event(
        win32con.MOUSEEVENTF_LEFTDOWN | win32con.MOUSEEVENTF_ABSOLUTE,
        x, y, 0, 0,
    )
    win32api.mouse_event(
        win32con.MOUSEEVENTF_LEFTUP | win32con.MOUSEEVENTF_ABSOLUTE,
        x, y, 0, 0,
    )


def resolveComposer(chatgpt):
    selectors = (
        ({"title": "\nMessage ChatGPT", "control_type": "Edit"}, "title + Edit"),
        ({"class_name": "ProseMirror", "control_type": "Edit"}, "ProseMirror + Edit"),
    )
    selector_errors = []

    for selector, label in selectors:
        try:
            composer = chatgpt.child_window(**selector).wrapper_object()
            print(f"Composer resolved: {label}")
            return composer
        except Exception as error:
            selector_errors.append(f"{label}: {error}")

    candidates = []
    unreadable_count = 0
    for index, control in enumerate(chatgpt.descendants()):
        try:
            info = control.element_info
            control_type = info.control_type or ""
            name = control.window_text() or ""
            class_name = info.class_name or ""
            automation_id = info.automation_id or ""
            searchable = " ".join((name, class_name, automation_id)).lower()
            is_editor_type = control_type in ("Edit", "Document")
            has_composer_marker = any(
                marker in searchable
                for marker in (
                    "message chatgpt", "prompt-textarea", "prosemirror",
                    "contenteditable",
                )
            )
            if not (is_editor_type or has_composer_marker):
                continue

            rect = control.rectangle()
            visible = control.is_visible()
            enabled = control.is_enabled()
            score = 40 if control_type == "Edit" else 20
            score += 60 if has_composer_marker else 0
            score += 15 if visible else -50
            score += 10 if enabled else -25
            score += max(0, rect.top) / 100000
            candidates.append(
                (score, rect.top, index, control, control_type, name,
                 class_name, automation_id, visible, enabled, rect)
            )
        except Exception:
            unreadable_count += 1

    candidates.sort(key=lambda candidate: (candidate[0], candidate[1]), reverse=True)
    if candidates and candidates[0][0] >= 55:
        best = candidates[0]
        print(
            "Composer resolved: diagnostic scored fallback "
            f"(descendant {best[2]}, score {best[0]:.3f})"
        )
        return best[3]

    diagnostics = [
        "Could not resolve the ChatGPT composer.",
        *[f"Selector missed: {error}" for error in selector_errors],
        (f"Found {len(candidates)} plausible candidate(s); "
         f"{unreadable_count} descendant(s) were unreadable."),
    ]
    for rank, candidate in enumerate(candidates[:10], start=1):
        diagnostics.append(
            f"{rank}. descendant={candidate[2]} score={candidate[0]:.3f} "
            f"type={candidate[4]!r} name={candidate[5]!r} "
            f"class={candidate[6]!r} automation_id={candidate[7]!r} "
            f"visible={candidate[8]} enabled={candidate[9]} rect={candidate[10]}"
        )
    raise RuntimeError("\n".join(diagnostics))


def pasteIntoChatGPTAndRestore(chatgpt, original_foreground_hwnd):
    user32 = ctypes.windll.user32
    try:
        chatgpt.set_focus()

        # Chromium exposes the composer reliably only while ChatGPT is foregrounded.
        composer = resolveComposer(chatgpt)

        # Query geometry live after focus; cached coordinates caused failures.
        rect = composer.rectangle()
        composer_x = (rect.left + rect.right) // 2
        composer_y = (rect.top + rect.bottom) // 2
        defocus_x = composer_x
        defocus_y = rect.top - DEFOCUS_OFFSET

        fastMouseClick(defocus_x, defocus_y, DEFOCUS_MOUSE_DELAY)
        fastMouseClick(composer_x, composer_y, REFOCUS_MOUSE_DELAY)
        sendCtrlV()
    finally:
        if original_foreground_hwnd:
            user32.SetForegroundWindow(original_foreground_hwnd)


def queueAttachments(attachment_queue):
    if not attachment_queue:
        print("No files found to attach.")
        return False

    user32 = ctypes.windll.user32
    # Capture the user's window before anything can focus ChatGPT.
    original_foreground_hwnd = user32.GetForegroundWindow()

    try:
        # Prepare the complete payload outside the focus-disturbance critical section.
        copyFilesToClipboard(attachment_queue)
    except Exception as error:
        print("Could not prepare files on the clipboard:")
        print(error)
        return False

    try:
        # Only resolve the top-level window here; resolve the composer after focus.
        chatgpt = Desktop(backend="uia").window(title="ChatGPT")
        chatgpt.wait("visible", timeout=5)
    except Exception as error:
        print("Could not find ChatGPT:")
        print(error)
        return False

    try:
        pasteIntoChatGPTAndRestore(chatgpt, original_foreground_hwnd)
    except Exception as error:
        print("Could not attach files to ChatGPT:")
        print(error)
        return False

    print(f"Queued all {len(attachment_queue)} files in one paste.")
    return True


def parseArguments():
    parser = argparse.ArgumentParser(
        description="Queue a filtered project snapshot as ChatGPT attachments."
    )
    parser.add_argument("source", type=Path, help="project directory to snapshot")
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "context-courier-snapshot",
        help="working snapshot directory (default: system temporary directory)",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="build and list the filtered snapshot without attaching files",
    )
    return parser.parse_args()


def main():
    args = parseArguments()
    total_start = time.perf_counter()
    snapshot_start = time.perf_counter()
    try:
        buildSnapshot(args.source, args.snapshot_dir)
    except (OSError, ValueError) as error:
        print(f"Could not build snapshot: {error}", file=sys.stderr)
        return 1
    print(f"\nSnapshot build: {time.perf_counter() - snapshot_start:.2f}s")

    attachment_queue = createAttachmentQueue(args.snapshot_dir)
    print(f"Total files: {len(attachment_queue)}")

    if args.list_only:
        print("List-only mode: no files were attached.")
        return 0

    timings.Timings.after_clickinput_wait = 0.0
    if not queueAttachments(attachment_queue):
        print("Attachment failed.")
        return 1

    print(
        "\nALL FILES QUEUED\n"
        f"TOTAL RUNTIME: {time.perf_counter() - total_start:.2f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
