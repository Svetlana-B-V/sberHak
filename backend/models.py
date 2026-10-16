from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from ml.schemas import ClarifyResponse, CourseProgram


ProjectId = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]


class ReferenceFile(BaseModel):
    filename: str
    kind: Literal["docx", "pdf"]
    sha256: str
    text: str
    warnings: list[str] = Field(default_factory=list)


class ProjectRecord(BaseModel):
    project_id: ProjectId
    query: str
    revision: int = 0
    execution_mode: Literal["demo", "cloud"]
    references: list[ReferenceFile] = Field(default_factory=list)
    analysis: ClarifyResponse | None = None
    course: CourseProgram | None = None
    busy: str | None = None
    warnings: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: dict = Field(default_factory=dict)
    slide_modules: dict[str, str] = Field(default_factory=dict)
    module_literature: dict[str, list[dict]] = Field(default_factory=dict)

    def reference_text(self) -> str:
        return "\n\n".join(f"Файл {item.filename}:\n{item.text}" for item in self.references)

    def public(self) -> dict:
        body = self.course.model_dump(mode="json") if self.course else {}
        body.update(
            project_id=self.project_id,
            revision=self.revision,
            execution_mode=self.execution_mode,
            busy=self.busy,
            backend_warnings=self.warnings,
            reference_files=[item.model_dump(exclude={"text"}) for item in self.references],
        )
        if self.course is None:
            body["analysis"] = self.analysis.model_dump() if self.analysis else None
        elif self.slide_modules:
            for slide in body.get("lecture_slides", []):
                slide["module_id"] = self.slide_modules.get(str(slide["slide_number"]))
        return body


class SkeletonRequest(BaseModel):
    query: str = Field(min_length=1, max_length=30000)
    project_id: ProjectId | None = None
    template_type: Literal["dpp_pk", "doop"] | None = None
    total_hours: int | None = Field(default=None, ge=1, strict=True)
    clarifications: str = Field(default="", max_length=30000)


class RegeneratePartRequest(BaseModel):
    element_type: Literal["topic", "test"]
    element_id: str = Field(min_length=1, max_length=128)
    instruction: str = Field(min_length=1, max_length=10000)
    revision: int | None = Field(default=None, ge=1)


class EvaluateRequest(SkeletonRequest):
    query: str = Field(default="", max_length=30000)
    action: Literal["analyze", "skeleton", "approve", "generate", "regenerate"] = "skeleton"
    approved: bool = False
    course: dict | None = None
    element_type: Literal["topic", "test"] | None = None
    element_id: str | None = None
    instruction: str = ""
