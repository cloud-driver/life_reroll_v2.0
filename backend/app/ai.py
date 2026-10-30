"""Optional OpenAI-compatible story authoring. Structured engine rules are never delegated."""

import json
import os
import urllib.request
from .content import EVENTS
from .zh import traditional


def propose_plan(persona, base_plan, start_age, min_index=0, anchor=None):
    """Optional LLM schedules curated cards; forced career milestones and anchor stay fixed."""
    base = os.environ.get('LIFE_AI_BASE_URL', '').rstrip('/')
    token = os.environ.get('LIFE_AI_API_KEY', '')
    model = os.environ.get('LIFE_AI_MODEL', '')
    if not base or not token or not model:
        return base_plan
    required_ids = {'CH07', 'CR03', 'CH08', 'CR04'}
    fixed = [x.copy() for x in base_plan if x['card_id'] in required_ids or x.get('anchor')]
    candidate = {e['id']: e for e in EVENTS}
    try:
        payload = {
            'model': model,
            'temperature': 0.5,
            'max_tokens': 900,
            'messages': [
                {
                    'role': 'system',
                    'content': '繁體中文人生教育遊戲編劇，只輸出 JSON array，每項 {"at_index":整數,"card_id":字串}。at_index 是初始年齡之後的月份。可從提供的既定候選重新安排，但不可新增事件、改寫金額、修改商品或移動固定職涯／錨點。不要安排超過 18 件；選擇合理且不全是負面事件。',
                },
                {
                    'role': 'user',
                    'content': json.dumps(
                        {
                            'persona': {
                                'occupation': persona['occupation'],
                                'industry': persona['industry'],
                                'commute_mode': persona['commute_mode'],
                                'starting_age': start_age,
                            },
                            'candidates': [{'id': x['id'], 'kind': x['kind'], 'title': x['title']} for x in EVENTS],
                            'baseline': base_plan,
                            'min_index': min_index,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        req = urllib.request.Request(
            base + '/chat/completions',
            data=json.dumps(payload).encode(),
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=float(os.environ.get('LIFE_AI_TIMEOUT', '8'))) as resp:
            response = json.loads(resp.read(128000))
        raw = response['choices'][0]['message']['content']
        entries = json.loads(raw[raw.find('[') : raw.rfind(']') + 1])
        if not isinstance(entries, list) or len(entries) > 18:
            raise ValueError
        plan = fixed[:]
        ids = {x['card_id'] for x in fixed}
        indices = {x['at_index'] for x in fixed}
        for item in entries:
            if not isinstance(item, dict):
                raise ValueError
            card_id = item.get('card_id')
            index = item.get('at_index')
            if card_id not in candidate or not isinstance(index, int) or isinstance(index, bool):
                raise ValueError
            age = start_age + index // 12
            event = candidate[card_id]
            rule = event.get('condition', {})
            if not (min_index < index <= (95 - start_age) * 12) or card_id in ids or index in indices:
                continue
            if (
                event['kind'] == 'CAREER'
                and age > 60
                or card_id in ('FA12', 'FA13')
                and age > 55
                or card_id == 'FA27'
                and age < 60
            ):
                continue
            if rule and (rule.get('unsupported_source_rule') or not _condition_match(rule, persona, age)):
                continue
            plan.append({'at_index': index, 'card_id': card_id, 'anchor': False})
            ids.add(card_id)
            indices.add(index)
        if len(plan) < 7:
            raise ValueError
        return sorted(plan, key=lambda x: x['at_index'])
    except (OSError, KeyError, ValueError, IndexError, TypeError):
        return base_plan


def _condition_match(rule, p, age):
    value = age if rule['field'] == 'age' else p.get(rule['field'])
    target = rule['value']
    return {
        '==': lambda: value == target,
        '!=': lambda: value != target,
        '>=': lambda: value >= target,
        '<=': lambda: value <= target,
        'in': lambda: value in target,
    }[rule['op']]()


def refine_story(persona, events):
    """Local fallback makes the game playable with no API key or internet."""
    result = {e['card_id']: None for e in events}
    base = os.environ.get('LIFE_AI_BASE_URL', '').rstrip('/')
    token = os.environ.get('LIFE_AI_API_KEY', '')
    model = os.environ.get('LIFE_AI_MODEL', '')
    if not base or not token or not model:
        return result
    try:
        payload = {
            'model': model,
            'temperature': 0.6,
            'max_tokens': 650,
            'messages': [
                {
                    'role': 'system',
                    'content': '以繁體中文為面向大眾的保險教育遊戲寫簡短敘事。只回傳 JSON 物件，key 為事件 ID，value 為不超過 100 字的中性文字。不可改年齡、金額、是否發生事件、選項、保障給付、任何規則；不得保證獲利或理賠。',
                },
                {
                    'role': 'user',
                    'content': json.dumps(
                        {
                            'persona': {'occupation': persona['occupation'], 'industry': persona['industry']},
                            'events': [{'id': e['card_id'], 'title': e['title']} for e in events[:16]],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        req = urllib.request.Request(
            base + '/chat/completions',
            data=json.dumps(payload).encode(),
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=float(os.environ.get('LIFE_AI_TIMEOUT', '8'))) as resp:
            reply = json.loads(resp.read(128000))
        raw = reply['choices'][0]['message']['content']
        start, end = raw.find('{'), raw.rfind('}')
        entries = json.loads(raw[start : end + 1])
        for e in events:
            title = entries.get(e['card_id'])
            if isinstance(title, str) and 3 <= len(title) <= 100 and '<' not in title and '{' not in title:
                result[e['card_id']] = traditional(title)
    except (OSError, KeyError, ValueError, IndexError, TypeError):
        pass
    return result


def refine_feedback(report):
    """Optionally improve wording; preserve computed scores, recommendations and evidence IDs."""
    base = os.environ.get('LIFE_AI_BASE_URL', '').rstrip('/')
    token = os.environ.get('LIFE_AI_API_KEY', '')
    model = os.environ.get('LIFE_AI_MODEL', '')
    if not base or not token or not model:
        return report
    try:
        feedback = [
            {'title': x['title'], 'explanation': x['explanation'], 'evidence_ids': x['evidence_ids']}
            for x in report['strengths'] + report['improvements']
        ]
        payload = {
            'model': model,
            'temperature': 0.2,
            'max_tokens': 500,
            'messages': [
                {
                    'role': 'system',
                    'content': '你為大眾保險教育遊戲撰寫繁體中文客觀回饋。只回傳 JSON 字串陣列，逐條對應輸入解釋；每項 20 至 100 字。不得新增事實、商品承諾、沒有證據的結果或更改數值與因果。強調生活品質與風險承受能力。',
                },
                {'role': 'user', 'content': json.dumps(feedback, ensure_ascii=False)},
            ],
        }
        req = urllib.request.Request(
            base + '/chat/completions',
            data=json.dumps(payload).encode(),
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=float(os.environ.get('LIFE_AI_TIMEOUT', '8'))) as resp:
            reply = json.loads(resp.read(128000))
        raw = reply['choices'][0]['message']['content']
        texts = json.loads(raw[raw.find('[') : raw.rfind(']') + 1])
        if not isinstance(texts, list) or len(texts) != len(feedback):
            return report
        for old, new in zip(report['strengths'] + report['improvements'], texts):
            if (
                isinstance(new, str)
                and 20 <= len(new) <= 100
                and '<' not in new
                and not any(ch.isdigit() for ch in new)
            ):
                old['explanation'] = traditional(new)
    except (OSError, KeyError, ValueError, IndexError, TypeError):
        pass
    return report
