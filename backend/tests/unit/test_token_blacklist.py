from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class TestTokenBlacklist:
    @patch("app.services.token_blacklist._get_redis")
    def test_add_to_blacklist(self, mock_get_redis):
        from app.services.token_blacklist import add_to_blacklist

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        add_to_blacklist("test-token-jti", ttl_seconds=900)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert "blacklist:test-token-jti" in call_args[0][0]
        assert call_args[0][1] == 900

    @patch("app.services.token_blacklist._get_redis")
    def test_is_blacklisted_returns_true_when_exists(self, mock_get_redis):
        from app.services.token_blacklist import is_blacklisted

        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1
        mock_get_redis.return_value = mock_redis

        result = is_blacklisted("test-token-jti")

        assert result is True

    @patch("app.services.token_blacklist._get_redis")
    def test_is_blacklisted_returns_false_when_not_exists(self, mock_get_redis):
        from app.services.token_blacklist import is_blacklisted

        mock_redis = MagicMock()
        mock_redis.exists.return_value = 0
        mock_get_redis.return_value = mock_redis

        result = is_blacklisted("test-token-jti")

        assert result is False
