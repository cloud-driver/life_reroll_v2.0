export type Point = { x: number; y: number };
export type DestinationId = 'work' | 'hospital' | 'leisure' | 'finance';

// Original illustration coordinates (1672 × 941). The SVG overlay scales with it.
// On the street immediately outside the house's southeast fence.
export const HOME: Point = { x: 932, y: 572 };
const WORK_START: Point = { x: 959, y: 414 };
const HOSPITAL_START: Point = { x: 946, y: 576 };
export const DESTINATIONS: Record<DestinationId, {label: string; action: string; detail: string; scene: string; durationMs: number; route: Point[]}> = {
  work: { label: '工作場域', action: '去工作', detail: '右下方・辦公園區', scene: '/scene-work.webp', durationMs: 6500, route: [WORK_START, {x:1324,y:624}, {x:1231,y:682}] },
  hospital: { label: '醫院', action: '去醫院', detail: '左下方・醫院外側道路', scene: '/scene-hospital.webp', durationMs: 7600, route: [HOSPITAL_START, {x:452,y:822}] },
  leisure: { label: '休閒區', action: '去出遊', detail: '右上方・商街與機場', scene: '/scene-leisure.webp', durationMs: 7600, route: [HOME, {x:1012,y:524}, {x:1068,y:436}, {x:1324,y:286}] },
  finance: { label: '金融大樓', action: '去金融大樓', detail: '左上方・銀行與保險', scene: '/scene-finance.webp', durationMs: 9000, route: [HOME, {x:742,y:670}, {x:318,y:441}, {x:408,y:388}] },
};
