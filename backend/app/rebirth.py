"""One source of truth for real rewinds and isolated hypothetical rewinds."""
import copy
from . import engine

def preview_source(current):
    """Only historical restore material crosses into a scenario worker."""
    result={k:copy.deepcopy(current[k]) for k in ('id','start_age','initial','snapshots')}
    result['events']=[{'id':e['id'],'at_index':e['at_index']} for e in current['events']]
    return result

def points(current):
    result=[{'id':current['id']+'-start','source_run_id':current['id'],'snapshot_id':'START',
        'restore_date':engine.sim_date(current['initial']),'restore_age':current['start_age']+current['initial']['month_index']//12,
        'anchor_event_id':None,'anchor_date':None,'anchor_title':None,'preparation_days':0,
        'balance_preview':engine.money({**current,**current['initial']}),
        'warnings':['起點可重新配置資產；原輪次歷史僅供閱讀。']}]
    for entry in current['snapshots']:
        st=entry['state'];idx=entry['at_index'];restore_index=st['month_index']
        result.append({'id':entry['point_id'],'source_run_id':current['id'],'snapshot_id':entry['point_id'],
            'restore_date':engine.sim_date(st),'restore_age':current['start_age']+restore_index//12,
            'anchor_event_id':next((e['id'] for e in current['events'] if e['at_index']==idx),None),
            'anchor_date':engine.sim_date({'month_index':idx}),'anchor_title':entry['title'],
            'preparation_days':max(0,idx-restore_index)*30,'balance_preview':engine.money({**current,**st}),
            'warnings':['事件與其發生的外部條件固定；原本的保單等待期與欠款也保留。']})
    return result

def restore(persona,current,point_id,seed):
    if point_id==current['id']+'-start':
        new=engine.create_run(persona,seed,current['start_age'],copy.deepcopy(current['initial']))
        new['status']='INITIAL_ALLOCATION'
        return new
    entry=next((x for x in current['snapshots'] if x['point_id']==point_id),None)
    if entry is None:raise ValueError('INVALID_REBIRTH_POINT')
    return engine.create_run(persona,seed,current['start_age'],entry['state'],entry['anchor'])
