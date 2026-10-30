"""Reviewed public teaching references; prices and payouts below are game assumptions.

No insurance quote or complete contract reproduction is provided. The original
life engine deliberately keeps its five-stock rules and existing save format.
"""

import copy

VERSION = 'training-20261027-1'
SOURCE_DATE = '2026-10-27'
SOURCES = {
    'vul': {
        'id': 'vul',
        'title': '享富足變額萬能壽險商品說明書（115 年 7 月版）',
        'url': 'https://life.cardif.com.tw/documents/418719/461863/Vie_SPM_UL0092.pdf',
        'locator': '商品說明書第 1–3 頁、費用及風險揭露章節',
    },
    'annuity': {
        'id': 'annuity',
        'title': '享富足變額年金保險商品說明書（115 年 7 月版）',
        'url': 'https://life.cardif.com.tw/documents/418719/461863/Vie_SPM_UA0092.pdf',
        'locator': '商品說明書第 1–3 頁、年金及費用章節',
    },
    'credit': {
        'id': 'credit',
        'title': '活力成家定期壽險保單條款（114 年 1 月版）',
        'url': 'https://life.cardif.com.tw/documents/418719/462049/VIE_XCSAG.pdf/d6e527ff-6580-0cc1-5e38-b15f531e79b9?t=1735629278306',
        'locator': '第 1–2 頁；第 5、13、14、17 條',
    },
    'general': {
        'id': 'general',
        'title': '一般保險規則練習，非巴黎人壽商品',
        'url': '',
        'locator': '虛構教學範本，實際範圍須依正式條款核對',
    },
}
PRODUCTS = [
    {
        'id': 'CARDIF_VUL',
        'name': '法商法國巴黎人壽享富足變額萬能壽險',
        'kind': 'INVESTMENT_LIFE',
        'provider': '法國巴黎人壽',
        'source_id': 'vul',
        'facts': ['結合壽險保障與投資帳戶。', '投資價值會波動，須了解費用與風險。', '提領或解約會影響保單帳戶及保障。'],
    },
    {
        'id': 'CARDIF_ANNUITY',
        'name': '法商法國巴黎人壽享富足變額年金保險',
        'kind': 'ANNUITY',
        'provider': '法國巴黎人壽',
        'source_id': 'annuity',
        'facts': [
            '給付項目包含返還保單帳戶價值、年金及未支領年金餘額。',
            '投資與年金給付須區分不同階段。',
            '投資部分不能當作保證收益。',
        ],
    },
    {
        'id': 'CARDIF_CREDIT',
        'name': '法商法國巴黎人壽活力成家定期壽險',
        'kind': 'TERM_LIFE',
        'provider': '法國巴黎人壽',
        'source_id': 'credit',
        'facts': [
            '有效期間的身故或完全失能依條款給付。',
            '投保類型含平準型與遞減型。',
            '一般支出或股票虧損不因此自動獲賠。',
        ],
    },
    {
        'id': 'SIM_MEDICAL',
        'name': '一般醫療保障練習（虛構）',
        'kind': 'MEDICAL',
        'provider': '一般概念／非法巴商品',
        'source_id': 'general',
        'facts': ['核實費用、有給付上限與等待期。', '不替代任何正式醫療險條款。'],
    },
    {
        'id': 'SIM_LIABILITY',
        'name': '第三人責任險練習（虛構）',
        'kind': 'LIABILITY',
        'provider': '一般概念／非法巴商品',
        'source_id': 'general',
        'facts': ['練習依法應負的第三人賠償責任。', '自己的受傷與車損不能直接當成第三人損失。'],
    },
]
KINDS = {'INVESTMENT_LIFE', 'ANNUITY', 'TERM_LIFE', 'MEDICAL', 'LIABILITY'}
ASSUMPTIONS = {
    'premium_minor': 1200000,
    'face_minor': 100000000,
    'entry_fee_bps': 300,
    'monthly_fee_minor': 10000,
    'withdrawal_fee_bps': 100,
    'equity_bps': 6000,
    'claim_delay_months': 1,
    'waiting_months': 2,
}


def products():
    out = copy.deepcopy(PRODUCTS)
    for p in out:
        p.update(
            source=copy.deepcopy(SOURCES[p['source_id']]),
            retrieved_at=SOURCE_DATE,
            simulation=copy.deepcopy(ASSUMPTIONS),
            simulation_notice='下方金額、費用、等待期與配置為統一遊戲假設，不是該真實商品的費率、核保或理賠承諾。',
        )
    return out


NAMES = [
    ('STABLE', '穩健製造', '製造'),
    ('TECH', '成長科技', '科技'),
    ('HEALTH', '健康照護', '醫療'),
    ('CONSUMER', '民生消費', '民生'),
    ('GREEN', '綠能轉型', '能源'),
    ('CLOUD', '雲端服務', '科技'),
    ('FOOD', '食品供應', '民生'),
    ('WATER', '水資源', '公用'),
    ('LOGISTICS', '城市物流', '運輸'),
    ('CHIP', '半導體設備', '科技'),
    ('CARE', '銀髮服務', '醫療'),
    ('RETAIL', '社區零售', '民生'),
    ('GRID', '電網工程', '公用'),
    ('TRAVEL', '旅遊服務', '觀光'),
    ('SOFTWARE', '企業軟體', '科技'),
    ('MATERIAL', '循環材料', '工業'),
    ('TELECOM', '通訊網路', '通訊'),
    ('AGRI', '智慧農業', '農業'),
    ('HOUSING', '住宅維護', '工業'),
    ('TOOLS', '精密工具', '製造'),
]
STOCKS = [
    {
        'id': id,
        'name': name + '（虛構）',
        'sector': sector,
        'beta_bps': 650 + (i % 5) * 180,
        'vol_bps': 600 + (i % 4) * 180,
        'drift_bps': -350 + i * 20 if i < 5 else -40 + (i % 5) * 35,
        'dividend_bps': 0 if i < 5 else 30 + (i % 3) * 20,
        'group': '低成長／產業逆風' if i < 5 else '一般波動',
        'description': '教學排序前五檔為固定逆風組；不依持股或點擊臨時改價。'
        if i < 5
        else '可能與大盤同跌，不保證長期獲利。',
    }
    for i, (id, name, sector) in enumerate(NAMES)
]


def event(id, topic, title, prompt, lesson, choices, correct, explanation, source='vul', loss=0, loss_kind='NONE'):
    return {
        'id': id,
        'topic': topic,
        'title': title,
        'prompt': prompt,
        'lesson': lesson,
        'choices': [{'id': str(i + 1), 'label': x} for i, x in enumerate(choices)],
        'correct_id': str(correct),
        'explanation': explanation,
        'source_ids': [source],
        'loss_minor': loss,
        'loss_kind': loss_kind,
    }


EVENTS = [
    event(
        'needs',
        'NEEDS',
        '銀行理專的一個提問',
        '客戶下半年要付頭期款，卻想把預備金全放進投資型保單。你會如何回應？',
        '先確認用途、資金期限與風險承受度，再討論商品。',
        ['先保留短期支出與預備金，再討論長期安排', '只要有保險，就把短期用錢全部投入', '先看商品排名，不必問資金用途'],
        1,
        '短期必要支出需要流動資金。商品適合度不能只看預期收益。',
    ),
    event(
        'fees',
        'FEES',
        '投入的錢去哪裡了？',
        '客戶發現投資帳戶沒有等於所繳保費。理專應先說明什麼？',
        '保費、保障成本、其他費用及實際配置金額是不同概念。',
        ['保證之後會補足差額', '核對費用結構與配置紀錄，再說明扣除項目', '把差額直接說成股票下跌'],
        2,
        '先核對費用與配置，不把所有差額都歸因市場。此關的扣費數值是遊戲假設。',
    ),
    event(
        'market',
        'MARKET',
        '市場跌了，保障還在嗎？',
        '股市回落，客戶認為「既然是保險，投資本金就不會虧」。你會如何說明？',
        '保障給付與投資帳戶績效要分開解釋。',
        ['保險公司會補回所有投資虧損', '只要再多繳保費就保證回本', '說明投資風險、帳戶價值及契約保障各自的範圍'],
        3,
        '投資型保險不等於保本存款；連結市場下跌時，投資帳戶也會承受風險。',
    ),
    event(
        'liquidity',
        'LIQUIDITY',
        '家裡臨時需要一筆錢',
        '家中必要維修要支付 6 萬元，客戶打算立即解約。你要先協助檢查什麼？',
        '比較可用資金、部分提領、費用與保障影響。',
        ['先比較現金、提領與解約影響，再決定', '直接解約，不必確認條款', '再買一張保單來支付支出'],
        1,
        '解約與提領都可能有成本與保障影響，不能只看帳戶顯示金額。',
        loss=6000000,
        loss_kind='LIVING',
    ),
    event(
        'credit',
        'PROTECTION',
        '房貸與家庭責任',
        '客戶問：信用保障型壽險能不能補償所有家庭開支或股票虧損？',
        '給付須符合契約約定事故；保障金額也可能隨投保類型變化。',
        ['有買保險就能支付任何支出', '核對身故／完全失能等給付條件與保障金額', '只要繳過一次保費就永久有效'],
        2,
        '活力成家條款列有身故及完全失能給付；仍須核對有效期間、投保類型及除外責任。',
        'credit',
    ),
    event(
        'annuity',
        'ANNUITY',
        '退休帳戶與年金給付',
        '客戶把帳戶目前價值直接當成未來每年的保證年金。你會如何處理？',
        '累積期帳戶價值與年金開始後的給付條件須分開理解。',
        [
            '告知帳戶現在有多少，以後每年就固定領多少',
            '只展示高報酬圖表',
            '依契約核對年金開始日及給付方式，並說明投資風險',
        ],
        3,
        '年金保險有不同階段與給付條件，不能用目前帳戶價值直接承諾未來收益。',
        'annuity',
    ),
    event(
        'accident',
        'LIABILITY',
        '路口的碰撞',
        '事故造成自己的修車費與對方財物損失，如何分辨保障？',
        '第三人責任與自己的車損／醫療是不同損害。',
        ['把所有損失都用自己的醫療險申請', '先分辨損害對象、責任與適用條款', '只要是車禍就一定全額理賠'],
        2,
        '須確認對誰負責、哪種損失及保單範圍。本案例是一般責任險範本，非法巴商品。',
        'general',
        loss=18000000,
        loss_kind='LIABILITY',
    ),
    event(
        'medical',
        'MEDICAL',
        '等待期內的醫療支出',
        '剛投保後發生醫療事件，可以直接承諾給付嗎？',
        '先核對事故、有效日、等待期、證據與除外責任。',
        ['先核對條款與單據，不能直接承諾', '保費剛繳完就必定賠付', '把所有疾病都當成意外'],
        1,
        '是否給付須按條款及事件條件檢查；本關醫療金額與等待期為虛構練習。',
        'general',
        loss=8000000,
        loss_kind='MEDICAL',
    ),
]


def base_course():
    return {
        'title': '法巴通路情境：保障、投資與現金流',
        'audience': '銀行理專／保經代',
        'instructions': '在生活事件與客戶提問中練習需求訪談、費用說明、保障範圍及風險揭露。',
        'product_ids': ['CARDIF_VUL', 'CARDIF_ANNUITY', 'CARDIF_CREDIT'],
        'material_ids': [],
        'rules': {
            'horizon_months': 36,
            'salary_minor': 5000000,
            'living_bps': 7000,
            'reserve_months': 2,
            'market': 'NORMAL',
            'drop_bps': 2500,
            'stress_start': 6,
            'stress_end': 12,
            'emphasis_topic': 'NONE',
            'emphasis_multiplier': 1,
            'guaranteed_topic': False,
        },
        'events': copy.deepcopy(EVENTS[:6]),
        'reviewed': False,
        'mode': 'MANUAL_TEMPLATE',
        'unresolved': [],
    }
