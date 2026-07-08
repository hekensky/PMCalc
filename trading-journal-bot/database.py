import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

DB_PATH = os.environ.get('DB_PATH', 'trades.db')


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                setup_type TEXT,
                direction TEXT GENERATED ALWAYS AS (
                    CASE
                        WHEN take_profit > entry_price THEN 'LONG'
                        WHEN take_profit < entry_price THEN 'SHORT'
                        ELSE 'UNKNOWN'
                    END
                ) STORED,
                risk_reward REAL GENERATED ALWAYS AS (
                    CASE
                        WHEN stop_loss = entry_price THEN NULL
                        ELSE ABS((take_profit - entry_price) / (entry_price - stop_loss))
                    END
                ) STORED,
                open_comment TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                outcome TEXT,
                close_comment TEXT,
                pnl_screenshot_file_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP
            )
        ''')


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
        cur = conn.execute(
            '''INSERT INTO trades (user_id, ticker, entry_price, stop_loss, take_profit, setup_type, open_comment)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (user_id, ticker.upper(), entry_price, stop_loss, take_profit, setup_type, open_comment)
        )
        return cur.lastrowid


def get_trade(trade_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            'SELECT * FROM trades WHERE id = ? AND user_id = ?',
            (trade_id, user_id)
        ).fetchone()
        return dict(row) if row else None


def get_active_trades(user_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE user_id = ? AND status IN ('pending', 'active') ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]


def get_history_trades(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE user_id = ? AND status IN ('closed_tp', 'closed_sl', 'cancelled') ORDER BY closed_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [dict(row) for row in rows]


def close_trade(
    trade_id: int,
    user_id: int,
    outcome: str,
    close_comment: Optional[str] = None,
    pnl_screenshot_file_id: Optional[str] = None
) -> bool:
    if outcome not in ('closed_tp', 'closed_sl', 'cancelled'):
        raise ValueError('Invalid outcome')
    with get_connection() as conn:
        cur = conn.execute(
            '''UPDATE trades
               SET status = ?, outcome = ?, close_comment = ?, pnl_screenshot_file_id = ?, closed_at = ?
               WHERE id = ? AND user_id = ? AND status IN ('pending', 'active')''',
            (outcome, outcome, close_comment, pnl_screenshot_file_id, datetime.now().isoformat(), trade_id, user_id)
        )
        return cur.rowcount > 0


def get_stats(user_id: int) -> Dict[str, Any]:
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE user_id = ? AND status IN ('closed_tp', 'closed_sl', 'cancelled')",
            (user_id,)
        ).fetchone()[0]

        wins = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE user_id = ? AND status = 'closed_tp'",
            (user_id,)
        ).fetchone()[0]

        losses = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE user_id = ? AND status = 'closed_sl'",
            (user_id,)
        ).fetchone()[0]

        cancelled = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE user_id = ? AND status = 'cancelled'",
            (user_id,)
        ).fetchone()[0]

        avg_rr = conn.execute(
            "SELECT AVG(risk_reward) FROM trades WHERE user_id = ? AND status = 'closed_tp' AND risk_reward IS NOT NULL",
            (user_id,)
        ).fetchone()[0]

        return {
            'total': total,
            'wins': wins,
            'losses': losses,
            'cancelled': cancelled,
            'win_rate': round(wins / max(total - cancelled, 1) * 100, 1),
            'avg_rr': round(avg_rr or 0, 2)
        }


def get_all_trades_for_export(user_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            'SELECT * FROM trades WHERE user_id = ? ORDER BY created_at DESC',
            (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]
