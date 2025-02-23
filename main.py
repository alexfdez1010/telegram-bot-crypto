import os
import time
import threading
import sqlite3
from datetime import datetime
from typing import Dict, Tuple, List

import telebot
from dotenv import load_dotenv
import requests
from croniter import croniter
import pytz

# Load environment variables
load_dotenv()

# Initialize bot and API configuration
bot = telebot.TeleBot(os.getenv('TELEGRAM_BOT_TOKEN'))
CMC_API_KEY = os.getenv('COINMARKETCAP_API_KEY')
CMC_BASE_URL = 'https://pro-api.coinmarketcap.com/v1'

# Database setup
DB_FILE = 'crypto_reminders.db'

def init_db():
    """Initialize SQLite database."""
    with sqlite3.connect(DB_FILE) as conn:
        # Drop existing table to update schema
        conn.execute('DROP TABLE IF EXISTS reminders')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                symbol TEXT PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                cron_expr TEXT NOT NULL,
                last_run TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

def get_crypto_price(symbol: str) -> float:
    """Get the current price of a cryptocurrency in USDT."""
    try:
        url = f"{CMC_BASE_URL}/cryptocurrency/quotes/latest"
        headers = {
            'X-CMC_PRO_API_KEY': CMC_API_KEY,
            'Accept': 'application/json'
        }
        params = {
            'symbol': symbol,
            'convert': 'USD'  # CoinMarketCap uses USD as base currency
        }
        
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        
        if response.status_code == 200 and data['status']['error_code'] == 0:
            return float(data['data'][symbol]['quote']['USD']['price'])
        else:
            print(f"Error from CMC API: {data['status']['error_message']}")
            return None
    except Exception as e:
        print(f"Error getting price for {symbol}: {e}")
        return None

def send_price_reminder(chat_id: int, symbol: str):
    """Send a price reminder to a specific chat."""
    price = get_crypto_price(symbol)
    if price is not None:
        message = f"🔔 Price Alert for {symbol}\n💰 Current price: ${price:.3f} USDT"
        bot.send_message(chat_id, message)
    else:
        bot.send_message(chat_id, f"❌ Error getting price for {symbol}")

def get_all_reminders() -> List[Tuple]:
    """Get all reminders from the database."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute(
            'SELECT symbol, chat_id, cron_expr, last_run FROM reminders'
        )
        return cursor.fetchall()

def update_reminder_last_run(symbol: str):
    """Update the last run time of a reminder."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            'UPDATE reminders SET last_run = ? WHERE symbol = ?',
            (datetime.now(), symbol)
        )
        conn.commit()

def check_reminders():
    """Check and execute due reminders."""
    while True:
        now = datetime.now(pytz.UTC)
        reminders = get_all_reminders()
        
        for symbol, chat_id, cron_expr, last_run in reminders:
            try:
                cron = croniter(cron_expr, now)
                next_run = cron.get_prev(datetime) if last_run else cron.get_next(datetime)
                
                if last_run is None or (now - next_run).total_seconds() > -60:
                    send_price_reminder(chat_id, symbol)
                    update_reminder_last_run(symbol)
            except Exception as e:
                print(f"Error processing reminder {symbol}: {e}")
        
        time.sleep(60)  # Check every minute

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Handle the /start command."""
    welcome_text = (
        "👋 Welcome to the Crypto Price Reminder Bot!\n\n"
        "Use /setreminder to set up price alerts for cryptocurrencies.\n"
        "Format: /setreminder SYMBOL CRON_EXPRESSION\n"
        "Example: /setreminder BTC */30 * * * *\n\n"
        "Cron Expression Format:\n"
        "* * * * * (minute hour day month weekday)\n"
        "Examples:\n"
        "*/30 * * * * - Every 30 minutes\n"
        "0 */2 * * * - Every 2 hours\n"
        "0 10 * * * - Every day at 10:00\n\n"
        "Use /myreminders to see your active reminders\n"
        "Use /help for more information"
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['help'])
def send_help(message):
    """Handle the /help command."""
    help_text = (
        "🤖 Available Commands:\n\n"
        "/setreminder SYMBOL CRON - Set a new price reminder\n"
        "/myreminders - List your active reminders\n"
        "/removereminder SYMBOL - Remove a reminder\n"
        "/price SYMBOL - Get current price\n\n"
        "Cron Expression Examples:\n"
        "*/30 * * * * - Every 30 minutes\n"
        "0 */2 * * * - Every 2 hours\n"
        "0 10 * * * - Every day at 10:00\n"
        "0 9-17 * * 1-5 - Every hour from 9-5 on weekdays\n\n"
        "SYMBOL examples: BTC, ETH, SOL"
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['setreminder'])
def set_reminder(message):
    """Handle the /setreminder command."""
    try:
        # Parse command arguments
        args = message.text.split(None, 2)
        if len(args) != 3:
            raise ValueError("Invalid number of arguments")

        symbol = args[1].upper()
        cron_expr = args[2]

        # Validate cron expression
        if not croniter.is_valid(cron_expr):
            raise ValueError("Invalid cron expression")

        # Store in database, using REPLACE to handle existing reminders
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                'REPLACE INTO reminders (symbol, chat_id, cron_expr) VALUES (?, ?, ?)',
                (symbol, message.chat.id, cron_expr)
            )
            conn.commit()

        bot.reply_to(
            message,
            f"✅ Reminder set!\nYou will receive {symbol} price updates according to: {cron_expr}"
        )
        
        # Get and send current price to verify it works
        price = get_crypto_price(symbol)
        if price is not None:
            bot.reply_to(
                message,
                f"🔄 Testing price fetch for {symbol}...\n💰 Current price: ${price:.3f} USD"
            )
        else:
            bot.reply_to(
                message,
                f"⚠️ Warning: Could not fetch current price for {symbol}. Please verify the symbol is correct."
            )

    except ValueError as e:
        bot.reply_to(
            message,
            f"❌ Error: {str(e)}\nUse format: /setreminder SYMBOL 'CRON_EXPRESSION'"
        )
    except Exception as e:
        bot.reply_to(message, f"❌ An error occurred: {str(e)}")

@bot.message_handler(commands=['myreminders'])
def list_reminders(message):
    """Handle the /myreminders command."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute(
            'SELECT symbol, cron_expr FROM reminders WHERE chat_id = ?',
            (message.chat.id,)
        )
        reminders = cursor.fetchall()

    if not reminders:
        bot.reply_to(message, "You have no active reminders")
        return

    reminder_list = "\n".join(
        f"🔔 {symbol}: {cron_expr}"
        for symbol, cron_expr in reminders
    )
    bot.reply_to(message, f"Your active reminders:\n\n{reminder_list}")

@bot.message_handler(commands=['removereminder'])
def remove_reminder(message):
    """Handle the /removereminder command."""
    try:
        symbol = message.text.split()[1].upper()
        
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.execute(
                'DELETE FROM reminders WHERE chat_id = ? AND symbol = ?',
                (message.chat.id, symbol)
            )
            conn.commit()
            
            if cursor.rowcount > 0:
                bot.reply_to(message, f"✅ Removed reminder for {symbol}")
            else:
                bot.reply_to(message, f"❌ No active reminder found for {symbol}")

    except IndexError:
        bot.reply_to(
            message,
            "❌ Please specify a symbol to remove\nExample: /removereminder BTC"
        )

@bot.message_handler(commands=['price'])
def get_price(message):
    """Handle the /price command."""
    try:
        symbol = message.text.split()[1].upper()
        price = get_crypto_price(symbol)
        
        if price is not None:
            bot.reply_to(
                message,
                f"💰 {symbol} price: ${price:.2f} USDT"
            )
        else:
            bot.reply_to(message, f"❌ Error getting price for {symbol}")

    except IndexError:
        bot.reply_to(
            message,
            "❌ Please specify a symbol\nExample: /price BTC"
        )

if __name__ == "__main__":
    # Initialize database
    init_db()
    
    # Start the reminder checker in a separate thread
    checker_thread = threading.Thread(target=check_reminders)
    checker_thread.daemon = True
    checker_thread.start()

    # Start the bot
    print("🤖 Bot is running...")
    bot.infinity_polling()
