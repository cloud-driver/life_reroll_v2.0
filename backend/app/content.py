"""Versioned and explicitly fictional education content."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERSONAS = json.loads((ROOT / 'data/personas.json').read_text(encoding='utf-8'))
EVENTS = json.loads((ROOT / 'data/events.json').read_text(encoding='utf-8'))
EVENT_BY_ID = {x['id']: x for x in EVENTS}
CONTENT_VERSION = '2026.09.simulated.1'
MARKET_VERSION = 'market-20261023-2'
STOCK_TRADE_FEE_BPS = 30
HOSPITAL_EVENTS = {x['id']: x for x in json.loads((ROOT / 'data/hospital_events.json').read_text(encoding='utf-8'))}

STOCKS = [
    {
        'id': 'STABLE',
        'name': '穩健製造（虛構）',
        'sector': '製造',
        'beta_bps': 650,
        'drift_bps': 80,
        'vol_bps': 430,
        'dividend_bps': 100,
    },
    {
        'id': 'TECH',
        'name': '成長科技（虛構）',
        'sector': '科技',
        'beta_bps': 1450,
        'drift_bps': 130,
        'vol_bps': 1200,
        'dividend_bps': 0,
    },
    {
        'id': 'HEALTH',
        'name': '健康照護（虛構）',
        'sector': '醫療',
        'beta_bps': 920,
        'drift_bps': 100,
        'vol_bps': 620,
        'dividend_bps': 50,
    },
    {
        'id': 'CONSUMER',
        'name': '民生消費（虛構）',
        'sector': '民生',
        'beta_bps': 760,
        'drift_bps': 70,
        'vol_bps': 560,
        'dividend_bps': 80,
    },
    {
        'id': 'GREEN',
        'name': '綠能轉型（虛構）',
        'sector': '能源',
        'beta_bps': 1250,
        'drift_bps': 110,
        'vol_bps': 950,
        'dividend_bps': 30,
    },
]
STOCK_BY_ID = {s['id']: s for s in STOCKS}

PRODUCTS = [
    {
        'id': 'MEDICAL',
        'name': '住院及手術費用保障（模擬）',
        'category': 'MEDICAL',
        'benefit_type': 'REIMBURSEMENT',
        'premium_rate_bps': 95,
        'waiting_months': 2,
        'claim_delay_months': 1,
        'coverage_options_minor': [30000000, 60000000, 100000000],
        'benefit_limit_minor': 100000000,
        'exclusions': ['等待期間新發生的疾病', '投保前已存在並於事件中明示的確診疾病'],
        'summary': '符合事故與單據條件時，核實支出後給付；不能超過實際醫療費。',
    },
    {
        'id': 'ACCIDENT',
        'name': '意外傷害保障（模擬）',
        'category': 'ACCIDENT',
        'benefit_type': 'REIMBURSEMENT',
        'premium_rate_bps': 65,
        'waiting_months': 0,
        'claim_delay_months': 0,
        'coverage_options_minor': [20000000, 50000000, 80000000],
        'benefit_limit_minor': 80000000,
        'exclusions': ['非意外造成的疾病', '未提供事故與費用證據'],
        'summary': '意外事件發生後按有紀錄的損失核付；不涵蓋車體與第三人責任。',
    },
    {
        'id': 'CRITICAL_ILLNESS',
        'name': '重大疾病一次給付（模擬）',
        'category': 'CRITICAL_ILLNESS',
        'benefit_type': 'FIXED',
        'premium_rate_bps': 135,
        'waiting_months': 6,
        'claim_delay_months': 1,
        'coverage_options_minor': [50000000, 100000000, 150000000],
        'benefit_limit_minor': 150000000,
        'exclusions': ['非條款列出的重大疾病', '等待期間發病的事件'],
        'summary': '符合疾病分類時一次定額給付，可用於醫療以外的收入缺口。',
    },
    {
        'id': 'LONG_TERM_CARE',
        'name': '長期照顧給付（模擬）',
        'category': 'LONG_TERM_CARE',
        'benefit_type': 'FIXED',
        'premium_rate_bps': 115,
        'waiting_months': 6,
        'claim_delay_months': 2,
        'coverage_options_minor': [30000000, 60000000, 100000000],
        'benefit_limit_minor': 100000000,
        'exclusions': ['未達照護事件條件', '等待期間發病'],
        'summary': '符合照護事件條件給付；不把一般休閒活動當事故。',
    },
    {
        'id': 'LIFE',
        'name': '定期壽險（模擬）',
        'category': 'LIFE',
        'benefit_type': 'DEATH',
        'premium_rate_bps': 75,
        'waiting_months': 3,
        'claim_delay_months': 0,
        'coverage_options_minor': [100000000, 200000000, 300000000],
        'benefit_limit_minor': 300000000,
        'exclusions': ['生存期間不可申請身故給付'],
        'summary': '僅於人生結束後計入受益家庭成績，不提供玩家生存期間的籌資。',
    },
]
PRODUCT_BY_ID = {p['id']: p for p in PRODUCTS}

LESSONS = [
    {
        'id': 'reserve',
        'title': '緊急預備金',
        'short_text': '先保留幾個月的必要開支，遭遇意外才有時間選擇。',
        'detail_text': '預備金是可立即動用的活存或現金；股票與未入帳的理賠不可當作立即支付能力。',
    },
    {
        'id': 'claim',
        'title': '理賠時點',
        'short_text': '核准不等於已到帳，留意等待期和給付日。',
        'detail_text': '檢視保障類別、事故日期、有效狀態、除外責任、證據、核准與真正入帳時點。正式理賠須看實際條款及官方程序。',
        'source_urls': ['https://life.cardif.com.tw/a314'],
    },
    {
        'id': 'portfolio',
        'title': '分散風險',
        'short_text': '五檔股票有共同大盤風險，也各有自身波動。',
        'detail_text': '波動與獲利都不保證；交易費與現金不足可能影響選擇。',
    },
    {
        'id': 'budget',
        'title': '花錢也能換生活品質',
        'short_text': '旅行或與家人相聚，是預算規劃後可做的選擇。',
        'detail_text': '遊戲評價同時看風險、保障、債務和長期生活品質，不以買最多保險為最高分。',
        'source_urls': ['https://life.cardif.com.tw/a233'],
    },
]
SCENES = [
    {'id': 'HOME', 'name': '家', 'connections': ['STREET'], 'interactions': ['BED', 'SAVE', 'LIFESTYLE']},
    {'id': 'STREET', 'name': '街道', 'connections': ['HOME', 'FINANCE', 'HOSPITAL', 'WORK'], 'interactions': []},
    {'id': 'WORK', 'name': '工作區', 'connections': ['STREET'], 'interactions': ['COMPLETE_WORK']},
    {
        'id': 'FINANCE',
        'name': '金融大樓',
        'connections': ['STREET'],
        'interactions': ['SAVINGS', 'STOCKS', 'INSURANCE', 'LOANS'],
    },
    {'id': 'HOSPITAL', 'name': '醫院', 'connections': ['STREET'], 'interactions': ['COVERAGE', 'CLAIMS']},
]


def product_view(p):
    return {
        **p,
        'source_mode': 'SIMULATED',
        'source_url': None,
        'version': CONTENT_VERSION,
        'is_simulated': True,
        'enabled': True,
        'waiting_days': p['waiting_months'] * 30,
        'premium_period_options_months': [12],
        'plain_summary': p['summary'],
        'eligibility_summary': '無真實核保；以已知遊戲條件模擬。',
        'simulation_differences': ['虛構保費與核付條件', '沒有真實保險契約或投保流程'],
        'benefits': [
            {
                'code': p['id'],
                'payout_type': p['benefit_type'],
                'waiting_days': p['waiting_months'] * 30,
                'limit_minor': p['benefit_limit_minor'],
                'exclusions': p['exclusions'],
            }
        ],
    }
