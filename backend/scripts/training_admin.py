"""Grant/revoke an existing verified instructor. Never creates public admin signup."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store
p=argparse.ArgumentParser(description='授予或撤銷已驗證帳號的講師權限（使用 LIFE_REPLAY_DB 指定資料庫）')
p.add_argument('email');p.add_argument('--revoke',action='store_true');args=p.parse_args()
store.init()
with store.tx() as db:
 user=db.execute('SELECT id,verified FROM users WHERE email=?',(args.email.strip().lower(),)).fetchone()
 if not user or not user['verified']:p.error('帳號不存在或尚未完成信箱驗證')
 if args.revoke:db.execute('DELETE FROM training_admins WHERE user_id=?',(user['id'],))
 else:db.execute('INSERT OR IGNORE INTO training_admins VALUES(?)',(user['id'],))
print('講師權限已撤銷' if args.revoke else '講師權限已授予')
