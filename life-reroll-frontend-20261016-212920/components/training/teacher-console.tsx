import { TeacherTutorial } from './teacher-tutorial';
import { TrainingPlay } from './training-play';
import { useTeacherStudio, type StudioProps, stages } from './teacher-studio-state';
import { CoursesStage } from './teacher-courses-stage';
import { MaterialsStage } from './teacher-materials-stage';
import { ClassesStage } from './teacher-classes-stage';
import { AiStage } from './teacher-ai-stage';

export function TeacherConsole(props: StudioProps) {
  const s = useTeacherStudio(props);
  const {
    write,
    setNotice,
    setTab,
    catalog,
    selectedCourse,
    dirty,
    error,
    trial,
    setTrial,
    tour,
    course,
    page,
    save,
    navigate,
    nextFromCourse,
    publishReason,
    publishNext,
  } = s;
  if (trial)
    return (
      <TrainingPlay
        exitLabel="返回教案工作區"
        run={trial}
        write={write}
        onRun={setTrial}
        onExit={() => setTrial(null)}
      />
    );
  return (
    <div className="tr-studio">
      <div className="tr-heading">
        <div>
          <p className="tr-eyebrow">INSTRUCTOR STUDIO</p>
          <h1>把教材變成一次次選擇</h1>
          <p>準備教材 → 建立教案 → AI 編課與發布 → 開班回顧</p>
        </div>
        <button data-teach-launch disabled={!catalog} onClick={tour.start}>
          工作室教學
        </button>
      </div>
      <div data-teach-target="tabs" className="tr-tabs tr-stages" role="tablist" aria-label="講師授課流程">
        {stages.map(([id, label, description], i) => (
          <button
            id={'tr-tab-' + id}
            key={id}
            role="tab"
            aria-selected={page === id}
            aria-controls="tr-studio-page"
            tabIndex={page === id ? 0 : -1}
            className={page === id ? 'tr-selected' : ''}
            onClick={() => {
              setNotice('');
              navigate(id);
            }}
            onKeyDown={e => {
              const delta = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
              if (!delta && e.key !== 'Home' && e.key !== 'End') return;
              e.preventDefault();
              const n =
                e.key === 'Home'
                  ? 0
                  : e.key === 'End'
                    ? stages.length - 1
                    : (i + delta + stages.length) % stages.length;
              setTab(stages[n][0]);
              document.getElementById('tr-tab-' + stages[n][0])?.focus();
            }}
          >
            <span className="tr-stage-number">{i + 1}</span>
            <span>
              {label}
              <small>{description}</small>
            </span>
          </button>
        ))}
      </div>
      <section id="tr-studio-page" role="tabpanel" aria-labelledby={'tr-tab-' + page} tabIndex={-1}>
        {dirty && selectedCourse && !tour.active && (
          <p className="tr-warning">
            「{selectedCourse.title || '未命名教案'}」有未儲存的編輯，切換步驟仍會保留。
            {page !== 'courses' && (
              <button className="tr-inline-save" onClick={() => void save()}>
                儲存目前草稿
              </button>
            )}
          </p>
        )}
        {tour.active && tour.step?.example && (
          <p className="tr-tutorial-example">教學範本 · 僅供導覽，尚未建立或儲存教案。</p>
        )}
        {error && (
          <p role="alert" className="tr-error">
            {error}
          </p>
        )}
        {!catalog ? (
          <p role="status">正在載入講師資料…</p>
        ) : page === 'courses' ? (
          <CoursesStage s={s} />
        ) : page === 'materials' ? (
          <MaterialsStage s={s} />
        ) : page === 'classes' ? (
          <ClassesStage s={s} />
        ) : (
          <AiStage s={s} />
        )}
      </section>
      {catalog && (
        <nav data-teach-target="workflow" className="tr-workflow-footer" aria-label="步驟導覽">
          <div>
            <small>
              步驟 {stages.findIndex(([id]) => id === page) + 1}／{stages.length}
            </small>
            <strong>{stages.find(([id]) => id === page)?.[1]}</strong>
            {page === 'courses' && !course && <p>先選擇教案或從範本建立草稿。</p>}
            {page === 'ai' && publishReason && <p>{publishReason}</p>}
          </div>
          <div className="tr-actions">
            {page !== 'materials' && (
              <button onClick={() => navigate(stages[stages.findIndex(([id]) => id === page) - 1][0])}>
                上一步：{stages[stages.findIndex(([id]) => id === page) - 1][1]}
              </button>
            )}
            {page === 'materials' && (
              <button className="tr-primary" onClick={() => navigate('courses')}>
                下一步：建立教案
              </button>
            )}
            {page === 'courses' && (
              <button className="tr-primary" disabled={!course} onClick={() => void nextFromCourse()}>
                {course?.status === 'DRAFT' && (dirty || !course.id)
                  ? '儲存草稿並前往 AI 編課'
                  : '下一步：AI 編課與發布'}
              </button>
            )}
            {page === 'ai' && (
              <button
                data-teach-target="publish-next"
                className="tr-primary"
                disabled={!!publishReason}
                onClick={() => void publishNext()}
              >
                {course?.status === 'PUBLISHED' ? '下一步：建立班次' : '核對後發布，前往開班'}
              </button>
            )}
            {page === 'classes' && <button onClick={() => navigate('materials')}>準備下一堂課</button>}
          </div>
        </nav>
      )}
      {tour.active && <TeacherTutorial tour={tour} />}
    </div>
  );
}
