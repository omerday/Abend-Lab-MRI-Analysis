#!/usr/bin/env python3
"""
Abend Lab MRI Analysis - Telegram Bot Daemon
Provides remote monitoring, QA inspection, and execution control from a smartphone.
Uses HTML formatting and robust escaping to prevent entity parse errors.
"""

import os
import sys
import glob
import html
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

def h(text: Any) -> str:
    """HTML escape helper for safe Telegram message formatting."""
    return html.escape(str(text)) if text is not None else ""

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

SUBJECTS_PER_PAGE = 12

# -------------------------------------------------------------------------
# Command Handlers
# -------------------------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start and /help commands."""
    if not is_authorized(update):
        await update.message.reply_text(
            "⛔ <b>Unauthorized Access</b>\nYour Telegram user ID is not authorized to control this server.", 
            parse_mode=ParseMode.HTML
        )
        return

    welcome_text = (
        "🧠 <b>Abend Lab fMRI Remote Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Welcome! Use this bot to monitor analyses, review QA images, and control batch jobs while away.\n\n"
        "<b>Quick Commands:</b>\n"
        "• <code>/status</code> — View system resources, active jobs, and recent log states.\n"
        "• <code>/run</code> — Launch single or multi-subject batch jobs with interactive menus.\n"
        "• <code>/qa</code> — Inspect <code>@chauffeur_afni</code> axial montage PNGs and QC PDFs.\n"
        "• <code>/logs</code> — Read live log tails from recent runs.\n"
        "• <code>/kill</code> — Cancel an active running batch.\n\n"
        "<i>Tip: You can also use the touch buttons below on your phone screen.</i>"
    )
    await update.message.reply_text(welcome_text, reply_markup=MAIN_KEYBOARD, parse_mode=ParseMode.HTML)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and send system metrics, active AFNI jobs, and batch status."""
    if not is_authorized(update): return

    msg_parts = ["<b>🧠 Abend Lab System &amp; Pipeline Status</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━"]

    # 1. Active Batch Job (if launched through bot)
    tracker = pipeline_manager.active_batch
    if tracker and tracker.is_running:
        pct = tracker.progress_percent
        bar_len = 10
        filled = int((pct / 100) * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        
        msg_parts.append(
            f"🔄 <b>Active Batch:</b> <code>{h(tracker.pipeline.upper())}</code> ({h(tracker.step)})\n"
            f"⏱️ Elapsed: <b>{h(tracker.formatted_elapsed)}</b> | Cores: <b>{tracker.n_procs}</b>\n"
            f"📈 Progress: <code>[{bar}]</code> <b>{pct}%</b> ({tracker.completed_count}/{len(tracker.subjects)} Subjects)\n"
        )
        
        running_subs = [s for s, st in tracker.subject_states.items() if st["status"] == "RUNNING"]
        queued_subs = [s for s, st in tracker.subject_states.items() if st["status"] == "QUEUED"]
        success_subs = [s for s, st in tracker.subject_states.items() if st["status"] == "SUCCESS"]
        failed_subs = [s for s, st in tracker.subject_states.items() if st["status"] == "FAILED"]

        if running_subs:
            msg_parts.append("⚡ <b>Currently Processing:</b>")
            for s in running_subs[:4]:
                st = tracker.subject_states[s]
                msg_parts.append(f"• <code>{h(s)}</code>: ⏳ <i>{h(st['current_step'])}</i>")
        
        if failed_subs:
            msg_parts.append(f"❌ <b>Failed:</b> {', '.join([f'<code>{h(s)}</code>' for s in failed_subs])}")
        
        if success_subs:
            msg_parts.append(f"✅ <b>Completed:</b> {len(success_subs)} subjects")

        msg_parts.append("")
    else:
        # Check if AFNI / Python processes are running in terminal
        active_procs = get_active_afni_processes()
        if active_procs:
            msg_parts.append(f"⚙️ <b>Running Processes ({len(active_procs)} active):</b>")
            for p in active_procs[:5]:
                sub_label = f"[{h(p['subject'])}] " if p['subject'] else ""
                msg_parts.append(f"• <code>{h(p['name'])}</code> (PID {p['pid']}): {sub_label}<i>{h(p['keyword'])}</i> ({h(p['elapsed'])})")
            msg_parts.append("")
        else:
            msg_parts.append("💤 <i>No active analyses currently running.</i>\n")

    # 2. System Hardware Metrics
    metrics = get_system_metrics(config.monitored_storage_paths)
    msg_parts.append(
        f"💻 <b>Host Resources:</b>\n"
        f"• CPU: <b>{metrics['cpu_percent']}%</b> | RAM: <b>{metrics['ram_used']}</b> / {metrics['ram_total']} (<b>{metrics['ram_percent']}%</b>)"
    )
    for d in metrics["disks"]:
        msg_parts.append(f"• Storage (<code>{h(d['path'])}</code>): <b>{h(d['free'])} free</b> ({d['percent_used']}% used)")
    msg_parts.append("")

    # 3. Recent Logs
    logs = get_recent_logs(config.repo_root, limit=5)
    if logs:
        msg_parts.append("📋 <b>Recent Log Runs:</b>")
        for l in logs:
            msg_parts.append(f"{l['icon']} <code>{h(l['subject'])}</code> ({h(l['pipeline'])}) — <i>{h(l['modified_time'])}</i>\n   └ <code>{h(l['last_line'])}</code>")

    await update.message.reply_text("\n".join(msg_parts), parse_mode=ParseMode.HTML)


# -------------------------------------------------------------------------
# Interactive Run Wizard Handlers
# -------------------------------------------------------------------------

WIZARD_STATE: Dict[int, Dict[str, Any]] = {}

async def run_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /run command either with CLI arguments or via interactive wizard."""
    if not is_authorized(update): return

    args = context.args
    if args and len(args) >= 2:
        await launch_from_cli_args(update, context, args)
        return

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
    await update.message.reply_text(
        "🚀 <b>Launch Analysis Wizard</b>\nStep 1/5: Select which pipeline to run:",
        parse_mode=ParseMode.HTML,
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
        await update.message.reply_text(
            f"🚀 <b>Batch Dispatched Successfully!</b>\n"
            f"• Pipeline: <code>{h(pipeline.upper())}</code> | Step: <code>{h(step)}</code>\n"
            f"• Subjects: <b>{len(tracker.subjects)} subjects</b> | Cores: <b>{n_procs}</b>\n"
            f"• PID: <code>{tracker.process.pid}</code>\n\n"
            f"<i>You will receive real-time notifications as each subject finishes.</i>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Failed to start batch:</b>\n<code>{h(e)}</code>", parse_mode=ParseMode.HTML)


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
            f"Selected Pipeline: <b>{h(state['pipeline'].upper())}</b>\n\nStep 2/5: Select processing step:",
            parse_mode=ParseMode.HTML,
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
            f"Step: <b>{h(state['step'])}</b>\n\nStep 3/5: Select subject scope:",
            parse_mode=ParseMode.HTML,
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
            recent = get_recent_logs(config.repo_root, limit=25)
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
                f"Subjects: <b>{len(state['subjects'])} selected</b>\n\nStep 4/5: Select Analysis Model:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
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
            "📋 <b>Review Execution Plan</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Pipeline: <code>{h(state['pipeline'].upper())}</code>\n"
            f"• Processing Step: <code>{h(state['step'])}</code>\n"
            f"• Subjects: <b>{len(state['subjects'])} subjects</b> (<code>{', '.join([h(s) for s in state['subjects'][:4]])}{'...' if len(state['subjects']) > 4 else ''}</code>)\n"
            f"• Analysis Model: <code>{', '.join([h(a) for a in state.get('analysis', [])]) or 'Default'}</code>\n"
            f"• Parallel Cores (<code>--n_procs</code>): <b>{state['n_procs']}</b>\n\n"
            "Are you ready to start this run?"
        )
        await query.edit_message_text(summary, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

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
                    f"🚀 <b>Batch Started (PID {tracker.process.pid})</b>\n"
                    f"Processing <b>{len(tracker.subjects)} subjects</b> across <b>{tracker.n_procs} cores</b>.\n\n"
                    f"<i>You will receive milestone updates as subjects finish.</i>",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                await query.edit_message_text(f"❌ <b>Failed to start batch:</b>\n<code>{h(e)}</code>", parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text("Execution cancelled.", parse_mode=ParseMode.HTML)
        WIZARD_STATE.pop(user_id, None)

async def show_cores_selection(query, state: Dict[str, Any]):
    keyboard = [
        [InlineKeyboardButton("1 Core (Sequential)", callback_data="wiz|cores|1"), InlineKeyboardButton("2 Cores", callback_data="wiz|cores|2")],
        [InlineKeyboardButton("4 Cores", callback_data="wiz|cores|4"), InlineKeyboardButton("8 Cores", callback_data="wiz|cores|8")],
    ]
    await query.edit_message_text(
        "Step 5/5: Select CPU cores (<code>--n_procs</code>):",
        parse_mode=ParseMode.HTML,
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
                f"✅ <b>Subject Finished Successfully!</b>\n"
                f"• Subject: <code>{h(subject_id)}</code> | Pipeline: <code>{h(tracker.pipeline.upper())}</code>\n"
                f"• Step: <code>{h(tracker.step)}</code> | Batch Progress: <b>{tracker.progress_percent}%</b>\n"
            )
            
            chauffeur_imgs = state.get("chauffeur_images", [])
            keyboard = None
            if chauffeur_imgs:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🖼️ Inspect QA", callback_data=f"view_qa|{tracker.pipeline}|{subject_id}|0")]
                ])

            await bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML, reply_markup=keyboard)

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
                f"❌ <b>Analysis Failed for {h(subject_id)}</b>\n"
                f"• Pipeline: <code>{h(tracker.pipeline.upper())}</code> | Step: <code>{h(tracker.step)}</code>\n\n"
                f"📄 <b>Error Snippet:</b>\n<pre>{h(err_text[:400])}</pre>"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🔁 Retry {subject_id}", callback_data=f"retry|{tracker.pipeline}|{tracker.step}|{subject_id}|{','.join(tracker.analysis)}")]
            ])
            await bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def handle_batch_complete(bot, tracker: BatchJobTracker):
    """Called asynchronously when the entire multi-subject batch finishes."""
    total = len(tracker.subjects)
    succ = tracker.success_count
    fail = tracker.failed_count
    
    status_icon = "🎉" if fail == 0 else "⚠️"
    msg = (
        f"{status_icon} <b>Batch Run Finished!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Pipeline: <code>{h(tracker.pipeline.upper())}</code> ({h(tracker.step)})\n"
        f"• Total Elapsed: <b>{h(tracker.formatted_elapsed)}</b>\n"
        f"• Results: <b>{succ}/{total} Succeeded</b>, <b>{fail} Failed</b>\n\n"
        f"<i>Use <code>/qa</code> to review images or <code>/status</code> to verify system health.</i>"
    )
    for chat_id in config.allowed_user_ids:
        await bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)


# -------------------------------------------------------------------------
# QA Inspection with Model Selection & Group Analysis
# -------------------------------------------------------------------------

async def qa_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allow user to inspect QA images and PDFs for any subject or group analysis."""
    if not is_authorized(update): return

    args = context.args
    if args and len(args) >= 2:
        pipeline, target = args[0].lower(), args[1]
        model = args[2] if len(args) > 2 else None
        if target.lower() == "group":
            await send_group_qa_artifacts_to_chat(update.effective_chat.id, context.bot, pipeline, model)
        else:
            await send_qa_artifacts_to_chat(update.effective_chat.id, context.bot, pipeline, target, analysis=model)
        return

    tim_info = pipeline_manager.get_pipeline_info("tim")
    war_info = pipeline_manager.get_pipeline_info("war")
    keyboard = [
        [
            InlineKeyboardButton(f"🧠 TIM: Single Subjects ({len(tim_info['subjects'])})", callback_data="qa_page|tim|0"),
            InlineKeyboardButton("🧠 TIM: Group Analyses", callback_data="qa_group|tim"),
        ],
        [
            InlineKeyboardButton(f"⚔️ WAR: Single Subjects ({len(war_info['subjects'])})", callback_data="qa_page|war|0"),
            InlineKeyboardButton("⚔️ WAR: Group Analyses", callback_data="qa_group|war"),
        ],
    ]
    await update.message.reply_text("🖼️ <b>Inspect QA: Select Category</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


async def qa_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle QA button clicks, subject pagination, model selection, and group analysis."""
    query = update.callback_query
    await query.answer()
    if not is_authorized(update): return

    data = query.data.split("|")
    action = data[0]

    # --- Home Menu ---
    if action == "qa_home":
        tim_info = pipeline_manager.get_pipeline_info("tim")
        war_info = pipeline_manager.get_pipeline_info("war")
        keyboard = [
            [
                InlineKeyboardButton(f"🧠 TIM: Single Subjects ({len(tim_info['subjects'])})", callback_data="qa_page|tim|0"),
                InlineKeyboardButton("🧠 TIM: Group Analyses", callback_data="qa_group|tim"),
            ],
            [
                InlineKeyboardButton(f"⚔️ WAR: Single Subjects ({len(war_info['subjects'])})", callback_data="qa_page|war|0"),
                InlineKeyboardButton("⚔️ WAR: Group Analyses", callback_data="qa_group|war"),
            ],
        ]
        await query.edit_message_text("🖼️ <b>Inspect QA: Select Category</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

    # --- Subject Pagination ---
    elif action == "qa_page":
        pipeline = data[1]
        page = int(data[2])
        p_info = pipeline_manager.get_pipeline_info(pipeline)
        all_subs = p_info["subjects"]
        total_subs = len(all_subs)

        total_pages = max(1, (total_subs + SUBJECTS_PER_PAGE - 1) // SUBJECTS_PER_PAGE)
        page = max(0, min(page, total_pages - 1))

        start_idx = page * SUBJECTS_PER_PAGE
        end_idx = min(start_idx + SUBJECTS_PER_PAGE, total_subs)
        page_subs = all_subs[start_idx:end_idx]

        keyboard = []
        row = []
        for s in page_subs:
            row.append(InlineKeyboardButton(s, callback_data=f"qa_subj_models|{pipeline}|{s}|{page}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"qa_page|{pipeline}|{page - 1}"))
        nav_row.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="qa_noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"qa_page|{pipeline}|{page + 1}"))
        keyboard.append(nav_row)

        keyboard.append([InlineKeyboardButton("🔙 Switch Pipeline / Group", callback_data="qa_home")])

        await query.edit_message_text(
            f"🖼️ Select Subject for <b>{h(pipeline.upper())}</b> QA (Total: {total_subs}):\n<i>Page {page + 1} of {total_pages}</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # --- Model Selection for a Specific Subject ---
    elif action == "qa_subj_models":
        pipeline, subject = data[1], data[2]
        return_page = int(data[3]) if len(data) > 3 and data[3].isdigit() else 0

        models = pipeline_manager.get_subject_available_models(pipeline, subject)
        keyboard = []

        for m in models:
            badge = f" ({m['image_count']} imgs)" if m["image_count"] > 0 else (" (PDF)" if m["pdf_count"] > 0 else "")
            icon = "✅ " if m["has_data"] else "⚪ "
            btn_text = f"{icon}{m['label']}{badge}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"view_qa|{pipeline}|{subject}|{m['id']}|{return_page}")])

        # All models option
        keyboard.append([InlineKeyboardButton("🌟 All Analyses Combined", callback_data=f"view_qa|{pipeline}|{subject}|all|{return_page}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Subjects", callback_data=f"qa_page|{pipeline}|{return_page}")])

        await query.edit_message_text(
            f"🔬 <b>Subject: {h(subject)}</b> ({h(pipeline.upper())})\nSelect which analysis model to view QA for:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # --- Group Analysis Model Picker ---
    elif action == "qa_group":
        pipeline = data[1]
        group_models = pipeline_manager.get_available_group_models(pipeline)
        
        keyboard = []
        for gm in group_models:
            badge = f" ({gm['image_count']} imgs)" if gm["image_count"] > 0 else ""
            icon = "📊 " if gm["has_data"] else "⚪ "
            btn_text = f"{icon}{gm['label']}{badge}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"view_group_qa|{pipeline}|{gm['id']}")])

        keyboard.append([InlineKeyboardButton("🔙 Back to Main Categories", callback_data="qa_home")])

        await query.edit_message_text(
            f"📊 <b>{h(pipeline.upper())} Group Analyses</b>\nSelect a group model to inspect statistical montages:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # --- View Subject QA Artifacts ---
    elif action == "view_qa":
        pipeline, subject, model = data[1], data[2], data[3]
        return_page = int(data[4]) if len(data) > 4 and data[4].isdigit() else 0
        analysis_filter = None if model == "all" else model
        await send_qa_artifacts_to_chat(query.message.chat_id, context.bot, pipeline, subject, analysis=analysis_filter, return_page=return_page)

    # --- View Group QA Artifacts ---
    elif action == "view_group_qa":
        pipeline, group_model = data[1], data[2]
        await send_group_qa_artifacts_to_chat(query.message.chat_id, context.bot, pipeline, group_model)

    elif action == "qa_noop":
        pass


async def send_qa_artifacts_to_chat(chat_id: int, bot, pipeline: str, subject: str, analysis: Optional[str] = None, return_page: int = 0):
    """Upload chauffeur PNGs and QC PDFs for a subject with clear model captions."""
    qa = pipeline_manager.find_qa_artifacts(pipeline, subject, analysis=analysis)
    annotated_imgs = qa.get("annotated_images", [])
    imgs = qa["chauffeur_images"]
    pdfs = qa["qc_pdfs"]

    back_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 Back to Models", callback_data=f"qa_subj_models|{pipeline}|{subject}|{return_page}"),
            InlineKeyboardButton("👥 Other Subjects", callback_data=f"qa_page|{pipeline}|{return_page}")
        ]
    ])

    model_label = f"Model: <code>{h(analysis)}</code>" if analysis else "All Models"

    if not imgs and not pdfs:
        await bot.send_message(
            chat_id=chat_id, 
            text=f"No QA images or PDFs found for <code>{h(subject)}</code> ({model_label}).", 
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard
        )
        return

    await bot.send_message(
        chat_id=chat_id, 
        text=f"🔍 Uploading QA artifacts for <b>{h(subject)}</b> [{model_label}] ({len(imgs)} images, {len(pdfs)} PDFs)...", 
        parse_mode=ParseMode.HTML
    )

    # Send images in albums of up to 5 with detailed captions
    if annotated_imgs:
        for i in range(0, min(len(annotated_imgs), 10), 5):
            batch = annotated_imgs[i:i+5]
            media = []
            for item in batch:
                caption = f"🧠 {subject} | {item['model']}\nContrast/Stim: {item['stimulus']}"
                media.append(InputMediaPhoto(open(item['path'], 'rb'), caption=caption))
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

    await bot.send_message(
        chat_id=chat_id,
        text=f"✅ Finished sending artifacts for <b>{h(subject)}</b> ({model_label}).",
        parse_mode=ParseMode.HTML,
        reply_markup=back_keyboard
    )


async def send_group_qa_artifacts_to_chat(chat_id: int, bot, pipeline: str, group_model: str):
    """Upload group analysis statistical montages and PDFs with informative captions."""
    qa = pipeline_manager.find_group_qa_artifacts(pipeline, group_model=group_model)
    annotated_imgs = qa.get("annotated_images", [])
    pdfs = qa["qc_pdfs"]

    back_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Group Analyses", callback_data=f"qa_group|{pipeline}")]
    ])

    if not annotated_imgs and not pdfs:
        await bot.send_message(
            chat_id=chat_id, 
            text=f"No group QA images found for model <code>{h(group_model)}</code> in <code>{h(pipeline.upper())}</code>.", 
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard
        )
        return

    await bot.send_message(
        chat_id=chat_id, 
        text=f"📊 Uploading group statistical montages for <b>{h(group_model)}</b> ({len(annotated_imgs)} images)...", 
        parse_mode=ParseMode.HTML
    )

    if annotated_imgs:
        for i in range(0, min(len(annotated_imgs), 10), 5):
            batch = annotated_imgs[i:i+5]
            media = []
            for item in batch:
                caption = f"📊 Group: {group_model} ({pipeline.upper()})\nSub-brick / Contrast: {item['stimulus']}"
                media.append(InputMediaPhoto(open(item['path'], 'rb'), caption=caption))
            try:
                await bot.send_media_group(chat_id=chat_id, media=media)
            except Exception as e:
                logger.error(f"Failed to upload group media group: {e}")

    for pdf in pdfs[:2]:
        try:
            await bot.send_document(chat_id=chat_id, document=open(pdf, 'rb'), caption=os.path.basename(pdf))
        except Exception as e:
            logger.error(f"Failed to upload group PDF: {e}")

    await bot.send_message(
        chat_id=chat_id,
        text=f"✅ Finished sending group artifacts for <b>{h(group_model)}</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=back_keyboard
    )


# -------------------------------------------------------------------------
# Logs Inspection Handlers
# -------------------------------------------------------------------------

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tail recent logs for debugging."""
    if not is_authorized(update): return

    args = context.args
    if args and len(args) >= 2:
        pipeline, subject = args[0].lower(), args[1]
        log_text = pipeline_manager.get_log_tail(pipeline, subject)
        await update.message.reply_text(f"<pre>{h(log_text)}</pre>", parse_mode=ParseMode.HTML)
        return

    recent = get_recent_logs(config.repo_root, limit=6)
    if not recent:
        await update.message.reply_text("No recent log files found.")
        return

    keyboard = [
        [InlineKeyboardButton(f"{r['icon']} {r['filename']}", callback_data=f"read_log|{r['pipeline']}|{r['subject']}")]
        for r in recent
    ]
    await update.message.reply_text("📋 <b>Select a log file to view tail:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


async def logs_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle log file selection callback."""
    query = update.callback_query
    await query.answer()
    if not is_authorized(update): return

    data = query.data.split("|")
    pipeline, subject = data[1], data[2]
    log_text = pipeline_manager.get_log_tail(pipeline, subject)
    await query.message.reply_text(f"<pre>{h(log_text)}</pre>", parse_mode=ParseMode.HTML)


async def retry_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 1-tap retry button for failed subjects."""
    query = update.callback_query
    await query.answer()
    if not is_authorized(update): return

    data = query.data.split("|")
    pipeline, step, subject = data[1], data[2], data[3]
    analyses = data[4].split(",") if len(data) > 4 and data[4] else None

    await query.edit_message_text(f"🔄 Re-launching <code>{h(subject)}</code> ({h(step)})...", parse_mode=ParseMode.HTML)

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
        await query.message.reply_text(f"🚀 Re-run started for <code>{h(subject)}</code> (PID <code>{tracker.process.pid}</code>).", parse_mode=ParseMode.HTML)
    except Exception as e:
        await query.message.reply_text(f"❌ Failed to re-launch: <code>{h(e)}</code>", parse_mode=ParseMode.HTML)


async def kill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Terminate currently running batch job."""
    if not is_authorized(update): return

    if pipeline_manager.active_batch and pipeline_manager.active_batch.is_running:
        pid = pipeline_manager.active_batch.process.pid
        ok = pipeline_manager.kill_active_batch()
        if ok:
            await update.message.reply_text(f"🛑 <b>Batch Terminated:</b> Sent termination signal to PID <code>{pid}</code>.", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"⚠️ <b>Warning:</b> Failed to terminate PID <code>{pid}</code>.", parse_mode=ParseMode.HTML)
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


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global exception handler to capture and log any unhandled update errors."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            err_msg = str(context.error)
            await update.effective_message.reply_text(
                f"⚠️ <b>An error occurred:</b>\n<code>{h(err_msg)}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass


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

    # Register Error Handler
    app.add_error_handler(global_error_handler)

    # Register Command Handlers
    app.add_handler(CommandHandler(["start", "help"], start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("run", run_command))
    app.add_handler(CommandHandler("qa", qa_command))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("kill", kill_command))

    # Register Callback Handlers (Inline Buttons)
    app.add_handler(CallbackQueryHandler(wizard_callback_handler, pattern=r"^wiz\|"))
    app.add_handler(CallbackQueryHandler(qa_callback_handler, pattern=r"^(qa_page|qa_subj_models|qa_group|qa_home|qa_noop|view_qa|view_group_qa)($|\|)"))
    app.add_handler(CallbackQueryHandler(logs_callback_handler, pattern=r"^read_log\|"))
    app.add_handler(CallbackQueryHandler(retry_callback_handler, pattern=r"^retry\|"))

    # Register Text Message Router (Main Keyboard Buttons)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_router))

    logger.info("Bot is polling Telegram. Ready to accept commands!")
    app.run_polling()

if __name__ == "__main__":
    main()
