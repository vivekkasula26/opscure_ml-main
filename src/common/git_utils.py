"""
Git Utilities Module

Provides tools for interacting with Git configuration and state.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional
from src.common.types import GitConfig


class GitConfigCollector:
    """
    Collects git configuration from various sources (local repo, global user).
    """

    @staticmethod
    def collect_config(repo_path: str = ".") -> Optional[GitConfig]:
        """
        Collect git configuration details.
        
        Args:
            repo_path: Path to the local git repository (default: current dir)
            
        Returns:
            Populated GitConfig object or None if git is not available/configured.
        """
        try:
            # 1. Get Basic Identity (UserName/Email) via git command
            # This handles precedence (local > global > system) automatically
            user_name = GitConfigCollector._run_git_config_get("user.name", repo_path)
            user_email = GitConfigCollector._run_git_config_get("user.email", repo_path)
            
            if not user_name or not user_email:
                # If we can't get identity, we can't make commits, but we might still want the config files?
                # For now, let's treat identity as required for a valid GitConfig object in our system.
                return None

            # 2. Read Local Config Content (.git/config)
            local_content = None
            git_dir = Path(repo_path) / ".git"
            if git_dir.exists() and git_dir.is_dir():
                config_path = git_dir / "config"
                if config_path.exists() and config_path.is_file():
                    try:
                        local_content = config_path.read_text(encoding="utf-8")
                    except Exception as e:
                        print(f"[GitConfigCollector] Failed to read local config: {e}")

            # 3. Read Global Config Content (~/.gitconfig)
            global_content = None
            try:
                # Expand ~ to full path
                global_path = Path("~/.gitconfig").expanduser()
                if global_path.exists() and global_path.is_file():
                    global_content = global_path.read_text(encoding="utf-8")
                
                # Check for XDG config path as fallback (~/.config/git/config)
                if not global_content:
                    xdg_path = Path("~/.config/git/config").expanduser()
                    if xdg_path.exists() and xdg_path.is_file():
                        global_content = xdg_path.read_text(encoding="utf-8")
                        
            except Exception as e:
                print(f"[GitConfigCollector] Failed to read global config: {e}")

            return GitConfig(
                user_name=user_name,
                user_email=user_email,
                local_config_content=local_content,
                global_config_content=global_content
            )

        except Exception as e:
            print(f"[GitConfigCollector] Error collecting config: {e}")
            return None

    @staticmethod
    def _run_git_config_get(key: str, repo_path: str) -> Optional[str]:
        """Run `git config --get <key>` and return stripped output."""
        try:
            # Check if repo_path exists, else use current dir
            cwd = repo_path if os.path.isdir(repo_path) else "."
            
            result = subprocess.run(
                ["git", "config", "--get", key],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False # Don't raise on exit 1 (key not found)
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None
