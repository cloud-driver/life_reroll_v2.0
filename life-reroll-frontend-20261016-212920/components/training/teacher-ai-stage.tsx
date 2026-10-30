import { plan, type Course, type Job, type Run } from '../../lib/training';
import { SourceLinks } from './training-play';
import { type Studio } from './teacher-studio-state';

export function AiStage({ s }: { s: Studio }) {
  const {
    write,
    llmEnabled,
    setNotice,
    courses,
    jobs,
    dirty,
    setTrial,
    course,
    load,
    edit,
    switchCourse,
    accepted,
    navigate,
  } = s;
  return (
    <section className="tr-card">
      <h2 data-teach-target="ai">AI 編課與發布</h2>
      <label>
        選擇要編課或發布的教案
        <select
          value={course?.id ?? ''}
          onChange={e => {
            const c = courses.find(c => c.id === e.target.value);
            if (c) switchCourse(c);
          }}
        >
          <option value="" disabled>
            請選擇已儲存的教案
          </option>
          {courses.map(c => (
            <option key={c.id} value={c.id}>
              {c.title} · {c.status === 'DRAFT' ? '草稿' : '已發布'} · v{c.version}
            </option>
          ))}
        </select>
      </label>
      <p>AI 編課是選用功能；也可以直接核對下方現有教案，再發布開班。</p>
      {!course && <button onClick={() => navigate('courses')}>前往教案工作區，建立或選擇教案</button>}
      {course?.status === 'PUBLISHED' && (
        <p className="tr-warning">
          此版本已發布，內容已固定。可直接前往開班；要修改內容，請回教案工作區複製為新草稿。
        </p>
      )}
      {dirty && <p>請先儲存目前編輯，再產生 AI 草稿。</p>}
      <p className="tr-warning">
        {llmEnabled
          ? '模型接口已啟用；生成結果仍須講師核對。'
          : 'AI 編課目前未啟用。可以先保存編課需求，服務啟用後再重試。'}
      </p>
      <p>
        先在教案工作區選擇草稿，加入教材與「希望怎麼教」，並儲存。模型會在背景整理帶來源的短劇情草稿；不會直接發布或變更商品價格。
      </p>
      <p>目前教案：{course?.title ?? '尚未選擇'}</p>
      <button
        className="tr-primary"
        disabled={
          !course?.id ||
          course.status !== 'DRAFT' ||
          dirty ||
          jobs.some(j => j.course_id === course.id && ['QUEUED', 'RUNNING'].includes(j.status))
        }
        onClick={() => void write<Job>(plan('/admin/ai-jobs', { course_id: course!.id }), () => void load())}
      >
        {llmEnabled ? '背景產生劇情草稿' : '保存編課需求，等待模型開啟'}
      </button>
      <div className="tr-stack">
        {jobs
          .filter(j => course && j.course_id === course.id)
          .map(j => (
            <article className="tr-tile" key={j.id}>
              <p>
                {courses.find(c => c.id === j.course_id)?.title ?? '教案'} · 版本 {j.course_version} · 工作{' '}
                {j.id.slice(0, 8)}
              </p>
              <strong>
                {(
                  {
                    WAITING_PROVIDER: '等待模型開啟',
                    QUEUED: '等待背景處理',
                    RUNNING: '編課中',
                    COMPLETE: '草稿待審核',
                    APPLIED: '已套用草稿',
                    CANCELLED: '已取消',
                    FAILED: '未完成',
                    INTERRUPTED: '處理中斷',
                  } as Record<string, string>
                )[j.status] ?? j.status}
              </strong>
              <p
                role={j.status === 'FAILED' ? 'alert' : undefined}
                className={j.status === 'FAILED' ? 'tr-error' : undefined}
              >
                {j.message}
              </p>
              {j.elapsed_seconds !== undefined && (
                <small>
                  經過 {j.elapsed_seconds} 秒{j.progress_chars ? ` · 已接收 ${j.progress_chars} 字` : null}
                  {['QUEUED', 'RUNNING'].includes(j.status) ? ' · 可繼續編課或離開本頁。' : null}
                </small>
              )}
              {j.result && (
                <details>
                  <summary>核對生成草稿</summary>
                  {j.result.events.map(e => (
                    <article key={e.id}>
                      <h3>{e.title}</h3>
                      <p>{e.lesson}</p>
                      <p>{e.prompt}</p>
                      <ul>
                        {e.choices.map(c => (
                          <li key={c.id}>
                            {c.label}
                            {c.id === e.correct_id ? '（教學答案）' : ''}
                          </li>
                        ))}
                      </ul>
                      <p>{e.explanation}</p>
                      <SourceLinks ids={e.source_ids} sources={j.sources ?? {}} />
                    </article>
                  ))}
                  {j.result.extracted_facts?.map((f, i) => (
                    <article key={i}>
                      <strong>擷取重點</strong>
                      <p>{f.text}</p>
                      <SourceLinks ids={[f.source_id]} sources={j.sources ?? {}} />
                    </article>
                  ))}
                  {j.result.unresolved.map(x => (
                    <p key={x}>{x}</p>
                  ))}
                </details>
              )}
              <div className="tr-actions">
                {llmEnabled &&
                  ['WAITING_PROVIDER', 'FAILED', 'INTERRUPTED'].includes(j.status) &&
                  courses.some(
                    c => c.id === j.course_id && c.status === 'DRAFT' && c.version === j.course_version,
                  ) && (
                    <button
                      onClick={() =>
                        void write(plan('/admin/ai-jobs/' + j.id + '/retry', {}), () => void load())
                      }
                    >
                      重新排入編課
                    </button>
                  )}
                {['COMPLETE', 'WAITING_PROVIDER', 'FAILED', 'INTERRUPTED'].includes(j.status) &&
                  !courses.some(
                    c => c.id === j.course_id && c.status === 'DRAFT' && c.version === j.course_version,
                  ) && <small>教案已更新或發布，這份舊需求不能重試或覆寫目前版本。</small>}
                {j.status === 'COMPLETE' &&
                  courses.some(
                    c => c.id === j.course_id && c.status === 'DRAFT' && c.version === j.course_version,
                  ) && (
                    <button
                      disabled={dirty}
                      onClick={() =>
                        void write<Course>(plan('/admin/ai-jobs/' + j.id + '/apply', {}), c => {
                          accepted(c);
                          setNotice('AI 草稿已套用。請核對下方教案與待核對事項，重新審核後發布。');
                        })
                      }
                    >
                      套用到目前教案
                    </button>
                  )}
                {['WAITING_PROVIDER', 'QUEUED', 'RUNNING'].includes(j.status) && (
                  <button
                    onClick={() =>
                      void write(plan('/admin/ai-jobs/' + j.id + '/cancel', {}), () => void load())
                    }
                  >
                    取消需求
                  </button>
                )}
              </div>
            </article>
          ))}
      </div>
      {course && (
        <section className="tr-final-review">
          <h3>核對教案並發布</h3>
          <p>
            目前版本：{course.title} · {course.events.length} 則情境。發布前請核對實際要交給學員的內容。
          </p>
          <details className="tr-rule-box">
            <summary>查看完整教案、答案與引用</summary>
            {course.events.map(e => (
              <article className="tr-tile" key={e.id}>
                <h3>{e.title}</h3>
                <p>{e.lesson}</p>
                <p>{e.prompt}</p>
                <ul>
                  {e.choices.map(c => (
                    <li key={c.id}>
                      {c.label}
                      {c.id === e.correct_id ? '（教學答案）' : ''}
                    </li>
                  ))}
                </ul>
                <p>{e.explanation}</p>
                <SourceLinks ids={e.source_ids} sources={course.sources} />
              </article>
            ))}
          </details>
          <fieldset className="tr-workspace" disabled={course.status === 'PUBLISHED'}>
            {course.unresolved.length > 0 && (
              <label>
                待核對事項（每行一項；核對後刪除）
                <textarea
                  rows={4}
                  value={course.unresolved.join('\n')}
                  onChange={e => edit({ unresolved: e.target.value.split('\n').filter(Boolean) })}
                />
              </label>
            )}
            <label data-teach-target="review" className="tr-check">
              <input
                type="checkbox"
                checked={course.reviewed}
                onChange={e => edit({ reviewed: e.target.checked })}
              />
              我已核對來源、商品範圍、教學答案與遊戲假設。
            </label>
          </fieldset>
          {course.id && (
            <div data-teach-target="publish" className="tr-actions tr-publish">
              <button
                disabled={dirty}
                onClick={() => void write<Run>(plan('/admin/courses/' + course.id + '/trial', {}), setTrial)}
              >
                實際試玩
              </button>
              <button onClick={() => navigate('courses')}>返回編輯情境</button>
            </div>
          )}
        </section>
      )}
    </section>
  );
}
