import { Brand } from '@/components/brand';
import { useEffect, useState, type ReactNode } from 'react';
import { GameClient } from '@/lib/game-client';
import type { LegalDocument } from '@/lib/game-types';
import './legal-page.css';
function links(text: string): ReactNode[] {
  return text.split(/(https:\/\/law\.moj\.gov\.tw\/[^\s。]+|hasaki@hasaki\.idv\.tw)/g).map((part, i) =>
    part === 'hasaki@hasaki.idv.tw' ? (
      <a key={i} href={`mailto:${part}`}>
        {part}
      </a>
    ) : part.startsWith('https://law.moj.gov.tw/') ? (
      <a key={i} href={part} target="_blank" rel="noopener noreferrer">
        個人資料保護法（全國法規資料庫）
      </a>
    ) : (
      part
    ),
  );
}
export function LegalPage({ kind }: { kind: 'TERMS' | 'PRIVACY' }) {
  const [doc, setDoc] = useState<LegalDocument | null>(null),
    [error, setError] = useState(''),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    setError('');
    document.title = `${kind === 'TERMS' ? '服務條款' : '隱私政策'}｜Life Reroll`;
    void new GameClient()
      .call<LegalDocument>('B08', { kind }, undefined, {}, abort.signal)
      .then(value => {
        if (!abort.signal.aborted) setDoc(value);
      })
      .catch(() => {
        if (!abort.signal.aborted) setError('暫時無法讀取文件，請確認網路後重試。');
      });
    return () => abort.abort();
  }, [kind, retry]);
  const sections =
    doc?.body.split(/\n\n(?=## )/).map(part => {
      const [title, ...body] = part.split('\n');
      return { title: title.replace(/^## /, ''), body: body.join('\n') };
    }) ?? [];
  return (
    <main className="legal-page">
      <header>
        <a className="legal-brand" href="/full">
          <Brand />
        </a>
        <nav aria-label="法律文件">
          <a href="/terms" aria-current={kind === 'TERMS' ? 'page' : undefined}>
            服務條款
          </a>
          <a href="/privacy" aria-current={kind === 'PRIVACY' ? 'page' : undefined}>
            隱私政策
          </a>
        </nav>
      </header>
      <article>
        <p className="legal-eyebrow">知嶼科技 · LIFE REROLL</p>
        <h1>{kind === 'TERMS' ? '服務條款' : '隱私政策'}</h1>
        {doc && (
          <p className="legal-version">
            版本 {doc.version} · 生效日期 {doc.effective_on}
          </p>
        )}
        <p className="legal-intro">
          {kind === 'TERMS'
            ? '這是一款保險與資金規劃教育遊戲。請先了解模擬內容、帳號使用及 AI 回饋的範圍。'
            : '這裡說明本站如何使用帳號、遊戲與 AI 問答資料，以及你可以如何行使個人資料權利。'}
        </p>
        {!doc && !error && <p role="status">正在讀取文件…</p>}
        {error && (
          <div role="alert">
            <p>{error}</p>
            <button onClick={() => setRetry(v => v + 1)}>重新讀取</button>
          </div>
        )}
        {sections.length > 0 && (
          <nav className="legal-contents" aria-label="文件章節">
            {sections.map((s, i) => (
              <a key={i} href={`#section-${i + 1}`}>
                {s.title}
              </a>
            ))}
          </nav>
        )}
        {sections.map((s, i) => (
          <section key={i} id={`section-${i + 1}`}>
            <h2>{s.title}</h2>
            {s.body
              .split('\n')
              .filter(Boolean)
              .map((p, j) => (
                <p key={j}>{links(p)}</p>
              ))}
          </section>
        ))}
        <footer>
          <p>
            服務提供者：知嶼科技 · 聯絡信箱：<a href="mailto:hasaki@hasaki.idv.tw">hasaki@hasaki.idv.tw</a>
          </p>
          <p>本文件在獨立分頁開啟；關閉此分頁即可回到剛才的遊戲。</p>
        </footer>
      </article>
    </main>
  );
}
