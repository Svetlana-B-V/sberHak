import type { AnalyzeResult, Course, Project } from "./types";

const base = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");
export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public status: number,
    public context: Record<string, unknown> = {},
  ) {
    super(message);
  }
}
async function checked(response: Response) {
  if (response.ok) return response;
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  const message = Array.isArray(detail)
    ? detail
        .map(
          (item: { loc: string[]; msg: string }) =>
            `${item.loc.slice(1).join(".")}: ${item.msg}`,
        )
        .join("; ")
    : detail?.message ||
      (typeof detail === "string"
        ? detail
        : `Сервис вернул ошибку ${response.status}`);
  throw new ApiError(
    message,
    detail?.code || "request_failed",
    response.status,
    detail || {},
  );
}
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  try {
    return (await (
      await checked(
        await fetch(base + path, {
          ...init,
          signal: AbortSignal.timeout(1260000),
        }),
      )
    ).json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "TimeoutError")
      throw new ApiError(
        "Время ожидания истекло. Обновите проект, чтобы проверить результат.",
        "client_timeout",
        0,
      );
    throw new ApiError(
      "Не удалось связаться с сервером. Проверьте, что бэкенд запущен.",
      "network_error",
      0,
    );
  }
}
const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
});
export const api = {
  health: () =>
    fetch(base + "/api/health", { signal: AbortSignal.timeout(5000) }).then(
      checked,
    ),
  get: (id: string) =>
    request<Project | Course>(`/api/projects/${encodeURIComponent(id)}`),
  analyze: (query: string, files: File[], id?: string) => {
    const form = new FormData();
    form.set("query", query);
    for (const file of files) form.append("files", file);
    if (id) form.set("project_id", id);
    return request<AnalyzeResult>("/api/projects/analyze", {
      method: "POST",
      body: form,
    });
  },
  skeleton: (body: unknown) =>
    request<Course>("/api/projects/skeleton", json("POST", body)),
  approve: (course: Course) =>
    request<Course>(
      `/api/projects/${course.project_id}/skeleton`,
      json("PUT", course),
    ),
  generate: (id: string) =>
    request<Course>(`/api/projects/${id}/generate-content`, json("POST")),
  regenerate: (id: string, body: unknown) =>
    request<Course>(`/api/projects/${id}/regenerate-part`, json("POST", body)),
  download: async (course: Project, format: string) => {
    let response: Response;
    try {
      response = await checked(
        await fetch(
          `${base}/api/projects/${course.project_id}/export/${format}?revision=${course.revision}`,
          { signal: AbortSignal.timeout(120000) },
        ),
      );
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(
        "Не удалось скачать файл. Проверьте соединение с сервером.",
        "download_failed",
        0,
      );
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `Course_${course.project_id}.${format}`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  },
};
