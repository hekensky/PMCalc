import io
from typing import List, Dict, Any

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def _setup_style():
    plt.style.use('dark_background')
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.size'] = 10
    plt.rcParams['axes.facecolor'] = '#0a0e1a'
    plt.rcParams['figure.facecolor'] = '#0a0e1a'
    plt.rcParams['axes.edgecolor'] = '#2a3a5e'
    plt.rcParams['axes.labelcolor'] = '#a0a0b0'
    plt.rcParams['xtick.color'] = '#a0a0b0'
    plt.rcParams['ytick.color'] = '#a0a0b0'
    plt.rcParams['grid.color'] = '#1a2340'
    plt.rcParams['grid.alpha'] = 0.5


def _save_to_buffer(fig) -> bytes:
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def generate_stats_image(stats: Dict[str, Any], setup_dist: List[Dict[str, Any]], pnl_series: List[Dict[str, Any]]) -> bytes:
    _setup_style()

    fig = plt.figure(figsize=(10, 10))
    gs = fig.add_gridspec(3, 2, hspace=0.35, wspace=0.3)

    # 1. Win/Loss pie chart
    ax1 = fig.add_subplot(gs[0, 0])
    labels = ['Победы', 'Стопы']
    sizes = [stats['wins'], stats['losses']]
    colors = ['#00e59b', '#ff4d6a']
    if sum(sizes) > 0:
        ax1.pie(sizes, labels=labels, colors=colors, autopct='%1.0f%%', startangle=90,
                textprops={'color': 'white'})
    else:
        ax1.text(0.5, 0.5, 'Нет данных', ha='center', va='center', color='#a0a0b0')
        ax1.set_xticks([])
        ax1.set_yticks([])
    ax1.set_title('Win / Loss', color='white', fontweight='bold')

    # 2. Net PnL big number
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.axis('off')
    pnl = stats['net_pnl']
    color = '#00e59b' if pnl >= 0 else '#ff4d6a'
    ax2.text(0.5, 0.7, f"{pnl:+.2f} USDT", ha='center', va='center',
             fontsize=28, color=color, fontweight='bold')
    ax2.text(0.5, 0.35, f"Прибыль: +{stats['total_profit']:.2f}\nУбыток: {stats['total_loss']:.2f}",
             ha='center', va='center', fontsize=12, color='#a0a0b0')
    ax2.set_title('Net PnL', color='white', fontweight='bold')

    # 3. Setup distribution
    ax3 = fig.add_subplot(gs[1, :])
    if setup_dist:
        names = [s['setup_type'] for s in setup_dist]
        counts = [s['count'] for s in setup_dist]
        wins = [s['wins'] for s in setup_dist]
        x = range(len(names))
        ax3.bar(x, counts, color='#4e7cff', label='Всего', alpha=0.8)
        ax3.bar(x, wins, color='#00e59b', label='Побед', alpha=0.9)
        ax3.set_xticks(x)
        ax3.set_xticklabels(names, rotation=15, ha='right')
        ax3.legend()
        ax3.grid(axis='y', linestyle='--', alpha=0.3)
    else:
        ax3.text(0.5, 0.5, 'Нет данных по сетапам', ha='center', va='center', color='#a0a0b0')
        ax3.set_xticks([])
        ax3.set_yticks([])
    ax3.set_title('Сетапы', color='white', fontweight='bold')

    # 4. Cumulative PnL
    ax4 = fig.add_subplot(gs[2, :])
    if pnl_series:
        cumulative = []
        running = 0
        for t in pnl_series:
            running += t['pnl_amount'] or 0
            cumulative.append(running)
        colors = ['#00e59b' if c >= 0 else '#ff4d6a' for c in cumulative]
        ax4.plot(range(len(cumulative)), cumulative, color='#4e7cff', linewidth=2, marker='o', markersize=4)
        ax4.fill_between(range(len(cumulative)), cumulative, 0, alpha=0.15, color='#4e7cff')
        ax4.axhline(0, color='white', linewidth=0.5, linestyle='--')
        ax4.set_title('Кумулятивный PnL', color='white', fontweight='bold')
        ax4.grid(axis='y', linestyle='--', alpha=0.3)
        ax4.set_xticks([])
    else:
        ax4.text(0.5, 0.5, 'Нет данных по PnL', ha='center', va='center', color='#a0a0b0')
        ax4.set_xticks([])
        ax4.set_yticks([])
        ax4.set_title('Кумулятивный PnL', color='white', fontweight='bold')

    return _save_to_buffer(fig)
