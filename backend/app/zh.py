"""Convert every model-authored display string, including partial replies, to Taiwan Chinese."""
from threading import local
from opencc import OpenCC

_local = local()

def traditional(text: str) -> str:
    if not hasattr(_local, 'converter'):
        _local.converter = OpenCC('s2twp')
    return _local.converter.convert(text).replace('賬','帳').replace('審核透過','審核通過').replace('稽核透過','審核通過').replace('釦除','扣除').replace('扣除專案','扣除項目')

def display_tree(value):
    """Preserve JSON keys and numbers; only human-readable values are converted."""
    if isinstance(value, str):return traditional(value)
    if isinstance(value, list):return [display_tree(x) for x in value]
    if isinstance(value, dict):return {k:display_tree(v) for k,v in value.items()}
    return value
