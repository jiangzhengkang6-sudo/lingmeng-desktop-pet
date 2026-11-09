from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from os import getenv

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VOICEPRINT_RTC_API_VERSION = "2025-06-01"


def _runtime_directory(name: str, default: Path) -> Path:
    value = getenv(name, "").strip()
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


CONFIG_DIRECTORY = _runtime_directory("DESKTOP_PET_CONFIG_DIR", PROJECT_ROOT)
load_dotenv(CONFIG_DIRECTORY / ".env")


def _env(name: str, default: str = "") -> str:
    return getenv(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if not value:
        return default
    if value.lower() in {"1", "true", "yes", "on"}:
        return True
    if value.lower() in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass(frozen=True)
class Settings:
    speech_provider: str
    speech_model: str
    speech_api_base_url: str
    speech_api_key: str
    speech_tts_endpoint: str
    speech_asr_endpoint: str
    speech_voice_id: str
    speech_timeout_seconds: float
    cors_origins: tuple[str, ...]
    # 安全默认关闭：必须通过人脸/声纹验证才解锁私有记忆与受控工具。
    # 仅本地开发调试时可用 DESKTOP_PET_TEMP_OPEN_ACCESS=true 显式放开。
    identity_temp_open_access: bool = False
    agent_provider: str = "mock"
    agent_model: str = "qwen3.8-flash"
    agent_api_base_url: str = ""
    agent_api_key: str = ""
    agent_chat_endpoint: str = ""
    agent_timeout_seconds: float = 30.0
    agent_fallback_to_mock: bool = True
    agent_require_remote: bool = False
    agent_context_turn_limit: int = 6
    # 工作流引擎：默认保留旧链路，显式切换到 langgraph 后才启用新图。
    agent_workflow_engine: str = "legacy"
    # 影子模式用于后续比对新旧链路，第一阶段仅保留配置位，不改变最终响应。
    agent_workflow_shadow: bool = False
    # LangGraph 检查点默认仍使用内存实现；显式开启后才写入 SQLite。
    langgraph_checkpoint_enabled: bool = False
    langgraph_checkpoint_path: Path = (
        PROJECT_ROOT / "backend" / "data" / "langgraph-checkpoints.sqlite3"
    )
    # 工具审批中断默认关闭；显式开启后，open_file 才走 interrupt/恢复路径。
    langgraph_approval_interrupt_enabled: bool = False
    memory_database_path: Path = PROJECT_ROOT / "backend" / "data" / "desktop-pet.sqlite3"
    memory_context_limit: int = 12
    local_state_database_path: Path = PROJECT_ROOT / "backend" / "data" / "desktop-pet.sqlite3"
    tools_database_path: Path = PROJECT_ROOT / "backend" / "data" / "desktop-pet.sqlite3"
    tools_allowed_directories: tuple[Path, ...] = ()
    tools_allowed_applications: tuple[tuple[str, str], ...] = ()
    doubao_asr_ws_url: str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream"
    doubao_api_key: str = ""
    doubao_app_key: str = ""
    doubao_access_key: str = ""
    doubao_resource_id: str = "volc.bigasr.sauc.duration"
    doubao_uid: str = "desktop_pet"
    doubao_segment_duration_ms: int = 200
    voiceprint_provider: str = "mock"
    voiceprint_max_audio_bytes: int = 5 * 1024 * 1024
    voiceprint_rtc_owner_name: str = ""
    voiceprint_rtc_score_threshold: float | None = None
    voiceprint_rtc_bridge_secret: str = ""
    voiceprint_rtc_callback_url: str = ""
    voiceprint_rtc_callback_secret: str = ""
    voiceprint_rtc_clock_skew_seconds: int = 300
    voiceprint_rtc_access_key_id: str = ""
    voiceprint_rtc_secret_access_key: str = ""
    voiceprint_rtc_app_id: str = ""
    voiceprint_rtc_app_key: str = ""
    voiceprint_rtc_region: str = "cn-north-1"
    voiceprint_rtc_api_version: str = DEFAULT_VOICEPRINT_RTC_API_VERSION
    voiceprint_rtc_scene_path: Path = PROJECT_ROOT / "backend" / "config" / "voiceprint-rtc-scene.json"
    voiceprint_rtc_timeout_seconds: float = 15.0
    voiceprint_rtc_session_ttl_seconds: float = 3600.0
    # RAG 存储迁移期默认仍保留 Milvus；显式设置 RAG_STORE=sqlite-vec 后启用本地库。
    rag_store: str = "milvus"
    rag_milvus_uri: str = "http://127.0.0.1:19530"
    # RAG 元数据与 sqlite-vec 向量使用独立文件，不混入 desktop-pet.sqlite3。
    rag_sqlite_path: Path = PROJECT_ROOT / "backend" / "data" / "rag.sqlite3"
    rag_timeout_seconds: float = 10.0
    rag_embedding_provider: str = "hash"
    rag_embedding_model: str = "local-hash-v1"
    rag_embedding_dimension: int = 384
    rag_embedding_api_base_url: str = ""
    rag_embedding_api_key: str = ""
    rag_embedding_endpoint: str = ""
    rag_chunk_size: int = 900
    rag_chunk_overlap: int = 120
    # 人脸识别（MediaPipe）
    face_recognition_enabled: bool = True
    face_recognition_model_path: Path = PROJECT_ROOT / "backend" / "models" / "face_landmarker.task"
    # P1-2：身份认证改用 OpenCV YuNet 检测 + SFace 身份嵌入
    face_detection_model_path: Path = PROJECT_ROOT / "backend" / "models" / "face_detection_yunet_2023mar.onnx"
    face_recognizer_model_path: Path = PROJECT_ROOT / "backend" / "models" / "face_recognition_sface_2021dec.onnx"
    face_recognition_profile_path: Path = PROJECT_ROOT / "backend" / "data" / "face_profile.json"
    # SFace 余弦阈值：实测主人最低 0.654、他人最高 0.245，中点 0.45 两侧余量充分
    face_recognition_similarity_threshold: float = 0.45
    face_recognition_min_samples: int = 3
    rag_max_upload_bytes: int = 5 * 1024 * 1024

    @classmethod
    def from_environment(cls) -> "Settings":
        config_directory = _runtime_directory("DESKTOP_PET_CONFIG_DIR", PROJECT_ROOT)
        data_directory = _runtime_directory(
            "DESKTOP_PET_DATA_DIR",
            PROJECT_ROOT / "backend" / "data",
        )
        base_url = _env("SPEECH_API_BASE_URL", "https://api.minimax.io/v1").rstrip("/")
        tts_endpoint = _resolve_endpoint(_env("SPEECH_TTS_ENDPOINT"), base_url, "/t2a_v2")
        asr_endpoint = _resolve_endpoint(_env("SPEECH_ASR_ENDPOINT"), base_url)
        agent_base_url = _env("AGENT_API_BASE_URL").rstrip("/")
        agent_endpoint = _resolve_endpoint(
            _env("AGENT_CHAT_ENDPOINT"),
            agent_base_url,
            "/chat/completions",
        )
        embedding_base_url = _env("RAG_EMBEDDING_API_BASE_URL").rstrip("/")
        embedding_endpoint = _resolve_endpoint(
            _env("RAG_EMBEDDING_ENDPOINT"),
            embedding_base_url,
            "/embeddings",
        )
        origins = tuple(
            origin.strip()
            for origin in _env(
                "CORS_ORIGINS",
                # Windows WebView2 下 Tauri 页面 origin 是 https://tauri.localhost，
                # 旧版 Windows 与开发服务器使用 http 变体，两者都要放行。
                "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174,http://tauri.localhost,https://tauri.localhost",
            ).split(",")
            if origin.strip()
        )
        allowed_directories = tuple(
            _resolve_project_path(item, config_directory)
            for item in _split_path_list(_env("TOOLS_ALLOWED_DIRECTORIES"))
        )
        allowed_applications = tuple(
            (name.strip(), command.strip())
            for item in _split_path_list(_env("TOOLS_ALLOWED_APPLICATIONS"))
            if "=" in item
            for name, command in [item.split("=", 1)]
            if name.strip() and command.strip()
        )
        workflow_engine = _env("AGENT_WORKFLOW_ENGINE", "legacy").lower()
        rag_store = _env("RAG_STORE", "milvus").lower()
        return cls(
            speech_provider=_env("SPEECH_PROVIDER", "minimax"),
            speech_model=_env("SPEECH_MODEL", "speech-2.8-hd"),
            speech_api_base_url=base_url,
            speech_api_key=_env("SPEECH_API_KEY"),
            speech_tts_endpoint=tts_endpoint,
            speech_asr_endpoint=asr_endpoint,
            speech_voice_id=_env("SPEECH_VOICE_ID"),
            speech_timeout_seconds=float(_env("SPEECH_TIMEOUT_SECONDS", "30")),
            cors_origins=origins,
            identity_temp_open_access=_env_bool("DESKTOP_PET_TEMP_OPEN_ACCESS", False),
            agent_provider=_env("AGENT_PROVIDER", "mock").lower(),
            agent_model=_env("AGENT_MODEL", "qwen3.8-flash"),
            agent_api_base_url=agent_base_url,
            agent_api_key=_env("AGENT_API_KEY"),
            agent_chat_endpoint=agent_endpoint,
            agent_timeout_seconds=float(_env("AGENT_TIMEOUT_SECONDS", "30")),
            agent_fallback_to_mock=_env_bool("AGENT_FALLBACK_TO_MOCK", True),
            agent_require_remote=_env_bool("AGENT_REQUIRE_REMOTE", False),
            agent_context_turn_limit=int(_env("AGENT_CONTEXT_TURN_LIMIT", "6")),
            agent_workflow_engine=(
                workflow_engine
                if workflow_engine in {"legacy", "langgraph"}
                else "legacy"
            ),
            agent_workflow_shadow=_env_bool("AGENT_WORKFLOW_SHADOW", False),
            langgraph_checkpoint_enabled=_env_bool(
                "LANGGRAPH_CHECKPOINT_ENABLED",
                False,
            ),
            langgraph_checkpoint_path=_path_env(
                "LANGGRAPH_CHECKPOINT_PATH",
                data_directory / "langgraph-checkpoints.sqlite3",
                config_directory,
            ),
            langgraph_approval_interrupt_enabled=_env_bool(
                "LANGGRAPH_APPROVAL_INTERRUPT_ENABLED",
                False,
            ),
            memory_database_path=_path_env(
                "MEMORY_DATABASE_PATH",
                data_directory / "desktop-pet.sqlite3",
                config_directory,
            ),
            memory_context_limit=int(_env("MEMORY_CONTEXT_LIMIT", "12")),
            local_state_database_path=_path_env(
                "LOCAL_STATE_DATABASE_PATH",
                data_directory / "desktop-pet.sqlite3",
                config_directory,
            ),
            tools_database_path=_path_env(
                "TOOLS_DATABASE_PATH",
                data_directory / "desktop-pet.sqlite3",
                config_directory,
            ),
            tools_allowed_directories=allowed_directories,
            tools_allowed_applications=allowed_applications,
            doubao_asr_ws_url=_env(
                "DOUBAO_ASR_WS_URL",
                "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream",
            ),
            doubao_api_key=_env("DOUBAO_API_KEY"),
            doubao_app_key=_env("DOUBAO_APP_KEY"),
            doubao_access_key=_env("DOUBAO_ACCESS_KEY"),
            doubao_resource_id=_env("DOUBAO_RESOURCE_ID", "volc.bigasr.sauc.duration"),
            doubao_uid=_env("DOUBAO_UID", "desktop_pet"),
            doubao_segment_duration_ms=int(_env("DOUBAO_SEGMENT_DURATION_MS", "200")),
            voiceprint_provider=_env("VOICEPRINT_PROVIDER", "mock").lower(),
            voiceprint_max_audio_bytes=int(_env("VOICEPRINT_MAX_AUDIO_BYTES", str(5 * 1024 * 1024))),
            voiceprint_rtc_owner_name=_env("VOICEPRINT_RTC_OWNER_NAME"),
            voiceprint_rtc_score_threshold=_optional_float(_env("VOICEPRINT_RTC_SCORE_THRESHOLD")),
            voiceprint_rtc_bridge_secret=_env("VOICEPRINT_RTC_BRIDGE_SECRET"),
            voiceprint_rtc_callback_url=_env("VOICEPRINT_RTC_CALLBACK_URL"),
            voiceprint_rtc_callback_secret=_env("VOICEPRINT_RTC_CALLBACK_SECRET"),
            voiceprint_rtc_clock_skew_seconds=int(_env("VOICEPRINT_RTC_CLOCK_SKEW_SECONDS", "300")),
            voiceprint_rtc_access_key_id=_env("VOICEPRINT_RTC_ACCESS_KEY_ID"),
            voiceprint_rtc_secret_access_key=_env("VOICEPRINT_RTC_SECRET_ACCESS_KEY"),
            voiceprint_rtc_app_id=_env("VOICEPRINT_RTC_APP_ID"),
            voiceprint_rtc_app_key=_env("VOICEPRINT_RTC_APP_KEY"),
            voiceprint_rtc_region=_env("VOICEPRINT_RTC_REGION", "cn-north-1"),
            voiceprint_rtc_api_version=_env(
                "VOICEPRINT_RTC_API_VERSION",
                DEFAULT_VOICEPRINT_RTC_API_VERSION,
            ),
            voiceprint_rtc_scene_path=_path_env(
                "VOICEPRINT_RTC_SCENE_PATH",
                config_directory / "backend" / "config" / "voiceprint-rtc-scene.json",
                config_directory,
            ),
            voiceprint_rtc_timeout_seconds=float(_env("VOICEPRINT_RTC_TIMEOUT_SECONDS", "15")),
            voiceprint_rtc_session_ttl_seconds=float(
                _env("VOICEPRINT_RTC_SESSION_TTL_SECONDS", "3600")
            ),
            rag_store=rag_store if rag_store in {"milvus", "sqlite-vec"} else "milvus",
            rag_milvus_uri=_env("RAG_MILVUS_URI", "http://127.0.0.1:19530"),
            rag_sqlite_path=_path_env(
                "RAG_SQLITE_PATH",
                data_directory / "rag.sqlite3",
                config_directory,
            ),
            rag_timeout_seconds=float(_env("RAG_TIMEOUT_SECONDS", "10")),
            rag_embedding_provider=_env("RAG_EMBEDDING_PROVIDER", "hash").lower(),
            rag_embedding_model=_env("RAG_EMBEDDING_MODEL", "local-hash-v1"),
            rag_embedding_dimension=int(_env("RAG_EMBEDDING_DIMENSION", "384")),
            rag_embedding_api_base_url=embedding_base_url,
            rag_embedding_api_key=_env("RAG_EMBEDDING_API_KEY"),
            rag_embedding_endpoint=embedding_endpoint,
            rag_chunk_size=int(_env("RAG_CHUNK_SIZE", "900")),
            rag_chunk_overlap=int(_env("RAG_CHUNK_OVERLAP", "120")),
            rag_max_upload_bytes=int(_env("RAG_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024))),
            face_recognition_enabled=_env_bool("FACE_RECOGNITION_ENABLED", True),
            face_recognition_model_path=_path_env(
                "FACE_RECOGNITION_MODEL_PATH",
                config_directory / "backend" / "models" / "face_landmarker.task",
            ),
            face_detection_model_path=_path_env(
                "FACE_DETECTION_MODEL_PATH",
                config_directory / "backend" / "models" / "face_detection_yunet_2023mar.onnx",
            ),
            face_recognizer_model_path=_path_env(
                "FACE_RECOGNIZER_MODEL_PATH",
                config_directory / "backend" / "models" / "face_recognition_sface_2021dec.onnx",
            ),
            face_recognition_profile_path=_path_env(
                "FACE_RECOGNITION_PROFILE_PATH",
                data_directory / "face_profile.json",
            ),
            face_recognition_similarity_threshold=float(
                _env("FACE_RECOGNITION_SIMILARITY_THRESHOLD", "0.45")
            ),
            face_recognition_min_samples=int(_env("FACE_RECOGNITION_MIN_SAMPLES", "3")),
        )

    @property
    def tts_configured(self) -> bool:
        return bool(self.speech_api_key and self.speech_tts_endpoint and self.speech_model)

    @property
    def asr_configured(self) -> bool:
        return bool(self.speech_api_key and self.speech_asr_endpoint)

    @property
    def doubao_asr_configured(self) -> bool:
        has_auth = bool(self.doubao_api_key) or bool(self.doubao_app_key and self.doubao_access_key)
        return bool(self.doubao_asr_ws_url and self.doubao_resource_id and has_auth)

    @property
    def agent_configured(self) -> bool:
        return bool(
            self.agent_provider != "mock"
            and self.agent_model
            and self.agent_api_key
            and self.agent_chat_endpoint
        )

    @property
    def agent_configuration_issues(self) -> tuple[str, ...]:
        """Describe provider conflicts without exposing credentials."""
        issues: list[str] = []
        if self.agent_provider not in {"mock", "qwen", "openai-compatible"}:
            issues.append("unsupported_provider")
        if self.agent_require_remote and self.agent_provider == "mock":
            issues.append("remote_required_but_provider_is_mock")
        if self.agent_require_remote and self.agent_fallback_to_mock:
            issues.append("remote_required_but_mock_fallback_enabled")
        if self.agent_provider in {"qwen", "openai-compatible"}:
            missing = [
                name
                for name, value in (
                    ("model", self.agent_model),
                    ("api_key", self.agent_api_key),
                    ("chat_endpoint", self.agent_chat_endpoint),
                )
                if not value
            ]
            if missing:
                issues.append("remote_configuration_incomplete:" + ",".join(missing))
        return tuple(issues)

    @property
    def agent_ready(self) -> bool:
        """Whether the selected mode can run without an implicit contradiction."""
        if self.agent_provider == "mock":
            return not self.agent_require_remote and not self.agent_configuration_issues
        return self.agent_configured and not self.agent_configuration_issues

    @property
    def rag_embedding_configured(self) -> bool:
        if self.rag_embedding_provider == "hash":
            return self.rag_embedding_dimension > 0
        if self.rag_embedding_provider == "openai-compatible":
            return bool(
                self.rag_embedding_model
                and self.rag_embedding_api_key
                and self.rag_embedding_endpoint
            )
        return False

    @property
    def voiceprint_rtc_configured(self) -> bool:
        return bool(
            self.voiceprint_provider == "volcengine-rtc"
            and self.voiceprint_rtc_owner_name
            and self.voiceprint_rtc_score_threshold is not None
            and 1 <= self.voiceprint_rtc_score_threshold <= 100
            and self.voiceprint_rtc_bridge_secret
            and self.voiceprint_rtc_clock_skew_seconds > 0
        )

    @property
    def voiceprint_rtc_callback_configured(self) -> bool:
        """官方 RTS 服务端回调必须是带独立共享密钥的公网 HTTPS 地址。"""
        url = self.voiceprint_rtc_callback_url.strip()
        secret = self.voiceprint_rtc_callback_secret.strip()
        if not (url.startswith("https://") and secret):
            return False
        host = url.split("/", 3)[2].split(":", 1)[0].lower()
        return host not in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}

    @property
    def voiceprint_rtc_live_configured(self) -> bool:
        return bool(
            self.voiceprint_rtc_openapi_configured
            and self.voiceprint_rtc_callback_configured
            and self.voiceprint_rtc_client_token_configured
        )

    @property
    def voiceprint_rtc_client_token_configured(self) -> bool:
        return bool(
            self.voiceprint_rtc_configured
            and self.voiceprint_rtc_app_id
            and self.voiceprint_rtc_app_key
        )

    @property
    def voiceprint_rtc_openapi_configured(self) -> bool:
        return bool(
            self.voiceprint_rtc_configured
            and self.voiceprint_rtc_access_key_id
            and self.voiceprint_rtc_secret_access_key
            and self.voiceprint_rtc_app_id
            and self.voiceprint_rtc_region
            and self.voiceprint_rtc_api_version
            and self.voiceprint_rtc_timeout_seconds > 0
            and self.voiceprint_rtc_session_ttl_seconds > 0
        )


def _resolve_endpoint(value: str, base_url: str, fallback_path: str = "") -> str:
    if not value:
        return f"{base_url}{fallback_path}" if fallback_path else ""
    if value.startswith("/") and base_url:
        return f"{base_url}{value}"
    return value


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _optional_float(value: str) -> float | None:
    return float(value) if value else None


def _path_env(name: str, default: Path, base_directory: Path = PROJECT_ROOT) -> Path:
    value = _env(name)
    if not value:
        return default
    path = Path(value)
    return path if path.is_absolute() else base_directory / path


def _split_path_list(value: str) -> tuple[str, ...]:
    r"""Parse Windows lists without splitting a drive letter such as C:\."""
    separator = ";" if ";" in value else ","
    return tuple(item.strip() for item in value.split(separator) if item.strip())


def _resolve_project_path(value: str, base_directory: Path = PROJECT_ROOT) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base_directory / path
