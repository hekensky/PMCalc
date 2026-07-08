import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any

DATABASE_URL = os.environ.get('DATABASE_URL')
DB_PATH = os.environ.get('DB_PATH', 'trades.db')
IS_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith('postgres'))

if IS_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor


def _connection_kwargs():
    if IS_POSTGRES:
        return {'dsn': DATABASE_URL}
    return {'database': DB_PATH}


def get_connection():
    if IS_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _dict_row(row, cur):
    if IS_POSTGRES:
        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))
    return dict(row)


def _now():
    return datetime.utcnow().isoformat()


def _direction(entry: float, take: float) -> str:
    if take > entry:
        return 'LONG'
    if take < entry:
        return 'SHORT'
    return 'UNKNOWN'


def _risk_reward(entry: float, stop: float, take: float) -> Optional[float]:
    if stop == entry:
        return None
    return abs((take - entry) / (entry - stop))


def init_db():
    with get_connection() as conn:
        cur = conn.cursor()
        if IS_POSTGRES:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    ticker TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    setup_type TEXT,
                    direction TEXT,
                    risk_reward REAL,
                    open_comment TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    outcome TEXT,
                    close_comment TEXT,
                    pnl_amount REAL,
                    pnl_screenshot_file_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP
                )
            ''')
        else:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    ticker TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    setup_type TEXT,
                    direction TEXT,
                    risk_reward REAL,
                    open_comment TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    outcome TEXT,
                    close_comment TEXT,
                    pnl_amount REAL,
                    pnl_screenshot_file_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP
                )
            ''')
        conn.commit()


def add_trade(
    user_id: int,
    ticker: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    setup_type: Optional[str],
    open_comment: Optional[str]
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        if IS_POSTGRES:
            cur.execute(
                '''INSERT INTO trades
                   (user_id, ticker, entry_price, stop_loss, take_profit, setup_type,
                    direction, risk_reward, open_comment, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id''',
                (
                    user_id, ticker.upper(), entry_price, stop_loss, take_profit,
                    setup_type,
                    _direction(entry_price, take_profit),
                    _risk_reward(entry_price, stop_loss, take_profit),
                    open_comment,
                    'pending'
                )
            )
            row = cur.fetchone()
            trade_id = row[0]
        else:
            cur.execute(
                '''INSERT INTO trades
                   (user_id, ticker, entry_price, stop_loss, take_profit, setup_type,
                    direction, risk_reward, open_comment, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    user_id, ticker.upper(), entry_price, stop_loss, take_profit,
                    setup_type,
                    _direction(entry_price, take_profit),
                    _risk_reward(entry_price, stop_loss, take_profit),
                    open_comment,
                    'pending'
                )
            )
            trade_id = cur.lastrowid
        conn.commit()
        return trade_id


def _fetch_one(sql: str, params: tuple) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return None
        return _dict_row(row, cur)


def _fetch_all(sql: str, params: tuple) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [_dict_row(row, cur) for row in rows]


def get_trade(trade_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    placeholder = '%s' if IS_POSTGRES else '?'
    return _fetch_one(
        f'SELECT * FROM trades WHERE id = {placeholder} AND user_id = {placeholder}',
        (trade_id, user_id)
    )


def get_active_trades(user_id: int) -> List[Dict[str, Any]]:
    placeholder = '%s' if IS_POSTGRES else '?'
    return _fetch_all(
        f"SELECT * FROM trades WHERE user_id = {placeholder} AND status IN ('pending', 'active') ORDER BY created_at DESC",
        (user_id,)
    )


def get_history_trades(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    placeholder = '%s' if IS_POSTGRES else '?'
    return _fetch_all(
        f"SELECT * FROM trades WHERE user_id = {placeholder} AND status IN ('closed_tp', 'closed_sl', 'cancelled') ORDER BY closed_at DESC LIMIT {placeholder}",
        (user_id, limit)
    )


def close_trade(
    trade_id: int,
    user_id: int,
    outcome: str,
    close_comment: Optional[str] = None,
    pnl_amount: Optional[float] = None,
    pnl_screenshot_file_id: Optional[str] = None
) -> bool:
    if outcome not in ('closed_tp', 'closed_sl', 'cancelled'):
        raise ValueError('Invalid outcome')
    ph = '%s' if IS_POSTGRES else '?'
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f'''UPDATE trades
               SET status = {ph}, outcome = {ph}, close_comment = {ph},
                   pnl_amount = {ph}, pnl_screenshot_file_id = {ph}, closed_at = {ph}
               WHERE id = {ph} AND user_id = {ph} AND status IN ('pending', 'active')''',
            (outcome, outcome, close_comment, pnl_amount, pnl_screenshot_file_id,
             _now(), trade_id, user_id)
        )
        conn.commit()
        return cur.rowcount > 0


def get_stats(user_id: int) -> Dict[str, Any]:
    ph = '%s' if IS_POSTGRES else '?'
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            f"SELECT COUNT(*) FROM trades WHERE user_id = {ph} AND status IN ('closed_tp', 'closed_sl', 'cancelled')",
            (user_id,)
        )
        total = cur.fetchone()[0]

        cur.execute(
            f"SELECT COUNT(*) FROM trades WHERE user_id = {ph} AND status = 'closed_tp'",
            (user_id,)
        )
        wins = cur.fetchone()[0]

        cur.execute(
            f"SELECT COUNT(*) FROM trades WHERE user_id = {ph} AND status = 'closed_sl'",
            (user_id,)
        )
        losses = cur.fetchone()[0]

        cur.execute(
            f"SELECT COUNT(*) FROM trades WHERE user_id = {ph} AND status = 'cancelled'",
            (user_id,)
        )
        cancelled = cur.fetchone()[0]

        cur.execute(
            f"SELECT AVG(risk_reward) FROM trades WHERE user_id = {ph} AND status = 'closed_tp' AND risk_reward IS NOT NULL",
            (user_id,)
        )
        avg_rr = cur.fetchone()[0]

        cur.execute(
            f"SELECT COALESCE(SUM(pnl_amount), 0) FROM trades WHERE user_id = {ph} AND status = 'closed_tp' AND pnl_amount IS NOT NULL",
            (user_id,)
        )
        total_profit = cur.fetchone()[0]

        cur.execute(
            f"SELECT COALESCE(SUM(pnl_amount), 0) FROM trades WHERE user_id = {ph} AND status = 'closed_sl' AND pnl_amount IS NOT NULL",
            (user_id,)
        )
        total_loss = cur.fetchone()[0]

        cur.execute(
            f"SELECT COALESCE(SUM(pnl_amount), 0) FROM trades WHERE user_id = {ph} AND status IN ('closed_tp', 'closed_sl') AND pnl_amount IS NOT NULL",
            (user_id,)
        )
        net_pnl = cur.fetchone()[0]

    return {
        'total': total,
        'wins': wins,
        'losses': losses,
        'cancelled': cancelled,
        'win_rate': round(wins / max(total - cancelled, 1) * 100, 1),
        'avg_rr': round(avg_rr or 0, 2),
        'total_profit': round(total_profit, 2),
        'total_loss': round(total_loss, 2),
        'net_pnl': round(net_pnl, 2)
    }


def get_setup_distribution(user_id: int) -> List[Dict[str, Any]]:
    ph = '%s' if IS_POSTGRES else '?'
    return _fetch_all(
        f'''SELECT setup_type, COUNT(*) as count,
                   SUM(CASE WHEN status = 'closed_tp' THEN 1 ELSE 0 END) as wins
            FROM trades
            WHERE user_id = {ph} AND setup_type IS NOT NULL AND setup_type != ''
            GROUP BY setup_type
            ORDER BY count DESC''',
        (user_id,)
    )


def get_pnl_series(user_id: int) -> List[Dict[str, Any]]:
    ph = '%s' if IS_POSTGRES else '?'
    return _fetch_all(
        f'''SELECT id, ticker, status, pnl_amount, closed_at
            FROM trades
            WHERE user_id = {ph} AND status IN ('closed_tp', 'closed_sl') AND pnl_amount IS NOT NULL
            ORDER BY closed_at''',
        (user_id,)
    )


def get_all_trades_for_export(user_id: int) -> List[Dict[str, Any]]:
    ph = '%s' if IS_POSTGRES else '?'
    return _fetch_all(
        f'SELECT * FROM trades WHERE user_id = {ph} ORDER BY created_at DESC',
        (user_id,)
    )
