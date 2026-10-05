# ContextCourier

ContextCourier builds a filtered snapshot of a project and sends it to ChatGPT through a fast Windows attachment workflow.

For snapshots that fit within a single ChatGPT attachment batch, ContextCourier queues all files in one paste operation. Larger snapshots can optionally be delivered across multiple synchronized batches with `--batch-send`.

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

Open ChatGPT and navigate to the conversation that should receive the files.

For a snapshot that fits within a single attachment batch:

```powershell
context-courier C:\path\to\your\project
```

To automatically deliver a larger snapshot across multiple batches:

```powershell
context-courier C:\path\to\your\project --batch-send
```

To inspect the filtered file list without interacting with ChatGPT:

```powershell
context-courier C:\path\to\your\project --list-only
```

By default, the snapshot is rebuilt at `%TEMP%\context-courier-snapshot`. Use `--snapshot-dir PATH` to choose another working directory. The snapshot directory must be outside the source project because it is replaced on each run.

## Batch sending

ChatGPT currently accepts a maximum of 20 attachments in a single message. ContextCourier normally rejects snapshots above this limit rather than partially attaching them.

`--batch-send` enables automatic multi-batch delivery. ContextCourier splits the attachment queue into batches of up to 20 files while preserving file order, then processes each batch in sequence.

For each batch, ContextCourier:

1. attaches the files in a single clipboard paste;
2. waits until every expected attachment is visible in the ChatGPT composer;
3. adds a small ContextCourier message identifying the batch;
4. submits the message;
5. waits for ChatGPT generation to start and finish before continuing.

Intermediate batches ask ChatGPT for a minimal `OK` response. The final batch identifies itself as the completed delivery.

If attachment readiness, generation start, or generation completion times out, ContextCourier aborts the remaining batches rather than continuing from an uncertain UI state.

Batch sending is opt-in. Normal mode retains the original fast single-paste attachment workflow.

## Snapshot filtering

ContextCourier respects the source project's root `.gitignore` rules, including normal directory patterns and negation, and also excludes common repository metadata, virtual environments, dependency trees, build output, editor state, and caches. The built-in exclusions include `.git`, `.venv`, `.vscode`, `.idea`, `__pycache__`, Python tool caches, `node_modules`, `build`, and `dist`.

Filtering is not a security boundary. Files that are not covered by `.gitignore` or the built-in exclusions remain eligible for attachment, so review the `--list-only` output before attaching an unfamiliar or sensitive project.

## How attachment works

ContextCourier encodes each attachment batch as a native Windows `CF_HDROP` clipboard payload and pastes the complete batch into the ChatGPT composer at once.

It prepares the payload before briefly focusing ChatGPT, reads the composer geometry while it is live, pastes the files, and restores the previously focused window. This avoids driving the Windows file picker or attaching files one at a time.

The focus, live-geometry, and paste sequence is intentionally conservative: cached composer coordinates caused attachment failures during development.

In normal mode, ContextCourier stops after the attachments are queued and does not submit the message.

In `--batch-send` mode, ContextCourier additionally uses Windows UI Automation to observe attachment readiness, locate the enabled Send control, submit each batch, and detect ChatGPT's generation state before proceeding.

## Example benchmark

In one development test with 19 files using normal mode, the measured total runtime was approximately **0.20 seconds**, with about **0.15 seconds** of user-visible focus disturbance.

This is an example from one machine and UI state, not a performance guarantee. Project size, storage speed, Windows scheduling, and ChatGPT UI behavior will affect results.

Multi-batch mode intentionally prioritizes synchronization and correctness over raw speed because each batch waits for ChatGPT before the next is delivered.

## Limitations

- Windows only; clipboard handling and focus restoration use Win32 APIs.
- ChatGPT and Chromium UI Automation selectors can change and may require updates.
- Normal mode queues attachments but does not submit the message.
- `--batch-send` submits messages automatically and waits for ChatGPT between batches.
- ChatGPT's attachment limits may change in the future.
- Individual files may still exceed ChatGPT's supported file size or file type limits.
- The configured snapshot directory is replaced on every run.
- Clipboard contents are replaced with the generated file list.
- UI Automation depends on the expected ChatGPT window and composer being available.

## License

MIT. See [LICENSE](LICENSE).
