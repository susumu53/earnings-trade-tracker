/**
 * 決算トレード・サイクル予測検証システム
 * フロントエンドロジック (app.js) - 東証リアルタイムデータ & 金融テクニカルチャート完全統合版
 */

let allRecords = [];
let currentFilter = 'all';
let currentOpportunities = [];
let currentChartData = null;

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initFormCalculations();
  initMarketDataHandlers();
  initEventListeners();
  loadData();
});

// タブ切り替え
function initTabs() {
  const tabs = document.querySelectorAll('.tab-btn');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

      tab.classList.add('active');
      const targetPane = document.getElementById(tab.dataset.tab);
      if (targetPane) targetPane.classList.add('active');

      if (tab.dataset.tab === 'tab-insights') {
        loadAnalysis();
      }
    });
  });
}

// 市場APIハンドラーの初期化
function initMarketDataHandlers() {
  // 1. 銘柄コードから市場データをリアルタイム自動取得
  const btnFetch = document.getElementById('btn-fetch-live');
  if (btnFetch) {
    btnFetch.addEventListener('click', async () => {
      const tickerInput = document.getElementById('p-ticker').value.trim();
      const statusDiv = document.getElementById('fetch-status-msg');

      if (!tickerInput) {
        alert('東証の銘柄コード（4桁、例: 6501, 6758）を入力してください。');
        return;
      }

      statusDiv.className = 'fetch-status loading';
      statusDiv.innerHTML = `📡 東証市場APIから [${tickerInput}] のリアルタイム株価・日足・決算日を取得中...`;
      btnFetch.disabled = true;

      try {
        const res = await fetch(`/api/stock/fetch?ticker=${encodeURIComponent(tickerInput)}`);
        const result = await res.json();

        if (!result.success) {
          throw new Error(result.error || 'データ取得に失敗しました。');
        }

        const d = result.data;

        document.getElementById('p-name').value = d.name;
        document.getElementById('p-sector').value = d.sector;
        document.getElementById('p-current-price').value = d.current_price;
        if (d.earnings_date) {
          document.getElementById('p-earnings-date').value = d.earnings_date;
        }
        document.getElementById('p-target-price').value = d.target_price;
        document.getElementById('p-stop-loss').value = d.stop_loss;
        document.getElementById('p-pattern').value = d.technical_pattern;
        document.getElementById('p-progress').value = d.trailing_pe || '';
        document.getElementById('p-consensus').value = d.consensus_status || '中立';

        // 波動計算値の設定
        document.getElementById('wave-a').value = d.wave_a;
        document.getElementById('wave-b').value = d.wave_b;
        document.getElementById('wave-c').value = d.wave_c;
        document.getElementById('wave-n-val').textContent = `${d.wave_targets.N_target.toLocaleString()} 円`;
        document.getElementById('wave-v-val').textContent = `${d.wave_targets.V_target.toLocaleString()} 円`;
        document.getElementById('wave-e-val').textContent = `${d.wave_targets.E_target.toLocaleString()} 円`;
        document.getElementById('wave-n-val').dataset.val = d.wave_targets.N_target;
        document.getElementById('wave-v-val').dataset.val = d.wave_targets.V_target;
        document.getElementById('wave-e-val').dataset.val = d.wave_targets.E_target;

        // テクニカル指標カード表示
        const techCard = document.getElementById('tech-metrics-card');
        if (techCard) {
          techCard.style.display = 'block';
          document.getElementById('metric-ma25').textContent = `${d.ma25} 円`;
          document.getElementById('metric-bias').textContent = `${d.ma25_bias_pct >= 0 ? '+' : ''}${d.ma25_bias_pct}%`;
          document.getElementById('metric-bias').style.color = d.ma25_bias_pct >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)';
          document.getElementById('metric-bbu').textContent = `${d.bb_upper} 円`;
          document.getElementById('metric-bbl').textContent = `${d.bb_lower} 円`;
        }

        document.getElementById('p-notes').value = 
          `【自動テクニカル判定】パターン: ${d.technical_pattern}\n` +
          `25日線: ${d.ma25}円 (乖離: ${d.ma25_bias_pct}%), 上方修正確度: ${d.revision_probability || '★★★'}\n` +
          (d.earnings_growth ? `純利益成長: ${d.earnings_growth >= 0 ? '+' : ''}${d.earnings_growth}%\n` : '') +
          `波動目標: N=${d.wave_targets.N_target}円 / V=${d.wave_targets.V_target}円 / E=${d.wave_targets.E_target}円`;

        statusDiv.className = 'fetch-status success';
        statusDiv.innerHTML = `✅ [${d.ticker}] ${d.name}（現値: ${d.current_price.toLocaleString()}円 / 決算予定: ${d.earnings_date}）の市場データを正常反映しました！`;

        triggerPreviewEvaluation();
        calculateTab2Position();

      } catch (err) {
        statusDiv.className = 'fetch-status error';
        statusDiv.innerHTML = `❌ エラー: ${err.message}`;
      } finally {
        btnFetch.disabled = false;
      }
    });
  }

  // フォーム側の「チャート表示」ボタン
  const btnFormChart = document.getElementById('btn-view-chart-form');
  if (btnFormChart) {
    btnFormChart.addEventListener('click', () => {
      let ticker = document.getElementById('p-ticker').value.trim();
      if (!ticker) {
        // 空の場合は監視リストの先頭銘柄、または代表銘柄(6501)を自動セット
        if (allRecords && allRecords.length > 0) {
          ticker = allRecords[0].ticker;
        } else {
          ticker = '6501';
        }
        document.getElementById('p-ticker').value = ticker;
      }
      openChartModal(ticker);
    });
  }

  // 2. 決算後1週間の実績株価自動取得ボタン（モーダル内）
  const btnFetchPost = document.getElementById('btn-fetch-post-prices');
  if (btnFetchPost) {
    btnFetchPost.addEventListener('click', async () => {
      const ticker = document.getElementById('r-ticker').value;
      const actualDate = document.getElementById('r-actual-date').value;
      const statusDiv = document.getElementById('result-fetch-status');

      if (!ticker || !actualDate) {
        alert('銘柄コードと決算日が必要です。');
        return;
      }

      statusDiv.className = 'fetch-status loading';
      statusDiv.innerHTML = `📡 東証データから決算日(${actualDate})以降の実際の値動きを抽出中...`;
      btnFetchPost.disabled = true;

      try {
        const res = await fetch(`/api/stock/post-earnings?ticker=${encodeURIComponent(ticker)}&date=${encodeURIComponent(actualDate)}`);
        const result = await res.json();

        if (!result.success) {
          throw new Error(result.error || '実績データの取得に失敗しました。');
        }

        const d = result.data;
        document.getElementById('r-post-open').value = d.post_open_price;
        document.getElementById('r-week-high').value = d.week_high_price;
        document.getElementById('r-week-low').value = d.week_low_price;
        document.getElementById('r-week-close').value = d.week_close_price;

        statusDiv.className = 'fetch-status success';
        statusDiv.innerHTML = `✅ 決算後${d.trading_days_counted}営業日の市場株価（寄付:${d.post_open_price}円, 高値:${d.week_high_price}円, 終値:${d.week_close_price}円）を自動入力しました！`;
      } catch (err) {
        statusDiv.className = 'fetch-status error';
        statusDiv.innerHTML = `❌ 取得失敗: ${err.message}`;
      } finally {
        btnFetchPost.disabled = false;
      }
    });
  }

  // 3. 決算直前 注目銘柄スクリーナーモーダル
  const btnAutoScreen = document.getElementById('btn-auto-screen-modal');
  if (btnAutoScreen) {
    btnAutoScreen.addEventListener('click', openAutoScreenModal);
  }

  // 4. DBクリア（本番用リセット）
  const btnClear = document.getElementById('btn-clear-db');
  if (btnClear) {
    btnClear.addEventListener('click', async () => {
      if (confirm('【確認】データベース内の全レコードを削除し、実運用のためにまっさらな状態に初期化しますか？')) {
        try {
          const res = await fetch('/api/db/clear', { method: 'POST' });
          const result = await res.json();
          if (result.success) {
            alert('データベースを初期化しました。本番トレードの予測を登録してください。');
            loadData();
            loadAnalysis();
          }
        } catch (err) {
          alert('初期化エラー: ' + err);
        }
      }
    });
  }
}

let currentSelectedStrategy = 'ALL';

// 決算直前 注目銘柄スクリーナーモーダルの制御
async function openAutoScreenModal() {
  const modal = document.getElementById('auto-screen-modal');
  const loading = document.getElementById('auto-screen-loading');
  const resultsDiv = document.getElementById('auto-screen-results');
  const container = document.getElementById('opportunities-container');

  modal.classList.add('active');
  loading.style.display = 'block';
  resultsDiv.style.display = 'none';
  container.innerHTML = '';
  currentOpportunities = [];
  currentSelectedStrategy = 'ALL';

  // 既存の統計バーがあれば削除
  const existingStats = document.querySelector('.scan-stats-bar');
  if (existingStats) existingStats.remove();

  try {
    const res = await fetch('/api/stock/auto-screen');
    const result = await res.json();

    loading.style.display = 'none';
    resultsDiv.style.display = 'block';

    if (!result.opportunities || result.opportunities.length === 0) {
      container.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-dim);">現在、決算日が近く一定のスコア基準を満たす銘柄は見つかりませんでした。別の日に再度お試しください。</div>`;
      return;
    }

    currentOpportunities = result.opportunities;

    // スキャン統計を表示
    const scanStats = result.scan_stats;
    if (scanStats) {
      const statsHtml = `<div class="scan-stats-bar" style="background:rgba(6,182,212,0.08); border:1px solid rgba(6,182,212,0.2); border-radius:8px; padding:10px 16px; margin-bottom:12px; font-size:13px; color:var(--text-muted);">
        📊 スキャン統計: 東証 <strong>${scanStats.total_scanned || '---'}</strong> 銘柄走査 → 決算日該当 <strong>${scanStats.matched || '---'}</strong> 銘柄 → 3大戦略スコア基準通過 <strong>${currentOpportunities.length}</strong> 銘柄
        ${scanStats.from_cache ? ' (キャッシュデータ)' : ` (${scanStats.elapsed_sec || '---'}秒)`}
      </div>`;
      const tabsEl = document.querySelector('.strategy-filter-tabs');
      if (tabsEl) {
        tabsEl.insertAdjacentHTML('beforebegin', statsHtml);
      }
    }

    // 各戦略ごとの件数を集計してバッジを更新
    updateStrategyTabCounts();

    // デフォルト（ALL）を描画
    filterOpportunitiesByStrategy('ALL');

    document.getElementById('btn-batch-register-selected').onclick = handleBatchRegister;

  } catch (err) {
    loading.innerHTML = `<p style="color:var(--accent-rose);">自動発掘エラー: ${err.message}</p>`;
  }
}

// 戦略タブごとの件数更新
function updateStrategyTabCounts() {
  const countAll = currentOpportunities.length;
  const countA = currentOpportunities.filter(o => o.strategy === 'A').length;
  const countB = currentOpportunities.filter(o => o.strategy === 'B').length;
  const countC = currentOpportunities.filter(o => o.strategy === 'C').length;

  const elAll = document.getElementById('strat-count-all');
  const elA = document.getElementById('strat-count-a');
  const elB = document.getElementById('strat-count-b');
  const elC = document.getElementById('strat-count-c');

  if (elAll) elAll.textContent = countAll;
  if (elA) elA.textContent = countA;
  if (elB) elB.textContent = countB;
  if (elC) elC.textContent = countC;
}

// 戦略タブ切り替えフィルタ
function filterOpportunitiesByStrategy(strategy) {
  currentSelectedStrategy = strategy;

  // タブボタンのアクティブ表示切替
  document.querySelectorAll('.strat-tab-btn').forEach(btn => {
    if (btn.dataset.strategy === strategy) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  // ガイドバナーの更新
  const bannerIcon = document.getElementById('strat-guide-icon');
  const bannerText = document.getElementById('strat-guide-text');
  if (bannerText && bannerIcon) {
    if (strategy === 'A') {
      bannerIcon.textContent = '⚡';
      bannerText.innerHTML = '<strong>【戦略A: 決算前モメンタム】</strong> 決算発表7〜14日前に仕込み、決算発表直前（前日引け）に全決済するノーリスク先回り手法です。<span style="color:var(--accent-rose); font-weight:700;">※ 決算持ち越しは厳禁</span>';
    } else if (strategy === 'B') {
      bannerIcon.textContent = '🎯';
      bannerText.innerHTML = '<strong>【戦略B: 決算またぎ上方修正】</strong> 強い上昇トレンド・低時価総額から上方修正の確度が高い銘柄を厳選し、<span style="color:var(--accent-amber); font-weight:700;">翌日のストップ高</span>を狙って決算を跨ぐ本命手法です。';
    } else if (strategy === 'C') {
      bannerIcon.textContent = '🚀';
      bannerText.innerHTML = '<strong>【戦略C: 決算後PEAD】</strong> 決算発表直後、好決算＋大出来高を伴って急騰した銘柄の押し目・寄り付きに乗り、数週間のドリフトを抜く安全追随手法です。';
    } else {
      bannerIcon.textContent = '🌐';
      bannerText.innerHTML = 'プロの決算トレード3大戦略（戦略A: 前モメンタム / 戦略B: またぎS高 / 戦略C: 後PEAD）に基づき銘柄を自動分類。タブをクリックして戦略別に絞り込めます。';
    }
  }

  renderFilteredOpportunities();
}

// 絞り込んだ銘柄カードを描画
function renderFilteredOpportunities() {
  const container = document.getElementById('opportunities-container');
  const chkSelectAll = document.getElementById('chk-select-all-opps');
  container.innerHTML = '';

  const filtered = currentSelectedStrategy === 'ALL'
    ? currentOpportunities
    : currentOpportunities.filter(o => o.strategy === currentSelectedStrategy);

  if (filtered.length === 0) {
    container.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-dim);">現在この戦略に適合する銘柄はありません。他の戦略タブをご覧ください。</div>`;
    updateSelectedCount();
    return;
  }

  filtered.forEach((opp) => {
    // 元の配列でのインデックスを探す
    const origIdx = currentOpportunities.indexOf(opp);
    const card = document.createElement('div');
    card.className = `opp-card opp-card-strat-${opp.strategy.toLowerCase()}`;

    const reasonsHtml = opp.reasons.map(r => `<span class="opp-reason-tag">✓ ${r}</span>`).join('');

    // 戦略バッジのスタイル定義
    let stratBadgeClass = 'strat-badge-a';
    if (opp.strategy === 'B') stratBadgeClass = 'strat-badge-b';
    if (opp.strategy === 'C') stratBadgeClass = 'strat-badge-c';

    card.innerHTML = `
      <div class="opp-checkbox-wrap">
        <input type="checkbox" class="opp-check-item" data-index="${origIdx}" checked>
      </div>
      <div style="flex:1;">
        <div class="opp-header">
          <span class="strat-badge ${stratBadgeClass}">${opp.strategy_badge}</span>
          <span class="opp-ticker">${opp.ticker}</span>
          <span class="opp-name">${opp.name}</span>
          <span class="opp-rank">${opp.rank}</span>
        </div>

        <!-- プロトレーダーの売買アクション指針 -->
        <div class="opp-action-callout">
          <span class="opp-action-text">${opp.trade_action}</span>
        </div>

        <div class="opp-meta">
          <span>決算予定: <strong>${opp.earnings_date}</strong> <span style="color:var(--accent-orange); font-weight:700;">(${opp.days_until_earnings === 0 ? '本日発表予定！' : opp.days_until_earnings === 1 ? '明日発表！' : `あと約${opp.days_until_earnings}日`})</span></span>
          <span>テクニカル: <strong>${opp.technical_pattern}</strong></span>
          <span>25日線乖離: ${opp.ma25_bias_pct >= 0 ? '+' : ''}${opp.ma25_bias_pct}%</span>
          <span>上方修正確度: <strong style="color:var(--accent-amber);">${opp.revision_probability || '★★★ 標準'}</strong></span>
          ${opp.earnings_growth !== null && opp.earnings_growth !== undefined ? `<span>純利益成長: <strong style="color:var(--accent-emerald);">${opp.earnings_growth >= 0 ? '+' : ''}${opp.earnings_growth}%</strong></span>` : ''}
          ${opp.market_cap ? `<span>時価総額: ${Math.round(opp.market_cap / 1000000000)}億円</span>` : ''}
          ${opp.volume_ratio ? `<span>出来高比: ${opp.volume_ratio}倍</span>` : ''}
        </div>
        <div class="opp-price-box">
          <span>現値: <strong>${opp.current_price.toLocaleString()}円</strong></span> ➔ 
          <span>想定目標: <strong class="opp-target-val">${opp.target_price.toLocaleString()}円 (+${opp.expected_return_pct}%)</strong></span>
          <span style="color:var(--text-dim);">| 損切り: ${opp.stop_loss.toLocaleString()}円 (RR: 1:${opp.risk_reward_ratio})</span>
        </div>
        <div class="opp-reasons">
          ${reasonsHtml}
        </div>
      </div>
      <div class="opp-actions">
        <div class="opp-score-badge">適性スコア ${opp.score} pt</div>
        <div class="opp-strat-scores" style="font-size:10px; color:var(--text-dim); text-align:center; margin-bottom:4px;">
          A:${opp.strategy_scores ? opp.strategy_scores.A : '--'} | B:${opp.strategy_scores ? opp.strategy_scores.B : '--'} | C:${opp.strategy_scores ? opp.strategy_scores.C : '--'}
        </div>
        <div style="display:flex; flex-direction:column; gap:5px; width:100%;">
          <button class="btn btn-secondary btn-sm" onclick='openPositionModalDirect(${JSON.stringify(opp).replace(/'/g, "&apos;")})'>
            💼 ロット計算
          </button>
          <button class="btn btn-secondary btn-sm" onclick="openChartModal('${opp.ticker}')">
            📈 チャート確認
          </button>
          <button class="btn btn-primary btn-sm" onclick='registerOpportunityDirectly(${JSON.stringify(opp).replace(/'/g, "&apos;")})'>
            💾 登録
          </button>
        </div>
      </div>
    `;
    container.appendChild(card);
  });

  document.querySelectorAll('.opp-check-item').forEach(chk => {
    chk.addEventListener('change', updateSelectedCount);
  });

  chkSelectAll.checked = true;
  chkSelectAll.onchange = () => {
    const isChecked = chkSelectAll.checked;
    document.querySelectorAll('.opp-check-item').forEach(chk => {
      chk.checked = isChecked;
    });
    updateSelectedCount();
  };

  updateSelectedCount();
}

function updateSelectedCount() {
  const checked = document.querySelectorAll('.opp-check-item:checked');
  const countEl = document.getElementById('opps-selected-count');
  if (countEl) countEl.textContent = checked.length;
}

// 選択された銘柄を一括登録
async function handleBatchRegister() {
  const checkedBoxes = document.querySelectorAll('.opp-check-item:checked');
  if (checkedBoxes.length === 0) {
    alert('登録する銘柄を1件以上選択してください。');
    return;
  }

  const season = document.getElementById('season-selector').value || '2026Q3';
  const todayStr = new Date().toISOString().split('T')[0];

  const itemsToRegister = [];
  checkedBoxes.forEach(chk => {
    const idx = parseInt(chk.dataset.index);
    const opp = currentOpportunities[idx];
    if (opp) {
      itemsToRegister.push({
        season_id: season,
        ticker: opp.ticker,
        name: opp.name,
        sector: opp.sector,
        pick_date: todayStr,
        earnings_date: opp.earnings_date,
        current_price: opp.current_price,
        target_price: opp.target_price,
        stop_loss: opp.stop_loss,
        expected_return_pct: opp.expected_return_pct,
        risk_reward_ratio: opp.risk_reward_ratio,
        technical_pattern: opp.technical_pattern,
        progress_rate: 0.0,
        consensus_status: '上振れ期待',
        notes: `【${opp.strategy_name || '決算スクリーナー'}】${opp.trade_action || ''}\nスコア: ${opp.score}pt (${opp.rank})\n根拠: ${opp.reasons.join(' / ')}`,
        status: 'pending'
      });
    }
  });

  try {
    const res = await fetch('/api/predictions/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: itemsToRegister })
    });
    const result = await res.json();
    if (result.success) {
      alert(`選択された ${result.inserted_count} 銘柄を一括登録しました！\n監視リストに追加されました。`);
      closeAutoScreenModal();
      document.querySelector('.tab-btn[data-tab="tab-watchlist"]').click();
      loadData();
    }
  } catch (err) {
    alert('一括登録エラー: ' + err);
  }
}

function closeAutoScreenModal() {
  document.getElementById('auto-screen-modal').classList.remove('active');
}

// 単一銘柄の登録
async function registerOpportunityDirectly(opp) {
  const season = document.getElementById('season-selector').value || '2026Q3';
  const todayStr = new Date().toISOString().split('T')[0];

  const payload = {
    season_id: season,
    ticker: opp.ticker,
    name: opp.name,
    sector: opp.sector,
    pick_date: todayStr,
    earnings_date: opp.earnings_date,
    current_price: opp.current_price,
    target_price: opp.target_price,
    stop_loss: opp.stop_loss,
    expected_return_pct: opp.expected_return_pct,
    risk_reward_ratio: opp.risk_reward_ratio,
    technical_pattern: opp.technical_pattern,
    progress_rate: 0.0,
    consensus_status: '上振れ期待',
    notes: `【${opp.strategy_name || '決算スクリーナー'}】${opp.trade_action || ''}\nスコア: ${opp.score}pt (${opp.rank})\n根拠: ${opp.reasons.join(' / ')}`,
    status: 'pending'
  };

  try {
    const res = await fetch('/api/predictions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (result.success) {
      alert(`[${opp.ticker}] ${opp.name} を監視・予測リストに登録しました！`);
      closeAutoScreenModal();
      document.querySelector('.tab-btn[data-tab="tab-watchlist"]').click();
      loadData();
    }
  } catch (err) {
    alert('登録エラー: ' + err);
  }
}

// スキャンからフォームへの読込
function selectStockForPrediction(ticker) {
  closeAutoScreenModal();
  document.querySelector('.tab-btn[data-tab="tab-new-pickup"]').click();
  document.getElementById('p-ticker').value = ticker;
  document.getElementById('btn-fetch-live').click();
}

// ==========================================================
// 📈 金融テクニカルチャート・Canvas描画エンジン
// ==========================================================

async function openChartModal(ticker) {
  // 他のモーダルが開いている場合は閉じる
  const autoModal = document.getElementById('auto-screen-modal');
  if (autoModal && autoModal.classList.contains('active')) {
    autoModal.classList.remove('active');
  }

  const modal = document.getElementById('chart-modal');
  const loading = document.getElementById('chart-loading');
  const content = document.getElementById('chart-content-area');

  modal.classList.add('active');
  loading.style.display = 'block';
  content.style.display = 'none';

  try {
    const res = await fetch(`/api/stock/chart?ticker=${encodeURIComponent(ticker)}&period=6mo`);
    const json = await res.json();

    if (!json.success) {
      throw new Error(json.error || 'チャートデータの取得に失敗しました。');
    }

    const data = json.data;
    currentChartData = data;

    // ヘッダー情報セット
    document.getElementById('chart-stock-title').textContent = `[${data.ticker}] ${data.name}`;
    document.getElementById('chart-pattern-badge').textContent = data.technical_pattern;

    // サマリーバー
    document.getElementById('cs-price').textContent = `${data.current_price.toLocaleString()} 円`;
    document.getElementById('cs-target').textContent = `${data.target_price.toLocaleString()} 円`;
    document.getElementById('cs-stop').textContent = `${data.stop_loss.toLocaleString()} 円`;
    document.getElementById('cs-gain').textContent = `+${data.expected_return_pct}%`;
    document.getElementById('cs-rr').textContent = `1 : ${data.risk_reward_ratio}`;
    document.getElementById('cs-earnings').textContent = data.earnings_date || '--';

    // テクニカル診断リスト描画
    const diagList = document.getElementById('chart-diagnosis-list');
    diagList.innerHTML = '';
    data.technical_diagnosis.forEach(txt => {
      const li = document.createElement('li');
      li.textContent = txt;
      diagList.appendChild(li);
    });

    // 波動マトリクス
    document.getElementById('cw-a').textContent = `${data.wave_points.a}円`;
    document.getElementById('cw-b').textContent = `${data.wave_points.b}円`;
    document.getElementById('cw-c').textContent = `${data.wave_points.c}円`;
    document.getElementById('cw-n').textContent = `${data.wave_targets.N_target.toLocaleString()} 円`;
    document.getElementById('cw-v').textContent = `${data.wave_targets.V_target.toLocaleString()} 円`;
    document.getElementById('cw-e').textContent = `${data.wave_targets.E_target.toLocaleString()} 円`;

    // チャートから予測登録へ採用ボタン
    document.getElementById('btn-chart-adopt').onclick = () => {
      closeChartModal();
      selectStockForPrediction(data.ticker);
    };

    loading.style.display = 'none';
    content.style.display = 'block';

    // Canvasのレンダリング
    setTimeout(() => {
      renderCandleChart(data.candles, data);
    }, 50);

  } catch (err) {
    loading.innerHTML = `<p style="color:var(--accent-rose);">チャートエラー: ${err.message}</p>`;
  }
}

function closeChartModal() {
  document.getElementById('chart-modal').classList.remove('active');
}

// Canvasによる高精細金融チャート描画
function renderCandleChart(candles, meta) {
  const canvas = document.getElementById('main-stock-canvas');
  if (!canvas) return;

  // Retina対応
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;

  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const w = rect.width;
  const h = rect.height;

  // 上下分割（上75%が価格、下25%が出来高）
  const priceH = h * 0.72;
  const volH = h * 0.22;
  const volTop = h * 0.78;
  const padRight = 60; // Y軸マージン
  const padTop = 20;

  // 表示するローソク足数（直近70日分）
  const viewCandles = candles.slice(-70);
  const n = viewCandles.length;
  if (n === 0) return;

  // 価格の最小・最大値（目標株価や損切りライン、ボリンジャーバンドも含めてスケーリング）
  let minP = Math.min(...viewCandles.map(c => c.low));
  let maxP = Math.max(...viewCandles.map(c => c.high));

  if (meta.target_price) maxP = Math.max(maxP, meta.target_price * 1.02);
  if (meta.stop_loss) minP = Math.min(minP, meta.stop_loss * 0.98);

  viewCandles.forEach(c => {
    if (c.bb_upper) maxP = Math.max(maxP, c.bb_upper);
    if (c.bb_lower) minP = Math.min(minP, c.bb_lower);
  });

  const pRange = maxP - minP || 1;
  const pToY = (p) => padTop + (priceH - padTop) * (1 - (p - minP) / pRange);

  // 出来高の最大値
  const maxV = Math.max(...viewCandles.map(c => c.volume)) || 1;
  const vToH = (v) => (v / maxV) * volH;

  const candleW = (w - padRight) / n;
  const barW = Math.max(2, candleW * 0.65);

  // 背景クリア
  ctx.fillStyle = '#0a0e17';
  ctx.fillRect(0, 0, w, h);

  // グリッド線（価格）
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
  ctx.lineWidth = 1;
  const gridSteps = 5;
  for (let i = 0; i <= gridSteps; i++) {
    const gP = minP + (pRange / gridSteps) * i;
    const gY = pToY(gP);
    ctx.beginPath();
    ctx.moveTo(0, gY);
    ctx.lineTo(w - padRight, gY);
    ctx.stroke();

    // Y軸目盛りラベル
    ctx.fillStyle = '#64748b';
    ctx.font = '10px JetBrains Mono, monospace';
    ctx.textAlign = 'left';
    ctx.fillText(`${Math.round(gP).toLocaleString()}`, w - padRight + 6, gY + 3);
  }

  // ボリンジャーバンド帯の塗りつぶし
  ctx.beginPath();
  let firstBB = true;
  for (let i = 0; i < n; i++) {
    const c = viewCandles[i];
    if (c.bb_upper) {
      const x = i * candleW + candleW / 2;
      const y = pToY(c.bb_upper);
      if (firstBB) { ctx.moveTo(x, y); firstBB = false; }
      else { ctx.lineTo(x, y); }
    }
  }
  for (let i = n - 1; i >= 0; i--) {
    const c = viewCandles[i];
    if (c.bb_lower) {
      const x = i * candleW + candleW / 2;
      const y = pToY(c.bb_lower);
      ctx.lineTo(x, y);
    }
  }
  ctx.closePath();
  ctx.fillStyle = 'rgba(139, 92, 246, 0.07)';
  ctx.fill();

  // ボリンジャーバンド外枠線 (±2σ)
  ['bb_upper', 'bb_lower'].forEach(key => {
    ctx.beginPath();
    ctx.strokeStyle = 'rgba(139, 92, 246, 0.4)';
    ctx.lineWidth = 1;
    let started = false;
    for (let i = 0; i < n; i++) {
      const c = viewCandles[i];
      if (c[key]) {
        const x = i * candleW + candleW / 2;
        const y = pToY(c[key]);
        if (!started) { ctx.moveTo(x, y); started = true; }
        else { ctx.lineTo(x, y); }
      }
    }
    ctx.stroke();
  });

  // 移動平均線（75MA: アンバー）
  ctx.beginPath();
  ctx.strokeStyle = '#f59e0b';
  ctx.lineWidth = 1.5;
  let started75 = false;
  for (let i = 0; i < n; i++) {
    const c = viewCandles[i];
    if (c.ma75) {
      const x = i * candleW + candleW / 2;
      const y = pToY(c.ma75);
      if (!started75) { ctx.moveTo(x, y); started75 = true; }
      else { ctx.lineTo(x, y); }
    }
  }
  ctx.stroke();

  // 移動平均線（25MA: シアン）
  ctx.beginPath();
  ctx.strokeStyle = '#06b6d4';
  ctx.lineWidth = 2;
  let started25 = false;
  for (let i = 0; i < n; i++) {
    const c = viewCandles[i];
    if (c.ma25) {
      const x = i * candleW + candleW / 2;
      const y = pToY(c.ma25);
      if (!started25) { ctx.moveTo(x, y); started25 = true; }
      else { ctx.lineTo(x, y); }
    }
  }
  ctx.stroke();

  // 目標株価ライン（エメラルド点線）
  if (meta.target_price) {
    const tY = pToY(meta.target_price);
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = '#10b981';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(0, tY);
    ctx.lineTo(w - padRight, tY);
    ctx.stroke();
    ctx.fillStyle = '#10b981';
    ctx.font = '10px JetBrains Mono';
    ctx.fillText(`目標: ${meta.target_price}円`, w - padRight + 6, tY + 3);
    ctx.restore();
  }

  // 損切りライン（ローズ点線）
  if (meta.stop_loss) {
    const sY = pToY(meta.stop_loss);
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = '#f43f5e';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(0, sY);
    ctx.lineTo(w - padRight, sY);
    ctx.stroke();
    ctx.fillStyle = '#f43f5e';
    ctx.font = '10px JetBrains Mono';
    ctx.fillText(`損切: ${meta.stop_loss}円`, w - padRight + 6, sY + 3);
    ctx.restore();
  }

  // ローソク足＆出来高バーの描画
  for (let i = 0; i < n; i++) {
    const c = viewCandles[i];
    const x = i * candleW + candleW / 2;
    const isUp = c.close >= c.open;
    const color = isUp ? '#10b981' : '#f43f5e';

    // 1. ローソク足のヒゲ
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, pToY(c.high));
    ctx.lineTo(x, pToY(c.low));
    ctx.stroke();

    // 2. ローソク足の実体
    const openY = pToY(c.open);
    const closeY = pToY(c.close);
    const bodyTop = Math.min(openY, closeY);
    const bodyH = Math.max(2, Math.abs(closeY - openY));

    ctx.fillStyle = color;
    ctx.fillRect(x - barW / 2, bodyTop, barW, bodyH);

    // 3. 出来高バー
    const vH = vToH(c.volume);
    ctx.fillStyle = isUp ? 'rgba(16, 185, 129, 0.35)' : 'rgba(244, 63, 94, 0.35)';
    ctx.fillRect(x - barW / 2, h - vH - 6, barW, vH);
  }

  // マウスホバー処理（クロスヘアと四本値ツールチップ）
  canvas.onmousemove = (e) => {
    const mRect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - mRect.left;
    const idx = Math.floor(mouseX / candleW);

    if (idx >= 0 && idx < n) {
      const c = viewCandles[idx];
      document.getElementById('th-date').textContent = c.date;
      document.getElementById('th-open').textContent = c.open.toLocaleString();
      document.getElementById('th-high').textContent = c.high.toLocaleString();
      document.getElementById('th-low').textContent = c.low.toLocaleString();
      document.getElementById('th-close').textContent = c.close.toLocaleString();
      document.getElementById('th-ma25').textContent = c.ma25 ? `${c.ma25.toLocaleString()}` : '--';
      document.getElementById('th-ma75').textContent = c.ma75 ? `${c.ma75.toLocaleString()}` : '--';
      document.getElementById('th-vol').textContent = c.volume.toLocaleString();
    }
  };
}

// 監視リストテーブル描画
function renderTable(records) {
  const tbody = document.getElementById('records-tbody');
  tbody.innerHTML = '';

  const filtered = records.filter(r => {
    if (currentFilter === 'pending') return r.status === 'pending';
    if (currentFilter === 'completed') return r.status === 'completed';
    return true;
  });

  document.getElementById('badge-total').textContent = filtered.length;

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding: 40px; color: var(--text-dim);">登録されている銘柄データがありません。「🔍 決算直前 注目銘柄スクリーナー」から一括登録するか、銘柄コードを入力して登録してください。</td></tr>`;
    return;
  }

  const today = new Date();
  today.setHours(0,0,0,0);

  filtered.forEach(r => {
    const tr = document.createElement('tr');

    const eDate = new Date(r.earnings_date);
    eDate.setHours(0,0,0,0);
    const diffDays = Math.round((eDate - today) / (1000 * 60 * 60 * 24));

    let statusHtml = '';
    if (r.status === 'completed') {
      const badgeClass = r.win_loss === 'WIN' ? 'win-badge' : (r.win_loss === 'LOSS' ? 'loss-badge' : 'status-pill');
      statusHtml = `<span class="${badgeClass}">検証済 (${r.win_loss})</span>`;
    } else {
      if (diffDays > 0) {
        statusHtml = `<span class="status-pill status-pending">決算まで ${diffDays} 日</span>`;
      } else if (diffDays === 0) {
        statusHtml = `<span class="status-pill status-pending" style="color:var(--accent-cyan); border-color:var(--accent-cyan);">本日決算！</span>`;
      } else {
        statusHtml = `<span class="status-pill status-pending" style="color:var(--accent-emerald); border-color:var(--accent-emerald);">決算通過 (結果自動取得可)</span>`;
      }
    }

    let resultColHtml = '<span class="text-dim">未検証</span>';
    if (r.status === 'completed') {
      const retColor = r.actual_return_pct >= 0 ? 'text-success' : 'text-danger';
      resultColHtml = `
        <div>
          <strong class="${retColor}">確定: ${r.actual_return_pct >= 0 ? '+' : ''}${r.actual_return_pct}%</strong>
          <span style="font-size:11px; display:block; color:var(--text-muted)">最大: +${r.max_gain_pct}% (${r.target_hit ? '目標達成🎯' : '未達'})</span>
        </div>
      `;
    }

    tr.innerHTML = `
      <td>${statusHtml}</td>
      <td class="stock-clickable-cell" onclick="jumpToRealtimeAnalysis('${r.ticker}')" title="クリックしてリアルタイム分析へジャンプ">
        <strong class="stock-jump-link">${r.ticker} ↗</strong><br>
        <span style="font-size:12px; color:var(--text-muted);">${r.name}</span>
      </td>
      <td>${r.earnings_date}</td>
      <td onclick="jumpToRealtimeAnalysis('${r.ticker}')" style="cursor:pointer;" title="クリックしてリアルタイム分析へジャンプ">
        <span style="font-size:12px;">${r.technical_pattern}</span>
      </td>
      <td onclick="jumpToRealtimeAnalysis('${r.ticker}')" style="cursor:pointer;" title="クリックしてリアルタイム分析へジャンプ">
        <span style="font-family:var(--font-mono);">${r.current_price.toLocaleString()}円</span> ➔ 
        <strong style="font-family:var(--font-mono); color:var(--accent-cyan);">${r.target_price.toLocaleString()}円</strong>
      </td>
      <td><strong class="text-success">+${r.expected_return_pct}%</strong></td>
      <td><span style="font-family:var(--font-mono); color:var(--accent-rose);">${r.stop_loss.toLocaleString()}円</span></td>
      <td><span style="font-family:var(--font-mono);">1 : ${r.risk_reward_ratio}</span></td>
      <td><span style="font-size:12px;">${r.consensus_status || '中立'}</span></td>
      <td>${resultColHtml}</td>
      <td>
        <div style="display:flex; gap:6px; flex-wrap:nowrap;">
          <button class="btn btn-secondary btn-sm" onclick="jumpToRealtimeAnalysis('${r.ticker}')" title="リアルタイム分析へジャンプして最新データを取得">
            🔍 分析
          </button>
          <button class="btn btn-secondary btn-sm" onclick="openChartModal('${r.ticker}')" title="テクニカルチャートを表示">
            📈
          </button>
          <button class="btn btn-secondary btn-sm" onclick="openResultModal(${r.pred_id})">
            ${r.status === 'completed' ? '修正' : '📝 結果記録'}
          </button>
          <button class="btn btn-danger-outline btn-sm" onclick="handleDelete(${r.pred_id})">🗑️</button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// 監視リストからリアルタイム分析タブへの即時ジャンプ
function jumpToRealtimeAnalysis(ticker) {
  // 1. タブ2（銘柄ピックアップ＆リアルタイム分析）に切り替え
  const tabBtn = document.querySelector('.tab-btn[data-tab="tab-new-pickup"]');
  if (tabBtn) tabBtn.click();

  // 2. 銘柄コードをセット
  const tickerInput = document.getElementById('p-ticker');
  if (tickerInput) {
    tickerInput.value = ticker;
  }

  // 3. 自動フェッチを実行
  const btnFetch = document.getElementById('btn-fetch-live');
  if (btnFetch) {
    btnFetch.click();
  }

  // 4. 画面トップへスクロール
  window.scrollTo({ top: 0, behavior: 'smooth' });
}


// イベントリスナー初期化
function initEventListeners() {
  document.querySelectorAll('.filter-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      currentFilter = chip.dataset.filter;
      renderTable(allRecords);
    });
  });

  const seasonSelect = document.getElementById('season-selector');
  if (seasonSelect) {
    seasonSelect.addEventListener('change', () => {
      loadData();
      loadAnalysis();
    });
  }

  document.getElementById('form-prediction').addEventListener('submit', handlePredictionSubmit);
  document.getElementById('form-result').addEventListener('submit', handleResultSubmit);
  document.getElementById('btn-export-md').addEventListener('click', showMarkdownReport);

  const todayStr = new Date().toISOString().split('T')[0];
  document.getElementById('p-pick-date').value = todayStr;
}

// 波動計算
function initFormCalculations() {
  const waveA = document.getElementById('wave-a');
  const waveB = document.getElementById('wave-b');
  const waveC = document.getElementById('wave-c');

  function updateWaves() {
    const a = parseFloat(waveA.value);
    const b = parseFloat(waveB.value);
    const c = parseFloat(waveC.value);

    if (b > a && c <= b) {
      const n = Math.round(c + (b - a));
      const v = Math.round(b + (b - c));
      const e = Math.round(b + (b - a));
      document.getElementById('wave-n-val').textContent = `${n.toLocaleString()} 円`;
      document.getElementById('wave-v-val').textContent = `${v.toLocaleString()} 円`;
      document.getElementById('wave-e-val').textContent = `${e.toLocaleString()} 円`;
      document.getElementById('wave-n-val').dataset.val = n;
      document.getElementById('wave-v-val').dataset.val = v;
      document.getElementById('wave-e-val').dataset.val = e;
    } else {
      document.getElementById('wave-n-val').textContent = '-- 円';
      document.getElementById('wave-v-val').textContent = '-- 円';
      document.getElementById('wave-e-val').textContent = '-- 円';
    }
  }

  [waveA, waveB, waveC].forEach(el => el.addEventListener('input', updateWaves));
  document.getElementById('btn-calc-preview').addEventListener('click', triggerPreviewEvaluation);
}

function applyTarget(type) {
  let val = null;
  if (type === 'wave-n') val = document.getElementById('wave-n-val').dataset.val;
  if (type === 'wave-v') val = document.getElementById('wave-v-val').dataset.val;
  if (type === 'wave-e') val = document.getElementById('wave-e-val').dataset.val;

  if (val) {
    document.getElementById('p-target-price').value = val;
    triggerPreviewEvaluation();
  }
}

// リアルタイム評価プレビュー
async function triggerPreviewEvaluation() {
  const payload = {
    ticker: document.getElementById('p-ticker').value,
    name: document.getElementById('p-name').value,
    current_price: parseFloat(document.getElementById('p-current-price').value || 0),
    target_price: parseFloat(document.getElementById('p-target-price').value || 0),
    stop_loss: parseFloat(document.getElementById('p-stop-loss').value || 0),
    technical_pattern: document.getElementById('p-pattern').value,
    progress_rate: parseFloat(document.getElementById('p-progress').value || 0),
    consensus_status: document.getElementById('p-consensus').value,
    low_a: parseFloat(document.getElementById('wave-a').value || 0),
    high_b: parseFloat(document.getElementById('wave-b').value || 0),
    pull_c: parseFloat(document.getElementById('wave-c').value || 0)
  };

  if (!payload.current_price || !payload.target_price || !payload.stop_loss) {
    return;
  }

  try {
    const res = await fetch('/api/predict/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    document.getElementById('preview-score').textContent = data.score;
    document.getElementById('preview-rating').textContent = data.rating;
    document.getElementById('preview-expected-return').textContent = `+${data.expected_return_pct}%`;
    document.getElementById('preview-risk').textContent = `-${data.risk_pct}%`;
    document.getElementById('preview-rr').textContent = `1 : ${data.risk_reward_ratio}`;

    const hStats = data.historical_stats;
    if (hStats.sample_count > 0) {
      document.getElementById('preview-history-text').innerHTML = 
        `過去実績: 同パターン <strong>${hStats.sample_count}件</strong> 中、勝率 <strong class="text-success">${hStats.win_rate}%</strong>、平均最大上昇 <strong class="text-cyan">+${hStats.avg_gain}%</strong> です。`;
    } else {
      document.getElementById('preview-history-text').innerHTML = 
        `過去実績: 同パターンの検証データは収集中です。基準モデル勝率: <strong>${hStats.win_rate}%</strong>。実データを蓄積することで勝率精度が自動向上します。`;
    }
  } catch (err) {
    console.error('Preview error:', err);
  }
}

// 新規予測送信
async function handlePredictionSubmit(e) {
  e.preventDefault();

  const cur = parseFloat(document.getElementById('p-current-price').value);
  const target = parseFloat(document.getElementById('p-target-price').value);
  const stop = parseFloat(document.getElementById('p-stop-loss').value);

  const expGain = round2(((target - cur) / cur) * 100);
  const risk = cur - stop;
  const rr = risk > 0 ? round2((target - cur) / risk) : 99.9;

  const payload = {
    season_id: document.getElementById('p-season').value,
    ticker: document.getElementById('p-ticker').value,
    name: document.getElementById('p-name').value,
    sector: document.getElementById('p-sector').value,
    pick_date: document.getElementById('p-pick-date').value,
    earnings_date: document.getElementById('p-earnings-date').value,
    current_price: cur,
    target_price: target,
    stop_loss: stop,
    expected_return_pct: expGain,
    risk_reward_ratio: rr,
    technical_pattern: document.getElementById('p-pattern').value,
    progress_rate: parseFloat(document.getElementById('p-progress').value || 0),
    consensus_status: document.getElementById('p-consensus').value,
    notes: document.getElementById('p-notes').value,
    status: 'pending'
  };

  try {
    const res = await fetch('/api/predictions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (result.success) {
      alert(`実銘柄 [${payload.ticker}] ${payload.name} を予測リストに登録しました！`);
      document.getElementById('form-prediction').reset();
      document.getElementById('p-pick-date').value = new Date().toISOString().split('T')[0];
      document.querySelector('.tab-btn[data-tab="tab-watchlist"]').click();
      loadData();
    }
  } catch (err) {
    alert('登録エラー: ' + err);
  }
}

// データの読み込み
async function loadData() {
  const season = document.getElementById('season-selector').value;
  const url = season ? `/api/records?season_id=${encodeURIComponent(season)}` : '/api/records';

  try {
    const res = await fetch(url);
    allRecords = await res.json();
    renderTable(allRecords);
    updateKPIs(allRecords);
  } catch (err) {
    console.error('Load data error:', err);
  }
}

// KPIバー更新
function updateKPIs(records) {
  const total = records.length;
  const completed = records.filter(r => r.status === 'completed');
  const wins = completed.filter(r => r.win_loss === 'WIN');

  document.getElementById('kpi-total-preds').textContent = total;
  document.getElementById('kpi-completed-preds').textContent = completed.length;

  if (completed.length > 0) {
    const winRate = round1((wins.length / completed.length) * 100);
    const avgGain = round1(completed.reduce((acc, c) => acc + c.max_gain_pct, 0) / completed.length);

    const winGains = wins.reduce((acc, c) => acc + (c.actual_return_pct > 0 ? c.actual_return_pct : 0), 0);
    const losses = completed.filter(r => r.win_loss === 'LOSS');
    const lossAmounts = Math.abs(losses.reduce((acc, c) => acc + (c.actual_return_pct < 0 ? c.actual_return_pct : 0), 0));
    const pf = lossAmounts > 0 ? round2(winGains / lossAmounts) : (winGains > 0 ? 99.9 : 1.0);

    document.getElementById('kpi-win-rate').textContent = `${winRate}%`;
    document.getElementById('kpi-avg-max-gain').textContent = `+${avgGain}%`;
    document.getElementById('kpi-pf').textContent = pf;
  } else {
    document.getElementById('kpi-win-rate').textContent = '--%';
    document.getElementById('kpi-avg-max-gain').textContent = '--%';
    document.getElementById('kpi-pf').textContent = '--';
  }
}

// 結果記録モーダルを開く
function openResultModal(predId) {
  const record = allRecords.find(r => r.pred_id === predId);
  if (!record) return;

  document.getElementById('r-pred-id').value = predId;
  document.getElementById('r-ticker').value = record.ticker;
  document.getElementById('r-actual-date').value = record.earnings_actual_date || record.earnings_date;
  document.getElementById('r-result-type').value = record.earnings_result_type || '通期上方修正';

  document.getElementById('r-post-open').value = record.post_open_price || '';
  document.getElementById('r-week-high').value = record.week_high_price || '';
  document.getElementById('r-week-low').value = record.week_low_price || '';
  document.getElementById('r-week-close').value = record.week_close_price || '';
  document.getElementById('r-review-notes').value = record.review_notes || '';
  document.getElementById('result-fetch-status').innerHTML = '';

  const summary = `
    <strong>[${record.ticker}] ${record.name}</strong> 
    （決算予定日: <strong>${record.earnings_date}</strong> / パターン: ${record.technical_pattern}）<br>
    事前想定: エントリー <strong>${record.current_price}円</strong> ➔ 目標 <strong>${record.target_price}円</strong> (+${record.expected_return_pct}%) / 損切り <strong>${record.stop_loss}円</strong>
  `;
  document.getElementById('modal-stock-summary').innerHTML = summary;
  document.getElementById('result-modal').classList.add('active');
}

function closeResultModal() {
  document.getElementById('result-modal').classList.remove('active');
}

// 結果記録送信
async function handleResultSubmit(e) {
  e.preventDefault();

  const predId = document.getElementById('r-pred-id').value;
  const payload = {
    prediction_id: parseInt(predId),
    earnings_actual_date: document.getElementById('r-actual-date').value,
    earnings_result_type: document.getElementById('r-result-type').value,
    post_open_price: parseFloat(document.getElementById('r-post-open').value),
    week_high_price: parseFloat(document.getElementById('r-week-high').value),
    week_low_price: parseFloat(document.getElementById('r-week-low').value),
    week_close_price: parseFloat(document.getElementById('r-week-close').value),
    review_notes: document.getElementById('r-review-notes').value
  };

  try {
    const res = await fetch('/api/results', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      alert(`決算後1週間の結果を保存しました！\n判定: ${data.result.win_loss} (実確定損益: ${data.result.actual_return_pct >= 0 ? '+' : ''}${data.result.actual_return_pct}% / 最大上昇: +${data.result.max_gain_pct}%)`);
      closeResultModal();
      loadData();
      loadAnalysis();
    }
  } catch (err) {
    alert('保存エラー: ' + err);
  }
}

// 削除処理
async function handleDelete(predId) {
  if (confirm('この予測および結果データを削除しますか？')) {
    try {
      const res = await fetch(`/api/predictions/${predId}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.success) {
        loadData();
        loadAnalysis();
      }
    } catch (err) {
      alert('削除エラー: ' + err);
    }
  }
}

// シーズン分析の読み込みと描画
async function loadAnalysis() {
  const season = document.getElementById('season-selector').value;
  const url = season ? `/api/analysis?season_id=${encodeURIComponent(season)}` : '/api/analysis';

  try {
    const res = await fetch(url);
    const data = await res.json();
    renderAnalysis(data);
  } catch (err) {
    console.error('Analysis error:', err);
  }
}

function renderAnalysis(data) {
  const patTbody = document.getElementById('patterns-tbody');
  patTbody.innerHTML = '';
  if (data.pattern_ranking && data.pattern_ranking.length > 0) {
    data.pattern_ranking.forEach((p, idx) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>#${idx + 1}</strong></td>
        <td>${p.pattern}</td>
        <td>${p.sample_count}件</td>
        <td><strong class="text-success">${p.win_rate}%</strong> (${p.wins}勝)</td>
        <td><strong class="text-cyan">+${p.avg_max_gain}%</strong></td>
        <td>${p.avg_return >= 0 ? '+' : ''}${p.avg_return}%</td>
      `;
      patTbody.appendChild(tr);
    });
  } else {
    patTbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--text-dim);">実トレード検証データが蓄積されると、パターン別の実績勝率ランキングが自動集計されます。</td></tr>`;
  }

  const progTbody = document.getElementById('progress-tbody');
  progTbody.innerHTML = '';
  if (data.progress_summary && data.progress_summary.length > 0) {
    data.progress_summary.forEach(p => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>${p.bucket}</strong></td>
        <td>${p.count}件</td>
        <td><strong class="text-success">${p.win_rate}%</strong></td>
        <td>${p.avg_return >= 0 ? '+' : ''}${p.avg_return}%</td>
      `;
      progTbody.appendChild(tr);
    });
  }

  const insightsUl = document.getElementById('insights-ul');
  insightsUl.innerHTML = '';
  if (data.actionable_insights && data.actionable_insights.length > 0) {
    data.actionable_insights.forEach(txt => {
      const li = document.createElement('li');
      li.textContent = txt;
      insightsUl.appendChild(li);
    });
  } else {
    insightsUl.innerHTML = `<li>トレード結果を記録していくと、次の決算シーズンで勝率を最大化するアドバイスが自動生成されます。</li>`;
  }

  const reviewsDiv = document.getElementById('reviews-div');
  reviewsDiv.innerHTML = '';
  if (data.loss_reviews && data.loss_reviews.length > 0) {
    data.loss_reviews.forEach(lr => {
      const div = document.createElement('div');
      div.className = 'review-item';
      div.innerHTML = `
        <div class="review-title">[${lr.ticker}] ${lr.name}</div>
        <div class="review-desc">${lr.notes}</div>
      `;
      reviewsDiv.appendChild(div);
    });
  } else {
    reviewsDiv.innerHTML = `<p style="color:var(--text-dim); font-size:12px;">損切り・敗戦記録はありません。</p>`;
  }
}

// Markdownレポート表示
async function showMarkdownReport() {
  const season = document.getElementById('season-selector').value;
  const url = season ? `/api/report/markdown?season_id=${encodeURIComponent(season)}` : '/api/report/markdown';

  try {
    const res = await fetch(url);
    const md = await res.text();
    document.getElementById('markdown-content').value = md;
    document.getElementById('markdown-modal').classList.add('active');
  } catch (err) {
    alert('レポート取得エラー: ' + err);
  }
}

function closeMarkdownModal() {
  document.getElementById('markdown-modal').classList.remove('active');
}

function copyMarkdown() {
  const content = document.getElementById('markdown-content');
  content.select();
  document.execCommand('copy');
  alert('Markdownレポートをクリップボードにコピーしました！');
}

function round1(val) { return Math.round(val * 10) / 10; }
function round2(val) { return Math.round(val * 100) / 100; }

// ================================================================
// ポジションサイザー（資金管理＆ロット算出）制御
// ================================================================
let currentTab2Leverage = 1.0;
let currentModalLeverage = 1.0;
let currentModalOpp = null;

// タブ2のポジションサイズ自動計算
function calculateTab2Position() {
  const capital = parseFloat(document.getElementById('pos-capital')?.value || 1000000);
  const riskPct = parseFloat(document.getElementById('pos-risk-pct')?.value || 2.0);
  const curPrice = parseFloat(document.getElementById('p-current-price')?.value || 0);
  const targetPrice = parseFloat(document.getElementById('p-target-price')?.value || 0);
  const stopLoss = parseFloat(document.getElementById('p-stop-loss')?.value || 0);

  if (!curPrice || curPrice <= 0 || !stopLoss || stopLoss <= 0) {
    return;
  }

  // 1トレード許容最大損失額
  const maxLoss = capital * (riskPct / 100);
  const stopWidth = Math.abs(curPrice - stopLoss) || (curPrice * 0.05);
  let shares = Math.floor((maxLoss / stopWidth) / 100) * 100;
  if (shares === 0) shares = 100;

  const totalCost = shares * curPrice;
  const reqMargin = Math.round(totalCost / currentTab2Leverage);
  const actualLoss = Math.round(shares * stopWidth);
  const targetGain = targetPrice > 0 ? Math.round(shares * (targetPrice - curPrice)) : 0;
  const rr = stopWidth > 0 && targetPrice > curPrice ? round1((targetPrice - curPrice) / stopWidth) : 0;

  const elShares = document.getElementById('pos-res-shares');
  const elMargin = document.getElementById('pos-res-margin');
  const elLoss = document.getElementById('pos-res-loss');
  const elProfit = document.getElementById('pos-res-profit');
  const elRR = document.getElementById('pos-res-rr');

  if (elShares) elShares.textContent = `${shares.toLocaleString()} 株`;
  if (elMargin) elMargin.textContent = `${reqMargin.toLocaleString()} 円 (総額: ${totalCost.toLocaleString()}円)`;
  if (elLoss) elLoss.textContent = `-${actualLoss.toLocaleString()} 円 (${round1(actualLoss / capital * 100)}%)`;
  if (elProfit) elProfit.textContent = `+${targetGain.toLocaleString()} 円 (${round1(targetGain / capital * 100)}%)`;
  if (elRR) elRR.textContent = `1 : ${rr}`;
}

// 独立ポジションサイザーモーダル
function openPositionModalDirect(opp) {
  currentModalOpp = opp;
  const modal = document.getElementById('position-modal');
  if (!modal) return;

  const infoEl = document.getElementById('pos-modal-stock-info');
  if (infoEl) {
    infoEl.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.03); padding:10px 14px; border-radius:6px; margin-bottom:14px; border:1px solid rgba(255,255,255,0.06); flex-wrap:wrap; gap:8px;">
        <div>
          <strong style="font-size:16px; color:var(--text-main);">[${opp.ticker}] ${opp.name}</strong>
          <span class="strat-badge strat-badge-${opp.strategy.toLowerCase()}" style="margin-left:8px;">${opp.strategy_badge}</span>
        </div>
        <div style="font-size:13px;">
          現値: <strong style="color:var(--text-cyan); font-family:var(--font-mono);">${opp.current_price.toLocaleString()}円</strong> | 
          目標: <strong style="color:var(--accent-emerald); font-family:var(--font-mono);">${opp.target_price.toLocaleString()}円 (+${opp.expected_return_pct}%)</strong> | 
          損切り: <strong style="color:var(--accent-rose); font-family:var(--font-mono);">${opp.stop_loss.toLocaleString()}円</strong>
        </div>
      </div>
    `;
  }

  modal.classList.add('active');
  recalculateModalPosition();
}

function closePositionModal() {
  document.getElementById('position-modal')?.classList.remove('active');
}

function recalculateModalPosition() {
  if (!currentModalOpp) return;
  const capital = parseFloat(document.getElementById('pos-m-capital')?.value || 1000000);
  const riskPct = parseFloat(document.getElementById('pos-m-risk')?.value || 2.0);
  const cur = currentModalOpp.current_price;
  const stop = currentModalOpp.stop_loss;
  const target = currentModalOpp.target_price;

  const maxLoss = capital * (riskPct / 100);
  const stopWidth = Math.abs(cur - stop) || (cur * 0.05);
  let shares = Math.floor((maxLoss / stopWidth) / 100) * 100;
  if (shares === 0) shares = 100;

  const totalCost = shares * cur;
  const reqMargin = Math.round(totalCost / currentModalLeverage);
  const actualLoss = Math.round(shares * stopWidth);
  const profit = Math.round(shares * (target - cur));
  const rr = stopWidth > 0 ? round1((target - cur) / stopWidth) : 0;
  const capRatio = round1((reqMargin / capital) * 100);

  const elShares = document.getElementById('pos-m-shares');
  const elMargin = document.getElementById('pos-m-margin');
  const elLoss = document.getElementById('pos-m-loss');
  const elProfit = document.getElementById('pos-m-profit');
  const elRR = document.getElementById('pos-m-rr');
  const elCapRatio = document.getElementById('pos-m-cap-ratio');

  if (elShares) elShares.textContent = `${shares.toLocaleString()} 株`;
  if (elMargin) elMargin.textContent = `${reqMargin.toLocaleString()} 円 (総額: ${totalCost.toLocaleString()}円)`;
  if (elLoss) elLoss.textContent = `-${actualLoss.toLocaleString()} 円 (資金の -${round1(actualLoss / capital * 100)}%)`;
  if (elProfit) elProfit.textContent = `+${profit.toLocaleString()} 円 (資金の +${round1(profit / capital * 100)}%)`;
  if (elRR) elRR.textContent = `1 : ${rr}`;
  if (elCapRatio) elCapRatio.textContent = `${capRatio} %`;
}

// イベントリスナーの初期化
document.addEventListener('DOMContentLoaded', () => {
  // タブ2のポジションサイザー入力変更監視
  ['pos-capital', 'pos-risk-pct', 'p-current-price', 'p-target-price', 'p-stop-loss'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', calculateTab2Position);
  });

  // タブ2 レバレッジ切替
  document.querySelectorAll('.btn-lev').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.btn-lev').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      currentTab2Leverage = parseFloat(e.target.dataset.lev || 1.0);
      calculateTab2Position();
    });
  });

  // モーダル側 レバレッジ切替
  document.querySelectorAll('.btn-lev-m').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.btn-lev-m').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      currentModalLeverage = parseFloat(e.target.dataset.lev || 1.0);
      recalculateModalPosition();
    });
  });

  // モーダル側 資金・リスク入力変更監視
  ['pos-m-capital', 'pos-m-risk'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', recalculateModalPosition);
  });
});

