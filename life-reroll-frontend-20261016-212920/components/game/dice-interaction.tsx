'use client';
const pips: Record<number, number[]> = {
  1: [4],
  2: [0, 8],
  3: [0, 4, 8],
  4: [0, 2, 6, 8],
  5: [0, 2, 4, 6, 8],
  6: [0, 2, 3, 5, 6, 8],
};
export function DiceInteraction({ value }: { value: number | null }) {
  return (
    <div className="dice-overlay" role="status" aria-live="polite">
      <div className="dice-dialog">
        <span className="eyebrow">YOUR NEXT CHAPTER</span>
        <div className={`interactive-die ${value === null ? 'dice-spinning' : ''}`} aria-hidden="true">
          {Array.from({ length: 9 }, (_, i) => (
            <span key={i} className={(pips[value ?? 1] ?? []).includes(i) ? 'die-pip' : ''} />
          ))}
        </div>
        <h2>{value === null ? '正在擲骰…' : `前進 ${value} 年`}</h2>
        <p>{value === null ? '正在準備這次人生行程。' : '期間遇到事件會停下來，讓你做出選擇。'}</p>
      </div>
    </div>
  );
}
