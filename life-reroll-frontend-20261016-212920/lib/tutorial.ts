import type { RunState } from './game-types';

export type TutorialStep = {
  id: string;
  title: string;
  text: string;
  panel?: string;
  scene?: 'HOME' | 'FINANCE';
  target?: string;
};
export function canTourFinance(run: RunState | null) {
  return (
    !!run &&
    ['INITIAL_ALLOCATION', 'EXPLORING'].includes(run.status) &&
    ['HOME', 'FINANCE'].includes(run.scene_id) &&
    ['HOME_READY', 'FREE_TIME'].includes(run.daily_phase ?? 'HOME_READY')
  );
}
export function fullTutorialSteps(visitFinance: boolean): TutorialStep[] {
  return [
    {
      id: 'welcome',
      title: '先認識你的人生',
      text: '上方是可用資金、淨資產與目前進度。跟著我們看一圈，再開始遊玩。',
      target: '.workspace-hud',
    },
    {
      id: 'overview',
      title: '生活也有不同步調',
      text: '這裡能查看角色與生活品質，也能調整每月的生活方案。',
      panel: 'overview',
    },
    {
      id: 'assets',
      title: '先看手上有多少錢',
      text: '現金與活存可立即使用；股票和定存需要先處理，才能拿來支付。',
      panel: 'assets',
    },
    ...(visitFinance
      ? [
          {
            id: 'finance',
            title: '來到金融大樓',
            text: '存款、定存、股票與借款都在這裡。交易會先預覽，確認後才執行。',
            panel: 'finance',
            scene: 'FINANCE' as const,
          },
        ]
      : []),
    {
      id: 'insurance',
      title: '保障要提前準備',
      text: '這裡可查看保單與理賠。留意等待期，核准的理賠也可能還沒入帳。',
      panel: 'insurance',
    },
    {
      id: 'event',
      title: '人生事件由你選擇',
      text: '事件發生時會在這裡停下來。看清費用與影響，再選擇要怎麼做。',
      panel: 'event',
    },
    {
      id: 'review',
      title: '每段人生都有結算',
      text: '擲骰後可查看這段期間的收支與資產變化。確認結算後，再接續行程。',
      panel: 'review',
    },
    {
      id: 'reports',
      title: '從上一輪學到下一輪',
      text: '一輪結束後，可在這裡回顧並讀檔重生；總共能體驗三輪人生。',
      panel: 'reports',
    },
    {
      id: 'settings',
      title: '隨時回來重看',
      text: '忘記操作時，在設定按「重新觀看遊玩教學」，就能再走一遍。',
      panel: 'settings',
    },
    {
      id: 'ready',
      title: visitFinance ? '回家，開始你的人生' : '接下來，輪到你了',
      text: '首次遊玩先確認配置，再在家擲骰前進 1～6 年。在職時，結算後先上班、再回家。',
      ...(visitFinance ? { scene: 'HOME' as const } : {}),
      target: '.routine-scene-actions',
    },
  ];
}
export function demoTutorialSteps(canTravel: boolean): TutorialStep[] {
  return [
    {
      id: 'map',
      title: '歡迎來到 Demo',
      text: '這是免登入的展示模式。地圖呈現城市，進度會保存在這個瀏覽器。',
      target: '.workspace-map-viewport',
    },
    {
      id: 'assets',
      title: '查看你的資產',
      text: '先看看現金、活存與投資市值。完整交易功能在後端整合版。',
      panel: 'assets',
    },
    ...(canTravel
      ? [
          {
            id: 'finance',
            title: '實際走一趟城市',
            text: '我們已抵達金融大樓。Demo 可體驗場景移動，完整服務需進入正式遊戲。',
            scene: 'FINANCE' as const,
            target: '.workspace-scene',
          },
        ]
      : []),
    {
      id: 'dice',
      title: '回家擲骰，推進人生',
      text: '骰出 1～6，代表前進 1～6 年。教學不會替你擲骰或花費資金。',
      ...(canTravel ? { scene: 'HOME' as const } : {}),
      target: '.roll-button',
    },
    {
      id: 'review',
      title: '看看每次的變化',
      text: '擲骰後會打開結算。確認摘要與明細後，就能繼續下一段人生。',
      panel: 'review',
    },
    {
      id: 'settings',
      title: '想重看，來這裡',
      text: '在「設定與教學」可隨時重看導覽。現在可以開始自由體驗了！',
      panel: 'settings',
    },
  ];
}

export function tutorialSeen(storage: Pick<Storage, 'getItem'> | undefined, key: string) {
  try {
    return storage?.getItem(key) === 'done';
  } catch {
    return false;
  }
}
