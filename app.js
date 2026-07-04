// Telegram WebApp init
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
    document.body.classList.add('telegram');
}

// Leverage buttons
const levBtns = document.querySelectorAll('.lev-btn');
const leverageInput = document.getElementById('leverage');

levBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        levBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        leverageInput.value = btn.dataset.lev;
    });
});

leverageInput.addEventListener('input', () => {
    const val = parseInt(leverageInput.value);
    levBtns.forEach(b => {
        b.classList.toggle('active', parseInt(b.dataset.lev) === val);
    });
});

// Auto-calculate on Enter
document.querySelectorAll('input').forEach(input => {
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            calculate();
        }
    });
});

function fmt(num, decimals = 2) {
    if (num >= 1000000) return (num / 1000000).toFixed(2) + 'M';
    if (num >= 100000) return (num / 1000).toFixed(1) + 'K';
    return num.toLocaleString('ru-RU', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

function calculate() {
    const errorEl = document.getElementById('errorMsg');
    const resultsEl = document.getElementById('results');
    errorEl.className = 'error-msg';
    resultsEl.className = 'results';

    const deposit = parseFloat(document.getElementById('deposit').value);
    const entry = parseFloat(document.getElementById('entry').value);
    const stop = parseFloat(document.getElementById('stop').value);
    const riskPct = parseFloat(document.getElementById('risk').value);
    const leverage = parseFloat(document.getElementById('leverage').value) || 1;

    // Validation
    if (!deposit || !entry || !stop || !riskPct) {
        showError('Заполните все поля');
        return;
    }
    if (deposit <= 0) {
        showError('Депозит должен быть > 0');
        return;
    }
    if (entry <= 0 || stop <= 0) {
        showError('Цены должны быть > 0');
        return;
    }
    if (entry === stop) {
        showError('Точка входа и стоп не могут быть равны');
        return;
    }
    if (riskPct <= 0 || riskPct > 100) {
        showError('Риск должен быть от 0.01% до 100%');
        return;
    }
    if (leverage < 1) {
        showError('Плечо должно быть >= 1');
        return;
    }

    // Calculations
    const isLong = stop < entry;  // stop below entry = LONG; stop above entry = SHORT
    const direction = isLong ? 'LONG' : 'SHORT';
    
    const riskAmountUSD = deposit * (riskPct / 100);
    const stopDistance = Math.abs(entry - stop);
    const stopPercent = (stopDistance / entry) * 100;
    
    // Position size (notional value in USDT)
    // riskAmount = positionSize * (stopDistance / entry)
    // positionSize = riskAmount * entry / stopDistance
    const positionSize = (riskAmountUSD * entry) / stopDistance;
    
    // Margin required
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

    document.getElementById('riskAmount').textContent = fmt(riskAmountUSD) + ' USDT';
    document.getElementById('stopSize').textContent = fmt(stopDistance) + ' (' + fmt(stopPercent) + '%)';
    document.getElementById('positionSize').textContent = fmt(positionSize) + ' USDT';
    document.getElementById('margin').textContent = fmt(margin) + ' USDT';
    document.getElementById('lossAtStop').textContent = '-' + fmt(riskAmountUSD) + ' USDT (-' + fmt(riskPct) + '%)';

    resultsEl.className = 'results show';

    // Haptic feedback
    if (tg?.HapticFeedback) {
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
