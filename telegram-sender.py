import logging
from telegram import Update
from telegram.ext import ApplicationBuilder,CommandHandler,ContextTypes,MessageHandler,filters
from dotenv import load_dotenv
import os

# load env vars
load_dotenv()


#logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

#Token
TOKEN= os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Telegram token not found")

# Command handlers

async def start_command(update: Update, context:ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f'🛥️ Hello, {user.first_name}!')

async def help_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    help_text = """
    Commands:
    /start - Start the bot
    /help - Show this help message
    /send <chat_id> <message> - Send a message to a specific chat
    """
    await update.message.reply_text(help_text)


async def send_message_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /send <chat_id> <message>")
        return
    
    try: 
        chat_id = context.args[0]
        message = ' '.joint(context.args[1:])
        
        #Send the message
        await context.bot.send_message(chat_id=chat_id,text=message)
        await update.message.reply_text(f"Message sent to {chat_id}")

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")


async def echo(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start",start_command))
    application.add_handler(CommandHandler("help",help_command))
    application.add_handler(CommandHandler("send",send_message_command))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    #run bot

    print("Bot is running")
    application.run_polling()


if __name__ == "__main__":
    main()












