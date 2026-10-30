"""Read the supplied workbook with the Python standard library; emit audited game content."""
from __future__ import annotations
import json
import re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source' / 'personas_events_original.xlsx'
NS = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def sheets():
    with ZipFile(SOURCE) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('x:si', NS):
                shared.append(''.join(t.text or '' for t in si.findall('.//x:t', NS)))
        for number in range(1, 4):
            root = ET.fromstring(z.read(f'xl/worksheets/sheet{number}.xml'))
            rows = []
            for row in root.findall('.//x:sheetData/x:row', NS):
                d = {}
                for c in row.findall('x:c', NS):
                    col = re.match(r'[A-Z]+', c.attrib['r']).group()
                    v, inline = c.find('x:v', NS), c.find('x:is', NS)
                    value = v.text if v is not None else ''.join(x.text or '' for x in inline.findall('.//x:t', NS)) if inline is not None else ''
                    if c.get('t') == 's' and value:
                        value = shared[int(value)]
                    d[col] = value
                rows.append(d)
            headers = rows.pop(0)
            yield [{headers.get(col, col): v for col, v in row.items() if col in headers} for row in rows]


def condition(source):
    source = source or '無限制'
    if source == '無限制':
        return {}
    source = source.replace(' ', '')
    field_map = {'industry': 'industry', 'occupation': 'occupation', 'annualIncome': 'annual_income',
                 'commuteMode': 'commute_mode', 'familyMedicalHistory': 'family_history', 'age': 'age'}
    m = re.fullmatch(r'(industry|occupation|annualIncome|commuteMode|familyMedicalHistory|age)(==|!=|>=|<=)(.+)', source)
    if m:
        field, op, val = m.groups()
        if val.startswith('['):
            return {'field': field_map[field], 'op': 'in', 'value': re.findall(r"'([^']+)'", val)}
        val = val.strip("'\"")
        if val.isdecimal(): val = int(val)
        if field == 'occupation' and val.endswith('業'):
            field = 'industry'  # Repair the provided FA17 occupation=='科技業' mismatch.
        return {'field': field_map[field], 'op': op, 'value': val}
    m = re.fullmatch(r'(industry|occupation|commuteMode)in\[(.+)\]', source)
    if m:
        return {'field': field_map[m.group(1)], 'op': 'in', 'value': re.findall(r"'([^']+)'", m.group(2))}
    return {'unsupported_source_rule': source}  # Fail closed, never eval workbook formulas.


def make_card(row):
    key = row['cardID']
    impact = row.get('impact') or ''
    amount_m = re.search(r'(存款|醫療支出)\s*([+-])\s*(\d+(?:\.\d+)?)(萬|元)', impact)
    amount = int(float(amount_m.group(3)) * (10_000 if amount_m.group(4) == '萬' else 1)) if amount_m else 0
    sign = amount_m.group(2) if amount_m else '-'
    if amount_m and amount_m.group(1) == '醫療支出':
        sign = '-'  # "醫療支出 +2萬" means 2萬 more spending, i.e. a cash loss.
    critical = key in {'FA01', 'FA02', 'FA05', 'FA07', 'FA17', 'FA25', 'FA26'}
    amount = min(amount or (60_000 if key.startswith('FA') else 15_000), 800_000 if critical else 180_000)
    if key in {'CH03', 'CH04', 'CH06', 'CH18', 'FA21', 'FA22', 'FA23'}:
        amount = 0  # Unsupported crypto, funds, property and ETF holdings are never fabricated.
    if key in {'FA14', 'FA16'}:
        return None  # Gratuitous child death and predatory coercion are unsuitable for public teaching.
    kind = 'HEALTH' if key.startswith('FA') and (critical or key in {'FA03', 'FA19', 'FA20'}) else ('ACCIDENT' if key.startswith('FA') and 6 <= int(key[2:]) <= 11 else 'LIFE' if key.startswith('FA') else 'CAREER' if key in {'CH07', 'CH08', 'CH09', 'CH10', 'CH11', 'CH12', 'CH15'} else 'MARKET' if key in {'CH01', 'CH03', 'CH04', 'CH06', 'CH13', 'CH14', 'CH18'} else 'LIFE')
    if key in {'CH29'}:kind = 'TRAVEL'
    if key in {'CH03','CH04','CH06','CH18','FA21','FA22','FA23'}:
        risk = 0
    else:
        risk = -amount if sign == '-' else amount
    if key in {'CH07', 'CH09', 'CH12'}:risk = 0
    if key == 'FA15':risk = -min(amount, 120_000)  # Wedding budget is a voluntary choice.
    if key == 'FA27':risk = 0  # Retirement living choice, with no forced loss.
    default_effect = {'cash_delta_minor': risk * 100, 'quality_delta': 0,
                      'salary_change_bps': 0, 'monthly_cost_delta_minor': 0, 'market_shock_bps': 0}
    if key in {'CH01', 'CH13', 'CH14'}:
        default_effect['cash_delta_minor'] = 0
        default_effect['market_shock_bps'] = {'CH01': -700, 'CH13': 500, 'CH14': -500}[key]
    if key in {'CH07','CH09','CH12'}:
        default_effect['salary_change_bps'] = {'CH07':1200,'CH09':1600,'CH12':1200}[key]
    if key == 'CH08':default_effect['salary_change_bps'] = -4000
    if key in {'FA01','FA02','FA05','FA07','FA17','FA25','FA26'}:
        default_effect['cash_delta_minor'] = -amount * 100
    if key == 'CH29':default_effect = {'cash_delta_minor':-20_000*100,'quality_delta':8,'salary_change_bps':0,'monthly_cost_delta_minor':0,'market_shock_bps':0}
    if key.startswith('FA') and kind == 'LIFE':
        default_effect['quality_delta'] = 3 if key in {'FA12','FA15','FA27'} else -1
    insurance = 'MEDICAL' if kind == 'HEALTH' else 'ACCIDENT' if kind == 'ACCIDENT' else 'LONG_TERM_CARE' if key in {'FA04','FA07','FA26'} else None
    if key in {'FA09','FA10','FA21','FA22','FA23'}:insurance = None  # No motor/property coverage in this release.
    if key in {'FA12','FA13','FA15','FA27','CH29'}: insurance = None  # Predictable life choices are not insured losses.
    desc = row.get('description') or row['eventName']
    if key == 'FA15':desc = '考慮和伴侶舉辦婚禮；可以依可支配資金選擇形式，關係本身不由花費決定。'
    if key == 'FA27':desc = '想規劃退休居所；先估算預算與照護需求，再決定生活方式。'
    if key in {'CH03','CH04','CH06','CH18','FA21','FA22','FA23'}:
        desc += '（本遊戲未提供該項持有資產；只呈現市場或生活決策，不直接扣除不存在的資產。）'
    if key == 'FA12':desc = '家中新添成員，面臨購物與照顧安排；可以選擇規模，不假定玩家的性別與生育情況。'
    return {'id':key,'source':'uploaded_workbook','kind':kind,'title':row['eventName'],'description':desc,
            'condition':condition(row.get('condition')),'source_impact':impact,'source_mitigation':row.get('insuranceMitigation') or '',
            'major': key.startswith('FA') or key in {'CH01','CH07','CH08','CH09','CH13','CH14'},
            'critical':critical,'effect':default_effect,'insurance_category':insurance,
            'choices':[{'id':'BALANCED','label':'謹慎處理','effect_multiplier_bps':10000},
                       {'id':'PREPARED','label':'優先維持預備金與生活品質','effect_multiplier_bps':7000 if risk < 0 else 9000},
                       {'id':'EXPANDED','label':'擴大支出或積極應對','effect_multiplier_bps':14000 if risk < 0 else 11000}]}


EXTRAS = [
    ('TR01','周末小旅行','安排兩天一夜的近郊旅行，重新調整工作與生活的節奏。',9000,5),
    ('TR02','家族同遊','和家人一起旅行，預算內留下回憶，也需考量原本的生活支出。',36000,8),
    ('TR03','出國深度旅行','多年夢想的旅程成行，選擇符合緊急預備金的花費。',75000,11),
    ('TR04','退休慢旅','退休後安排分段旅行，保留醫療與照護資金。',45000,7),
    ('LF01','朋友聚餐','和朋友一起吃飯交流，控制預算也享受生活。',2400,2),
    ('LF02','進修與閱讀','參加實作課程或買書，短期支出換取技能與滿足感。',12000,4),
    ('LF03','家庭慶生','為家人籌辦小型慶祝，衡量當月的自由支配額度。',6500,4),
    ('LF04','健身與興趣','購買運動課程或興趣材料，支持長期生活品質。',9500,5),
    ('LF05','陪伴長輩','安排陪同出遊和無障礙交通，有支出也有陪伴的價值。',12500,5),
    ('LF06','居家改造','在現有住處改善照明、收納和安全，避免勉強一次花光預備金。',23000,5),
    ('LF07','公益捐助','支持在意的公益計畫，先評估自己本月的收支。',5000,4),
    ('LF08','節慶返鄉','春節返鄉與親友相聚，交通與住宿也要編列預算。',8000,4),
    ('CR01','技能獲認可','在工作中完成重要的培訓，未來有機會加薪。',6500,3),
    ('CR02','短期休息','安排一段合理的休息時間，有減少收入的可能，也讓生活品質回升。',13000,9),
    ('CR03','轉換職涯跑道','取得另一家公司面試機會，可保留收入與技能再換工作。',18000,5),
    ('CR04','轉職空窗期','工作結束後有一段尋職空窗，預備金能降低壓力。',22000,3),
    ('LF09','搬到更適合的住處','通勤和生活品質改進，搬遷需支付一次性費用。',38000,6),
    ('LF10','修繕舊物','維修常用家具和設備，是可規劃的必要支出。',7000,2),
]


def main():
    identities, chances, fates = list(sheets())
    personas = []
    for row in identities:
        personas.append({'id':str(row['id']),'occupation':row['occupation'],'industry':row['industry'],
                         'annual_income_minor':int(row['annualIncome'])*100,'commute_mode':row['commuteMode'],
                         'family_history':row['familyMedicalHistory']})  # User asked us to ignore age and gender.
    events = [c for c in (make_card(r) for r in chances+fates) if c]
    for id_,title,description,cost,quality in EXTRAS:
        events.append({'id':id_,'source':'new_quality_of_life','kind':'TRAVEL' if id_.startswith('TR') else 'CAREER' if id_.startswith('CR') else 'LIFE',
                       'title':title,'description':description,'condition':{'field':'age','op':'>=','value':60} if id_ == 'TR04' else {},
                       'source_impact':'玩家選擇後才支出','source_mitigation':'這是有意義的生活支出，不應推薦理賠。',
                       'major':id_ in {'TR03','TR04','LF09'},'critical':False,'insurance_category':None,
                       'effect':{'cash_delta_minor':-cost*100,'quality_delta':quality,'salary_change_bps':0,
                                 'monthly_cost_delta_minor':0,'market_shock_bps':0},
                       'choices':[{'id':'SKIP','label':'暫緩安排','effect_multiplier_bps':0},
                                  {'id':'BALANCED','label':'量力而為','effect_multiplier_bps':6000},
                                  {'id':'FULL','label':'完整體驗','effect_multiplier_bps':10000}]})
    assert len(personas)==20 and len(events)>=75 and len({e['id'] for e in events})==len(events)
    (ROOT/'data/personas.json').write_text(json.dumps(personas,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'data/events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2)+'\n')
    print(f'{len(personas)} personas; {len(events)} event cards; ignored age and gender')


if __name__=='__main__': main()
