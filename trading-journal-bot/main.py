import os
import asyncio
import logging

from aiohttp import web
from telegram import Update

import database as db
from bot import make_application

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ['BOT_TOKEN']
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 10000))


def build_application():
    db.init_db()
    return make_application(TOKEN)


async def run_polling():
    application = build_application()
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    logger.info('Bot started in polling mode')
    await asyncio.Event().wait()


async def run_webhook():
    logger.info('Starting webhook mode...')
    application = build_application()
    await application.initialize()

    async def health(request):
        return web.Response(text='OK')

    async def webhook(request):
        try:
            data = await request.json()
            await application.update_queue.put(Update.de_json(data, application.bot))
            return web.Response(text='OK')
        except Exception:
            logger.exception('Error processing webhook')
            return web.Response(text='Error', status=500)

    app = web.Application()
    app.router.add_get('/', health)
    app.router.add_post(f'/{TOKEN}', webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f'Server listening on port {PORT}')

    try:
        await application.bot.set_webhook(WEBHOOK_URL)
        logger.info(f'Webhook set to {WEBHOOK_URL}')
    except Exception:
        logger.exception('Failed to set webhook')
        raise

    await application.start()
    logger.info('Application started')
    await asyncio.Event().wait()


if __name__ == '__main__':
    if WEBHOOK_URL:
        asyncio.run(run_webhook())
    else:
        asyncio.run(run_polling())
