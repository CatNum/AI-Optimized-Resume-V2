from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from career_os.config import settings
from career_os.platform.market_research.errors import (
    MarketResearchError,
    MarketResearchErrorCode,
)
from career_os.platform.market_research.models import (
    CollectedJob,
    DirectionResult,
    DirectionResultRef,
    MarketResearchResult,
    ReferencedDirectionResult,
    ResearchSnapshot,
    ResearchStage,
    ResearchStatus,
    ResultRef,
    ScreenshotManifest,
    ScreenshotManifestItem,
    SkillTaxonomy,
)


_store_lock = threading.RLock()
_RESEARCH_ID_PATTERN = re.compile(r"^research_[0-9a-f]+$")
_DIRECTION_RUN_ID_PATTERN = re.compile(r"^direction_[0-9a-f]+$")
_PLAN_ID_PATTERN = re.compile(r"^plan_[0-9a-f]+$")
_VERSION_DIR_PATTERN = re.compile(r"^v([1-9][0-9]*)$")
_ACTIVE_STATUSES = {
    ResearchStatus.QUEUED,
    ResearchStatus.RUNNING,
    ResearchStatus.WAITING_USER,
    ResearchStatus.CANCELLING,
}
_SCREENSHOT_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class MarketResearchStore:
    """MarketResearchStore（市场调研存储器）隔离运行数据并原子发布不可变正式版本。"""

    def __init__(self, root: Path | None = None) -> None:
        """初始化市场数据根目录；root 用于显式指定当前 demo 的隔离目录。"""
        self.root = (root or Path(settings.data_dir) / "market_research").resolve()
        self.index_path = self.root / "index.json"
        self.plans_dir = self.root / "plans"
        self.runs_dir = self.root / "runs"
        self.temp_dir = self.root / "temp"
        self.staging_dir = self.root / "staging"
        self.results_dir = self.root / "results"
        self.events_dir = self.root / "events"
        self.browser_profile_dir = self.root / "browser_profile"
        self.runtime_dir = self.root / "runtime"
        self._initialize_layout()

    def write_status(self, snapshot: ResearchSnapshot) -> None:
        """原子写入 status.json（状态快照），供状态 API 和进程恢复读取。"""
        parsed = ResearchSnapshot.model_validate(snapshot)
        path = self.run_status_path(parsed.research_id)
        with _store_lock:
            self._write_json_atomic(path, parsed.model_dump(mode="json"))

    def read_status(self, research_id: str) -> ResearchSnapshot | None:
        """读取 research_id（调研编号）对应的状态快照；不存在时返回空值。"""
        path = self.run_status_path(research_id)
        if not path.exists():
            return None
        return ResearchSnapshot.model_validate(self._read_json(path))

    def append_event(self, research_id: str, event: dict[str, Any]) -> None:
        """追加一条不含页面原文的脱敏生命周期事件并同步到磁盘。"""
        self._validate_research_id(research_id)
        allowed_keys = {
            "event",
            "status",
            "stage",
            "direction_run_id",
            "direction_name",
            "keyword",
            "city",
            "candidate_count",
            "valid_job_count",
            "semantic_analyzed_count",
            "elapsed_seconds",
            "error_code",
            "retry_count",
            "result_version",
            "published",
            "timestamp",
        }
        safe_event = {key: value for key, value in event.items() if key in allowed_keys}
        safe_event.setdefault("timestamp", datetime.now(UTC).isoformat())
        path = self.events_path(research_id)
        with _store_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(safe_event, ensure_ascii=False, sort_keys=True))
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            self._fsync_directory(path.parent)

    def publish_result(
        self,
        research_id: str,
        result: MarketResearchResult,
        jobs: list[CollectedJob],
        skill_taxonomy: SkillTaxonomy,
    ) -> ResultRef:
        """验证 staging 版本集合后原子发布不可变版本；失败时不更新 latest 指针。"""
        self._validate_research_id(research_id)
        parsed_result = MarketResearchResult.model_validate(result)
        parsed_jobs = [CollectedJob.model_validate(job) for job in jobs]
        parsed_skills = SkillTaxonomy.model_validate(skill_taxonomy)
        if parsed_result.research_id != research_id:
            raise ValueError("result research_id must match publish research_id")

        last_error: Exception | None = None
        attempt_count = settings.market_research.storage_retry_times + 1
        with _store_lock:
            for _attempt in range(attempt_count):
                try:
                    return self._publish_once(
                        research_id,
                        parsed_result,
                        parsed_jobs,
                        parsed_skills,
                    )
                except Exception as error:
                    last_error = error
            raise MarketResearchError(
                MarketResearchErrorCode.STORAGE_FAILED,
                stage=ResearchStage.PERSISTING.value,
                message=f"formal result publication failed: {type(last_error).__name__}",
            ) from last_error

    def read_latest_ref(self, research_id: str) -> ResultRef | None:
        """读取 research_id（调研编号）当前最新正式版本引用。"""
        path = self.latest_path(research_id)
        if not path.exists():
            return None
        return ResultRef.model_validate(self._read_json(path))

    def read_result(
        self,
        research_id: str,
        result_version: int | None = None,
    ) -> MarketResearchResult:
        """只通过 latest 或明确版本读取正式结果，绝不读取 temp 或 staging。"""
        version = result_version
        if version is None:
            latest = self.read_latest_ref(research_id)
            if latest is None:
                raise FileNotFoundError(research_id)
            version = latest.result_version
        path = self.result_version_dir(research_id, version) / "result.json"
        return MarketResearchResult.model_validate(self._read_json(path))

    def read_jobs(self, research_id: str, result_version: int) -> list[CollectedJob]:
        """读取明确正式版本中的结构化岗位列表，不返回任何原始 JD。"""
        path = self.result_version_dir(research_id, result_version) / "jobs.json"
        payload = self._read_json(path)
        return [CollectedJob.model_validate(item) for item in payload]

    def read_skill_taxonomy(
        self,
        research_id: str,
        result_version: int,
    ) -> SkillTaxonomy:
        """读取明确正式版本中的冻结技能词表和确定性计数。"""
        path = self.result_version_dir(research_id, result_version) / "skills.json"
        return SkillTaxonomy.model_validate(self._read_json(path))

    def read_screenshot_manifest(
        self,
        research_id: str,
        result_version: int | None = None,
    ) -> ScreenshotManifest:
        """通过正式版本读取 10% 页面抽样截图清单，不暴露任意本地路径。"""
        version = result_version
        if version is None:
            latest = self.read_latest_ref(research_id)
            if latest is None:
                raise FileNotFoundError(research_id)
            version = latest.result_version
        path = self.result_version_dir(research_id, version) / "screenshots_manifest.json"
        manifest = ScreenshotManifest.model_validate(self._read_json(path))
        self._verify_manifest_files(path.parent, manifest)
        return manifest

    def next_result_version(self, research_id: str) -> int:
        """根据已发布 latest 引用返回下一个版本；没有正式结果时固定返回一。"""
        latest = self.read_latest_ref(research_id)
        return 1 if latest is None else latest.result_version + 1

    def build_direction_reference(
        self,
        research_id: str,
        result_version: int,
        direction_key: str,
    ) -> ReferencedDirectionResult:
        """从正式旧版本构造单方向不可变引用，供方向重试的新版本合并。"""
        result = self.read_result(research_id, result_version)
        for direction in result.successful_directions:
            resolved = self._resolve_direction_entry(direction)
            if resolved.direction_key != direction_key:
                continue
            return ReferencedDirectionResult(
                direction_name=resolved.direction_name,
                direction_key=resolved.direction_key,
                researched_at=resolved.researched_at,
                expires_at=resolved.expires_at,
                direction_result_ref=DirectionResultRef(
                    research_id=research_id,
                    result_version=result_version,
                    direction_key=resolved.direction_key,
                    direction_run_id=resolved.direction_run_id,
                ),
            )
        raise KeyError(direction_key)

    def cleanup_direction_temp(
        self,
        research_id: str,
        direction_run_id: str,
    ) -> None:
        """删除一个失败方向的临时数据和截图，不影响其他方向或正式版本。"""
        path = self.direction_temp_dir(research_id, direction_run_id)
        with _store_lock:
            shutil.rmtree(path, ignore_errors=True)

    def cleanup_cancelled_run(self, research_id: str) -> None:
        """删除整次取消的 temp 和 staging，仅保留一条最小 cancelled 事件。"""
        self._validate_research_id(research_id)
        with _store_lock:
            shutil.rmtree(self.temp_research_dir(research_id), ignore_errors=True)
            shutil.rmtree(self.staging_research_dir(research_id), ignore_errors=True)
            event_path = self.events_path(research_id)
            event_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_text_atomic(
                event_path,
                json.dumps(
                    {
                        "event": "research.cancelled",
                        "status": ResearchStatus.CANCELLED.value,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n",
            )

    def recover_interrupted_runs(self) -> list[str]:
        """把进程遗留的活动运行标记为中断失败，并清理临时数据与浏览器锁。"""
        recovered: list[str] = []
        with _store_lock:
            if self.runs_dir.exists():
                for status_path in sorted(self.runs_dir.glob("research_*/status.json")):
                    try:
                        snapshot = ResearchSnapshot.model_validate(self._read_json(status_path))
                    except (OSError, ValueError, json.JSONDecodeError):
                        continue
                    if snapshot.status not in _ACTIVE_STATUSES:
                        continue
                    interrupted = snapshot.model_copy(
                        update={
                            "status": ResearchStatus.FAILED,
                            "stage": ResearchStage.FINISHED,
                            "available_actions": (),
                            "error": MarketResearchError(
                                MarketResearchErrorCode.PROCESS_INTERRUPTED,
                                stage=snapshot.stage.value,
                            ).to_payload(),
                            "updated_at": datetime.now(UTC),
                        }
                    )
                    self._write_json_atomic(
                        status_path,
                        interrupted.model_dump(mode="json"),
                    )
                    shutil.rmtree(
                        self.temp_research_dir(snapshot.research_id),
                        ignore_errors=True,
                    )
                    shutil.rmtree(
                        self.staging_research_dir(snapshot.research_id),
                        ignore_errors=True,
                    )
                    recovered.append(snapshot.research_id)
            for lock_path in self.runtime_dir.glob("*.lock"):
                lock_path.unlink(missing_ok=True)
        return recovered

    def run_status_path(self, research_id: str) -> Path:
        """返回受控 research_id（调研编号）的 status.json 路径。"""
        self._validate_research_id(research_id)
        return self.runs_dir / research_id / "status.json"

    def events_path(self, research_id: str) -> Path:
        """返回受控 research_id（调研编号）的脱敏事件文件路径。"""
        self._validate_research_id(research_id)
        return self.events_dir / f"{research_id}.jsonl"

    def temp_research_dir(self, research_id: str) -> Path:
        """返回受控 research_id（调研编号）的临时运行目录。"""
        self._validate_research_id(research_id)
        return self.temp_dir / research_id

    def direction_temp_dir(self, research_id: str, direction_run_id: str) -> Path:
        """返回受控方向运行编号对应的临时目录。"""
        self._validate_research_id(research_id)
        self._validate_direction_run_id(direction_run_id)
        return self.temp_dir / research_id / direction_run_id

    def staging_research_dir(self, research_id: str) -> Path:
        """返回受控 research_id（调研编号）的未发布版本父目录。"""
        self._validate_research_id(research_id)
        return self.staging_dir / research_id

    def result_research_dir(self, research_id: str) -> Path:
        """返回受控 research_id（调研编号）的正式版本父目录。"""
        self._validate_research_id(research_id)
        return self.results_dir / research_id

    def result_version_dir(self, research_id: str, result_version: int) -> Path:
        """返回明确 result_version（结果版本）对应的不可变正式目录。"""
        self._validate_research_id(research_id)
        if result_version < 1:
            raise ValueError("result_version must be at least 1")
        return self.results_dir / research_id / f"v{result_version}"

    def latest_path(self, research_id: str) -> Path:
        """返回受控 research_id（调研编号）的最新正式版本指针路径。"""
        return self.result_research_dir(research_id) / "latest.json"

    def _publish_once(
        self,
        research_id: str,
        result: MarketResearchResult,
        jobs: list[CollectedJob],
        skill_taxonomy: SkillTaxonomy,
    ) -> ResultRef:
        """执行一次完整 staging 构建、验证、目录发布和 latest 切换。"""
        target_dir = self.result_version_dir(research_id, result.result_version)
        result_ref = ResultRef(
            research_id=research_id,
            result_version=result.result_version,
        )
        if target_dir.exists():
            self._verify_existing_version(target_dir, result, jobs, skill_taxonomy)
            self._publish_latest_and_index(result, result_ref)
            return result_ref

        publish_token = uuid.uuid4().hex
        staging_parent = self.staging_research_dir(research_id)
        staging_parent.mkdir(parents=True, exist_ok=True)
        staging_version = staging_parent / f"v{result.result_version}-{publish_token}"
        screenshots_dir = staging_version / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=False)

        manifest = self._stage_screenshots(result, screenshots_dir)
        self._validate_version_collection(result, jobs, skill_taxonomy, manifest)
        self._write_json_file(staging_version / "result.json", result.model_dump(mode="json"))
        self._write_json_file(
            staging_version / "jobs.json",
            [job.model_dump(mode="json") for job in jobs],
        )
        self._write_json_file(
            staging_version / "skills.json",
            skill_taxonomy.model_dump(mode="json"),
        )
        self._write_json_file(
            staging_version / "screenshots_manifest.json",
            manifest.model_dump(mode="json"),
        )
        self._fsync_directory_tree(screenshots_dir)
        self._fsync_directory(staging_version)

        target_parent = self.result_research_dir(research_id)
        target_parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging_version, target_dir)
        self._fsync_directory(staging_parent)
        self._fsync_directory(target_parent)
        self._publish_latest_and_index(result, result_ref)
        for direction in result.successful_directions:
            if isinstance(direction, DirectionResult):
                self.cleanup_direction_temp(research_id, direction.direction_run_id)
        return result_ref

    def _stage_screenshots(
        self,
        result: MarketResearchResult,
        screenshots_dir: Path,
    ) -> ScreenshotManifest:
        """把成功新方向的临时抽样截图复制到 staging 并生成完整性清单。"""
        items: list[ScreenshotManifestItem] = []
        for direction in result.successful_directions:
            if not isinstance(direction, DirectionResult):
                continue
            source_dir = (
                self.direction_temp_dir(result.research_id, direction.direction_run_id)
                / "screenshots"
            )
            if not source_dir.exists():
                continue
            target_direction_dir = screenshots_dir / direction.direction_run_id
            target_direction_dir.mkdir(parents=True, exist_ok=True)
            for source in sorted(source_dir.iterdir()):
                if (
                    not source.is_file()
                    or source.is_symlink()
                    or source.suffix.lower() not in _SCREENSHOT_SUFFIXES
                ):
                    continue
                target = target_direction_dir / source.name
                shutil.copy2(source, target)
                self._fsync_file(target)
                relative_ref = target.relative_to(screenshots_dir.parent).as_posix()
                items.append(
                    ScreenshotManifestItem(
                        screenshot_ref=relative_ref,
                        direction_run_id=direction.direction_run_id,
                        sha256=self._sha256_file(target),
                        size_bytes=target.stat().st_size,
                    )
                )
        return ScreenshotManifest(
            research_id=result.research_id,
            result_version=result.result_version,
            screenshots=tuple(items),
        )

    def _validate_version_collection(
        self,
        result: MarketResearchResult,
        jobs: list[CollectedJob],
        skill_taxonomy: SkillTaxonomy,
        manifest: ScreenshotManifest,
    ) -> None:
        """交叉校验结果、岗位、技能、旧方向引用和截图引用后才允许发布。"""
        if manifest.research_id != result.research_id:
            raise ValueError("screenshot manifest research_id mismatch")
        if manifest.result_version != result.result_version:
            raise ValueError("screenshot manifest result_version mismatch")

        direction_keys = {direction.direction_key for direction in result.successful_directions}
        if skill_taxonomy.direction_key not in direction_keys:
            raise ValueError("skill taxonomy direction must exist in successful directions")
        if result.expires_at != min(
            direction.expires_at for direction in result.successful_directions
        ):
            raise ValueError("result expires_at must be the earliest successful direction expiry")
        if result.status == "completed" and result.failed_directions:
            raise ValueError("completed result cannot contain failed directions")
        if result.status == "partial_completed" and not result.failed_directions:
            raise ValueError("partial_completed result requires a failed direction")
        if result.comparison is not None and not set(result.comparison.direction_keys).issubset(
            direction_keys
        ):
            raise ValueError("comparison references an unknown direction")
        if len(direction_keys) >= 2 and result.comparison is None:
            raise ValueError("multiple successful directions require a comparison")
        if len(direction_keys) < 2 and result.comparison is not None:
            raise ValueError("single successful direction cannot contain a comparison")

        job_map: dict[str, CollectedJob] = {}
        for job in jobs:
            identity = job.job_id or job.fingerprint
            if identity is None or identity in job_map:
                raise ValueError("persisted job identities must be unique")
            job_map[identity] = job
        screenshot_refs = {item.screenshot_ref for item in manifest.screenshots}
        for direction in result.successful_directions:
            if isinstance(direction, ReferencedDirectionResult):
                self._validate_direction_reference(result, direction)
                continue
            self._validate_inline_direction(direction, job_map, screenshot_refs)
        self._validate_audit_refs(result.audit_refs, screenshot_refs)

    def _validate_inline_direction(
        self,
        direction: DirectionResult,
        job_map: dict[str, CollectedJob],
        screenshot_refs: set[str],
    ) -> None:
        """校验一个新方向中的主题岗位、代表岗位和截图审计引用。"""
        themes = (
            *direction.responsibility_themes,
            *direction.requirement_themes,
            *direction.preference_themes,
            *direction.evidence_themes,
        )
        for theme in themes:
            if not set(theme.support_job_ids).issubset(job_map):
                raise ValueError("theme references an unknown job")
            for representative in theme.representative_jobs:
                if representative.job_id not in job_map:
                    raise ValueError("theme representative references an unknown job")
        for representative in direction.representative_jobs:
            if representative.job_id not in job_map:
                raise ValueError("direction representative references an unknown job")
        self._validate_audit_refs(direction.audit_refs, screenshot_refs)

    def _validate_direction_reference(
        self,
        result: MarketResearchResult,
        direction: ReferencedDirectionResult,
    ) -> None:
        """重新解析旧正式版本并验证方向引用身份和有效期没有被新版本改写。"""
        reference = direction.direction_result_ref
        if reference.research_id != result.research_id:
            raise ValueError("direction retry must reference the same research")
        if reference.result_version >= result.result_version:
            raise ValueError("direction retry must reference an older result version")
        referenced_result = self.read_result(reference.research_id, reference.result_version)
        for entry in referenced_result.successful_directions:
            resolved = self._resolve_direction_entry(entry)
            if resolved.direction_key != reference.direction_key:
                continue
            if resolved.direction_run_id != reference.direction_run_id:
                raise ValueError("direction reference run id mismatch")
            if direction.researched_at != resolved.researched_at:
                raise ValueError("referenced direction researched_at cannot change")
            if direction.expires_at != resolved.expires_at:
                raise ValueError("referenced direction expires_at cannot change")
            return
        raise ValueError("referenced direction does not exist")

    def _resolve_direction_entry(
        self,
        direction: DirectionResult | ReferencedDirectionResult,
    ) -> DirectionResult:
        """递归解析方向引用并返回最初发布的完整方向数据。"""
        if isinstance(direction, DirectionResult):
            return direction
        reference = direction.direction_result_ref
        result = self.read_result(reference.research_id, reference.result_version)
        for entry in result.successful_directions:
            if entry.direction_key == reference.direction_key:
                return self._resolve_direction_entry(entry)
        raise ValueError("referenced direction does not exist")

    def _validate_audit_refs(
        self,
        audit_refs: Iterable[str],
        screenshot_refs: set[str],
    ) -> None:
        """拒绝绝对路径、父目录跳转和不存在的正式截图引用。"""
        for audit_ref in audit_refs:
            path = Path(audit_ref)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("audit reference must be a controlled relative path")
            if audit_ref.startswith("screenshots/") and audit_ref not in screenshot_refs:
                raise ValueError("audit screenshot reference is not in the manifest")

    def _verify_existing_version(
        self,
        target_dir: Path,
        result: MarketResearchResult,
        jobs: list[CollectedJob],
        skill_taxonomy: SkillTaxonomy,
    ) -> None:
        """确认既有版本与调用内容完全一致并验证截图清单，禁止任何覆盖。"""
        expected = {
            "result.json": result.model_dump(mode="json"),
            "jobs.json": [job.model_dump(mode="json") for job in jobs],
            "skills.json": skill_taxonomy.model_dump(mode="json"),
        }
        for name, payload in expected.items():
            if self._read_json(target_dir / name) != payload:
                raise ValueError("immutable result version already exists with different content")
        manifest = ScreenshotManifest.model_validate(
            self._read_json(target_dir / "screenshots_manifest.json")
        )
        self._verify_manifest_files(target_dir, manifest)
        self._validate_version_collection(result, jobs, skill_taxonomy, manifest)

    def _verify_manifest_files(
        self,
        version_dir: Path,
        manifest: ScreenshotManifest,
    ) -> None:
        """验证正式截图均位于版本目录内且大小与 SHA-256 清单一致。"""
        for item in manifest.screenshots:
            reference_path = Path(item.screenshot_ref)
            if (
                reference_path.is_absolute()
                or ".." in reference_path.parts
                or not reference_path.parts
                or reference_path.parts[0] != "screenshots"
            ):
                raise ValueError("manifest screenshot reference is not controlled")
            screenshot = version_dir / item.screenshot_ref
            if not screenshot.is_file() or screenshot.is_symlink():
                raise ValueError("manifest screenshot is missing")
            if screenshot.stat().st_size != item.size_bytes:
                raise ValueError("manifest screenshot size mismatch")
            if self._sha256_file(screenshot) != item.sha256:
                raise ValueError("manifest screenshot hash mismatch")

    def _publish_latest_and_index(
        self,
        result: MarketResearchResult,
        result_ref: ResultRef,
    ) -> None:
        """先更新可重建索引，最后原子切换作为发布提交点的 latest 指针。"""
        index = self._read_index()
        rows = [
            row
            for row in index["results"]
            if not (
                row.get("research_id") == result.research_id
                and row.get("result_version") == result.result_version
            )
        ]
        rows.append(
            {
                "research_id": result.research_id,
                "result_version": result.result_version,
                "origin_session_id": result.origin_session_id,
                "status": result.status,
                "researched_at": result.researched_at.isoformat(),
                "expires_at": result.expires_at.isoformat(),
                "direction_keys": [
                    direction.direction_key for direction in result.successful_directions
                ],
            }
        )
        index["results"] = sorted(
            rows,
            key=lambda row: (row["research_id"], row["result_version"]),
        )
        self._write_json_atomic(self.index_path, index)
        latest_path = self.latest_path(result.research_id)
        self._write_json_atomic(latest_path, result_ref.model_dump(mode="json"))
        self._fsync_directory(latest_path.parent)

    def _read_index(self) -> dict[str, Any]:
        """读取市场正式结果索引；不存在时返回版本一的空索引。"""
        if not self.index_path.exists():
            return {"schema_version": 1, "results": []}
        payload = self._read_json(self.index_path)
        if payload.get("schema_version") != 1 or not isinstance(payload.get("results"), list):
            raise ValueError("invalid market research index")
        return payload

    def _initialize_layout(self) -> None:
        """创建当前 demo 固定的方案、运行、临时、正式结果、事件和浏览器目录。"""
        for directory in (
            self.root,
            self.plans_dir,
            self.runs_dir,
            self.temp_dir,
            self.staging_dir,
            self.results_dir,
            self.events_dir,
            self.browser_profile_dir,
            self.runtime_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_json_atomic(
                self.index_path,
                {"schema_version": 1, "results": []},
            )

    def _write_json_atomic(self, path: Path, payload: Any) -> None:
        """用同目录临时文件、flush、fsync 和 os.replace 原子写单个 JSON。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            self._write_json_file(temp, payload)
            os.replace(temp, path)
            self._fsync_directory(path.parent)
        finally:
            temp.unlink(missing_ok=True)

    def _write_text_atomic(self, path: Path, content: str) -> None:
        """原子写入单个 UTF-8 文本文件，用于最小取消事件。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temp.open("w", encoding="utf-8") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp, path)
            self._fsync_directory(path.parent)
        finally:
            temp.unlink(missing_ok=True)

    def _write_json_file(self, path: Path, payload: Any) -> None:
        """写入并 fsync 一个 JSON 文件；调用方决定它是否已对正式读取可见。"""
        with path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())

    @staticmethod
    def _read_json(path: Path) -> Any:
        """读取一个 UTF-8 JSON 文件并返回解析后的 Python 值。"""
        with path.open(encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        """流式计算文件 SHA-256 摘要，避免把完整截图一次载入内存。"""
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _fsync_file(path: Path) -> None:
        """同步一个已写入文件的内容和元数据到磁盘。"""
        with path.open("rb") as file:
            os.fsync(file.fileno())

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        """同步目录项，保证 rename 或 replace 的目录结构持久化。"""
        directory_fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _fsync_directory_tree(self, root: Path) -> None:
        """从最深层开始同步截图目录树中的全部目录项。"""
        directories = [path for path in root.rglob("*") if path.is_dir()]
        for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
            self._fsync_directory(directory)
        self._fsync_directory(root)

    @staticmethod
    def _validate_research_id(research_id: str) -> None:
        """校验 research_id（调研编号）符合受控十六进制格式。"""
        if not _RESEARCH_ID_PATTERN.fullmatch(research_id):
            raise ValueError("invalid research_id")

    @staticmethod
    def _validate_direction_run_id(direction_run_id: str) -> None:
        """校验 direction_run_id（方向运行编号）符合受控十六进制格式。"""
        if not _DIRECTION_RUN_ID_PATTERN.fullmatch(direction_run_id):
            raise ValueError("invalid direction_run_id")

    @staticmethod
    def validate_plan_id(plan_id: str) -> None:
        """校验 plan_id（方案编号）符合受控十六进制格式。"""
        if not _PLAN_ID_PATTERN.fullmatch(plan_id):
            raise ValueError("invalid plan_id")

    @staticmethod
    def validate_version_directory_name(name: str) -> int:
        """校验 vN（结果版本目录名）并返回其中的大于零版本号。"""
        match = _VERSION_DIR_PATTERN.fullmatch(name)
        if match is None:
            raise ValueError("invalid result version directory")
        return int(match.group(1))
