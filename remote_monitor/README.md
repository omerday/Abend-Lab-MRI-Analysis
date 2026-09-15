# Abend Lab fMRI Remote Monitor & Job Controller (Telegram Bot)

A mobile-friendly, asynchronous **ChatOps** solution designed for researchers in the Abend Lab for Neuroscience of Psychopathology. It allows you to monitor running fMRI analyses, view generated `@chauffeur_afni` axial montage PNGs and QC PDF reports, receive real-time push alerts on job success or failure, and re-run batch analyses directly from your phone while away.

---

## Key Features

- 📱 **Native Mobile Experience**: Control everything using the standard Telegram app on iOS or Android.
- 🔒 **Zero Port Forwarding / NAT Traversal**: Uses outbound HTTPS long-polling to the Telegram Cloud API. Works through university and lab firewalls without requiring IT permissions or public IP addresses.
- ⚡ **Multi-Subject Parallel Execution**: Launch concurrent batches across multiple subjects and CPU cores (`--n_procs > 1`).
- 🔔 **Per-Subject Milestone Alerts**: Pushes updates *as each subject completes* (with its `@chauffeur_afni` brain montages attached as a photo album) rather than waiting hours for the entire batch to finish.
- 🔁 **1-Tap Failure Recovery**: If a subject fails (e.g. motion censoring or disk issues), the bot sends an immediate alert with the error traceback and an inline `[🔁 Retry]` button to re-launch it with a single tap.
- 🖼️ **On-Demand QA Inspector**: Use `/qa` to pull chauffeur montage PNGs and QC PDF reports for any subject at any time.
- 💻 **Hardware Health Monitoring**: Monitor CPU%, RAM%, and remaining storage space on output drives (e.g. `/media/user/PortableSSD`).
- 🛡️ **Whitelist Security**: Only authorized numeric Telegram user IDs can interact with the bot.

---

## 1. Quick Setup (Takes ~5 minutes)

### Step 1: Create your Telegram Bot
1. Open Telegram on your phone or laptop and search for `@BotFather`.
2. Send the message `/newbot`.
3. Choose a display name (e.g. `Abend Lab MRI Bot`) and a username ending in `bot` (e.g. `AbendLabMriBot`).
4. `@BotFather` will reply with your **HTTP API Bot Token** (looks like `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`). Copy this token.

### Step 2: Get your Telegram User ID
1. On Telegram, search for `@userinfobot`.
2. Send `/start`.
3. It will reply with your numeric `Id` (e.g. `987654321`). Copy this number. This is your personal user ID used to whitelist you.

### Step 3: Install Dependencies on the Lab Linux PC
In the repository root, install the bot requirements:
```bash
pip install -r remote_monitor/requirements-bot.txt
```

### Step 4: Configure the Bot
Copy the template configuration file:
```bash
cp remote_monitor/bot_config.template.toml remote_monitor/bot_config.toml
```

Edit `remote_monitor/bot_config.toml` with your favorite editor (`nano` or `vim`):
```toml
[telegram]
bot_token = "YOUR_TELEGRAM_BOT_TOKEN"
allowed_user_ids = [
    987654321   # Replace with your numeric user ID from Step 2
]

[pipelines]
default_pipeline = "tim"
monitored_storage_paths = [
    "/",
    "/media/user/PortableSSD"
]
```

---

## 2. Running the Bot

### Testing in Terminal:
Run the bot directly to make sure everything connects:
```bash
python3 -m remote_monitor.bot
```
Now open your bot in Telegram and send `/start` or `/status`. You should see the welcome message and live host statistics!

### Running Permanently in Background (`systemd`):
To keep the bot running 24/7 (surviving reboots and auto-restarting if it crashes):

1. Edit `remote_monitor/mri_bot.service` to verify the `User` and `WorkingDirectory` paths match your Linux account:
   ```ini
   User=user
   WorkingDirectory=/home/user/Documents/Abend-Lab-MRI-Analysis
   ```
2. Copy the unit file and enable the service:
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

## 3. Usage & Command Reference

### `/status` — Live System & Batch Progress
Displays:
- Active batch progress bar: `[████████░░░░░] 60% (6/10)`
- Currently running subjects and their active step/runtime
- Succeeded vs. failed subjects
- Host CPU, RAM, and external storage space (`PortableSSD`)
- Latest 5 log entries

### `/run` — Launch Jobs
You can launch jobs in two ways:
1. **Interactive Wizard**:
   Simply send `/run` (or tap the `🚀 Run Job` button on your phone). The bot will guide you through inline buttons:
   - Select Task (`🧠 TIM Task` or `⚔️ WAR Task`)
   - Select Step (`glm`, `preprocess`, `all`, etc.)
   - Select Subject Scope (`All Subjects`, `Single Test`, `Failed Only`)
   - Select Analysis Model (`pain_by_rating`, `by_block`, etc.)
   - Select CPU Cores (`1`, `2`, `4`, or `8` parallel cores)
   - Confirm & Launch!

2. **Fast Command Shorthand**:
   ```text
   # Run GLM for 2 subjects in parallel
   /run tim glm --subjects sub-502,sub-504 --analysis pain_by_rating --n_procs 2

   # Run entire pipeline for WAR task across all subjects
   /run war all --analysis by_block --n_procs 4
   ```

### `/qa` — Inspect QA Images & PDFs
- Send `/qa` to pick a pipeline and subject.
- The bot uploads the generated `@chauffeur_afni` 3x3 axial montage PNGs directly into your chat as a photo album, and attaches the preproc QC PDF.

### `/logs` — View Live Log Tails
- Send `/logs` to see the most recently updated log files.
- Tapping any log immediately returns the last 35 lines of stdout/stderr.

### `/kill` — Cancel Running Batch
- Terminate the currently running `run_analysis.py` process tree safely.

---

## 4. Standalone Terminal Notification Helper

If you or a lab colleague run `run_analysis.py` directly from the Linux terminal (outside of Telegram), you can still receive push notifications using `remote_monitor.notify`:

```bash
# In your bash script or terminal:
python3 run_analysis.py --subject sub-502 --analysis pain_by_rating --step all

# Send notification when done:
python3 -m remote_monitor.notify --message "✅ Subject sub-502 finished GLM" --photo /media/user/PortableSSD/.../chauffeur_images/PAIN#0.png
```
