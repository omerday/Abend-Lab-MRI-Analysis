# Abend Lab fMRI Remote Monitor & Job Controller (Telegram Bot)

A mobile-friendly, asynchronous **ChatOps** daemon designed for researchers in the **Abend Lab for Neuroscience of Psychopathology**. It allows lab personnel to launch, inspect, and manage running fMRI analyses, review generated `@chauffeur_afni` axial montage PNGs and QC PDF reports, receive real-time push alerts on job milestones or failures, and safely monitor workstation hardware health from any smartphone.

---

## 🔒 Operational Safety & Security Policy

> **SECURITY & AUTHORIZATION NOTICE**:
> 1. **Whitelist Access Only**: Only numeric Telegram user IDs explicitly registered in `remote_monitor/bot_config.toml` (`allowed_user_ids`) are permitted to query status, receive logs, or launch pipeline jobs. Unauthorized messages are immediately rejected and logged.
> 2. **Process Tree Isolation**: Job cancellation via `/kill` gracefully terminates child processes using `SIGTERM` before sending `SIGKILL`, ensuring AFNI lockfiles and scratch disks are cleanly unmounted.
> 3. **AFNI Underscore Escaping**: Dataset identifiers containing underscores (e.g., `sub-435_pain_by_rating`) are automatically escaped or parsed via HTML entities to prevent Telegram Markdown V1 syntax crashes.

---

## Table of Contents
- [Architecture Overview](#architecture-overview)
- [Key Features](#key-features)
- [Module Breakdown](#module-breakdown)
- [Quick Setup Guide](#quick-setup-guide)
  - [Step 1: Create Your Bot via @BotFather](#step-1-create-your-bot-via-botfather)
  - [Step 2: Retrieve Your Telegram User ID](#step-2-retrieve-your-telegram-user-id)
  - [Step 3: Install Dependencies](#step-3-install-dependencies)
  - [Step 4: Configure `bot_config.toml`](#step-4-configure-bot_configtoml)
- [Running the Bot](#running-the-bot)
  - [Interactive Testing](#interactive-testing)
  - [Persistent Background Service (`systemd`)](#persistent-background-service-systemd)
- [Command Reference](#command-reference)
  - [`/status` — Live System & Progress](#status--live-system--progress)
  - [`/run` — Interactive Job Launcher](#run--interactive-job-launcher)
  - [`/qa` — On-Demand QC Inspector](#qa--on-demand-qc-inspector)
  - [`/logs` — Live Log Tail Viewer](#logs--live-log-tail-viewer)
  - [`/kill` — Cancel Running Batch](#kill--cancel-running-batch)
- [Standalone Terminal Notification Helper (`notify.py`)](#standalone-terminal-notification-helper-notifypy)
- [Troubleshooting & Diagnostics](#troubleshooting--diagnostics)

---

## Architecture Overview

The daemon runs locally on the laboratory analysis workstation or cloud jumpbox. It connects to the Telegram Cloud API using outbound HTTPS long-polling:

```text
  📱 Mobile Telegram App (iOS / Android)
                 │
                 │ Outbound HTTPS (TLS 443)
                 ▼
  ☁️ Telegram Bot API Servers (api.telegram.org)
                 ▲
                 │ Long-polling GET /getUpdates (Zero open inbound ports)
                 │
  💻 Abend Lab Workstation (remote_monitor daemon)
     ├── bot.py                (Async Telegram Bot Interface)
     ├── pipeline_manager.py   (Background Job Runner & Process Tree Tracker)
     ├── system_monitor.py     (Hardware Metrics & Log Parser)
     ├── notify.py             (Webhook & Multipart Photo Uploader)
     └── config.py             (TOML Parser & Whitelist Validator)
```

**Zero Inbound NAT / Firewall Requirements**: Because the bot uses outbound polling, it operates seamlessly behind university, hospital, and enterprise firewalls without requiring public IP addresses, VPNs, or port forwarding.

---

## Key Features

- 📱 **Native Mobile Control**: Manage long-running fMRI batches from any iOS or Android device.
- ⚡ **Multi-Subject Parallel Execution**: Launch batch jobs across multiple subjects with configurable CPU concurrency (`--n_procs`).
- 🔔 **Per-Subject Milestone Alerts**: Pushes notification alerts *as each individual subject completes* (with its `@chauffeur_afni` brain montages attached as a photo album) rather than waiting hours for the entire batch to finish.
- 🔁 **1-Tap Failure Recovery**: If a subject fails (e.g., severe motion censoring or missing files), the bot immediately sends an alert with the error traceback and an inline `[🔁 Retry]` button to re-run that specific subject.
- 🖼️ **On-Demand QA Inspector**: Use `/qa` to inspect `@chauffeur_afni` axial montages and download preprocessed QC PDFs directly into chat.
- 💻 **Hardware Health Monitoring**: Real-time inspection of CPU load, RAM utilization, and storage capacity across internal and external drives (e.g. `/media/user/PortableSSD`).

---

## Module Breakdown

| Module | File | Responsibility |
| :--- | :--- | :--- |
| **Bot Controller** | `remote_monitor/bot.py` | Asynchronous event loop, command handlers, inline keyboards, and alert callbacks. |
| **Pipeline Manager** | `remote_monitor/pipeline_manager.py` | Launches `run_analysis.py` subprocesses, tracks job status, and handles process termination. |
| **System Monitor** | `remote_monitor/system_monitor.py` | Collects CPU, RAM, and disk statistics; parses AFNI process tables; classifies recent logs. |
| **Notifier** | `remote_monitor/notify.py` | Lightweight standard-library Telegram client for sending text, HTML, and image multipart payloads. |
| **Configuration** | `remote_monitor/config.py` | Loads and validates `bot_config.toml` using strict schema verification. |

---

## Quick Setup Guide

### Step 1: Create Your Bot via @BotFather
1. In Telegram, search for `@BotFather`.
2. Send `/newbot`.
3. Choose a name (e.g., `Abend Lab MRI Monitor`) and a username ending in `bot` (e.g., `AbendLabMriBot`).
4. Copy the issued **HTTP API Bot Token** (`123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`).

### Step 2: Retrieve Your Telegram User ID
1. In Telegram, search for `@userinfobot`.
2. Send `/start`.
3. Copy the returned numeric `Id` (e.g., `987654321`). This is your whitelist ID.

### Step 3: Install Dependencies
```bash
pip install -r remote_monitor/requirements-bot.txt
```

### Step 4: Configure `bot_config.toml`
Copy the configuration template:
```bash
cp remote_monitor/bot_config.template.toml remote_monitor/bot_config.toml
```

Edit `remote_monitor/bot_config.toml`:
```toml
[telegram]
bot_token = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
allowed_user_ids = [
    987654321   # Your numeric Telegram user ID from Step 2
]

[pipelines]
default_pipeline = "tim"
monitored_storage_paths = [
    "/",
    "/media/user/VERBATIM SD"
]
```

---

## Running the Bot

### Interactive Testing
To test the bot interactively in your terminal:
```bash
python3 -m remote_monitor.bot
```
Open Telegram and send `/status` to verify host connection.

---

### Persistent Background Service (`systemd`)
To keep the bot running 24/7 across workstation reboots:

1. Edit `remote_monitor/mri_bot.service` to verify `User`, `WorkingDirectory`, and `ExecStart`:
   ```ini
   [Unit]
   Description=Abend Lab fMRI Remote Monitor Telegram Bot
   After=network.target

   [Service]
   Type=simple
   User=user
   WorkingDirectory=/home/user/Documents/Abend-Lab-MRI-Analysis
   ExecStart=/usr/bin/python3 -m remote_monitor.bot
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```
2. Enable and start the systemd service:
   ```bash
   sudo cp remote_monitor/mri_bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now mri_bot
   ```
3. Check status:
   ```bash
   sudo systemctl status mri_bot
   ```

---

## Command Reference

### `/status` — Live System & Progress
Displays:
- **Active Batch Progress**: `[████████░░░░░] 60% (6/10 subjects)`
- **Running Workers**: Subject IDs, current pipeline step, and elapsed runtime.
- **Hardware Health**: CPU utilization (%), RAM utilization (%), and free space on monitored mount points.
- **Recent Log Status**: Categorized counts (`SUCCESS`, `FAILED`, `RUNNING`, `IDLE`).

### `/run` — Interactive Job Launcher
Can be used interactively or via shorthand command:
1. **Interactive Wizard**: Send `/run` and select options using inline buttons:
   - Pipeline (`TIM` vs. `WAR`)
   - Step (`glm`, `preprocess`, `all`)
   - Subject Selection (`All Subjects`, `Single Subject`, or `Failed Only`)
   - Analysis Model (`pain_by_rating`, `by_block`, etc.)
   - Concurrency (`1`, `2`, `4`, or `8` cores)
2. **Shorthand Syntax**:
   ```text
   # Run GLM for 2 subjects in parallel
   /run tim glm --subjects sub-502,sub-504 --analysis pain_by_rating --n_procs 2

   # Run full WAR pipeline across 4 cores
   /run war all --analysis by_block --n_procs 4
   ```

### `/qa` — On-Demand QC Inspector
- Send `/qa` and select pipeline and subject ID.
- The bot uploads `@chauffeur_afni` 3x3 axial montage PNGs directly into chat as an album and attaches the APQC PDF report.

### `/logs` — Live Log Tail Viewer
- Send `/logs` to view the 5 most recently updated execution logs.
- Tap any log to view the trailing 35 lines of stdout/stderr.

### `/kill` — Cancel Running Batch
- Safely terminates the active `run_analysis.py` process hierarchy.

---

## Standalone Terminal Notification Helper (`notify.py`)

If you or a colleague run analyses directly from a bash terminal or cron script, you can still dispatch Telegram alerts using `remote_monitor.notify`:

```bash
# Execute your analysis command
python tim_analysis/run_analysis.py --subject sub-435 --step all --analysis pain_by_rating

# Send instant push notification with brain montage photo
python3 -m remote_monitor.notify \
    --message "✅ Subject <b>sub-435</b> completed GLM (<code>pain_by_rating</code>)" \
    --photo "/path/to/sub-435/ses-1/glm/pain_by_rating/QC/PAIN#0.png" \
    --parse-mode HTML
```

### Underscore Escaping Protection:
Telegram's Markdown V1 parser treats unescaped underscores (`_`) as italics, causing parsing failures on dataset names like `sub-435_pain_by_rating.results`. `remote_monitor.notify` defaults to `HTML` formatting and automatically sanitizes solitary underscores under `--parse-mode Markdown`, falling back to plain text if the Telegram API rejects formatted entities.

---

## Troubleshooting & Diagnostics

- **Bot Not Responding**:
  - Verify your numeric Telegram user ID is listed in `allowed_user_ids` in `bot_config.toml`.
  - Check `systemctl status mri_bot` or run `python3 -m remote_monitor.bot` in terminal to inspect startup logs.
- **Image Upload Failures**:
  - Verify `@chauffeur_afni` generated `.png` files in the subject's `glm/<model>/QC/` directory.
- **Process Stuck**:
  - Use `/status` to see if an AFNI process is running. If stalled, use `/kill` to clean up the process tree.
