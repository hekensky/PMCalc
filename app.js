// Telegram WebApp init
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
    document.body.classList.add('telegram');

    // Apply Telegram theme colors
    const root = document.documentElement;
    const theme = tg.themeParams;
    if (theme.bg_color) root.style.setProperty('--bg', theme.bg_color);
    if (theme.text_color) root.style.setProperty('--text', theme.text_color);
    if (theme.hint_color) root.style.setProperty('--text-secondary', theme.hint_color);
    if (theme.button_color) root.style.setProperty('--blue', theme.button_color);
    if (theme.button_text_color) root.style.setProperty('--btn-text', theme.button_text_color);

    // Main button for quick calculate
    tg.MainButton.setText('Рассчитать');
    tg.MainButton.onClick(calculate);
}

// Leverage buttons
const levBtns = document.querySelectorAll('.lev-btn');
const leverageInput = document.getElementById('leverage');

levBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        levBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        leverageInput.value = btn.dataset.lev;
        autoCalculate();
    });
});

leverageInput.addEventListener('input', () => {
    const val = parseInt(leverageInput.value);
    levBtns.forEach(b => {
        b.classList.toggle('active', parseInt(b.dataset.lev) === val);
    });
    autoCalculate();
});

// Auto-calculate on input
const inputs = document.querySelectorAll('input[type="number"]');
inputs.forEach(input => {
    input.addEventListener('input', autoCalculate);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            calculate();
        }
    });
});

let lastResult = null;

function autoCalculate() {
    const deposit = parseFloat(document.getElementById('deposit').value);
    const entry = parseFloat(document.getElementById('entry').value);
    const stop = parseFloat(document.getElementById('stop').value);
    const riskPct = parseFloat(document.getElementById('risk').value);
    const leverage = parseFloat(document.getElementById('leverage').value) || 1;

    if (deposit && entry && stop && riskPct && leverage >= 1 && entry !== stop) {
        calculate(true);
    }
}

function fmt(num, decimals = 2) {
    if (!isFinite(num)) return '—';
    if (Math.abs(num) >= 1000000) return (num / 1000000).toFixed(decimals) + 'M';
    if (Math.abs(num) >= 100000) return (num / 1000).toFixed(Math.min(1, decimals)) + 'K';
    return num.toLocaleString('ru-RU', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

function setResult(id, value, rawValue) {
    const el = document.getElementById(id);
    el.textContent = value;
    el.dataset.raw = rawValue !== undefined ? rawValue : value;
}

function calculate(silent = false) {
    const errorEl = document.getElementById('errorMsg');
    const resultsEl = document.getElementById('results');
    errorEl.className = 'error-msg';

    const deposit = parseFloat(document.getElementById('deposit').value);
    const entry = parseFloat(document.getElementById('entry').value);
    const stop = parseFloat(document.getElementById('stop').value);
    const riskPct = parseFloat(document.getElementById('risk').value);
    const leverage = parseFloat(document.getElementById('leverage').value) || 1;

    // Validation
    if (!deposit || !entry || !stop || !riskPct) {
        if (!silent) showError('Заполните все поля');
        return;
    }
    if (deposit <= 0) {
        if (!silent) showError('Депозит должен быть > 0');
        return;
    }
    if (entry <= 0 || stop <= 0) {
        if (!silent) showError('Цены должны быть > 0');
        return;
    }
    if (entry === stop) {
        if (!silent) showError('Точка входа и стоп не могут быть равны');
        return;
    }
    if (riskPct <= 0 || riskPct > 100) {
        if (!silent) showError('Риск должен быть от 0.01% до 100%');
        return;
    }
    if (leverage < 1) {
        if (!silent) showError('Плечо должно быть >= 1');
        return;
    }

    // Calculations
    const isLong = stop < entry;
    const direction = isLong ? 'LONG' : 'SHORT';

    const riskAmountUSD = deposit * (riskPct / 100);
    const stopDistance = Math.abs(entry - stop);
    const stopPercent = (stopDistance / entry) * 100;
    const positionSize = (riskAmountUSD * entry) / stopDistance;
    const margin = positionSize / leverage;

    // Check if margin exceeds deposit
    if (margin > deposit) {
        showError(`Недостаточно маржи! Нужно: ${fmt(margin)} USDT, доступно: ${fmt(deposit)} USDT`);
        return;
    }

    // Display results
    const dirEl = document.getElementById('direction');
    dirEl.textContent = direction;
    dirEl.className = 'result-value ' + direction.toLowerCase();

    setResult('riskAmount', fmt(riskAmountUSD) + ' USDT', fmt(riskAmountUSD));
    setResult('stopSize', fmt(stopDistance) + ' (' + fmt(stopPercent) + '%)', fmt(stopDistance));
    setResult('positionSize', fmt(positionSize) + ' USDT', fmt(positionSize));
    setResult('margin', fmt(margin) + ' USDT', fmt(margin));
    setResult('lossAtStop', '-' + fmt(riskAmountUSD) + ' USDT (-' + fmt(riskPct) + '%)', '');

    resultsEl.className = 'results show';

    lastResult = {
        direction,
        deposit,
        entry,
        stop,
        riskPct,
        leverage,
        riskAmountUSD,
        stopDistance,
        stopPercent,
        positionSize,
        margin
    };

    if (tg?.MainButton && !tg.MainButton.isVisible) {
        tg.MainButton.show();
    }

    if (tg?.HapticFeedback && !silent) {
        tg.HapticFeedback.notificationOccurred('success');
    }
}

function showError(msg) {
    const errorEl = document.getElementById('errorMsg');
    errorEl.textContent = msg;
    errorEl.className = 'error-msg show';

    if (tg?.HapticFeedback) {
        tg.HapticFeedback.notificationOccurred('error');
    }
}

function copyValue(id) {
    const el = document.getElementById(id);
    const raw = el.dataset.raw || el.textContent;
    const clean = raw.replace(/ USDT|\(|\)|%/g, '').trim();

    if (navigator.clipboard) {
        navigator.clipboard.writeText(clean).then(() => {
            tg?.HapticFeedback?.impactOccurred('light');
            showToast('Скопировано');
        });
    } else {
        const ta = document.createElement('textarea');
        ta.value = clean;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        showToast('Скопировано');
    }
}

function copyAll() {
    if (!lastResult) return;
    const text = [
        `Направление: ${lastResult.direction}`,
        `Депозит: ${fmt(lastResult.deposit)} USDT`,
        `Точка входа: ${fmt(lastResult.entry)}`,
        `Стоп: ${fmt(lastResult.stop)}`,
        `Риск: ${fmt(lastResult.riskPct)}%`,
        `Плечо: ${fmt(lastResult.leverage, 0)}x`,
        ``,
        `💵 Сумма риска: ${fmt(lastResult.riskAmountUSD)} USDT`,
        `📏 Стоп: ${fmt(lastResult.stopDistance)} (${fmt(lastResult.stopPercent)}%)`,
        `📊 Позиция: ${fmt(lastResult.positionSize)} USDT`,
        `🔐 Маржа: ${fmt(lastResult.margin)} USDT`
    ].join('\n');

    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(() => showToast('Результат скопирован'));
    }
}

function showToast(message) {
    if (tg?.showPopup) {
        tg.showPopup({ title: '', message });
        return;
    }
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => document.body.removeChild(toast), 300);
    }, 2000);
}

// Expose for inline onclick
window.copyValue = copyValue;
window.copyAll = copyAll;
window.calculate = calculate;
