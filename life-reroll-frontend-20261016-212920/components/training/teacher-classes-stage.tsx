import { get, plan, topics, type ClassRoom } from '../../lib/training';
import { type Studio, Report } from './teacher-studio-state';

export function ClassesStage({ s }: { s: Studio }) {
  const {
    write,
    setNotice,
    courses,
    classes,
    setError,
    report,
    setReport,
    classTitle,
    setClassTitle,
    publishedId,
    setPublishedId,
    load,
  } = s;
  return (
    <div className="tr-stack">
      <section className="tr-card">
        <h2 data-teach-target="class-create">建立授課班次</h2>
        <p>班次固定使用發布當下的教案與共同市場情境。新版本不會悄悄改動學員進度。</p>
        <form
          onSubmit={e => {
            e.preventDefault();
            void write<ClassRoom>(
              plan('/admin/classes', { course_id: publishedId, title: classTitle }),
              v => {
                setClassTitle('');
                setNotice('班次已建立，加入代碼：' + v.code);
                void load();
              },
            );
          }}
        >
          <label>
            班次名稱
            <input
              required
              placeholder="例如：新進理專保障與投資訓練"
              maxLength={100}
              value={classTitle}
              onChange={e => setClassTitle(e.target.value)}
            />
          </label>
          <label>
            已發布教案
            <select required value={publishedId} onChange={e => setPublishedId(e.target.value)}>
              <option value="">請選擇已發布教案</option>
              {courses
                .filter(c => c.status === 'PUBLISHED')
                .map(c => (
                  <option key={c.id} value={c.id}>
                    {c.title} · v{c.version}
                  </option>
                ))}
            </select>
          </label>
          <button className="tr-primary" disabled={!publishedId || !classTitle.trim()}>
            建立班次與加入代碼
          </button>
        </form>
      </section>
      <section className="tr-card">
        <h2 data-teach-target="class-list">班次列表</h2>
        {classes.length === 0 && <p>尚未建立班次。請先發布教案，再使用上方表單開班。</p>}
        {classes.map(c => (
          <article className="tr-tile" key={c.id}>
            <h3>{c.title}</h3>
            <p>
              {c.course_title} · {c.status === 'OPEN' ? '開放加入' : '已關閉新加入'}
            </p>
            <p className="tr-code">{c.code}</p>
            <div className="tr-actions">
              <button
                onClick={() =>
                  void (navigator.clipboard?.writeText(c.code) ?? Promise.reject(Error('手動複製')))
                    .then(() => setNotice('班次代碼已複製。'))
                    .catch(() => setNotice('請直接選取上方代碼複製。'))
                }
              >
                複製代碼
              </button>
              <button
                onClick={() => {
                  setNotice('');
                  void get<Report>('/admin/classes/' + c.id + '/report')
                    .then(setReport)
                    .catch(e => setError(e.message));
                }}
              >
                查看學習成效
              </button>
              {c.status === 'OPEN' && (
                <button
                  onClick={() => void write(plan('/admin/classes/' + c.id + '/close', {}), () => void load())}
                >
                  關閉新加入
                </button>
              )}
            </div>
          </article>
        ))}
      </section>
      {report && (
        <section id="tr-class-report" className="tr-card">
          <h2>班次學習成效</h2>
          <p>{report.class.title}</p>
          <p>
            已完成 {report.completed}／{report.learners.length} 位學員
          </p>
          <div className="tr-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>學員</th>
                  <th>進度</th>
                  <th>判斷次數</th>
                  <th>學習分數</th>
                </tr>
              </thead>
              <tbody>
                {report.learners.map(l => (
                  <tr key={l.id}>
                    <td>{l.name}</td>
                    <td>{l.status === 'ENDED' ? '已完成' : '第 ' + l.month + ' 月'}</td>
                    <td>{l.decisions}</td>
                    <td>{l.score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>適合一起討論的重點</h3>
          {Object.entries(report.topics).map(([key, v]) => (
            <p key={key}>
              {topics[key]}：{v.incorrect}／{v.answered} 次判斷需要再釐清。
            </p>
          ))}
          <small>{report.notice}</small>
        </section>
      )}
    </div>
  );
}
