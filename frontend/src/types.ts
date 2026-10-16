export type Template = "dpp_pk" | "doop";
export interface Analysis {
  is_complete: boolean;
  template_type: Template;
  template_reason: string;
  extracted_params: Record<string, unknown>;
  clarifying_questions: string[];
}
export interface ReferenceFile {
  filename: string;
  kind: string;
  warnings: string[];
  sha256: string;
}
export interface Competency {
  id: string;
  activity_type: string;
  name: string;
  profstandard_code: string;
  labor_function_code: string;
  needs_verification: boolean;
  knowledge: string[];
  skills: string[];
  practical_experience: string[];
}
export interface Topic {
  id: string;
  title: string;
  total_hours: number;
  lecture_hours: number;
  practice_hours: number;
  lab_hours: number;
  srs_hours: number;
  control_form: string;
  linked_competencies: string[];
  content_bullets: string[];
  practice_description: string;
}
export interface Module {
  id: string;
  title: string;
  total_hours: number;
  lecture_hours: number;
  practice_hours: number;
  lab_hours: number;
  srs_hours: number;
  attestation_form: string;
  topics: Topic[];
}
export interface Question {
  id: string;
  question: string;
  options: string[];
  correct_answer: string;
  linked_topic_id: string;
  linked_competency_id: string;
}
export interface Seminar {
  id: string;
  title: string;
  linked_topic_id: string;
  scenario: string;
  deliverables: string[];
  evaluation_criteria: string[];
}
export interface Slide {
  slide_number: number;
  title: string;
  bullets: string[];
  speaker_notes: string;
  module_id?: string;
}
export interface Literature {
  category: string;
  reference: string;
  url: string | null;
  needs_verification: boolean;
}
export interface Report {
  is_valid: boolean;
  hours_math_ok: boolean;
  competency_coverage_ok: boolean;
  completeness_ok: boolean;
  unverified_sources_count: number;
  details: string[];
  errors: string[];
  metrics: Record<string, number | string | null>;
}
export interface Course {
  project_id: string;
  revision: number;
  status: "skeleton_ready" | "approved" | "completed";
  execution_mode: "demo" | "cloud";
  busy: string | null;
  backend_warnings: string[];
  reference_files: ReferenceFile[];
  template_type: Template;
  title: string;
  annotation: string;
  goal: string;
  tasks: string[];
  target_audience: string;
  education_form: string;
  total_hours: number;
  ia_hours: number;
  ia_form: string;
  duration_days: number;
  issued_document: string;
  competencies: Competency[];
  modules: Module[];
  tests: Question[];
  seminars: Seminar[];
  lecture_slides: Slide[];
  literature: Literature[];
  validation_report: Report | null;
}
export interface Project {
  project_id: string;
  revision: number;
  execution_mode: "demo" | "cloud";
  reference_files: ReferenceFile[];
  backend_warnings: string[];
  busy: string | null;
  analysis?: Analysis;
  status?: Course["status"];
}
export type AnalyzeResult = Analysis &
  Pick<
    Project,
    "project_id" | "revision" | "execution_mode" | "backend_warnings"
  >;
export const hourKeys = [
  "lecture_hours",
  "practice_hours",
  "lab_hours",
  "srs_hours",
] as const;
export const topicHours = (topic: Topic) =>
  hourKeys.reduce((sum, key) => sum + topic[key], 0);
export const studyHours = (course: Course) =>
  course.modules.reduce(
    (sum, m) => sum + m.topics.reduce((n, t) => n + topicHours(t), 0),
    0,
  );
export const isCourse = (p: Project | null): p is Course =>
  Boolean(p?.status && "modules" in p);
