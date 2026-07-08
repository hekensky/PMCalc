import os
import csv
import io
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import database as db

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# States
TICKER, ENTRY, STOP, TAKE, SETUP, OPEN_COMMENT = range(6)
CLOSE_SELECT, CLOSE_OUTCOME, CLOSE_COMMENT, CLOSE_PHOTO = range(6, 10)

SETUP_TYPES = [
    'Брейкаут', 'Отбой от уровня', 'Трендовое продолжение',
    'Разворот', 'Накопление', 'Другое'
]


def format_trade(trade: dict) -> str:
    status_emoji = {
        'pending': '⏳',
        'active': '🟢',
        'closed_tp': '✅',
        'closed_sl': '❌',
        'cancelled': '🚫'
    }
    lines = [
        f"{status_emoji.get(trade['status'], '•')} <b>#{trade['id']} {trade['ticker']}</b> — {trade['direction']}",
        f"🎯 Вход: {trade['entry_price']}",
        f"🛑 Стоп: {trade['stop_loss']}",
        f"🚀 Тейк: {trade['take_profit']}",
        f"📊 R/R: 1:{trade['risk_reward']:.2f}" if trade['risk_reward'] else "",
    ]
    if trade['setup_type']:
        lines.append(f"🧩 Сетап: {trade['setup_type']}")
    if trade['open_comment']:
        lines.append(f"📝 Идея: {trade['open_comment']}")
    if trade['status'] in ('closed_tp', 'closed_sl', 'cancelled'):
        lines.append(f"\n📅 Открыта: {trade['created_at']}")
        lines.append(f"📅 Закрыта: {trade['closed_at']}")
    if trade['close_comment']:
        outcome_text = {
            'closed_tp': '🏆 Итог:',
            'closed_sl': '📉 Итог:',
            'cancelled': '🚫 Причина:'
        }.get(trade['outcome'], '💬')
        lines.append(f"{outcome_text} {trade['close_comment']}")
    return '\n'.join(line for line in lines if line)


# ─── Start ───
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Привет! Это <b>Журнал трейдера</b>.\n\n"
        "Я помогу фиксировать сделки, анализировать результаты и учиться на ошибках.\n\n"
        "<b>Команды:</b>\n"
        "• /new — добавить новую сделку\n"
        "• /active — активные позиции / идеи\n"
        "• /history — история закрытых сделок\n"
        "• /stats — статистика торговли\n"
        "• /export — выгрузить журнал в CSV"
    )
    await update.message.reply_html(text)


# ─── New trade conversation ───
async def new_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Давай запишем новую сделку.\n\nВведи тикер (например, BTC):'
    )
    return TICKER


async def ticker_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ticker'] = update.message.text.strip()
    await update.message.reply_text('Введи точку входа:')
    return ENTRY


async def entry_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['entry_price'] = float(update.message.text.replace(',', '.'))
    except ValueError:
        await update.message.reply_text('Нужно число. Попробуй ещё раз:')
        return ENTRY
    await update.message.reply_text('Введи стоп-лосс:')
    return STOP


async def stop_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['stop_loss'] = float(update.message.text.replace(',', '.'))
    except ValueError:
        await update.message.reply_text('Нужно число. Попробуй ещё раз:')
        return STOP
    await update.message.reply_text('Введи тейк-профит:')
    return TAKE


async def take_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['take_profit'] = float(update.message.text.replace(',', '.'))
    except ValueError:
        await update.message.reply_text('Нужно число. Попробуй ещё раз:')
        return TAKE

    keyboard = [[InlineKeyboardButton(t, callback_data=f'setup:{t}')] for t in SETUP_TYPES]
    await update.message.reply_text(
        'Выбери тип сетапа:',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SETUP


async def setup_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['setup_type'] = query.data.split(':', 1)[1]
    await query.edit_message_text('Напиши комментарий / идею входа:')
    return OPEN_COMMENT


async def open_comment_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    data['open_comment'] = update.message.text.strip()

    trade_id = db.add_trade(
        user_id=update.effective_user.id,
        ticker=data['ticker'],
        entry_price=data['entry_price'],
        stop_loss=data['stop_loss'],
        take_profit=data['take_profit'],
        setup_type=data.get('setup_type'),
        open_comment=data['open_comment']
    )

    trade = db.get_trade(trade_id, update.effective_user.id)
    await update.message.reply_html(
        f"✅ Сделка <b>#{trade_id}</b> добавлена!\n\n{format_trade(trade)}",
        reply_markup=main_menu_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END


# ─── Active trades ───
async def active_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trades = db.get_active_trades(update.effective_user.id)
    if not trades:
        await update.message.reply_text(
            'Нет активных сделок. Добавь новую через /new',
            reply_markup=main_menu_keyboard()
        )
        return

    for trade in trades:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton('📝 Закрыть сделку', callback_data=f'close:{trade["id"]}')
        ]])
        await update.message.reply_html(format_trade(trade), reply_markup=keyboard)


# ─── Close trade conversation ───
async def close_trade_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trade_id = int(query.data.split(':', 1)[1])
    trade = db.get_trade(trade_id, update.effective_user.id)

    if not trade:
        await query.edit_message_text('Сделка не найдена.')
        return ConversationHandler.END

    context.user_data['close_trade_id'] = trade_id

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton('🚀 По тейку', callback_data='outcome:closed_tp')],
        [InlineKeyboardButton('🛑 По стопу', callback_data='outcome:closed_sl')],
        [InlineKeyboardButton('🚫 Не дошла до входа', callback_data='outcome:cancelled')],
        [InlineKeyboardButton('❌ Отмена', callback_data='cancel_close')]
    ])

    await query.edit_message_text(
        f'Закрываем сделку <b>#{trade_id} {trade["ticker"]}</b>.\nЧто произошло?',
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    return CLOSE_OUTCOME


async def close_outcome_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'cancel_close':
        await query.edit_message_text('Закрытие отменено.')
        context.user_data.clear()
        return ConversationHandler.END

    outcome = query.data.split(':', 1)[1]
    context.user_data['close_outcome'] = outcome

    prompts = {
        'closed_tp': '🏆 Отлично! Почему сделка зашла? Напиши краткий разбор:',
        'closed_sl': '📉 Что пошло не так? Напиши, почему стоп сработал:',
        'cancelled': '🚫 Почему сделка не дошла до входа?'
    }
    await query.edit_message_text(prompts[outcome])
    return CLOSE_COMMENT


async def close_comment_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['close_comment'] = update.message.text.strip()
    outcome = context.user_data['close_outcome']

    if outcome == 'cancelled':
        return await finish_close(update, context, photo=None)

    await update.message.reply_text(
        'Пришли скриншот PnL (или напиши "-" чтобы пропустить):'
    )
    return CLOSE_PHOTO


async def close_photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file_id = None
    if update.message.photo:
        photo_file_id = update.message.photo[-1].file_id
    return await finish_close(update, context, photo=photo_file_id)


async def finish_close(update: Update, context: ContextTypes.DEFAULT_TYPE, photo):
    trade_id = context.user_data['close_trade_id']
    outcome = context.user_data['close_outcome']
    comment = context.user_data.get('close_comment', '')

    ok = db.close_trade(
        trade_id=trade_id,
        user_id=update.effective_user.id,
        outcome=outcome,
        close_comment=comment,
        pnl_screenshot_file_id=photo
    )

    if not ok:
        await update.message.reply_text('Не удалось закрыть сделку. Возможно, она уже закрыта.')
        context.user_data.clear()
        return ConversationHandler.END

    trade = db.get_trade(trade_id, update.effective_user.id)
    messages = {
        'closed_tp': ('🏆 Сделка закрыта по тейку!', '🎉 Поздравляю с прибыльной сделкой!'),
        'closed_sl': ('❌ Сделка закрыта по стопу.', 'Главное — контроль риска. Разберём ошибку и двигаемся дальше.'),
        'cancelled': ('🚫 Сделка отменена.', 'Не дошла до точки входа — тоже результат. Записали.')
    }
    header, footer = messages[outcome]

    if photo:
        await update.message.reply_photo(
            photo=photo,
            caption=f'{header}\n\n{format_trade(trade)}\n\n{footer}',
            parse_mode='HTML',
            reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_html(
            f'{header}\n\n{format_trade(trade)}\n\n{footer}',
            reply_markup=main_menu_keyboard()
        )

    context.user_data.clear()
    return ConversationHandler.END


# ─── History ───
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trades = db.get_history_trades(update.effective_user.id, limit=20)
    if not trades:
        await update.message.reply_text(
            'История пуста.',
            reply_markup=main_menu_keyboard()
        )
        return

    await update.message.reply_text(
        f'📜 Последние {len(trades)} закрытых сделок:',
        reply_markup=main_menu_keyboard()
    )
    for trade in trades:
        if trade['pnl_screenshot_file_id']:
            await update.message.reply_photo(
                photo=trade['pnl_screenshot_file_id'],
                caption=format_trade(trade),
                parse_mode='HTML'
            )
        else:
            await update.message.reply_html(format_trade(trade))


# ─── Stats ───
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = db.get_stats(update.effective_user.id)
    active_count = len(db.get_active_trades(update.effective_user.id))

    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"Закрытых сделок: <b>{s['total']}</b>\n"
        f"• Побед: <b>{s['wins']}</b> ✅\n"
        f"• Стопов: <b>{s['losses']}</b> ❌\n"
        f"• Отменено: <b>{s['cancelled']}</b> 🚫\n\n"
        f"Win rate: <b>{s['win_rate']}%</b>\n"
        f"Средний R/R на победных: <b>1:{s['avg_rr']}</b>\n\n"
        f"Активных позиций: <b>{active_count}</b>"
    )
    await update.message.reply_html(text, reply_markup=main_menu_keyboard())


# ─── Export ───
async def export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trades = db.get_all_trades_for_export(update.effective_user.id)
    if not trades:
        await update.message.reply_text('Нет сделок для выгрузки.')
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'ID', 'Ticker', 'Direction', 'Entry', 'Stop', 'Take',
        'R/R', 'Setup', 'Open Comment', 'Status', 'Outcome',
        'Close Comment', 'Created', 'Closed'
    ])
    for t in trades:
        writer.writerow([
            t['id'], t['ticker'], t['direction'], t['entry_price'],
            t['stop_loss'], t['take_profit'], t['risk_reward'],
            t['setup_type'], t['open_comment'], t['status'],
            t['outcome'], t['close_comment'], t['created_at'], t['closed_at']
        ])

    output.seek(0)
    filename = f'trades_{datetime.now().strftime("%Y-%m-%d")}.csv'
    await update.message.reply_document(
        document=output.encode('utf-8-sig'),
        filename=filename,
        caption='📎 Вот твой журнал сделок в CSV'
    )


# ─── Helpers ───
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('➕ Новая сделка', callback_data='menu:new')],
        [InlineKeyboardButton('⏳ Активные', callback_data='menu:active'),
         InlineKeyboardButton('📜 История', callback_data='menu:history')],
        [InlineKeyboardButton('📊 Статистика', callback_data='menu:stats'),
         InlineKeyboardButton('📤 Экспорт', callback_data='menu:export')]
    ])


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data.split(':', 1)[1]

    if action == 'new':
        await query.edit_message_text('Давай запишем новую сделку.\n\nВведи тикер (например, BTC):')
        context.user_data.clear()
        return TICKER
    elif action == 'active':
        await query.edit_message_text('Загружаю активные сделки...')
        await active_trades(update, context)
    elif action == 'history':
        await query.edit_message_text('Загружаю историю...')
        await history(update, context)
    elif action == 'stats':
        await query.edit_message_text('Считаю статистику...')
        await stats(update, context)
    elif action == 'export':
        await export_csv(update, context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Отменено.', reply_markup=main_menu_keyboard())
    context.user_data.clear()
    return ConversationHandler.END


# ─── Main ───
def main():
    db.init_db()
    token = os.environ['BOT_TOKEN']
    application = Application.builder().token(token).build()

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
            CLOSE_PHOTO: [
                MessageHandler(filters.PHOTO, close_photo_received),
                MessageHandler(filters.Regex(r'^-$'), close_photo_received),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(new_trade_conv)
    application.add_handler(close_trade_conv)
    application.add_handler(CommandHandler('active', active_trades))
    application.add_handler(CommandHandler('history', history))
    application.add_handler(CommandHandler('stats', stats))
    application.add_handler(CommandHandler('export', export_csv))

    # Menu callbacks from inline keyboard
    application.add_handler(CallbackQueryHandler(menu_handler, pattern='^menu:'))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
