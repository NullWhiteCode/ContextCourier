# ContextCourier

ContextCourier queues a filtered snapshot of a project into ChatGPT in a single, fast attachment operation. It is a small Windows-only automation tool for sending source context without repeatedly using a native file picker.

## Requirements

- Windows 10 or 11
- Python 3.10 or newer
- The ChatGPT desktop app, or a ChatGPT Chromium window exposed through Windows UI Automation with the window title `ChatGPT`
- `pywinauto` and `pywin32` (installed automatically below)

## Installation

```powershell
git clone <your-repository-url>
cd ContextCourier
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## Usage

Open ChatGPT and navigate to the conversation that should receive the files. Then run:

```powershell
context-courier C:\path\to\your\project
```

To inspect the filtered file list without interacting with ChatGPT:

```powershell
context-courier C:\path\to\your\project --list-only
```

By default, the snapshot is rebuilt at `%TEMP%\context-courier-snapshot`. Use `--snapshot-dir PATH` to choose another working directory. The snapshot directory must be outside the source project because it is replaced on each run.

## Snapshot filtering

ContextCourier copies the project tree, excluding common repository metadata, virtual environments, dependency trees, build output, editor state, and caches. The built-in exclusions include `.git`, `.venv`, `.vscode`, `.idea`, `__pycache__`, Python tool caches, `node_modules`, `build`, and `dist`.

This is deliberately a simple name-based filter, not a security boundary. Review the `--list-only` output before attaching an unfamiliar or sensitive project. Project secrets and local configuration with other names are not automatically detected.

## How attachment works

The complete file list is encoded as a native Windows `CF_HDROP` clipboard payload and pasted once into the ChatGPT composer. ContextCourier prepares that payload before briefly focusing ChatGPT, reads the composer geometry while it is live, pastes the files, and restores the previously focused window. This avoids driving the Windows file picker or batching files one at a time.

The focus, live-geometry, and paste sequence is intentionally conservative: cached composer coordinates caused attachment failures during development.

## Example benchmark

In one development test with 19 files, the measured total runtime was approximately **0.20 seconds**, with about **0.15 seconds** of user-visible focus disturbance. This is an example from one machine and UI state, not a performance guarantee. Project size, storage speed, Windows scheduling, and ChatGPT UI behavior will affect results.

## Limitations

- Windows only; the clipboard payload and focus restoration use Win32 APIs.
- ChatGPT and Chromium UI Automation selectors can change and may require updates.
- The tool queues attachments but does not submit the message.
- It replaces the configured snapshot directory on every run.
- Clipboard contents are replaced with the generated file list.
- Large projects may exceed ChatGPT attachment count or size limits.

## License

MIT. See [LICENSE](LICENSE).
