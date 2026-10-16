import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronDown,
  CircleHelp,
  Clock3,
  FileCheck2,
  FileText,
  FolderOpen,
  GraduationCap,
  Layers3,
  ListChecks,
  LoaderCircle,
  MessageSquareText,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import { api, ApiError } from "./api";
import { hourKeys, isCourse, studyHours, topicHours } from "./types";
import type { Analysis, Course, Project, Template, Topic } from "./types";

type Step = 1 | 2 | 3;
type Tab = "program" | "tests" | "seminars" | "slides" | "literature";
interface Saved {
  id: string;
  query: string;
  template: Template | "";
  hours: string;
}
const storageKey = "eduagent.workbench.v1";
const presets = [
  {
    name: "ДПП ПК · 72 часа",
    template: "dpp_pk" as Template,
    hours: "72",
    query:
      "Повышение квалификации по анализу данных на Python для сотрудников банка, знающих основы Python. Объём — 72 академических часа. Форма обучения — очно-заочная. Итоговая аттестация — защита проекта.",
  },
  {
    name: "Интенсив ДООП · 24 часа",
    template: "doop" as Template,
    hours: "24",
    query:
      "Общеразвивающий интенсив по созданию ИИ-продуктов для студентов с базовыми навыками программирования. Объём — 24 академических часа. Форма обучения — очная. Итоговая аттестация — защита командного проекта. Выдаваемый документ — сертификат.",
  },
];
const templates = {
  dpp_pk: "Повышение квалификации",
  doop: "Общеразвивающая программа",
};
const steps = [
  { title: "Запрос и уточнение", subtitle: "Задача, аудитория и референсы" },
  { title: "Каркас программы", subtitle: "Компетенции, темы и часы" },
  { title: "Комплект и выгрузка", subtitle: "Материалы и автопроверка" },
];
function readSaved(): Saved | null {
  try {
    return JSON.parse(localStorage.getItem(storageKey) || "null");
  } catch {
    return null;
  }
}
function safeUrl(value: string | null) {
  try {
    const url = new URL(value || "");
    return ["http:", "https:"].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}
function copyCourse(course: Course) {
  return structuredClone(course);
}
function Badge({
  children,
  tone = "",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
function Spinner() {
  return <LoaderCircle className="spin" size={17} aria-hidden="true" />;
}
function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={`panel ${className}`}>{children}</section>;
}

export default function App() {
  const [saved] = useState(readSaved);
  const [project, setProject] = useState<Project | Course | null>(null);
  const [draft, setDraft] = useState<Course | null>(null);
  const [step, setStep] = useState<Step>(1);
  const [query, setQuery] = useState(saved?.query || "");
  const [template, setTemplate] = useState<Template | "">(
    saved?.template || "",
  );
  const [hours, setHours] = useState(saved?.hours || "");
  const [files, setFiles] = useState<File[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [answers, setAnswers] = useState<string[]>([]);
  const [busy, setBusy] = useState("");
  const [booting, setBooting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState("");
  const [health, setHealth] = useState<"checking" | "online" | "offline">(
    "checking",
  );
  const [tab, setTab] = useState<Tab>("program");
  const [openProject, setOpenProject] = useState(false);
  const [openId, setOpenId] = useState("");
  const [regenerate, setRegenerate] = useState<{
    type: "topic" | "test";
    id: string;
    title: string;
  } | null>(null);
  const [instruction, setInstruction] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const flight = useRef(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const modal = useRef<HTMLDialogElement>(null);
  const confirmationModal = useRef<HTMLDialogElement>(null);
  const confirmationResolve = useRef<((value: boolean) => void) | null>(null);
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const course = isCourse(project) ? project : null;
  const working = Boolean(busy || booting || project?.busy);
  const completed = course?.status === "completed";
  const sum = draft ? studyHours(draft) + draft.ia_hours : 0;
  const difference = draft ? draft.total_hours - sum : 0;
  const validDraft = Boolean(
    draft &&
    draft.title.trim() &&
    draft.goal.trim() &&
    draft.modules.every(
      (m) =>
        m.title.trim() &&
        m.topics.every(
          (t) =>
            t.title.trim() &&
            hourKeys.every((k) => Number.isInteger(t[k]) && t[k] >= 0),
        ),
    ) &&
    Number.isInteger(draft.total_hours) &&
    draft.total_hours > 0 &&
    Number.isInteger(draft.ia_hours) &&
    draft.ia_hours >= 0 &&
    draft.ia_hours < draft.total_hours &&
    difference === 0,
  );
  const draftChanged = Boolean(
    course &&
    draft &&
    (draft.title !== course.title ||
      draft.goal !== course.goal ||
      draft.total_hours !== course.total_hours ||
      draft.ia_hours !== course.ia_hours ||
      JSON.stringify(draft.modules) !== JSON.stringify(course.modules)),
  );

  function accept(p: Project | Course, go?: Step) {
    setProject(p);
    if (isCourse(p)) setDraft(copyCourse(p));
    if ("analysis" in p && p.analysis) {
      setAnalysis(p.analysis);
      setAnswers([]);
    }
    if (go) setStep(go);
  }
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }, [step]);
  useEffect(() => {
    let cancelled = false;
    const check = () => {
      api
        .health()
        .then(() => {
          if (!cancelled) setHealth("online");
        })
        .catch(() => {
          if (!cancelled) setHealth("offline");
        });
    };
    check();
    const timer = setInterval(check, 15000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    let cancelled = false;
    const id = new URLSearchParams(location.search).get("project") || saved?.id;
    if (id && /^[a-zA-Z0-9_-]{1,64}$/.test(id)) {
      if (id !== saved?.id) {
        setQuery("");
        setHours("");
        setTemplate("");
      }
      setBooting(true);
      api
        .get(id)
        .then((p) => {
          if (!cancelled)
            accept(
              p,
              isCourse(p) ? (p.status === "skeleton_ready" ? 2 : 3) : 1,
            );
        })
        .catch((e) => {
          if (!cancelled) setError(e);
        })
        .finally(() => {
          if (!cancelled) setBooting(false);
        });
    }
    return () => {
      cancelled = true;
    };
  }, [saved]);
  useEffect(() => {
    if (!project) return;
    try {
      localStorage.setItem(
        storageKey,
        JSON.stringify({ id: project.project_id, query, template, hours }),
      );
    } catch {
      /* A blocked browser store does not prevent server-side saving. */
    }
    const url = new URL(location.href);
    url.searchParams.set("project", project.project_id);
    history.replaceState(null, "", url);
  }, [project?.project_id, query, template, hours]);
  useEffect(() => {
    if (!project?.project_id || (!project.busy && busy !== "generate")) return;
    let cancelled = false;
    const started = Date.now();
    setElapsed(0);
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - started) / 1000));
      api
        .get(project.project_id)
        .then((p) => {
          if (!cancelled) {
            setProject((current) =>
              current &&
              current.project_id === p.project_id &&
              current.revision > p.revision
                ? current
                : p,
            );
            if (isCourse(p) && p.status === "completed" && !p.busy) {
              setDraft(copyCourse(p));
            }
          }
        })
        .catch(() => {
          /* The foreground request reports actionable failures. */
        });
    }, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [project?.project_id, Boolean(project?.busy), busy === "generate"]);
  useEffect(() => {
    if (regenerate) {
      setError(null);
      modal.current?.showModal();
      modal.current?.querySelector("textarea")?.focus();
      setInstruction("");
    } else modal.current?.close();
  }, [regenerate]);
  useEffect(() => {
    if (confirmation) confirmationModal.current?.showModal();
    else confirmationModal.current?.close();
  }, [confirmation]);
  useEffect(() => {
    if (!draftChanged || working) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [draftChanged, working]);

  async function run(label: string, action: () => Promise<void>) {
    if (flight.current) return;
    flight.current = true;
    setBusy(label);
    setError(null);
    setNotice("");
    try {
      await action();
    } catch (e) {
      const failure =
        e instanceof ApiError
          ? e
          : new ApiError(
              "Не удалось выполнить действие. Попробуйте ещё раз.",
              "unknown_error",
              0,
            );
      if (
        failure.code === "clarifications_required" &&
        failure.context.project_id
      ) {
        const p = await api
          .get(String(failure.context.project_id))
          .catch(() => null);
        if (p) accept(p, 1);
      }
      setError(failure);
    } finally {
      flight.current = false;
      setBusy("");
    }
  }
  function addFiles(incoming: File[]) {
    if (working) return;
    const next = [...files];
    for (const file of incoming) {
      if (!/\.(docx|pdf)$/i.test(file.name)) {
        setError(
          new ApiError("Можно прикрепить только DOCX и PDF.", "file_type", 0),
        );
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        setError(
          new ApiError(`Файл «${file.name}» больше 10 МБ.`, "file_size", 0),
        );
        return;
      }
      if (
        !next.some(
          (f) =>
            f.name === file.name &&
            f.size === file.size &&
            f.lastModified === file.lastModified,
        )
      )
        next.push(file);
    }
    if (next.length > 5) {
      setError(
        new ApiError(
          "Можно прикрепить не больше пяти файлов.",
          "file_count",
          0,
        ),
      );
      return;
    }
    setFiles(next);
    setAnalysis(null);
    setAnswers([]);
    setError(null);
  }
  function askConfirmation(message: string) {
    return new Promise<boolean>((resolve) => {
      confirmationResolve.current = resolve;
      setConfirmation(message);
    });
  }
  function finishConfirmation(value: boolean) {
    const resolve = confirmationResolve.current;
    confirmationResolve.current = null;
    setConfirmation(null);
    resolve?.(value);
  }
  async function newProject() {
    if (working) return;
    if (
      project &&
      !(await askConfirmation(
        draftChanged
          ? "Начать новую программу? Несохранённые правки будут потеряны. Последняя сохранённая версия останется на сервере."
          : "Начать новую программу? Текущий проект останется сохранён на сервере.",
      ))
    )
      return;
    setProject(null);
    setDraft(null);
    setAnalysis(null);
    setAnswers([]);
    setFiles([]);
    setQuery("");
    setTemplate("");
    setHours("");
    setError(null);
    setNotice("");
    setStep(1);
    try {
      localStorage.removeItem(storageKey);
    } catch {
      /* Optional browser persistence. */
    }
    history.replaceState(null, "", location.pathname);
  }
  async function refreshProject() {
    if (!project) return;
    if (
      draftChanged &&
      !(await askConfirmation(
        "Загрузить сохранённую версию? Несохранённые правки в редакторе будут заменены.",
      ))
    )
      return;
    await run("load", async () => {
      const p = await api.get(project.project_id);
      accept(p);
      setNotice("Загружена актуальная версия проекта.");
    });
  }
  function queryWithChoices() {
    return [
      query,
      template ? `Тип программы: ${templates[template]}.` : "",
      hours ? `Объём: ${hours} часов.` : "",
    ]
      .filter(Boolean)
      .join("\n");
  }
  async function analyze(event: FormEvent) {
    event.preventDefault();
    if (
      course &&
      !(await askConfirmation(
        "Повторный анализ заменит каркас и материалы этого проекта. Продолжить?",
      ))
    )
      return;
    void run("analyze", async () => {
      const result = await api.analyze(
        queryWithChoices(),
        files,
        project?.project_id,
      );
      setProject(await api.get(result.project_id));
      setDraft(null);
      setAnalysis(result);
      setAnswers([]);
      setNotice(
        result.is_complete
          ? "Параметры определены. Можно создать каркас программы."
          : "Агенту нужно уточнить несколько деталей.",
      );
    });
  }
  function clarificationText() {
    return answers
      .flatMap((a, i) => {
        if (!a.trim()) return [];
        const q = analysis?.clarifying_questions[i] || "";
        if (q.includes("час")) return [`Объём: ${a} часов.`];
        if (q.includes("Кто")) return [`Для ${a}.`];
        if (q.includes("аттестация")) return [`Итоговая аттестация: ${a}.`];
        return [a];
      })
      .join("\n");
  }
  function buildSkeleton() {
    void run("skeleton", async () => {
      const p = await api.skeleton({
        query,
        project_id: project?.project_id,
        ...(template ? { template_type: template } : {}),
        ...(hours ? { total_hours: Number(hours) } : {}),
        clarifications: clarificationText(),
      });
      accept(p, 2);
      setNotice(
        "Каркас сохранён. Проверьте название, компетенции и распределение часов.",
      );
    });
  }
  function updateTopic(
    moduleIndex: number,
    topicIndex: number,
    updates: Partial<Topic>,
  ) {
    setDraft((current) => {
      if (!current) return current;
      const next = copyCourse(current);
      Object.assign(next.modules[moduleIndex].topics[topicIndex], updates);
      return next;
    });
  }
  function approveAndGenerate() {
    if (!draft || !validDraft) return;
    void run("approve", async () => {
      const payload = copyCourse(draft);
      for (const m of payload.modules) {
        for (const t of m.topics) t.total_hours = topicHours(t);
        for (const key of hourKeys)
          m[key] = m.topics.reduce((sum, t) => sum + t[key], 0);
        m.total_hours = m.topics.reduce((sum, t) => sum + t.total_hours, 0);
      }
      const approved = await api.approve(payload);
      accept(approved, 3);
      setBusy("generate");
      try {
        const result = await api.generate(approved.project_id);
        accept(result, 3);
        setTab("program");
        setNotice(
          "Комплект сформирован и сохранён. Можно проверить материалы и скачать файлы.",
        );
      } catch (e) {
        const p = await api.get(approved.project_id).catch(() => null);
        if (p) accept(p, 3);
        throw e;
      }
    });
  }
  function retryGenerate() {
    if (!course) return;
    void run("generate", async () => {
      try {
        accept(await api.generate(course.project_id), 3);
        setNotice("Материалы сформированы.");
      } catch (e) {
        const p = await api.get(course.project_id).catch(() => null);
        if (p) accept(p, 3);
        throw e;
      }
    });
  }
  function download(format: string) {
    if (project)
      void run(`download-${format}`, async () => {
        await api.download(project, format);
        setNotice("Файл передан браузеру для скачивания.");
      });
  }
  function regeneratePart(event: FormEvent) {
    event.preventDefault();
    if (!course || !regenerate || !instruction.trim()) return;
    void run("regenerate", async () => {
      const p = await api.regenerate(course.project_id, {
        element_type: regenerate.type,
        element_id: regenerate.id,
        instruction,
        revision: course.revision,
      });
      accept(p, 3);
      setRegenerate(null);
      setNotice("Элемент обновлён. Часы и связи компетенций сохранены.");
    });
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace">
        Перейти к рабочей области
      </a>
      <aside className="sidebar">
        <a
          href={location.pathname}
          className="brand"
          onClick={(e) => {
            e.preventDefault();
            if (!working) setStep(1);
          }}
        >
          <span className="brand-icon">
            <GraduationCap size={25} />
          </span>
          <span>
            EduAgent<small>АКАДЕМИЯ ЦИФРОВОГО РАЗВИТИЯ</small>
          </span>
        </a>
        <div className="sidebar-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <button
          className="side-link selected"
          onClick={() => setStep(course ? 2 : 1)}
        >
          <Layers3 size={18} />
          Конструктор программ
          <span className="side-dot" />
        </button>
        <button className="side-link" onClick={() => setOpenProject((v) => !v)}>
          <FolderOpen size={18} />
          Открыть проект
        </button>
        {openProject && (
          <form
            className="open-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (!/^[a-zA-Z0-9_-]{1,64}$/.test(openId.trim())) {
                setError(
                  new ApiError(
                    "Укажите корректный ID проекта.",
                    "project_id",
                    0,
                  ),
                );
                return;
              }
              void run("load", async () => {
                if (
                  draftChanged &&
                  !(await askConfirmation(
                    "Открыть другой проект? Несохранённые правки текущего редактора будут потеряны.",
                  ))
                )
                  return;
                const p = await api.get(openId.trim());
                accept(
                  p,
                  isCourse(p) ? (p.status === "skeleton_ready" ? 2 : 3) : 1,
                );
                const previousSession = readSaved();
                const sameProject = previousSession?.id === p.project_id;
                setQuery(sameProject ? previousSession.query : "");
                setHours(sameProject ? previousSession.hours : "");
                setTemplate(sameProject ? previousSession.template : "");
                setFiles([]);
                setOpenProject(false);
              });
            }}
          >
            <label htmlFor="open-id">ID сохранённого проекта</label>
            <input
              id="open-id"
              value={openId}
              onChange={(e) => setOpenId(e.target.value)}
              placeholder="Вставьте ID"
              maxLength={64}
              disabled={working}
            />
            <button
              className="button secondary small"
              disabled={working || !openId.trim()}
            >
              Открыть
            </button>
          </form>
        )}
        <div className="sidebar-note">
          <span className="note-icon">
            <ShieldCheck size={21} />
          </span>
          <strong>Решение остаётся за вами</strong>
          <p>
            Агент предлагает структуру. Вы проверяете учебный план и утверждаете
            его перед генерацией.
          </p>
        </div>
        <div className="sidebar-bottom">
          <span className="avatar">М</span>
          <div>
            <strong>Методист АЦР</strong>
            <small>Рабочее пространство</small>
          </div>
          <Badge>v0.1</Badge>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Образовательные программы <span>/</span>{" "}
            <strong>{project ? "Текущий проект" : "Новая программа"}</strong>
          </div>
          <div className={`connection ${health}`}>
            <span />
            {health === "online"
              ? "Сервис доступен"
              : health === "offline"
                ? "Нет связи с сервером"
                : "Проверяем связь"}
          </div>
        </header>
        <main id="workspace" className="workspace">
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                КОНСТРУКТОР ОБРАЗОВАТЕЛЬНЫХ ПРОГРАММ
              </div>
              <h1>От идеи до готовой программы</h1>
              <p>
                Соберите учебный план и материалы в одном рабочем пространстве.
              </p>
            </div>
            <button
              className="button secondary"
              disabled={working}
              onClick={newProject}
            >
              <Plus size={17} />
              Новая программа
            </button>
          </div>
          <nav className="stepper" aria-label="Этапы создания программы">
            {steps.map((s, i) => {
              const n = (i + 1) as Step;
              const available =
                n === 1 ||
                (n === 2 && Boolean(course)) ||
                (n === 3 &&
                  Boolean(course && course.status !== "skeleton_ready"));
              const done =
                n === 1
                  ? Boolean(course)
                  : n === 2
                    ? Boolean(course && course.status !== "skeleton_ready")
                    : Boolean(completed);
              return (
                <button
                  key={s.title}
                  className={`step ${step === n ? "active" : ""} ${done ? "done" : ""}`}
                  aria-current={step === n ? "step" : undefined}
                  disabled={!available || booting}
                  onClick={() => setStep(n)}
                >
                  <span className="step-number">
                    {done && step !== n ? <Check size={18} /> : `0${n}`}
                  </span>
                  <span>
                    <strong>{s.title}</strong>
                    <small>{s.subtitle}</small>
                  </span>
                  {i !== 2 && <span className="step-line" />}
                </button>
              );
            })}
          </nav>
          {project && (
            <div className="project-strip">
              <span>
                <span
                  className={
                    step === 2 && draftChanged ? "amber-dot" : "green-dot"
                  }
                />
                {step === 2 && draftChanged
                  ? "Есть несохранённые правки"
                  : "Сохранено на сервере"}{" "}
                <span className="muted">· версия {project.revision}</span>
              </span>
              <div>
                <Badge
                  tone={project.execution_mode === "demo" ? "amber" : "green"}
                >
                  {project.execution_mode === "demo"
                    ? "Демонстрационный режим"
                    : "Генерация Cloud.ru"}
                </Badge>
                <button
                  className="text-button"
                  disabled={working}
                  onClick={() => void refreshProject()}
                  title="Загрузить актуальную версию проекта"
                >
                  <RefreshCw size={14} />
                  Обновить
                </button>
              </div>
            </div>
          )}
          {error && (
            <div className="message error" role="alert">
              <CircleHelp size={20} />
              <div>
                <strong>
                  {error.code === "revision_conflict"
                    ? "Проект уже изменился"
                    : "Не удалось завершить действие"}
                </strong>
                <p>{error.message}</p>
                {error.code === "revision_conflict" && (
                  <button
                    className="text-button"
                    disabled={working}
                    onClick={() => void refreshProject()}
                  >
                    Загрузить актуальную версию
                  </button>
                )}
              </div>
              <button
                aria-label="Скрыть ошибку"
                className="icon-button"
                onClick={() => setError(null)}
              >
                <X size={17} />
              </button>
            </div>
          )}
          {notice && (
            <div className="message success" role="status">
              <CheckCheck size={18} />
              <span>{notice}</span>
              <button
                aria-label="Скрыть уведомление"
                className="icon-button"
                onClick={() => setNotice("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {booting ? (
            <Panel className="empty-state">
              <Spinner />
              <h2>Открываем сохранённый проект</h2>
              <p>Загружаем данные и последнюю версию материалов.</p>
            </Panel>
          ) : (
            <>
              {step === 1 && (
                <div className="request-layout">
                  <div>
                    <Panel>
                      <div className="section-heading">
                        <span className="section-icon">
                          <MessageSquareText size={21} />
                        </span>
                        <div>
                          <h2>Какую программу создаём?</h2>
                          <p>
                            Опишите задачу своими словами — агент уточнит
                            детали.
                          </p>
                        </div>
                      </div>
                      <form onSubmit={analyze}>
                        <label className="field-label" htmlFor="query">
                          Запрос методиста
                        </label>
                        <textarea
                          id="query"
                          className="query-input"
                          value={query}
                          onChange={(e) => {
                            setQuery(e.target.value);
                            setAnalysis(null);
                            setAnswers([]);
                          }}
                          placeholder="Например: повышение квалификации по анализу данных на Python для сотрудников банка, 72 часа…"
                          maxLength={30000}
                          required
                          disabled={working}
                        />
                        <div className="presets">
                          <span>Попробуйте пример:</span>
                          {presets.map((p) => (
                            <button
                              key={p.template}
                              type="button"
                              disabled={working}
                              onClick={() => {
                                setQuery(p.query);
                                setTemplate(p.template);
                                setHours(p.hours);
                                setAnalysis(null);
                                setAnswers([]);
                              }}
                            >
                              <Sparkles size={13} />
                              {p.name}
                            </button>
                          ))}
                        </div>
                        <div className="form-grid">
                          <label>
                            Тип программы
                            <select
                              value={template}
                              onChange={(e) => {
                                setTemplate(e.target.value as Template | "");
                                setAnalysis(null);
                                setAnswers([]);
                              }}
                              disabled={working}
                            >
                              <option value="">Определить по запросу</option>
                              <option value="dpp_pk">
                                ДПП ПК · повышение квалификации
                              </option>
                              <option value="doop">
                                ДООП · общеразвивающая
                              </option>
                            </select>
                          </label>
                          <label>
                            Объём, академических часов
                            <input
                              type="number"
                              min="1"
                              max="10000"
                              step="1"
                              value={hours}
                              onChange={(e) => {
                                setHours(e.target.value);
                                setAnalysis(null);
                                setAnswers([]);
                              }}
                              placeholder="Определить по запросу"
                              disabled={working}
                            />
                          </label>
                        </div>
                        <label className="field-label" htmlFor="references">
                          Материалы для программы{" "}
                          <span className="optional">необязательно</span>
                        </label>
                        <div
                          className={`dropzone ${working ? "disabled" : ""}`}
                          onDragOver={(e) => e.preventDefault()}
                          onDrop={(e) => {
                            e.preventDefault();
                            addFiles(Array.from(e.dataTransfer.files));
                          }}
                        >
                          <UploadCloud size={27} />
                          <strong>
                            Перетащите файлы или{" "}
                            <button
                              type="button"
                              disabled={working}
                              className="text-button"
                              onClick={() => fileInput.current?.click()}
                            >
                              выберите на компьютере
                            </button>
                          </strong>
                          <span>
                            DOCX и PDF · до 5 файлов · до 10 МБ каждый
                          </span>
                          <input
                            ref={fileInput}
                            id="references"
                            type="file"
                            accept=".docx,.pdf"
                            multiple
                            className="visually-hidden"
                            disabled={working}
                            onChange={(e) => {
                              addFiles(Array.from(e.target.files || []));
                              e.target.value = "";
                            }}
                          />
                        </div>
                        {files.length > 0 && (
                          <ul className="file-list">
                            {files.map((f, i) => (
                              <li key={`${f.name}-${i}`}>
                                <FileText size={17} />
                                <span>
                                  {f.name}
                                  <small>{(f.size / 1024).toFixed(0)} КБ</small>
                                </span>
                                <button
                                  type="button"
                                  className="icon-button"
                                  aria-label={`Удалить ${f.name}`}
                                  disabled={working}
                                  onClick={() => {
                                    setFiles(files.filter((_, n) => n !== i));
                                    setAnalysis(null);
                                    setAnswers([]);
                                  }}
                                >
                                  <X size={16} />
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                        {!files.length &&
                          Boolean(project?.reference_files.length) && (
                            <p className="hint">
                              В проекте сохранены файлы:{" "}
                              {project?.reference_files
                                .map((f) => f.filename)
                                .join(", ")}
                              .
                            </p>
                          )}
                        <div className="form-footer">
                          <span>
                            <ShieldCheck size={15} />
                            Каркас появится до генерации материалов
                          </span>
                          <button
                            className="button primary"
                            disabled={working || !query.trim()}
                          >
                            {busy === "analyze" ? (
                              <>
                                <Spinner />
                                Анализируем запрос
                              </>
                            ) : (
                              <>
                                <Search size={17} />
                                Проанализировать запрос
                              </>
                            )}
                          </button>
                        </div>
                      </form>
                    </Panel>
                    {analysis && (
                      <Panel className="clarification-panel">
                        <div className="section-heading">
                          <span className="section-icon">
                            <Sparkles size={21} />
                          </span>
                          <div>
                            <h2>
                              {analysis.clarifying_questions.length
                                ? "Уточним несколько деталей"
                                : "Всё готово для каркаса"}
                            </h2>
                            <p>
                              {templates[template || analysis.template_type]}
                              {hours || analysis.extracted_params.total_hours
                                ? ` · ${hours || String(analysis.extracted_params.total_hours)} ч.`
                                : ""}
                            </p>
                          </div>
                        </div>
                        <p className="hint">{analysis.template_reason}</p>
                        {analysis.clarifying_questions.map((q, i) => (
                          <label className="answer-field" key={q}>
                            {q}
                            <input
                              value={answers[i] || ""}
                              disabled={working}
                              onChange={(e) =>
                                setAnswers((a) => {
                                  const next = [...a];
                                  next[i] = e.target.value;
                                  return next;
                                })
                              }
                              placeholder={
                                q.includes("час") ? "Например, 72" : "Ваш ответ"
                              }
                            />
                          </label>
                        ))}
                        <div className="right-actions">
                          <button
                            className="button primary"
                            onClick={buildSkeleton}
                            disabled={
                              working ||
                              !query.trim() ||
                              analysis.clarifying_questions.some(
                                (_, i) => !answers[i]?.trim(),
                              )
                            }
                          >
                            {busy === "skeleton" ? (
                              <>
                                <Spinner />
                                Собираем каркас
                              </>
                            ) : (
                              <>
                                Создать каркас
                                <ArrowRight size={17} />
                              </>
                            )}
                          </button>
                        </div>
                      </Panel>
                    )}
                  </div>
                  <aside className="context-column">
                    <div className="context-top">
                      <BookOpen size={26} />
                      <span>ВАШ ПОМОЩНИК В РАЗРАБОТКЕ ПРОГРАММ</span>
                      <h2>
                        Начните с задачи.
                        <br />
                        Детали уточним вместе.
                      </h2>
                      <p>
                        Можно описать курс свободно или взять один из примеров.
                      </p>
                    </div>
                    <div className="context-body">
                      <strong>Полезно указать в запросе</strong>
                      <ul>
                        <li>
                          <Check size={15} />
                          Тему и цель обучения
                        </li>
                        <li>
                          <Check size={15} />
                          Аудиторию и входной уровень
                        </li>
                        <li>
                          <Check size={15} />
                          Количество часов и формат
                        </li>
                        <li>
                          <Check size={15} />
                          Итоговую аттестацию
                        </li>
                      </ul>
                      <hr />
                      <p>
                        Старая программа, профстандарт или требования к курсу
                        помогут агенту учесть ваш контекст.
                      </p>
                      <span className="quiet-note">
                        <CircleHelp size={16} />
                        Для PDF нужен текстовый слой. Скан потребуется
                        распознать отдельно.
                      </span>
                    </div>
                  </aside>
                </div>
              )}
              {step === 2 && draft && (
                <>
                  <Panel>
                    <div className="section-heading">
                      <span className="section-icon">
                        <ListChecks size={21} />
                      </span>
                      <div>
                        <h2>Проверьте каркас программы</h2>
                        <p>
                          Измените название, цель и часы перед созданием полного
                          комплекта.
                        </p>
                      </div>
                      <Badge>{templates[draft.template_type]}</Badge>
                    </div>
                    <div className="form-grid wide-first">
                      <label>
                        Название программы
                        <input
                          value={draft.title}
                          disabled={working}
                          onChange={(e) =>
                            setDraft({ ...draft, title: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        Общий объём, ак. ч.
                        <input
                          type="number"
                          min="1"
                          step="1"
                          value={draft.total_hours}
                          disabled={working}
                          onChange={(e) =>
                            setDraft({
                              ...draft,
                              total_hours: Number(e.target.value),
                            })
                          }
                        />
                      </label>
                    </div>
                    <label className="block-field">
                      Цель программы
                      <textarea
                        value={draft.goal}
                        disabled={working}
                        onChange={(e) =>
                          setDraft({ ...draft, goal: e.target.value })
                        }
                        rows={2}
                      />
                    </label>
                    <div className="metadata-line">
                      <span>{draft.target_audience}</span>
                      <Badge>{draft.education_form}</Badge>
                    </div>
                  </Panel>
                  <Panel>
                    <div className="section-title-row">
                      <h2>Карта компетенций</h2>
                      <span className="muted">
                        {draft.competencies.length} компетенции
                      </span>
                    </div>
                    <div className="competency-list">
                      {draft.competencies.map((c) => (
                        <details key={c.id}>
                          <summary>
                            <Badge tone="green">{c.id}</Badge>
                            <span>{c.name}</span>
                            <ChevronDown size={16} />
                          </summary>
                          <div className="competency-detail">
                            {c.profstandard_code && (
                              <p>
                                <strong>Профстандарт:</strong>{" "}
                                {c.profstandard_code} · ТФ{" "}
                                {c.labor_function_code}
                              </p>
                            )}
                            {c.needs_verification && (
                              <Badge tone="amber">
                                Требует проверки методистом
                              </Badge>
                            )}
                            <div className="three-columns">
                              {[
                                ["Знания", c.knowledge],
                                ["Умения", c.skills],
                                ["Практический опыт", c.practical_experience],
                              ].map(([title, items]) => (
                                <div key={String(title)}>
                                  <strong>{String(title)}</strong>
                                  <ul>
                                    {(items as string[]).map((item) => (
                                      <li key={item}>{item}</li>
                                    ))}
                                  </ul>
                                </div>
                              ))}
                            </div>
                          </div>
                        </details>
                      ))}
                    </div>
                  </Panel>
                  <Panel className="plan-panel">
                    <div className="section-title-row">
                      <div>
                        <h2>Учебно-тематический план</h2>
                        <p className="hint">
                          Названия тем и часы можно редактировать прямо в
                          таблице.
                        </p>
                      </div>
                      <Badge tone={difference === 0 ? "green" : "red"}>
                        {difference === 0
                          ? "Часы сходятся"
                          : "Есть расхождение"}
                      </Badge>
                    </div>
                    {draft.modules.map((m, mi) => (
                      <div className="module-editor" key={m.id}>
                        <label className="module-title-label">
                          Модуль {m.id}
                          <input
                            aria-label={`Название модуля ${m.id}`}
                            value={m.title}
                            disabled={working}
                            onChange={(e) =>
                              setDraft((current) => {
                                if (!current) return current;
                                const next = copyCourse(current);
                                next.modules[mi].title = e.target.value;
                                return next;
                              })
                            }
                          />
                        </label>
                        <div className="table-scroll">
                          <table className="plan-table">
                            <thead>
                              <tr>
                                <th>№</th>
                                <th>Тема / компетенции</th>
                                {["ЛК", "ПР", "ЛБ", "СРС"].map((name) => (
                                  <th key={name}>{name}</th>
                                ))}
                                <th>Всего</th>
                                <th>Контроль</th>
                              </tr>
                            </thead>
                            <tbody>
                              {m.topics.map((t, ti) => (
                                <tr key={t.id}>
                                  <td>{t.id}</td>
                                  <td>
                                    <input
                                      aria-label={`Название темы ${t.id}`}
                                      value={t.title}
                                      disabled={working}
                                      onChange={(e) =>
                                        updateTopic(mi, ti, {
                                          title: e.target.value,
                                        })
                                      }
                                    />
                                    <small>
                                      {t.linked_competencies.join(" · ")}
                                    </small>
                                  </td>
                                  {hourKeys.map((key, ki) => (
                                    <td key={key}>
                                      <input
                                        aria-label={`${["Лекции", "Практика", "Лабораторные", "Самостоятельная работа"][ki]} темы ${t.id}`}
                                        type="number"
                                        min="0"
                                        step="1"
                                        value={t[key]}
                                        disabled={working}
                                        onChange={(e) =>
                                          updateTopic(mi, ti, {
                                            [key]: Number(e.target.value),
                                          })
                                        }
                                      />
                                    </td>
                                  ))}
                                  <td className="row-total">{topicHours(t)}</td>
                                  <td className="control-cell">
                                    {t.control_form}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        <div className="module-total">
                          Итого по модулю{" "}
                          <strong>
                            {m.topics.reduce((n, t) => n + topicHours(t), 0)} ч.
                          </strong>
                        </div>
                      </div>
                    ))}
                    <div className="attestation-row">
                      <div>
                        <strong>Итоговая аттестация</strong>
                        <span>{draft.ia_form}</span>
                      </div>
                      <label>
                        Часы ИА
                        <input
                          aria-label="Часы итоговой аттестации"
                          type="number"
                          min="0"
                          step="1"
                          value={draft.ia_hours}
                          disabled={working}
                          onChange={(e) =>
                            setDraft({
                              ...draft,
                              ia_hours: Number(e.target.value),
                            })
                          }
                        />
                      </label>
                    </div>
                    <div
                      className={`hours-summary ${difference ? "mismatch" : ""}`}
                      aria-live="polite"
                    >
                      <div>
                        <span>Общий объём</span>
                        <strong>
                          {draft.total_hours} <small>ч.</small>
                        </strong>
                      </div>
                      <div>
                        <span>Темы и аттестация</span>
                        <strong>
                          {sum} <small>ч.</small>
                        </strong>
                      </div>
                      <div>
                        <span>Проверка баланса</span>
                        <strong>
                          {difference === 0 ? (
                            <>
                              <Check size={21} />
                              Всё сходится
                            </>
                          ) : difference > 0 ? (
                            `Не хватает ${difference} ч.`
                          ) : (
                            `Лишних ${-difference} ч.`
                          )}
                        </strong>
                      </div>
                    </div>
                    {difference !== 0 && (
                      <p className="hint error-text">
                        Распределите часы по темам или измените общий объём,
                        чтобы сумма совпала перед утверждением.
                      </p>
                    )}
                  </Panel>
                  <div className="approval-footer">
                    <p>
                      <ShieldCheck size={21} />
                      <span>
                        Утверждая каркас, вы подтверждаете структуру и часы.
                        {completed && (
                          <small>
                            Новый запуск заменит предыдущие материалы этой
                            программы.
                          </small>
                        )}
                      </span>
                    </p>
                    <button
                      className="button primary"
                      disabled={working || !validDraft}
                      onClick={approveAndGenerate}
                    >
                      {busy === "approve" ? (
                        <>
                          <Spinner />
                          Утверждаем каркас
                        </>
                      ) : (
                        <>
                          <CheckCheck size={18} />
                          Утвердить каркас и создать материалы
                        </>
                      )}
                    </button>
                  </div>
                </>
              )}
              {step === 3 && course && (
                <>
                  {working && (busy === "generate" || course.busy) ? (
                    <Panel className="generation-state">
                      <span className="generation-symbol">
                        <Sparkles size={30} />
                      </span>
                      <Badge tone="green">Каркас утверждён</Badge>
                      <h2>Собираем материалы программы</h2>
                      <p>
                        Агент готовит тесты, практикумы, слайды и источники по
                        модулям.
                      </p>
                      <div className="indeterminate-progress">
                        <span />
                      </div>
                      <span className="muted">
                        <Clock3 size={15} />
                        Ожидание: {Math.floor(elapsed / 60)} мин {elapsed % 60}{" "}
                        с
                      </span>
                      <p className="hint">
                        Результат сохраняется на сервере. После обновления
                        страницы проект можно открыть снова.
                      </p>
                    </Panel>
                  ) : !completed ? (
                    <Panel className="empty-state">
                      <FileCheck2 size={34} />
                      <h2>Каркас утверждён</h2>
                      <p>
                        Полный комплект ещё не сформирован. Можно запустить
                        генерацию повторно.
                      </p>
                      <button
                        className="button primary"
                        disabled={working}
                        onClick={retryGenerate}
                      >
                        <Sparkles size={17} />
                        Создать материалы
                      </button>
                    </Panel>
                  ) : (
                    <>
                      <div className="result-heading">
                        <div>
                          <Badge tone="green">
                            <Check size={13} />
                            Комплект сформирован
                          </Badge>
                          <h2>{course.title}</h2>
                          <p>
                            {course.total_hours} академических часов{" "}
                            <span>·</span> {course.modules.length} модуля{" "}
                            <span>·</span>{" "}
                            {course.modules.reduce(
                              (n, m) => n + m.topics.length,
                              0,
                            )}{" "}
                            тем
                          </p>
                        </div>
                        <button
                          className="button secondary"
                          disabled={working}
                          onClick={() => setStep(2)}
                        >
                          <ArrowLeft size={16} />К каркасу
                        </button>
                      </div>
                      {course.execution_mode === "demo" && (
                        <div className="demo-note">
                          <Sparkles size={18} />
                          <span>
                            <strong>Демонстрационные материалы.</strong>{" "}
                            Используются примеры ML-навыков. Реальные модели не
                            вызывались; содержание и источники требуют проверки.
                          </span>
                        </div>
                      )}
                      <div className="materials-layout">
                        <div className="materials-main">
                          <div
                            className="tabs"
                            role="tablist"
                            aria-label="Материалы программы"
                          >
                            {(
                              [
                                {
                                  id: "program",
                                  title: "Программа",
                                  count: course.modules.length,
                                },
                                {
                                  id: "tests",
                                  title: "Тесты",
                                  count: course.tests.length,
                                },
                                {
                                  id: "seminars",
                                  title: "Семинары",
                                  count: course.seminars.length,
                                },
                                {
                                  id: "slides",
                                  title: "Слайды",
                                  count: course.lecture_slides.length,
                                },
                                {
                                  id: "literature",
                                  title: "Литература",
                                  count: course.literature.length,
                                },
                              ] as const
                            ).map((t) => (
                              <button
                                key={t.id}
                                role="tab"
                                id={`tab-${t.id}`}
                                aria-controls="materials-content"
                                aria-selected={tab === t.id}
                                onClick={() => setTab(t.id)}
                              >
                                {t.title}
                                <span>{t.count}</span>
                              </button>
                            ))}
                          </div>
                          <div
                            id="materials-content"
                            role="tabpanel"
                            aria-labelledby={`tab-${tab}`}
                            className="materials-content"
                          >
                            {tab === "program" &&
                              course.modules.map((m) => (
                                <div className="module-materials" key={m.id}>
                                  <div className="module-heading">
                                    <span className="section-icon">
                                      <BookOpen size={20} />
                                    </span>
                                    <div>
                                      <h3>{m.title}</h3>
                                      <span>
                                        {m.total_hours} ч. · {m.topics.length}{" "}
                                        темы
                                      </span>
                                    </div>
                                  </div>
                                  {m.topics.map((t) => (
                                    <Panel className="topic-card" key={t.id}>
                                      <div className="card-title-row">
                                        <Badge>{t.id}</Badge>
                                        <h4>{t.title}</h4>
                                        <button
                                          className="text-button regenerate-button"
                                          disabled={working}
                                          onClick={() =>
                                            setRegenerate({
                                              type: "topic",
                                              id: t.id,
                                              title: t.title,
                                            })
                                          }
                                          aria-label={`Пересобрать тему ${t.id}`}
                                        >
                                          <Sparkles size={14} />
                                          Пересобрать
                                        </button>
                                      </div>
                                      <div className="topic-meta">
                                        {t.total_hours} ч. <span>·</span>{" "}
                                        {t.linked_competencies.join(", ")}{" "}
                                        <span>·</span> {t.control_form}
                                      </div>
                                      <ul>
                                        {t.content_bullets.map((b, i) => (
                                          <li key={i}>{b}</li>
                                        ))}
                                      </ul>
                                      {t.practice_description && (
                                        <div className="practice-description">
                                          <strong>
                                            Практика и самостоятельная работа
                                          </strong>
                                          <p>{t.practice_description}</p>
                                        </div>
                                      )}
                                    </Panel>
                                  ))}
                                </div>
                              ))}
                            {tab === "tests" && (
                              <>
                                <p className="hint">
                                  Ответы показаны с ключами для проверки
                                  методистом.
                                </p>
                                {course.tests.map((q, i) => (
                                  <Panel className="question-card" key={q.id}>
                                    <div className="card-title-row">
                                      <Badge>
                                        {String(i + 1).padStart(2, "0")}
                                      </Badge>
                                      <span className="muted">
                                        Тема {q.linked_topic_id} ·{" "}
                                        {q.linked_competency_id}
                                      </span>
                                      <button
                                        className="text-button regenerate-button"
                                        disabled={working}
                                        onClick={() =>
                                          setRegenerate({
                                            type: "test",
                                            id: q.id,
                                            title: q.question,
                                          })
                                        }
                                        aria-label={`Пересобрать вопрос ${q.id}`}
                                      >
                                        <Sparkles size={14} />
                                        Пересобрать
                                      </button>
                                    </div>
                                    <h4>{q.question}</h4>
                                    <ol className="answer-options">
                                      {q.options.map((o, oi) => (
                                        <li
                                          key={oi}
                                          className={
                                            o === q.correct_answer
                                              ? "correct"
                                              : ""
                                          }
                                        >
                                          <span>
                                            {String.fromCharCode(65 + oi)}
                                          </span>
                                          {o}
                                          {o === q.correct_answer && (
                                            <Check
                                              size={16}
                                              role="img"
                                              aria-label="Верный ответ"
                                              aria-hidden={false}
                                            />
                                          )}
                                        </li>
                                      ))}
                                    </ol>
                                  </Panel>
                                ))}
                              </>
                            )}
                            {tab === "seminars" &&
                              course.seminars.map((s) => (
                                <Panel className="seminar-card" key={s.id}>
                                  <Badge>Тема {s.linked_topic_id}</Badge>
                                  <h3>{s.title}</h3>
                                  <p>{s.scenario}</p>
                                  <strong>Что сдаёт слушатель</strong>
                                  <ul>
                                    {s.deliverables.map((v, i) => (
                                      <li key={i}>{v}</li>
                                    ))}
                                  </ul>
                                  <div className="practice-description">
                                    <strong>Критерии оценки</strong>
                                    <ul>
                                      {s.evaluation_criteria.map((v, i) => (
                                        <li key={i}>{v}</li>
                                      ))}
                                    </ul>
                                  </div>
                                </Panel>
                              ))}
                            {tab === "slides" && (
                              <>
                                <p className="hint">
                                  Структура слайдов и заметки спикера. Готовую
                                  презентацию можно скачать в PPTX.
                                </p>
                                {course.lecture_slides.map((s) => (
                                  <Panel
                                    className="slide-card"
                                    key={s.slide_number}
                                  >
                                    <div className="slide-number">
                                      {String(s.slide_number).padStart(2, "0")}
                                      <small>СЛАЙД</small>
                                    </div>
                                    <div>
                                      <Badge>Модуль {s.module_id || "—"}</Badge>
                                      <h3>{s.title}</h3>
                                      <ul>
                                        {s.bullets.map((b, i) => (
                                          <li key={i}>{b}</li>
                                        ))}
                                      </ul>
                                      <details>
                                        <summary>Заметки спикера</summary>
                                        <p>{s.speaker_notes}</p>
                                      </details>
                                    </div>
                                  </Panel>
                                ))}
                              </>
                            )}
                            {tab === "literature" && (
                              <>
                                <div className="demo-note">
                                  <CircleHelp size={18} />
                                  <span>
                                    Пометка проверки означает, что существование
                                    и актуальность источника должен подтвердить
                                    методист.
                                  </span>
                                </div>
                                {course.literature.map((l, i) => (
                                  <Panel className="source-card" key={i}>
                                    <div>
                                      <Badge>
                                        {(
                                          {
                                            normative: "Нормативный документ",
                                            main: "Основная литература",
                                            additional:
                                              "Дополнительная литература",
                                            internet: "Интернет-ресурс",
                                            software: "Программное обеспечение",
                                          } as Record<string, string>
                                        )[l.category] || l.category}
                                      </Badge>
                                      <Badge
                                        tone={
                                          l.needs_verification
                                            ? "amber"
                                            : "green"
                                        }
                                      >
                                        {l.needs_verification
                                          ? "Требует проверки"
                                          : "Подтверждено в данных"}
                                      </Badge>
                                    </div>
                                    <p>{l.reference}</p>
                                    {safeUrl(l.url) && (
                                      <a
                                        href={safeUrl(l.url)}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                      >
                                        Открыть источник
                                        <ArrowRight size={13} />
                                      </a>
                                    )}
                                  </Panel>
                                ))}
                              </>
                            )}
                          </div>
                        </div>
                        <aside className="results-sidebar">
                          <Validation course={course} />
                          <Panel className="export-panel">
                            <div className="section-title-row">
                              <h3>Скачать комплект</h3>
                              <ArrowDownToLine size={18} />
                            </div>
                            <p className="hint">
                              Файлы из текущей версии программы.
                            </p>
                            {[
                              {
                                format: "docx",
                                title: "Программа Word",
                                detail: "DOCX · шаблон АЦР",
                              },
                              {
                                format: "pptx",
                                title: "Слайды лекций",
                                detail: "PPTX · заметки спикера",
                              },
                              {
                                format: "gift",
                                title: "Тесты для Moodle",
                                detail: "GIFT · вопросы и ключи",
                              },
                              {
                                format: "json",
                                title: "Все данные программы",
                                detail: "JSON · полный комплект",
                              },
                              {
                                format: "csv",
                                title: "Таблица тестов",
                                detail: "CSV · для обработки",
                              },
                            ].map((f) => (
                              <button
                                key={f.format}
                                className="export-button"
                                onClick={() => download(f.format)}
                                disabled={working}
                              >
                                <span className={`format-icon ${f.format}`}>
                                  {f.format.toUpperCase().slice(0, 4)}
                                </span>
                                <span>
                                  <strong>{f.title}</strong>
                                  <small>{f.detail}</small>
                                </span>
                                {busy === `download-${f.format}` ? (
                                  <Spinner />
                                ) : (
                                  <ArrowDownToLine size={16} />
                                )}
                              </button>
                            ))}
                          </Panel>
                        </aside>
                      </div>
                    </>
                  )}
                </>
              )}
            </>
          )}
          <footer className="workspace-footer">
            <span>
              EduAgent АЦР <span>·</span> Рабочее пространство методиста
            </span>
            {project && (
              <span className="project-id">ID: {project.project_id}</span>
            )}
          </footer>
        </main>
      </div>
      <dialog
        ref={modal}
        className="regenerate-dialog"
        aria-labelledby="regenerate-title"
        onCancel={(e) => {
          if (busy === "regenerate") e.preventDefault();
          else setRegenerate(null);
        }}
        onClose={() => {
          if (!busy) setRegenerate(null);
        }}
      >
        <form onSubmit={regeneratePart}>
          <div className="section-heading">
            <span className="section-icon">
              <Sparkles size={22} />
            </span>
            <div>
              <h2 id="regenerate-title">Точечная пересборка</h2>
              <p>
                {regenerate?.type === "topic"
                  ? `Тема ${regenerate.id}`
                  : `Вопрос ${regenerate?.id}`}
              </p>
            </div>
            <button
              type="button"
              className="icon-button"
              disabled={Boolean(busy)}
              aria-label="Закрыть пересборку"
              onClick={() => setRegenerate(null)}
            >
              <X size={20} />
            </button>
          </div>
          <p className="dialog-subject">{regenerate?.title}</p>
          <label className="block-field">
            Что нужно изменить?
            <textarea
              autoFocus
              rows={4}
              required
              maxLength={10000}
              value={instruction}
              disabled={Boolean(busy)}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="Например: добавь практический пример обработки пропущенных значений в банковских данных"
            />
          </label>
          <p className="hint">
            Часы и связи компетенций сохраняются. При изменении темы обновятся
            её задания и слайды затронутого модуля.
          </p>
          {error && regenerate && (
            <p className="hint error-text" role="alert">
              {error.message}
            </p>
          )}
          <div className="right-actions">
            <button
              type="button"
              className="button secondary"
              disabled={Boolean(busy)}
              onClick={() => setRegenerate(null)}
            >
              Отмена
            </button>
            <button
              className="button primary"
              disabled={Boolean(busy) || !instruction.trim()}
            >
              {busy === "regenerate" ? (
                <>
                  <Spinner />
                  Пересобираем
                </>
              ) : (
                <>
                  <Sparkles size={16} />
                  Применить изменение
                </>
              )}
            </button>
          </div>
        </form>
      </dialog>
      <dialog
        ref={confirmationModal}
        className="regenerate-dialog confirmation-dialog"
        aria-labelledby="confirmation-title"
        onCancel={(event) => {
          event.preventDefault();
          finishConfirmation(false);
        }}
        onClose={() => finishConfirmation(false)}
      >
        <h2 id="confirmation-title">Подтвердите действие</h2>
        <p className="confirmation-message">{confirmation}</p>
        <div className="right-actions">
          <button
            className="button secondary"
            onClick={() => finishConfirmation(false)}
          >
            Отмена
          </button>
          <button
            className="button primary"
            onClick={() => finishConfirmation(true)}
          >
            Продолжить
          </button>
        </div>
      </dialog>
    </div>
  );
}

function Validation({ course }: { course: Course }) {
  const report = course.validation_report;
  const metrics = report?.metrics || {};
  const rows = [
    {
      name: "Арифметика часов",
      detail: `${studyHours(course)} ч. тем + ${course.ia_hours} ч. ИА = ${course.total_hours} ч.`,
      okay: report?.hours_math_ok,
    },
    {
      name: "Покрытие компетенций",
      detail: report?.competency_coverage_ok
        ? `100% · ${course.competencies.length} из ${course.competencies.length} связаны с темами и заданиями`
        : "Проверьте связи с темами и оценочными заданиями",
      okay: report?.competency_coverage_ok,
    },
    {
      name: "Полнота структуры",
      detail: "Обязательные поля программы",
      okay: report?.completeness_ok,
    },
  ];
  return (
    <>
      <Panel className="validation-panel">
        <div className="section-title-row">
          <h3>Автопроверка</h3>
          <ShieldCheck size={19} />
        </div>
        <p className="hint">Структура, арифметика и связи данных.</p>
        {rows.map((row) => (
          <div className="validation-row" key={row.name}>
            <span className={`check-icon ${row.okay ? "pass" : "fail"}`}>
              {row.okay ? <Check size={14} /> : <CircleHelp size={14} />}
            </span>
            <div>
              <strong>{row.name}</strong>
              <small>{row.detail}</small>
            </div>
          </div>
        ))}
        <div className="validation-row">
          <span
            className={`check-icon ${report?.unverified_sources_count ? "warning" : "pass"}`}
          >
            {report?.unverified_sources_count ? (
              <CircleHelp size={14} />
            ) : (
              <Check size={14} />
            )}
          </span>
          <div>
            <strong>Источники и профстандарты</strong>
            <small>
              {report?.unverified_sources_count
                ? `${report.unverified_sources_count} требуют проверки методистом`
                : "Нет пометок непроверенных источников"}
            </small>
          </div>
        </div>
        <details className="report-details">
          <summary>Подробный отчёт</summary>
          {report?.details.map((d, i) => (
            <p key={i}>{d}</p>
          ))}
          {report?.errors.map((d, i) => (
            <p key={i} className="error-text">
              {d}
            </p>
          ))}
        </details>
      </Panel>
      <Panel className="metrics-panel">
        <h3>Метрики генерации</h3>
        <div>
          <span>Использовано токенов</span>
          <strong>
            {typeof metrics.total_tokens === "number"
              ? metrics.total_tokens.toLocaleString("ru-RU")
              : "Не измерено"}
          </strong>
        </div>
        <div>
          <span>Стоимость</span>
          <strong>
            {typeof metrics.estimated_cost_rub === "number"
              ? `${metrics.estimated_cost_rub} ₽`
              : "Не рассчитана"}
          </strong>
        </div>
        <div>
          <span>Экономия времени</span>
          <strong>
            {typeof metrics.saved_methodist_hours === "number"
              ? `${metrics.saved_methodist_hours} ч.`
              : "Не измерена"}
          </strong>
        </div>
        {course.execution_mode === "demo" && (
          <p className="hint">В деморежиме обращения к модели отсутствуют.</p>
        )}
      </Panel>
    </>
  );
}
