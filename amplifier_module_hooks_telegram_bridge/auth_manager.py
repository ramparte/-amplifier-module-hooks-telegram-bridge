"""
Shared authorization manager for Telegram bridge modules.
Reads pairing.json to determine authorized users.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel
from pydantic import Field

logger = logging.getLogger(__name__)


class AuthorizedUser(BaseModel):
    """Represents an authorized Telegram user."""

    user_id: int
    chat_id: int
    username: str | None = None
    paired_at: str


class RateLimit(BaseModel):
    """Rate limiting information for blocked users."""

    failed_attempts: int = 0
    blocked_until: str | None = None


class PairingFile(BaseModel):
    """Schema for pairing.json file."""

    version: str = "1.0"
    authorized_users: list[AuthorizedUser] = Field(default_factory=list)
    rate_limits: dict[str, RateLimit] = Field(default_factory=dict)


class AuthManager:
    """Manages authorization for Telegram bridge."""

    def __init__(self, pairing_file: Path):
        """
        Initialize auth manager.

        Args:
            pairing_file: Path to pairing.json file
        """
        self.pairing_file = pairing_file
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """Ensure pairing file exists with default structure."""
        if not self.pairing_file.exists():
            self.pairing_file.parent.mkdir(parents=True, exist_ok=True)
            default_pairing = PairingFile()
            self.pairing_file.write_text(json.dumps(default_pairing.model_dump(), indent=2))
            logger.info(f"Created default pairing file at {self.pairing_file}")

    def get_authorized_users(self) -> set[int]:
        """
        Get set of authorized user IDs.

        Returns:
            Set of authorized user IDs
        """
        try:
            pairing_data = json.loads(self.pairing_file.read_text())
            pairing = PairingFile(**pairing_data)
            return {user.user_id for user in pairing.authorized_users}
        except Exception as e:
            logger.error(f"Error reading pairing file: {e}")
            return set()

    def is_authorized(self, user_id: int) -> bool:
        """
        Check if user is authorized.

        Args:
            user_id: Telegram user ID

        Returns:
            True if authorized, False otherwise
        """
        return user_id in self.get_authorized_users()

    def get_chat_ids(self) -> set[int]:
        """
        Get set of authorized chat IDs.

        Returns:
            Set of authorized chat IDs
        """
        try:
            pairing_data = json.loads(self.pairing_file.read_text())
            pairing = PairingFile(**pairing_data)
            return {user.chat_id for user in pairing.authorized_users}
        except Exception as e:
            logger.error(f"Error reading pairing file: {e}")
            return set()

    def add_user(self, user_id: int, chat_id: int, username: str | None = None) -> bool:
        """
        Add user to authorized list.

        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID
            username: Optional username

        Returns:
            True if successful, False otherwise
        """
        try:
            pairing_data = json.loads(self.pairing_file.read_text())
            pairing = PairingFile(**pairing_data)

            # Check if already authorized
            if any(user.user_id == user_id for user in pairing.authorized_users):
                logger.info(f"User {user_id} already authorized")
                return True

            # Add new user
            new_user = AuthorizedUser(
                user_id=user_id, chat_id=chat_id, username=username, paired_at=datetime.now().isoformat()
            )
            pairing.authorized_users.append(new_user)

            # Save
            self.pairing_file.write_text(json.dumps(pairing.model_dump(), indent=2))
            logger.info(f"Added user {user_id} ({username}) to authorized users")
            return True

        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False

    def remove_user(self, user_id: int) -> bool:
        """
        Remove user from authorized list.

        Args:
            user_id: Telegram user ID

        Returns:
            True if successful, False otherwise
        """
        try:
            pairing_data = json.loads(self.pairing_file.read_text())
            pairing = PairingFile(**pairing_data)

            # Filter out user
            original_count = len(pairing.authorized_users)
            pairing.authorized_users = [user for user in pairing.authorized_users if user.user_id != user_id]

            if len(pairing.authorized_users) == original_count:
                logger.warning(f"User {user_id} not found in authorized users")
                return False

            # Save
            self.pairing_file.write_text(json.dumps(pairing.model_dump(), indent=2))
            logger.info(f"Removed user {user_id} from authorized users")
            return True

        except Exception as e:
            logger.error(f"Error removing user: {e}")
            return False

    def check_rate_limit(self, user_id: int) -> bool:
        """
        Check if user is rate limited.

        Args:
            user_id: Telegram user ID

        Returns:
            True if rate limited, False otherwise
        """
        try:
            pairing_data = json.loads(self.pairing_file.read_text())
            pairing = PairingFile(**pairing_data)

            user_key = str(user_id)
            if user_key not in pairing.rate_limits:
                return False

            rate_limit = pairing.rate_limits[user_key]
            if rate_limit.blocked_until:
                blocked_until = datetime.fromisoformat(rate_limit.blocked_until)
                if datetime.now() < blocked_until:
                    return True
                # Expired - clear block
                rate_limit.blocked_until = None
                rate_limit.failed_attempts = 0
                self.pairing_file.write_text(json.dumps(pairing.model_dump(), indent=2))

            return False

        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return False

    def record_failed_attempt(self, user_id: int, max_attempts: int = 5, block_duration_hours: int = 1) -> None:
        """
        Record failed auth attempt and block if threshold exceeded.

        Args:
            user_id: Telegram user ID
            max_attempts: Maximum attempts before blocking
            block_duration_hours: Hours to block after max attempts
        """
        try:
            pairing_data = json.loads(self.pairing_file.read_text())
            pairing = PairingFile(**pairing_data)

            user_key = str(user_id)
            if user_key not in pairing.rate_limits:
                pairing.rate_limits[user_key] = RateLimit()

            rate_limit = pairing.rate_limits[user_key]
            rate_limit.failed_attempts += 1

            if rate_limit.failed_attempts >= max_attempts:
                from datetime import timedelta

                blocked_until = datetime.now() + timedelta(hours=block_duration_hours)
                rate_limit.blocked_until = blocked_until.isoformat()
                logger.warning(f"User {user_id} blocked until {rate_limit.blocked_until}")

            self.pairing_file.write_text(json.dumps(pairing.model_dump(), indent=2))

        except Exception as e:
            logger.error(f"Error recording failed attempt: {e}")
