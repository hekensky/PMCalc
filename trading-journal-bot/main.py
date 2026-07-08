import os
import asyncio
import logging

from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db
from bot import (
    start, new_trade, ticker_received, entry_received, stop_received,
    take_received, setup_selected, open_comment_received, active_trades,
    close_trade_start, close_outcome_selected, close_comment_received,
    close_pnl_received, close_photo_received, history, stats, export_csv,
    remind_command, remind_select, remind_time_received,
    main_menu_keyboard, menu_handler, cancel,
    TICKER, ENTRY, STOP, TAKE, SETUP, OPEN_COMMENT,
    CLOSE_OUTCOME, CLOSE_COMMENT, CLOSE_PNL, CLOSE_PHOTO,
    REMIND_SELECT, REMIND_TIME,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ['BOT_TOKEN']
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 10000))


def build_application() -> Application:
    db.init_db()
    application = Application.builder().token(TOKEN).build()

    scheduler = AsyncIOScheduler()
    scheduler.start()
    application.bot_data['scheduler'] = scheduler
    application.bot._scheduler = scheduler

    new_trade_conv = ConversationHandler(
        entry_points=[
            CommandHandler('new', new_trade),
            CallbackQueryHandler(menu_handler, pattern='^menu:new$')
        ],
        states={
            TICKER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticker_received)],
            ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, entry_received)],
            STOP: [MessageHandler(filters.TEXT & ~filters.COMMAND, stop_received)],
            TAKE: [MessageHandler(filters.TEXT & ~filters.COMMAND, take_received)],
            SETUP: [CallbackQueryHandler(setup_selected, pattern='^setup:')],
            OPEN_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, open_comment_received)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    close_trade_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(close_trade_start, pattern='^close:')],
        states={
            CLOSE_OUTCOME: [CallbackQueryHandler(close_outcome_selected, pattern='^(outcome:|cancel_close)')],
            CLOSE_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, close_comment_received)],
            CLOSE_PNL: [MessageHandler(filters.TEXT & ~filters.COMMAND, close_pnl_received)],
            CLOSE_PHOTO: [
                MessageHandler(filters.PHOTO, close_photo_received),
                MessageHandler(filters.Regex(r'^-$'), close_photo_received),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    remind_conv = ConversationHandler(
        entry_points=[
            CommandHandler('remind', remind_command),
            CallbackQueryHandler(menu_handler, pattern='^menu:remind$')
        ],
        states={
            REMIND_SELECT: [CallbackQueryHandler(remind_select, pattern='^remind_select:')],
            REMIND_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, remind_time_received)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(new_trade_conv)
    application.add_handler(close_trade_conv)
    application.add_handler(remind_conv)
    application.add_handler(CommandHandler('active', active_trades))
    application.add_handler(CommandHandler('history', history))
    application.add_handler(CommandHandler('stats', stats))
    application.add_handler(CommandHandler('export', export_csv))
    application.add_handler(CallbackQueryHandler(menu_handler, pattern='^menu:'))

    return application


async def run_polling():
    application = build_application()
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    logger.info('Bot started in polling mode')
    await asyncio.Event().wait()


async def run_webhook():
    application = build_application()
    await application.initialize()

    async def health(request):
        return web.Response(text='OK')

    async def webhook(request):
        data = await request.json()
        await application.update_queue.put(Update.de_json(data, application.bot))
        return web.Response(text='OK')

    app = web.Application()
    app.router.add_get('/', health)
    app.router.add_post(f'/{TOKEN}', webhook)

    await application.start()
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f'Webhook set to {WEBHOOK_URL}')

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f'Server listening on port {PORT}')

    await asyncio.Event().wait()


if __name__ == '__main__':
    if WEBHOOK_URL:
        asyncio.run(run_webhook())
    else:
        asyncio.run(run_polling())
