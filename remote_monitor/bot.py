#!/usr/bin/env python3
"""
Abend Lab MRI Analysis - Telegram Bot Daemon
Provides remote monitoring, QA inspection, and execution control from a smartphone.
"""

import os
import sys
import glob
import logging
import asyncio
from typing import List, Dict, Any, Optional

try:
    from telegram import (
        Update, InlineKeyboardButton, InlineKeyboardMarkup, 
        ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
    )
    from telegram.ext import (
        ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
        MessageHandler, ContextTypes, filters
    )
    from telegram.constants import ParseMode
except ImportError:
    print("[Error] 'python-telegram-bot' is not installed. Please run: pip install -r remote_monitor/requirements-bot.txt", file=sys.stderr)
    sys.exit(1)

from .config import config
from .system_monitor import get_system_metrics, get_active_afni_processes, get_recent_logs
from .pipeline_manager import pipeline_manager, BatchJobTracker

# Configure Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("MriRemoteBot")

# Helper to verify authorization
def is_authorized(update: Update) -> bool:
    user = update.effective_user
    if not user or not config.is_user_allowed(user.id):
        logger.warning(f"Unauthorized access attempt from user_id: {user.id if user else 'Unknown'} (@{user.username if user else 'None'})")
        return False
    return True

# Persistent Reply Keyboard for quick access on mobile
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📊 Status"), KeyboardButton("🚀 Run Job")],
        [KeyboardButton("🖼️ Inspect QA"), KeyboardButton("📋 View Logs")],
    ],
    resize_keyboard=True
)

# -------------------------------------------------------------------------
# Command Handlers
# -------------------------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start and /help commands."""
    if not is_authorized(update):
        await update.message.reply_text("⛔ *Unauthorized Access*\nYour Telegram user ID is not authorized to control this server.", parse_mode=ParseMode.MARKDOWN)
        return

    welcome_text = (
        "🧠 *Abend Lab fMRI Remote Bot*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Welcome! Use this bot to monitor analyses, review QA images, and control batch jobs while away.\n\n"
        "*Quick Commands:*\n"
        "• `/status` — View system resources, active jobs, and recent log states.\n"
        "• `/run` — Launch single or multi-subject batch jobs with interactive menus.\n"
        "• `/qa` — Inspect `@chauffeur_afni` axial montage PNGs and QC PDFs.\n"
        "• `/logs` — Read live log tails from recent runs.\n"
        "• `/kill` — Cancel an active running batch.\n\n"
        "_Tip: You can also use the touch buttons below on your phone screen._"
    )
    await update.message.reply_markdown(welcome_text, reply_markup=MAIN_KEYBOARD)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and send system metrics, active AFNI jobs, and batch status."""
    if not is_authorized(update): return

    msg_parts = ["🧠 *Abend Lab System & Pipeline Status*\n━━━━━━━━━━━━━━━━━━━━━━━━━━"]

    # 1. Active Batch Job (if launched through bot)
    tracker = pipeline_manager.active_batch
    if tracker and tracker.is_running:
        pct = tracker.progress_percent
        bar_len = 10
        filled = int((pct / 100) * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        
        msg_parts.append(
            f"🔄 *Active Batch:* `{tracker.pipeline.upper()}` ({tracker.step})\n"
            f"⏱️ Elapsed: *{tracker.formatted_elapsed}* | Cores: *{tracker.n_procs}*\n"
            f"📈 Progress: `[{bar}]` *{pct}%* ({tracker.completed_count}/{len(tracker.subjects)} Subjects)\n"
        )
        
        # Breakdown of subjects
        running_subs = [s for s, st in tracker.subject_states.items() if st["status"] == "RUNNING"]
        queued_subs = [s for s, st in tracker.subject_states.items() if st["status"] == "QUEUED"]
        success_subs = [s for s, st in tracker.subject_states.items() if st["status"] == "SUCCESS"]
        failed_subs = [s for s, st in tracker.subject_states.items() if st["status"] == "FAILED"]

        if running_subs:
            msg_parts.append("⚡ *Currently Processing:*")
            for s in running_subs[:4]:
                st = tracker.subject_states[s]
                msg_parts.append(f"• `{s}`: ⏳ _{st['current_step']}_")
        
        if failed_subs:
            msg_parts.append(f"❌ *Failed:* {', '.join([f'`{s}`' for s in failed_subs])}")
        
        if success_subs:
            msg_parts.append(f"✅ *Completed:* {len(success_subs)} subjects")

        msg_parts.append("")
    else:
        # Check if AFNI / Python processes are running in terminal
        active_procs = get_active_afni_processes()
        if active_procs:
            msg_parts.append(f"⚙️ *Running Processes ({len(active_procs)} active):*")
            for p in active_procs[:5]:
                sub_label = f"[{p['subject']}] " if p['subject'] else ""
                msg_parts.append(f"• `{p['name']}` (PID {p['pid']}): {sub_label}_{p['keyword']}_ ({p['elapsed']})")
            msg_parts.append("")
        else:
            msg_parts.append("💤 *No active analyses currently running.*\n")

    # 2. System Hardware Metrics
    metrics = get_system_metrics(config.monitored_storage_paths)
    msg_parts.append(
        f"💻 *Host Resources:*\n"
        f"• CPU: *{metrics['cpu_percent']}%* | RAM: *{metrics['ram_used']}* / {metrics['ram_total']} (*{metrics['ram_percent']}%*)"
    )
    for d in metrics["disks"]:
        msg_parts.append(f"• Storage (`{d['path']}`): *{d['free']} free* ({d['percent_used']}% used)")
    msg_parts.append("")

    # 3. Recent Logs
    logs = get_recent_logs(config.repo_root, limit=5)
    if logs:
        msg_parts.append("📋 *Recent Log Runs:*")
        for l in logs:
            msg_parts.append(f"{l['icon']} `{l['subject']}` ({l['pipeline']}) — _{l['modified_time']}_\n   └ {l['last_line']}")

    await update.message.reply_markdown("\n".join(msg_parts))


# -------------------------------------------------------------------------
# Interactive Run Wizard Handlers
# -------------------------------------------------------------------------

# State cache for interactive wizard: user_id -> dict
WIZARD_STATE: Dict[int, Dict[str, Any]] = {}

async def run_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /run command either with CLI arguments or via interactive wizard."""
    if not is_authorized(update): return

    args = context.args
    # If arguments provided directly, e.g. /run tim glm --subjects sub-500,sub-502 --analysis pain_by_rating --n_procs 2
    if args and len(args) >= 2:
        await launch_from_cli_args(update, context, args)
        return

    # Otherwise open interactive wizard
    user_id = update.effective_user.id
    WIZARD_STATE[user_id] = {
        "pipeline": config.default_pipeline,
        "step": "glm",
        "scope": "all",
        "subjects": [],
        "analysis": [],
        "n_procs": 2,
    }

    keyboard = [
        [
            InlineKeyboardButton("🧠 TIM Task", callback_data="wiz|pipe|tim"),
            InlineKeyboardButton("⚔️ WAR Task", callback_data="wiz|pipe|war"),
        ]
    ]
    await update.message.reply_markdown(
        "🚀 *Launch Analysis Wizard*\nStep 1/5: Select which pipeline to run:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def launch_from_cli_args(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    """Parse CLI shorthand arguments and trigger the batch."""
    pipeline = args[0].lower()
    step = args[1].lower()
    
    subjects = []
    analyses = []
    n_procs = 1
    session = "1"
    group_model = None

    idx = 2
    while idx < len(args):
        flag = args[idx]
        if flag in ["--subjects", "--subject"] and idx + 1 < len(args):
            subjects = [s.strip() for s in args[idx+1].split(",") if s.strip()]
            idx += 2
        elif flag == "--analysis" and idx + 1 < len(args):
            analyses = [a.strip() for a in args[idx+1].split(",") if a.strip()]
            idx += 2
        elif flag == "--n_procs" and idx + 1 < len(args):
            n_procs = int(args[idx+1])
            idx += 2
        elif flag == "--session" and idx + 1 < len(args):
            session = args[idx+1]
            idx += 2
        elif flag == "--group_model" and idx + 1 < len(args):
            group_model = args[idx+1]
            idx += 2
        else:
            idx += 1

    try:
        tracker = await pipeline_manager.launch_batch(
            pipeline=pipeline,
            step=step,
            subjects=subjects,
            analysis=analyses,
            session=session,
            n_procs=n_procs,
            group_model=group_model,
            on_subject_milestone=lambda t, s, st: handle_subject_milestone(context.bot, t, s, st),
            on_batch_complete=lambda t: handle_batch_complete(context.bot, t),
        )
        await update.message.reply_markdown(
            f"🚀 *Batch Dispatched Successfully!*\n"
            f"• Pipeline: `{pipeline.upper()}` | Step: `{step}`\n"
            f"• Subjects: *{len(tracker.subjects)} subjects* | Parallel Cores: *{n_procs}*\n"
            f"• PID: `{tracker.process.pid}`\n\n"
            f"_You will receive real-time notifications as each subject finishes or if any step encounters errors._"
        )
    except Exception as e:
        await update.message.reply_markdown(f"❌ *Failed to start batch:*\n`{e}`")


async def wizard_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button selections in the interactive wizard."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data.split("|")

    if not is_authorized(update): return

    state = WIZARD_STATE.get(user_id, {})
    action = data[1]

    # --- Step 1: Pipeline Selected -> Select Step ---
    if action == "pipe":
        state["pipeline"] = data[2]
        keyboard = [
            [InlineKeyboardButton("GLM Regression", callback_data="wiz|step|glm"), InlineKeyboardButton("All Steps", callback_data="wiz|step|all")],
            [InlineKeyboardButton("Preprocess Func", callback_data="wiz|step|preprocess_func"), InlineKeyboardButton("Preprocess Anat", callback_data="wiz|step|preprocess_anat")],
            [InlineKeyboardButton("Create Timings", callback_data="wiz|step|create_timings"), InlineKeyboardButton("Full Preprocess", callback_data="wiz|step|preprocess")],
        ]
        await query.edit_message_text(
            f"Selected Pipeline: *{state['pipeline'].upper()}*\n\nStep 2/5: Select processing step:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # --- Step 2: Step Selected -> Select Subject Scope ---
    elif action == "step":
        state["step"] = data[2]
        p_info = pipeline_manager.get_pipeline_info(state["pipeline"])
        total_subs = len(p_info["subjects"])

        keyboard = [
            [InlineKeyboardButton(f"All Subjects ({total_subs})", callback_data="wiz|scope|all")],
            [InlineKeyboardButton("Single Test Subject", callback_data="wiz|scope|single")],
            [InlineKeyboardButton("Failed Subjects Only", callback_data="wiz|scope|failed")],
        ]
        await query.edit_message_text(
            f"Step: *{state['step']}*\n\nStep 3/5: Select subject scope:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # --- Step 3: Scope Selected -> Select Model or Cores ---
    elif action == "scope":
        scope = data[2]
        state["scope"] = scope
        p_info = pipeline_manager.get_pipeline_info(state["pipeline"])

        if scope == "all":
            state["subjects"] = p_info["subjects"]
        elif scope == "single":
            state["subjects"] = [p_info["subjects"][0]] if p_info["subjects"] else ["sub-001"]
        elif scope == "failed":
            # Auto-detect failed logs
            recent = get_recent_logs(config.repo_root, limit=20)
            failed = list(set([r["subject"] for r in recent if r["status"] == "FAILED" and r["pipeline"] == state["pipeline"]]))
            state["subjects"] = failed if failed else (p_info["subjects"][:3])

        # If step is GLM or All, prompt for analysis model
        if state["step"] in ["glm", "all"] and p_info["models"]:
            keyboard = []
            row = []
            for m in p_info["models"]:
                row.append(InlineKeyboardButton(m, callback_data=f"wiz|model|{m}"))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
            if row: keyboard.append(row)
            keyboard.append([InlineKeyboardButton("All Models", callback_data="wiz|model|all")])

            await query.edit_message_text(
                f"Subjects: *{len(state['subjects'])} selected*\n\nStep 4/5: Select Analysis Model:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            # Skip directly to cores
            await show_cores_selection(query, state)

    # --- Step 4: Model Selected -> Select Cores ---
    elif action == "model":
        selected_model = data[2]
        if selected_model == "all":
            p_info = pipeline_manager.get_pipeline_info(state["pipeline"])
            state["analysis"] = p_info["models"]
        else:
            state["analysis"] = [selected_model]
        await show_cores_selection(query, state)

    # --- Step 5: Cores Selected -> Show Confirmation ---
    elif action == "cores":
        state["n_procs"] = int(data[2])
        keyboard = [
            [
                InlineKeyboardButton("🚀 Launch Now", callback_data="wiz|confirm|yes"),
                InlineKeyboardButton("❌ Cancel", callback_data="wiz|confirm|no"),
            ]
        ]
        summary = (
            "📋 *Review Execution Plan*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Pipeline: `{state['pipeline'].upper()}`\n"
            f"• Processing Step: `{state['step']}`\n"
            f"• Subjects: *{len(state['subjects'])} subjects* (`{', '.join(state['subjects'][:4])}{'...' if len(state['subjects']) > 4 else ''}`)\n"
            f"• Analysis Model: `{', '.join(state.get('analysis', [])) or 'Default'}`\n"
            f"• Parallel Cores (`--n_procs`): *{state['n_procs']}*\n\n"
            "Are you ready to start this run?"
        )
        await query.edit_message_text(summary, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

    # --- Final Confirmation ---
    elif action == "confirm":
        if data[2] == "yes":
            try:
                tracker = await pipeline_manager.launch_batch(
                    pipeline=state["pipeline"],
                    step=state["step"],
                    subjects=state["subjects"],
                    analysis=state.get("analysis"),
                    n_procs=state["n_procs"],
                    on_subject_milestone=lambda t, s, st: handle_subject_milestone(context.bot, t, s, st),
                    on_batch_complete=lambda t: handle_batch_complete(context.bot, t),
                )
                await query.edit_message_text(
                    f"🚀 *Batch Started (PID {tracker.process.pid})*\n"
                    f"Processing *{len(tracker.subjects)} subjects* across *{tracker.n_procs} cores*.\n\n"
                    f"_You will receive milestone updates as subjects finish._",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                await query.edit_message_text(f"❌ *Failed to start batch:*\n`{e}`", parse_mode=ParseMode.MARKDOWN)
        else:
            await query.edit_message_text("Execution cancelled.", parse_mode=ParseMode.MARKDOWN)
        WIZARD_STATE.pop(user_id, None)

async def show_cores_selection(query, state: Dict[str, Any]):
    keyboard = [
        [InlineKeyboardButton("1 Core (Sequential)", callback_data="wiz|cores|1"), InlineKeyboardButton("2 Cores", callback_data="wiz|cores|2")],
        [InlineKeyboardButton("4 Cores", callback_data="wiz|cores|4"), InlineKeyboardButton("8 Cores", callback_data="wiz|cores|8")],
    ]
    await query.edit_message_text(
        f"Step 5/5: Select CPU cores (`--n_procs`):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# -------------------------------------------------------------------------
# Milestone & Event Callbacks (Push Notifications)
# -------------------------------------------------------------------------

async def handle_subject_milestone(bot, tracker: BatchJobTracker, subject_id: str, state: Dict[str, Any]):
    """Called asynchronously whenever an individual subject finishes or fails."""
    status = state["status"]
    
    for chat_id in config.allowed_user_ids:
        if status == "SUCCESS":
            msg = (
                f"✅ *Subject Finished Successfully!*\n"
                f"• Subject: `{subject_id}` | Pipeline: `{tracker.pipeline.upper()}`\n"
                f"• Step: `{tracker.step}` | Batch Progress: *{tracker.progress_percent}%*\n"
            )
            
            # Attach Chauffeur images if enabled
            chauffeur_imgs = state.get("chauffeur_images", [])
            keyboard = None
            if chauffeur_imgs:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🖼️ Inspect QA", callback_data=f"view_qa|{tracker.pipeline}|{subject_id}")]
                ])

            await bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

            if config.auto_upload_chauffeur and chauffeur_imgs:
                selected_imgs = chauffeur_imgs[:config.max_chauffeur_images]
                try:
                    media_group = [
                        InputMediaPhoto(open(img, 'rb'), caption=os.path.basename(img) if i == 0 else "")
                        for i, img in enumerate(selected_imgs)
                    ]
                    await bot.send_media_group(chat_id=chat_id, media=media_group)
                except Exception as e:
                    logger.error(f"Error uploading chauffeur images for {subject_id}: {e}")

        elif status == "FAILED":
            err_text = state.get("error_snippet") or "Check logs for details."
            msg = (
                f"❌ *Analysis Failed for {subject_id}*\n"
                f"• Pipeline: `{tracker.pipeline.upper()}` | Step: `{tracker.step}`\n\n"
                f"📄 *Error Snippet:*\n```\n{err_text[:400]}\n```"
            )
            # Inline button to retry just this subject with 1 tap
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🔁 Retry {subject_id}", callback_data=f"retry|{tracker.pipeline}|{tracker.step}|{subject_id}|{','.join(tracker.analysis)}")]
            ])
            await bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


async def handle_batch_complete(bot, tracker: BatchJobTracker):
    """Called asynchronously when the entire multi-subject batch finishes."""
    total = len(tracker.subjects)
    succ = tracker.success_count
    fail = tracker.failed_count
    
    status_icon = "🎉" if fail == 0 else "⚠️"
    msg = (
        f"{status_icon} *Batch Run Finished!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Pipeline: `{tracker.pipeline.upper()}` ({tracker.step})\n"
        f"• Total Elapsed: *{tracker.formatted_elapsed}*\n"
        f"• Results: *{succ}/{total} Succeeded*, *{fail} Failed*\n\n"
        f"_Use `/qa` to review images or `/status` to verify system health._"
    )
    for chat_id in config.allowed_user_ids:
        await bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)


# -------------------------------------------------------------------------
# QA & Logs Inspection Handlers
# -------------------------------------------------------------------------

async def qa_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allow user to inspect QA images and PDFs for any subject."""
    if not is_authorized(update): return

    args = context.args
    if args and len(args) >= 2:
        pipeline, subject = args[0].lower(), args[1]
        await send_qa_artifacts_to_chat(update.effective_chat.id, context.bot, pipeline, subject)
        return

    # Interactive QA selector
    keyboard = [
        [InlineKeyboardButton("TIM Task", callback_data="qa_pick|tim"), InlineKeyboardButton("WAR Task", callback_data="qa_pick|war")]
    ]
    await update.message.reply_markdown("🖼️ *Inspect QA: Select Pipeline:*", reply_markup=InlineKeyboardMarkup(keyboard))


async def qa_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle QA button clicks."""
    query = update.callback_query
    await query.answer()
    if not is_authorized(update): return

    data = query.data.split("|")
    action = data[0]

    if action == "qa_pick":
        pipeline = data[1]
        p_info = pipeline_manager.get_pipeline_info(pipeline)
        subs = p_info["subjects"][:12] # Show top 12 subjects
        
        keyboard = []
        row = []
        for s in subs:
            row.append(InlineKeyboardButton(s, callback_data=f"view_qa|{pipeline}|{s}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)

        await query.edit_message_text(
            f"Select Subject for *{pipeline.upper()}* QA:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == "view_qa":
        pipeline, subject = data[1], data[2]
        await send_qa_artifacts_to_chat(query.message.chat_id, context.bot, pipeline, subject)


async def send_qa_artifacts_to_chat(chat_id: int, bot, pipeline: str, subject: str):
    """Upload chauffeur PNGs and QC PDFs to Telegram chat."""
    qa = pipeline_manager.find_qa_artifacts(pipeline, subject)
    imgs = qa["chauffeur_images"]
    pdfs = qa["qc_pdfs"]

    if not imgs and not pdfs:
        await bot.send_message(chat_id=chat_id, text=f"No QA images or PDFs found for `{subject}` in `{pipeline}`.", parse_mode=ParseMode.MARKDOWN)
        return

    await bot.send_message(chat_id=chat_id, text=f"🔍 Uploading QA artifacts for *{subject}* ({len(imgs)} images, {len(pdfs)} PDFs)...", parse_mode=ParseMode.MARKDOWN)

    # Send images in albums of up to 5
    if imgs:
        for i in range(0, min(len(imgs), 10), 5):
            batch = imgs[i:i+5]
            media = [InputMediaPhoto(open(f, 'rb'), caption=os.path.basename(f) if j == 0 else "") for j, f in enumerate(batch)]
            try:
                await bot.send_media_group(chat_id=chat_id, media=media)
            except Exception as e:
                logger.error(f"Failed to upload media group: {e}")

    # Send up to 2 PDFs
    for pdf in pdfs[:2]:
        try:
            await bot.send_document(chat_id=chat_id, document=open(pdf, 'rb'), caption=os.path.basename(pdf))
        except Exception as e:
            logger.error(f"Failed to upload PDF: {e}")


async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tail recent logs for debugging."""
    if not is_authorized(update): return

    args = context.args
    if args and len(args) >= 2:
        pipeline, subject = args[0].lower(), args[1]
        log_text = pipeline_manager.get_log_tail(pipeline, subject)
        await update.message.reply_markdown(log_text)
        return

    recent = get_recent_logs(config.repo_root, limit=6)
    if not recent:
        await update.message.reply_text("No recent log files found.")
        return

    keyboard = [
        [InlineKeyboardButton(f"{r['icon']} {r['filename']}", callback_data=f"read_log|{r['pipeline']}|{r['subject']}")]
        for r in recent
    ]
    await update.message.reply_markdown("📋 *Select a log file to view tail:*", reply_markup=InlineKeyboardMarkup(keyboard))


async def logs_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle log file selection callback."""
    query = update.callback_query
    await query.answer()
    if not is_authorized(update): return

    data = query.data.split("|")
    pipeline, subject = data[1], data[2]
    log_text = pipeline_manager.get_log_tail(pipeline, subject)
    await query.message.reply_markdown(log_text)


async def retry_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 1-tap retry button for failed subjects."""
    query = update.callback_query
    await query.answer()
    if not is_authorized(update): return

    data = query.data.split("|")
    pipeline, step, subject = data[1], data[2], data[3]
    analyses = data[4].split(",") if len(data) > 4 and data[4] else None

    await query.edit_message_text(f"🔄 Re-launching `{subject}` ({step})...", parse_mode=ParseMode.MARKDOWN)

    try:
        tracker = await pipeline_manager.launch_batch(
            pipeline=pipeline,
            step=step,
            subjects=[subject],
            analysis=analyses,
            n_procs=1,
            on_subject_milestone=lambda t, s, st: handle_subject_milestone(context.bot, t, s, st),
            on_batch_complete=lambda t: handle_batch_complete(context.bot, t),
        )
        await query.message.reply_markdown(f"🚀 Re-run started for `{subject}` (PID `{tracker.process.pid}`).")
    except Exception as e:
        await query.message.reply_markdown(f"❌ Failed to re-launch: `{e}`")


async def kill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Terminate currently running batch job."""
    if not is_authorized(update): return

    if pipeline_manager.active_batch and pipeline_manager.active_batch.is_running:
        pid = pipeline_manager.active_batch.process.pid
        ok = pipeline_manager.kill_active_batch()
        if ok:
            await update.message.reply_markdown(f"🛑 *Batch Terminated:* Sent termination signal to PID `{pid}`.")
        else:
            await update.message.reply_markdown(f"⚠️ *Warning:* Failed to terminate PID `{pid}`.")
    else:
        await update.message.reply_text("No active batch currently managed by the bot to kill.")


async def text_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route button presses from the persistent reply keyboard."""
    if not is_authorized(update): return

    text = update.message.text
    if text == "📊 Status":
        await status_command(update, context)
    elif text == "🚀 Run Job":
        await run_command(update, context)
    elif text == "🖼️ Inspect QA":
        await qa_command(update, context)
    elif text == "📋 View Logs":
        await logs_command(update, context)
    else:
        await update.message.reply_text("Type /help to see available commands.")


# -------------------------------------------------------------------------
# Main Daemon Entry Point
# -------------------------------------------------------------------------

def main():
    validation_errors = config.validate()
    if validation_errors:
        print("\n[Configuration Errors Found]:", file=sys.stderr)
        for err in validation_errors:
            print(f"  ❌ {err}", file=sys.stderr)
        print("\nPlease copy 'bot_config.template.toml' to 'bot_config.toml' and fill in your Bot Token and User ID.\n", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print(" Abend Lab MRI Remote Monitor Bot Daemon Starting")
    print(f" • Repository Root: {config.repo_root}")
    print(f" • Authorized Users: {config.allowed_user_ids}")
    print(f" • Default Pipeline: {config.default_pipeline}")
    print("=" * 60)

    app = ApplicationBuilder().token(config.bot_token).build()

    # Register Command Handlers
    app.add_handler(CommandHandler(["start", "help"], start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("run", run_command))
    app.add_handler(CommandHandler("qa", qa_command))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("kill", kill_command))

    # Register Callback Handlers (Inline Buttons)
    app.add_handler(CallbackQueryHandler(wizard_callback_handler, pattern=r"^wiz\|"))
    app.add_handler(CallbackQueryHandler(qa_callback_handler, pattern=r"^(qa_pick|view_qa)\|"))
    app.add_handler(CallbackQueryHandler(logs_callback_handler, pattern=r"^read_log\|"))
    app.add_handler(CallbackQueryHandler(retry_callback_handler, pattern=r"^retry\|"))

    # Register Text Message Router (Main Keyboard Buttons)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_router))

    logger.info("Bot is polling Telegram. Ready to accept commands!")
    app.run_polling()

if __name__ == "__main__":
    main()
