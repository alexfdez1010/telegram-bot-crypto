import os
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import pytz

import main

# Test data
TEST_DB = "test_reminders.db"
TEST_SYMBOL = "BTC"
TEST_CHAT_ID = 123456789
TEST_CRON = "*/30 * * * *"
TEST_PRICE = 50000.00


@pytest.fixture(autouse=True)
def mock_bot():
    """Create a mock bot instance and patch the main bot."""
    mock = MagicMock()
    with patch("main.bot", mock):
        yield mock


@pytest.fixture
def mock_requests(mocker):
    """Mock requests to return test price data."""
    mock = mocker.patch("requests.get")
    mock.return_value.status_code = 200
    mock.return_value.json.return_value = {
        "status": {"error_code": 0},
        "data": {TEST_SYMBOL: {"quote": {"USD": {"price": TEST_PRICE}}}},
    }
    return mock


@pytest.fixture
def test_db():
    """Create a test database."""
    # Use test database
    main.DB_FILE = TEST_DB

    # Initialize database
    main.init_db()

    yield TEST_DB

    # Cleanup
    try:
        os.remove(TEST_DB)
    except OSError:
        pass


def test_get_crypto_price(mock_requests):
    """Test getting cryptocurrency price."""
    price = main.get_crypto_price(TEST_SYMBOL)
    assert price == TEST_PRICE

    # Test error handling
    mock_requests.return_value.status_code = 400
    price = main.get_crypto_price(TEST_SYMBOL)
    assert price is None


def test_set_reminder(test_db, mock_bot):
    """Test setting a reminder."""
    # Create a mock message
    message = MagicMock()
    message.chat.id = TEST_CHAT_ID
    message.text = f"/setreminder {TEST_SYMBOL} {TEST_CRON}"

    # Test setting a new reminder
    with patch("main.get_crypto_price", return_value=TEST_PRICE):
        main.set_reminder(message)

    # Verify reminder was stored
    with sqlite3.connect(test_db) as conn:
        cursor = conn.execute(
            "SELECT chat_id, cron_expr FROM reminders WHERE symbol = ?", (TEST_SYMBOL,)
        )
        reminder = cursor.fetchone()
        assert reminder is not None
        assert reminder[0] == TEST_CHAT_ID
        assert reminder[1] == TEST_CRON

    # Verify bot responses
    assert mock_bot.reply_to.call_count == 2  # Confirmation + price test

    # Test updating existing reminder
    new_cron = "0 */2 * * *"
    message.text = f"/setreminder {TEST_SYMBOL} {new_cron}"

    with patch("main.get_crypto_price", return_value=TEST_PRICE):
        main.set_reminder(message)

    # Verify reminder was updated
    with sqlite3.connect(test_db) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM reminders")
        count = cursor.fetchone()[0]
        assert count == 1  # Still only one reminder

        cursor = conn.execute(
            "SELECT cron_expr FROM reminders WHERE symbol = ?", (TEST_SYMBOL,)
        )
        updated_cron = cursor.fetchone()[0]
        assert updated_cron == new_cron


def test_remove_reminder(test_db, mock_bot):
    """Test removing a reminder."""
    # First add a reminder
    with sqlite3.connect(test_db) as conn:
        conn.execute(
            "INSERT INTO reminders (symbol, chat_id, cron_expr) VALUES (?, ?, ?)",
            (TEST_SYMBOL, TEST_CHAT_ID, TEST_CRON),
        )

    # Create a mock message
    message = MagicMock()
    message.chat.id = TEST_CHAT_ID
    message.text = f"/removereminder {TEST_SYMBOL}"

    # Test removing the reminder
    main.remove_reminder(message)

    # Verify reminder was removed
    with sqlite3.connect(test_db) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM reminders")
        count = cursor.fetchone()[0]
        assert count == 0

    # Verify bot response
    mock_bot.reply_to.assert_called_once()
    assert "Removed reminder" in mock_bot.reply_to.call_args[0][1]


def test_list_reminders(test_db, mock_bot):
    """Test listing reminders."""
    # First add some reminders
    with sqlite3.connect(test_db) as conn:
        conn.execute(
            "INSERT INTO reminders (symbol, chat_id, cron_expr) VALUES (?, ?, ?)",
            (TEST_SYMBOL, TEST_CHAT_ID, TEST_CRON),
        )
        conn.execute(
            "INSERT INTO reminders (symbol, chat_id, cron_expr) VALUES (?, ?, ?)",
            ("ETH", TEST_CHAT_ID, "0 */2 * * *"),
        )

    # Create a mock message
    message = MagicMock()
    message.chat.id = TEST_CHAT_ID

    # Test listing reminders
    main.list_reminders(message)

    # Verify bot response
    mock_bot.reply_to.assert_called_once()
    response = mock_bot.reply_to.call_args[0][1]
    assert TEST_SYMBOL in response
    assert "ETH" in response
    assert TEST_CRON in response


def test_check_reminders(test_db, mock_bot):
    """Test checking reminders."""
    test_time = datetime(2025, 2, 23, 10, 0, tzinfo=pytz.UTC)

    # Add a reminder that should trigger at 10:00
    with sqlite3.connect(test_db) as conn:
        conn.execute(
            "INSERT INTO reminders (symbol, chat_id, cron_expr) VALUES (?, ?, ?)",
            (TEST_SYMBOL, TEST_CHAT_ID, "*/5 * * * *"),  # Should trigger every 5 minutes
        )

    class MockDatetime(datetime):
        _current_time = test_time

        @classmethod
        def now(cls, tz=None):
            return cls._current_time

        @classmethod
        def fromisoformat(cls, date_string):
            return datetime.fromisoformat(date_string)

        @classmethod
        def set_time(cls, new_time):
            cls._current_time = new_time

    # Test 1: Reminder should trigger at start (10:00)
    with patch("main.datetime", MockDatetime), \
         patch("main.get_crypto_price", return_value=TEST_PRICE), \
         patch("main.bot", mock_bot):
        main.check_reminders(single_check=True)

        # Verify the price reminder was sent
        mock_bot.send_message.assert_called_once()
        message = mock_bot.send_message.call_args[0][1]
        assert TEST_SYMBOL in message
        assert str(TEST_PRICE) in message

    # Test 2: Reminder should not trigger at 10:01
    mock_bot.reset_mock()
    MockDatetime.set_time(test_time + timedelta(minutes=1))
    
    with patch("main.datetime", MockDatetime), \
         patch("main.get_crypto_price", return_value=TEST_PRICE), \
         patch("main.bot", mock_bot):
        main.check_reminders(single_check=True)

        # Verify no message was sent
        mock_bot.send_message.assert_not_called()

    # Test 3: Reminder should not trigger at 10:04
    mock_bot.reset_mock()
    MockDatetime.set_time(test_time + timedelta(minutes=4))
    
    with patch("main.datetime", MockDatetime), \
         patch("main.get_crypto_price", return_value=TEST_PRICE), \
         patch("main.bot", mock_bot):
        main.check_reminders(single_check=True)

        # Verify no message was sent
        mock_bot.send_message.assert_not_called()

    # Test 4: Reminder should trigger at 10:05
    mock_bot.reset_mock()
    MockDatetime.set_time(test_time + timedelta(minutes=5))
    
    with patch("main.datetime", MockDatetime), \
         patch("main.get_crypto_price", return_value=TEST_PRICE), \
         patch("main.bot", mock_bot):
        main.check_reminders(single_check=True)

        # Verify the price reminder was sent
        mock_bot.send_message.assert_called_once()
        message = mock_bot.send_message.call_args[0][1]
        assert TEST_SYMBOL in message
        assert str(TEST_PRICE) in message
