import os
import time
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from gps_ble_tracker import CombinedTracker
import threading
import queue

# Load environment variables
load_dotenv()

# Get token from environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables. Please set it in .env file.")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("TelegramTracker")

# Queue for communication between tracker and bot
message_queue = queue.Queue()
# Store chat IDs that should receive notifications
notification_chats = set()

class TelegramTracker(CombinedTracker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message_queue = kwargs.get('message_queue', None)
        
    def _store_buffer(self, header, devices):
        """Override to add Telegram notification"""
        # Call the parent method to store in MongoDB
        result = super()._store_buffer(header, devices)
        
        if result and self.message_queue:
            # Get GPS data
            gps_data = self.last_gps_data
            
            # Create message for Telegram
            devices_summary = [
                f"{dev['mac']}(RSSI:{dev['rssi']}dB)" 
                for dev in devices[:3]
            ]
            if len(devices) > 3:
                devices_summary.append(f"... +{len(devices)-3} more")
                
            message = (
                f"📡 Buffer Received!\n"
                f"Sequence: #{header['sequence']}\n"
                f"Devices: {len(devices)} ({', '.join(devices_summary)})\n"
                f"Advertisements: {header['n_adv_raw']}\n"
            )
            
            if gps_data and gps_data.get('coordinates'):
                lat = gps_data['coordinates']['latitude']
                lon = gps_data['coordinates']['longitude']
                speed = gps_data.get('speed', 0)
                message += f"📍 GPS: {lat:.6f}, {lon:.6f} ({speed:.2f} knots)\n"
                # Add location data for sending as location message
                location = {'latitude': lat, 'longitude': lon}
            else:
                message += "📍 GPS: No fix\n"
                location = None
                
            # Put in queue for the Telegram bot to send
            self.message_queue.put({
                'text': message,
                'location': location
            })
            
        return result

# Command handlers for Telegram bot
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_text(
        f'Hi {user.first_name}! I will notify you about BLE and GPS tracking events.'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    help_text = """
    Commands:
    /start - Start the bot
    /help - Show this help message
    /subscribe - Subscribe to buffer notifications
    /unsubscribe - Unsubscribe from buffer notifications
    /status - Show tracker status
    """
    await update.message.reply_text(help_text)

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Subscribe to buffer notifications."""
    chat_id = update.effective_chat.id
    notification_chats.add(chat_id)
    await update.message.reply_text("You are now subscribed to buffer notifications!")

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe from buffer notifications."""
    chat_id = update.effective_chat.id
    if chat_id in notification_chats:
        notification_chats.remove(chat_id)
        await update.message.reply_text("You are now unsubscribed from buffer notifications.")
    else:
        await update.message.reply_text("You were not subscribed.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show tracker status."""
    # You can expand this with more status information
    await update.message.reply_text(
        f"Tracker is running\n"
        f"Subscribed chats: {len(notification_chats)}\n"
        f"Notification queue size: {message_queue.qsize()}"
    )

# Function to run the tracker in a separate thread
def run_tracker(args, message_queue):
    try:
        tracker = TelegramTracker(
            gps_port=args.gps_port, 
            ble_port=args.ble_port, 
            mongo_uri=args.mongo_uri,
            log_level=args.log_level,
            message_queue=message_queue
        )
        tracker.logger.info(
            "Starting capture %s", 
            "indefinitely" if not args.duration else f"for {args.duration} seconds"
        )
        tracker.receive_messages(duration=args.duration)
    except Exception as e:
        logger.error(f"Tracker error: {e}")
    finally:
        if 'tracker' in locals():
            tracker.close()

# Function to process the message queue and send to Telegram
async def process_queue(context: ContextTypes.DEFAULT_TYPE):
    """Process messages from the queue and send to subscribed chats."""
    if message_queue.empty():
        return
        
    # Process all messages in the queue
    while not message_queue.empty():
        try:
            message_data = message_queue.get_nowait()
            text = message_data.get('text', '')
            location = message_data.get('location')
            
            # Send to all subscribed chats
            for chat_id in notification_chats:
                await context.bot.send_message(chat_id=chat_id, text=text)
                
                # If we have location data, send it as a location message
                if location:
                    await context.bot.send_location(
                        chat_id=chat_id,
                        latitude=location['latitude'],
                        longitude=location['longitude']
                    )
                    
        except queue.Empty:
            break
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")

def main():
    """Start the bot and tracker."""
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description="Telegram Bot for GPS + BLE Tracking")
    parser.add_argument(
        "--gps-port", type=str, default="COM26", help="GPS port (default: COM26)"
    )
    parser.add_argument(
        "--ble-port", type=str, default="COM20", help="BLE port (default: COM20)"
    )
    parser.add_argument("--duration", type=int, help="Tracking duration in seconds")
    parser.add_argument(
        "--mongo-uri",
        type=str,
        default="mongodb://localhost:27017/",
        help="MongoDB URI (default: mongodb://localhost:27017/)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["info", "debug"],
        default="info",
        help="Logging level (default: info)"
    )
    args = parser.parse_args()

    # Start tracker in a separate thread
    tracker_thread = threading.Thread(
        target=run_tracker,
        args=(args, message_queue),
        daemon=True
    )
    tracker_thread.start()

    # Create the Telegram application
    application = ApplicationBuilder().token(TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    application.add_handler(CommandHandler("status", status_command))
    
    # Add job to process message queue every 2 seconds
    application.job_queue.run_repeating(process_queue, interval=2, first=1)

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == "__main__":
    main()

