"""
Configuration loader and validator for the Abend Lab Remote Monitoring Bot.

Supports TOML parsing via standard library `tomllib` (Python 3.11+) with
automatic fallback to `toml` package, environment variable overrides,
and fail-closed access control.
"""

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger("remote_monitor.config")

# TOML Loader Setup
load_toml: Optional[Callable[[Union[str, Path]], Dict[str, Any]]] = None

try:
    import tomllib

    def _load_tomllib(path: Union[str, Path]) -> Dict[str, Any]:
        with open(path, "rb") as f:
            return tomllib.load(f)

    load_toml = _load_tomllib
except ImportError:
    try:
        import toml

        def _load_toml_pkg(path: Union[str, Path]) -> Dict[str, Any]:
            with open(path, "r", encoding="utf-8") as f:
                return toml.load(f)

        load_toml = _load_toml_pkg
    except ImportError:
        load_toml = None


class BotConfig:
    """
    Parses, validates, and provides access to Telegram bot and pipeline configurations.

    Attributes
    ----------
    config_path : Optional[str]
        Resolved path to the loaded TOML configuration file.
    raw_data : Dict[str, Any]
        Raw parsed dictionary from TOML.
    bot_token : str
        Telegram bot API token.
    allowed_user_ids : List[int]
        Whitelisted numeric Telegram user IDs.
    repo_root : str
        Absolute path to the MRI analysis repository root.
    default_pipeline : str
        Default pipeline identifier ('tim' or 'war').
    monitored_storage_paths : List[str]
        List of filesystem paths monitored for disk space.
    auto_upload_chauffeur : bool
        Whether to automatically push chauffeur axial montage PNGs on step completion.
    max_chauffeur_images : int
        Maximum number of montage PNGs to upload per subject.
    auto_upload_qc_pdf : bool
        Whether to upload QC PDF reports on completion.
    auto_export_results : bool
        Whether to trigger export_results.py automatically upon subject completion.
    poll_interval_seconds : int
        Polling frequency in seconds for active batch monitoring.
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config_path: Optional[str] = self._find_config_file(config_path)
        self.raw_data: Dict[str, Any] = {}

        if self.config_path and os.path.exists(self.config_path):
            if load_toml is not None:
                try:
                    self.raw_data = load_toml(self.config_path)
                except Exception as e:
                    logger.warning("Failed to parse config file %s: %s", self.config_path, e)
            else:
                logger.warning(
                    "Neither tomllib nor toml library found to parse config %s",
                    self.config_path,
                )

        # Telegram Settings
        tg = self.raw_data.get("telegram", {})
        self.bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", tg.get("bot_token", ""))

        # Allowed Users
        allowed_env = os.getenv("ALLOWED_USER_IDS")
        if allowed_env:
            self.allowed_user_ids: List[int] = [
                int(x.strip()) for x in allowed_env.split(",") if x.strip().isdigit()
            ]
        else:
            self.allowed_user_ids: List[int] = tg.get("allowed_user_ids", [])

        # Pipelines Settings
        pipelines_sec = self.raw_data.get("pipelines", {})
        configured_repo_root = pipelines_sec.get("repo_root", "").strip()
        if configured_repo_root and os.path.isdir(configured_repo_root):
            self.repo_root: str = os.path.abspath(configured_repo_root)
        else:
            # Default to the parent directory of remote_monitor
            self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        self.default_pipeline: str = pipelines_sec.get("default_pipeline", "tim").lower()
        self.monitored_storage_paths: List[str] = pipelines_sec.get(
            "monitored_storage_paths", ["/"]
        )

        # Notifications Settings
        notif_sec = self.raw_data.get("notifications", {})
        self.auto_upload_chauffeur: bool = notif_sec.get("auto_upload_chauffeur", True)
        self.max_chauffeur_images: int = int(notif_sec.get("max_chauffeur_images", 6))
        self.auto_upload_qc_pdf: bool = notif_sec.get("auto_upload_qc_pdf", True)
        self.auto_export_results: bool = notif_sec.get("auto_export_results", True)
        self.poll_interval_seconds: int = int(notif_sec.get("poll_interval_seconds", 15))

    def _find_config_file(self, explicit_path: Optional[str]) -> Optional[str]:
        """Resolve config path from argument, environment, or default search locations."""
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
        """Absolute path to the tim_analysis pipeline directory."""
        return os.path.join(self.repo_root, "tim_analysis")

    @property
    def war_dir(self) -> str:
        """Absolute path to the war_analysis pipeline directory."""
        return os.path.join(self.repo_root, "war_analysis")

    def get_pipeline_dir(self, pipeline: str) -> str:
        """
        Return the absolute directory path for the requested pipeline.

        Parameters
        ----------
        pipeline : str
            Pipeline name ('tim', 'war', 'tim_analysis', 'war_analysis').

        Returns
        -------
        str
            Absolute path to pipeline directory.

        Raises
        ------
        ValueError
            If pipeline name is unknown.
        """
        p = pipeline.lower()
        if "tim" in p:
            return self.tim_dir
        elif "war" in p:
            return self.war_dir
        raise ValueError(f"Unknown pipeline: '{pipeline}'. Expected 'tim' or 'war'.")

    def is_user_allowed(self, user_id: int) -> bool:
        """
        Check if a Telegram numeric user ID is authorized.

        Fails closed (returns False) if allowed_user_ids is empty or unconfigured.

        Parameters
        ----------
        user_id : int
            Telegram numeric user ID.

        Returns
        -------
        bool
            True if authorized, False otherwise.
        """
        if not self.allowed_user_ids:
            return False
        return user_id in self.allowed_user_ids

    def validate(self) -> List[str]:
        """
        Validate all configuration settings against operational schemas.

        Returns
        -------
        List[str]
            List of validation error messages, empty if configuration is valid.
        """
        errors: List[str] = []
        if not self.bot_token or self.bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
            errors.append(
                "Telegram bot token is not configured in bot_config.toml or TELEGRAM_BOT_TOKEN environment variable."
            )
        if not self.allowed_user_ids:
            errors.append(
                "allowed_user_ids is empty in bot_config.toml. You must add your Telegram numeric user ID."
            )
        if not os.path.isdir(self.tim_dir) and not os.path.isdir(self.war_dir):
            errors.append(
                f"Cannot find tim_analysis or war_analysis directories inside repo root: {self.repo_root}"
            )
        if self.poll_interval_seconds <= 0:
            errors.append(
                f"poll_interval_seconds must be a positive integer, got: {self.poll_interval_seconds}"
            )
        if self.max_chauffeur_images < 0:
            errors.append(
                f"max_chauffeur_images must be non-negative, got: {self.max_chauffeur_images}"
            )
        return errors


# Global default instance
config = BotConfig()
