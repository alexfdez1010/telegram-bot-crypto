# 📈 Telegram Crypto Reminder Bot

🚀 A simple Telegram bot to set reminders for cryptocurrency price alerts.

## 🛠️ Setup

1. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment variables**:

   Create a `.env` file with your required tokens:

    ```
    TELEGRAM_BOT_TOKEN=your_bot_token_here
    COINMARKETCAP_API_KEY=your_cmc_api_key_here
    ```

3. **Run the bot**:

   ```bash
   python main.py
   ```

## 🤖 Commands

- `/start` - Start the bot and get a welcome message
- `/help` - Display help information about available commands
- `/setreminder` - Set a new price reminder for a cryptocurrency, format: `/setreminder SYMBOL CRON_EXPRESSION`
- `/myreminders` - List all your active reminders
- `/removereminder` - Remove a specific reminder by symbol

## 🧪 Testing

Run the test suite to ensure everything works as expected:

```bash
pytest test_main.py
```

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
