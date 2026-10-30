import { plan, fileBody, kinds, type Product } from '../../lib/training';
import { type Studio, emptyProduct } from './teacher-studio-state';

export function MaterialsStage({ s }: { s: Studio }) {
  const {
    write,
    setNotice,
    products,
    materials,
    setError,
    uploadKey,
    setUploadKey,
    file,
    setFile,
    sourceUrl,
    setSourceUrl,
    custom,
    setCustom,
    load,
  } = s;
  return (
    <div className="tr-stack">
      <section className="tr-card">
        <h2 data-teach-target="upload">匯入授課教材</h2>
        <p>
          支援 PDF、DOCX、PPTX、TXT、Markdown，每檔 8 MiB；PDF／PPTX 最多 100
          頁或投影片。背景解析期間可以繼續編課。
        </p>
        <p>
          掃描圖片目前無法辨識文字，請先轉為可選取文字的文件。已有內建商品可直接編課，匯入教材不是必填步驟。
        </p>
        <form
          onSubmit={e => {
            e.preventDefault();
            if (file)
              void fileBody(file)
                .then(b =>
                  write(plan('/admin/materials', { ...b, source_url: sourceUrl }), () => {
                    setFile(null);
                    setUploadKey(k => k + 1);
                    setNotice('教材已接收，正在背景解析。');
                    void load();
                  }),
                )
                .catch(e => setError(e.message));
          }}
        >
          <label>
            教材檔案
            <input
              key={uploadKey}
              required={!file}
              type="file"
              accept=".pdf,.docx,.pptx,.txt,.md"
              onChange={e => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          {file && (
            <div className="tr-inline">
              <small>已選擇：{file.name}</small>
              <button
                type="button"
                onClick={() => {
                  setFile(null);
                  setUploadKey(k => k + 1);
                }}
              >
                移除選取
              </button>
            </div>
          )}
          <label>
            原始來源網址（選填）
            <input type="url" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)} />
          </label>
          <button className="tr-primary" disabled={!file}>
            上傳並解析
          </button>
        </form>
      </section>
      <section className="tr-card">
        <h2 data-teach-target="materials">教材資料庫</h2>
        {materials.length === 0 && <p>尚未匯入教材。</p>}
        {materials.map(m => (
          <article key={m.id} className="tr-tile">
            <h3>{m.name}</h3>
            <p>
              {
                (
                  {
                    READY: '可編課',
                    PARSING: '解析中',
                    NEEDS_OCR: '需要文字辨識',
                    FAILED: '解析失敗',
                  } as Record<string, string>
                )[m.status]
              }{' '}
              · {m.message}
            </p>
            {['FAILED', 'NEEDS_OCR'].includes(m.status) && (
              <button
                onClick={() => void write(plan('/admin/materials/' + m.id + '/retry', {}), () => void load())}
              >
                重新解析
              </button>
            )}
            <details>
              <summary>核對擷取內容（{m.sections.length} 段）</summary>
              {m.sections.map(s => (
                <article key={s.id}>
                  <strong>{s.label}</strong>
                  <p className="tr-pre">{s.text}</p>
                  <small>引用識別：{s.id}</small>
                </article>
              ))}
            </details>
          </article>
        ))}
      </section>
      <section className="tr-card">
        <h2>可選用的商品與概念</h2>
        <p>以下商品已可在教案中勾選，不需要重複新增。</p>
        <div className="tr-grid">
          {products.map(p => (
            <article key={p.id} className="tr-tile">
              <h3>{p.name}</h3>
              <small>
                {kinds[p.kind]} · {p.provider}
              </small>
            </article>
          ))}
        </div>
        <details className="tr-rule-box">
          <summary>新增自訂商品（選填）</summary>
          <h3>加入講師核對的商品</h3>
          <p>保留商品原始來源，套用既有模擬機制。此處不會自動推定真實保費或完整理賠公式。</p>
          <form
            onSubmit={e => {
              e.preventDefault();
              void write<Product>(
                plan('/admin/products', { ...custom, facts: custom.facts.split('\n').filter(Boolean) }),
                () => {
                  setCustom({ ...emptyProduct });
                  setNotice('商品已加入，可在教案中選用。');
                  void load();
                },
              );
            }}
          >
            <div className="tr-grid">
              {(
                [
                  ['name', '商品名稱'],
                  ['provider', '保險公司／來源單位'],
                  ['source_title', '來源文件名稱'],
                  ['source_locator', '頁碼／條號'],
                ] as const
              ).map(([key, label]) => (
                <label key={key}>
                  {label}
                  <input
                    required
                    maxLength={key === 'source_title' ? 160 : 100}
                    value={custom[key]}
                    onChange={e => setCustom({ ...custom, [key]: e.target.value })}
                  />
                </label>
              ))}
            </div>
            <label>
              模擬機制
              <select value={custom.kind} onChange={e => setCustom({ ...custom, kind: e.target.value })}>
                {Object.entries(kinds).map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              來源網址
              <input
                type="url"
                required={!custom.material_id}
                value={custom.source_url}
                onChange={e => setCustom({ ...custom, source_url: e.target.value })}
              />
            </label>
            <label>
              或引用自己的教材
              <select
                value={custom.material_id}
                onChange={e => setCustom({ ...custom, material_id: e.target.value })}
              >
                <option value="">不引用匯入檔案</option>
                {materials
                  .filter(m => m.status === 'READY')
                  .map(m => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              核對後的重點（每行一項，最多 8 項，每項 200 字）
              <textarea
                required
                rows={4}
                value={custom.facts}
                onChange={e => setCustom({ ...custom, facts: e.target.value })}
              />
            </label>
            <label className="tr-check">
              <input
                required
                type="checkbox"
                checked={custom.reviewed}
                onChange={e => setCustom({ ...custom, reviewed: e.target.checked })}
              />
              已核對商品內容與引用權限。
            </label>
            <button className="tr-primary">加入商品</button>
          </form>
        </details>
      </section>
    </div>
  );
}
