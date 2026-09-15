import os
import sys
from pathlib import Path
from typing import List, Optional
try:
    import tomllib
    def load_toml(path: str) -> dict:
        with open(path, "rb") as f:
            return tomllib.load(f)
except ImportError:
    try:
        import toml
        def load_toml(path: str) -> dict:
            with open(path, "r", encoding="utf-8") as f:
                return toml.load(f)
    except ImportError:
        load_toml = None

class BotConfig:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = self._find_config_file(config_path)
        self.raw_data = {}
        if self.config_path and os.path.exists(self.config_path):
            if load_toml is not None:
                try:
                    self.raw_data = load_toml(self.config_path)
                except Exception as e:
                    print(f"[Warning] Failed to parse config file {self.config_path}: {e}", file=sys.stderr)
            else:
                print(f"[Warning] Neither tomllib nor toml library found to parse {self.config_path}", file=sys.stderr)

        # Telegram Settings
        tg = self.raw_data.get("telegram", {})
        self.bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", tg.get("bot_token", ""))
        
        # Allowed Users
        allowed_env = os.getenv("ALLOWED_USER_IDS")
        if allowed_env:
            self.allowed_user_ids: List[int] = [int(x.strip()) for x in allowed_env.split(",") if x.strip().isdigit()]
        else:
            self.allowed_user_ids: List[int] = tg.get("allowed_user_ids", [])

        # Pipelines Settings
        pipelines_sec = self.raw_data.get("pipelines", {})
        configured_repo_root = pipelines_sec.get("repo_root", "").strip()
        if configured_repo_root and os.path.isdir(configured_repo_root):
            self.repo_root = os.path.abspath(configured_repo_root)
        else:
            # Default to the parent directory of remote_monitor
            self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        self.default_pipeline: str = pipelines_sec.get("default_pipeline", "tim").lower()
        self.monitored_storage_paths: List[str] = pipelines_sec.get("monitored_storage_paths", ["/"])

        # Notifications Settings
        notif_sec = self.raw_data.get("notifications", {})
        self.auto_upload_chauffeur: bool = notif_sec.get("auto_upload_chauffeur", True)
        self.max_chauffeur_images: int = int(notif_sec.get("max_chauffeur_images", 6))
        self.auto_upload_qc_pdf: bool = notif_sec.get("auto_upload_qc_pdf", True)
        self.auto_export_results: bool = notif_sec.get("auto_export_results", True)
        self.poll_interval_seconds: int = int(notif_sec.get("poll_interval_seconds", 15))

    def _find_config_file(self, explicit_path: Optional[str]) -> Optional[str]:
        if explicit_path and os.path.exists(explicit_path):
            return explicit_path
        env_path = os.getenv("BOT_CONFIG_PATH")
        if env_path and os.path.exists(env_path):
            return env_path

        current_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(current_dir, "bot_config.toml"),
            os.path.join(current_dir, "..", "bot_config.toml"),
            os.path.join(os.getcwd(), "bot_config.toml"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None

    @property
    def tim_dir(self) -> str:
        return os.path.join(self.repo_root, "tim_analysis")

    @property
    def war_dir(self) -> str:
        return os.path.join(self.repo_root, "war_analysis")

    def get_pipeline_dir(self, pipeline: str) -> str:
        p = pipeline.lower()
        if "tim" in p:
            return self.tim_dir
        elif "war" in p:
            return self.war_dir
        raise ValueError(f"Unknown pipeline: '{pipeline}'. Expected 'tim' or 'war'.")

    def is_user_allowed(self, user_id: int) -> bool:
        if not self.allowed_user_ids:
            # If no allowed users configured, warn and deny for safety
            return False
        return user_id in self.allowed_user_ids

    def validate(self) -> List[str]:
        errors = []
        if not self.bot_token or self.bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
            errors.append("Telegram bot token is not configured in bot_config.toml or TELEGRAM_BOT_TOKEN environment variable.")
        if not self.allowed_user_ids:
            errors.append("allowed_user_ids is empty in bot_config.toml. You must add your Telegram numeric user ID.")
        if not os.path.isdir(self.tim_dir) and not os.path.isdir(self.war_dir):
            errors.append(f"Cannot find tim_analysis or war_analysis directories inside repo root: {self.repo_root}")
        return errors

# Global default instance
config = BotConfig()
