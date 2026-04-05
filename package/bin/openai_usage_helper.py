import json
import logging
import os
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import import_declare_test
from solnlib import checkpointer, conf_manager, log
from splunklib import modularinput as smi

try:
    import requests
except ImportError:
    requests = None


ADDON_NAME = "TA-openai-usage"
BASE_URL = "https://api.openai.com/v1/organization/usage"
MAX_PAGES = 50
MAX_ERROR_DETAIL_LENGTH = 512

PROXY_CREDENTIALS_RE = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)(?P<creds>[^/@:\s]+(?::[^/@\s]*)?@)"
)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def logger_for_input(input_name: str) -> logging.Logger:
    return log.Logs().get_logger(f"{ADDON_NAME.lower()}_{input_name}")


def redact_url_credentials(value: str) -> str:
    """Redact credentials embedded in URLs before logging or indexing."""
    if not value:
        return value
    return PROXY_CREDENTIALS_RE.sub(r"\g<scheme>***:***@", value)


def sanitize_error_detail(detail: Optional[str]) -> str:
    """Normalize and trim error details to avoid leaking sensitive upstream data."""
    if not detail:
        return "No additional error details provided."
    sanitized = redact_url_credentials(str(detail)).replace("\r", " ").replace("\n", " ").strip()
    sanitized = re.sub(r"\s+", " ", sanitized)
    if len(sanitized) > MAX_ERROR_DETAIL_LENGTH:
        sanitized = sanitized[:MAX_ERROR_DETAIL_LENGTH] + "... [truncated]"
    return sanitized


def get_account_details(session_key: str, account_name: str) -> Dict[str, str]:
    """Get account details including API key and optional organization ID."""
    cfm = conf_manager.ConfManager(
        session_key,
        ADDON_NAME,
        realm=f"__REST_CREDENTIAL__#{ADDON_NAME}#configs/conf-ta-openai-usage_account",
    )
    account_conf_file = cfm.get_conf("ta-openai-usage_account")
    account_data = account_conf_file.get(account_name)
    return {
        "api_key": account_data.get("api_key"),
        "organization_id": account_data.get("organization_id", ""),
    }


def get_proxy_settings(session_key: str, logger: logging.Logger) -> Optional[Dict[str, str]]:
    """
    Read proxy configuration from the add-on settings conf file and return a
    dict suitable for passing as the ``proxies`` argument to ``requests.get()``.

    Returns None when the proxy is disabled or not configured.
    """
    try:
        cfm = conf_manager.ConfManager(session_key, ADDON_NAME)
        settings = cfm.get_conf("ta-openai-usage_settings")
        proxy = settings.get("proxy", {})

        if str(proxy.get("proxy_enabled", "0")).strip() != "1":
            return None

        proxy_type = proxy.get("proxy_type", "http").strip() or "http"
        proxy_url = proxy.get("proxy_url", "").strip()
        proxy_port = proxy.get("proxy_port", "").strip()

        if not proxy_url or not proxy_port:
            logger.warning("Proxy enabled but proxy_url or proxy_port is missing; skipping proxy.")
            return None

        username = proxy.get("proxy_username", "").strip()
        password = proxy.get("proxy_password", "").strip()

        if username and password:
            authority = f"{username}:{password}@{proxy_url}:{proxy_port}"
        else:
            authority = f"{proxy_url}:{proxy_port}"

        proxy_uri = f"{proxy_type}://{authority}"
        logger.info(f"Using proxy: {proxy_type}://{proxy_url}:{proxy_port}")
        return {"http": proxy_uri, "https": proxy_uri}

    except Exception as e:
        logger.warning(
            "Could not read proxy settings; proceeding without proxy: "
            f"{sanitize_error_detail(str(e))}"
        )
        return None


# ---------------------------------------------------------------------------
# Collector ABC
# ---------------------------------------------------------------------------

class UsageCollector(ABC):
    """
    Base class for all OpenAI usage collectors.

    Each subclass represents one logical billing dimension from the OpenAI
    Organization Usage API.  Subclasses MUST define the class-level
    attributes ``endpoint_type`` and ``url``, and MUST implement
    ``format_record()``.

    Subclasses that need non-standard fetch behaviour (e.g. different query
    parameters) should override ``collect()``.
    """

    endpoint_type: str          # Used as the Splunk event field value
    url: str                    # Full API endpoint URL
    supports_model_filter: bool = True   # Set False for tool/storage endpoints
    group_by: List[str] = ["model"]      # API group_by param; empty list omits it

    @abstractmethod
    def format_record(self, record: Dict) -> Optional[Dict]:
        """
        Map a single raw API response record to a Splunk event dict.

        Return None to silently skip the record.  This is used by collectors
        that share a URL (e.g. AudioTranscription and AudioSpeech both hit
        /audio but each owns a different model prefix).
        """
        ...

    def collect(
        self,
        logger: logging.Logger,
        headers: Dict[str, str],
        start_time: int,
        end_time: int,
        model_filter: Optional[List[str]],
        proxies: Optional[Dict[str, str]],
    ) -> List[Dict]:
        """Fetch and return all records for this collector's time window."""
        return fetch_usage_with_pagination(
            logger=logger,
            collector=self,
            headers=headers,
            start_time=start_time,
            end_time=end_time,
            model_filter=model_filter,
            proxies=proxies,
        )


# ---------------------------------------------------------------------------
# Shared formatting helper
# ---------------------------------------------------------------------------

def _base_event(record: Dict, endpoint_type: str) -> Dict:
    """Build the common fields present in every event."""
    now_ts = int(datetime.now(timezone.utc).timestamp())
    record_ts = record.get("start_time", now_ts)
    event: Dict = {
        "_time": record_ts,
        "timestamp": datetime.fromtimestamp(record_ts, tz=timezone.utc).isoformat(),
        "endpoint_type": endpoint_type,
    }
    if "model" in record:
        event["model"] = record["model"]
    for opt in ("project_id", "api_key_id", "model_id", "bucket_start_time", "bucket_end_time"):
        if opt in record:
            event[opt] = record[opt]
    return event


# ---------------------------------------------------------------------------
# Concrete collector implementations
# ---------------------------------------------------------------------------

class CompletionsCollector(UsageCollector):
    endpoint_type = "completions"
    url = BASE_URL + "/completions"
    supports_model_filter = True
    group_by = ["model"]

    def format_record(self, record: Dict) -> Optional[Dict]:
        event = _base_event(record, self.endpoint_type)
        event.update({
            "input_tokens": record.get("input_tokens", 0),
            "output_tokens": record.get("output_tokens", 0),
            "cached_tokens": record.get("input_cached_tokens", 0),
            "num_model_requests": record.get("num_model_requests", 0),
        })
        return event


class EmbeddingsCollector(UsageCollector):
    endpoint_type = "embeddings"
    url = BASE_URL + "/embeddings"
    supports_model_filter = True
    group_by = ["model"]

    def format_record(self, record: Dict) -> Optional[Dict]:
        event = _base_event(record, self.endpoint_type)
        event.update({
            "input_tokens": record.get("input_tokens", 0),
            "num_model_requests": record.get("num_model_requests", 0),
        })
        return event


class ImagesCollector(UsageCollector):
    endpoint_type = "images"
    url = BASE_URL + "/images"
    supports_model_filter = True
    group_by = ["model"]

    def format_record(self, record: Dict) -> Optional[Dict]:
        event = _base_event(record, self.endpoint_type)
        event.update({
            "num_model_requests": record.get("num_model_requests", 0),
            "num_images": record.get("num_images", 0),
        })
        if "size" in record:
            event["size"] = record["size"]
        if "quality" in record:
            event["quality"] = record["quality"]
        return event


class AudioTranscriptionCollector(UsageCollector):
    """
    Collects Whisper (speech-to-text) usage from the /audio endpoint.

    The /audio endpoint returns both Whisper and TTS records in the same
    response.  This collector claims only the Whisper records (model prefix
    ``whisper``); AudioSpeechCollector claims the TTS records.  Because both
    collectors hit the same URL, the API is called twice per run — once per
    collector.  This is intentional: the two billing dimensions (seconds vs.
    characters) are distinct enough that conflating them in a single event
    would make cost analysis misleading.
    """
    endpoint_type = "audio_transcription"
    url = BASE_URL + "/audio"
    supports_model_filter = True
    group_by = ["model"]
    _model_prefix = "whisper"

    def format_record(self, record: Dict) -> Optional[Dict]:
        if not record.get("model", "").startswith(self._model_prefix):
            return None
        event = _base_event(record, self.endpoint_type)
        event.update({
            "input_seconds": record.get("input_seconds", 0),
            "num_model_requests": record.get("num_model_requests", 0),
        })
        return event


class AudioSpeechCollector(UsageCollector):
    """Collects TTS (text-to-speech) usage from the /audio endpoint."""
    endpoint_type = "audio_speech"
    url = BASE_URL + "/audio"
    supports_model_filter = True
    group_by = ["model"]
    _model_prefix = "tts"

    def format_record(self, record: Dict) -> Optional[Dict]:
        if not record.get("model", "").startswith(self._model_prefix):
            return None
        event = _base_event(record, self.endpoint_type)
        event.update({
            "num_characters": record.get("num_characters", 0),
            "num_model_requests": record.get("num_model_requests", 0),
        })
        return event


class CodeInterpreterCollector(UsageCollector):
    endpoint_type = "code_interpreter"
    url = BASE_URL + "/code_interpreter"
    supports_model_filter = False
    group_by = []

    def format_record(self, record: Dict) -> Optional[Dict]:
        event = _base_event(record, self.endpoint_type)
        event.update({
            "num_sessions": record.get("num_sessions", 0),
        })
        return event


class WebSearchCollector(UsageCollector):
    endpoint_type = "web_search"
    url = BASE_URL + "/web_search"
    supports_model_filter = False
    group_by = []

    def format_record(self, record: Dict) -> Optional[Dict]:
        event = _base_event(record, self.endpoint_type)
        event.update({
            "num_queries": record.get("num_queries", 0),
            "context_tokens": record.get("context_tokens", 0),
        })
        return event


class VectorStoresCollector(UsageCollector):
    """
    Collects vector store storage usage.

    Vector store billing is per GB·day (a snapshot of bytes stored, not an
    aggregation of requests).  This collector overrides ``collect()`` to omit
    ``bucket_width`` from the request parameters because OpenAI returns storage
    snapshots, not daily-bucketed request streams.
    """
    endpoint_type = "vector_stores"
    url = BASE_URL + "/vector_stores"
    supports_model_filter = False
    group_by = []

    def format_record(self, record: Dict) -> Optional[Dict]:
        event = _base_event(record, self.endpoint_type)
        event.update({
            # API may return usage_bytes or bytes_stored depending on version
            "bytes_stored": record.get("usage_bytes", record.get("bytes_stored", 0)),
        })
        return event

    def collect(
        self,
        logger: logging.Logger,
        headers: Dict[str, str],
        start_time: int,
        end_time: int,
        model_filter: Optional[List[str]],
        proxies: Optional[Dict[str, str]],
    ) -> List[Dict]:
        return fetch_usage_with_pagination(
            logger=logger,
            collector=self,
            headers=headers,
            start_time=start_time,
            end_time=end_time,
            model_filter=model_filter,
            proxies=proxies,
            omit_bucket_width=True,
        )


class FineTuningCollector(UsageCollector):
    """
    Collects fine-tuning training job usage.

    Fine-tuning runs are often the single largest cost spike in an
    organization's OpenAI bill and are tracked separately from inference.
    """
    endpoint_type = "fine_tuning"
    url = BASE_URL + "/fine_tuning"
    supports_model_filter = True
    group_by = ["model"]

    def format_record(self, record: Dict) -> Optional[Dict]:
        event = _base_event(record, self.endpoint_type)
        event.update({
            "input_tokens": record.get("input_tokens", 0),
            "output_tokens": record.get("output_tokens", 0),
            "num_model_requests": record.get("num_model_requests", 0),
        })
        if "training_steps" in record:
            event["training_steps"] = record["training_steps"]
        return event


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

COLLECTOR_REGISTRY: List[UsageCollector] = [
    CompletionsCollector(),
    EmbeddingsCollector(),
    ImagesCollector(),
    AudioTranscriptionCollector(),
    AudioSpeechCollector(),
    CodeInterpreterCollector(),
    WebSearchCollector(),
    VectorStoresCollector(),
    FineTuningCollector(),
]


# ---------------------------------------------------------------------------
# Core fetch logic
# ---------------------------------------------------------------------------

def fetch_usage_with_pagination(
    logger: logging.Logger,
    collector: UsageCollector,
    headers: Dict[str, str],
    start_time: int,
    end_time: int,
    model_filter: Optional[List[str]] = None,
    proxies: Optional[Dict[str, str]] = None,
    omit_bucket_width: bool = False,
) -> List[Dict]:
    """
    Paginate through an OpenAI usage endpoint and return formatted records.

    Args:
        logger:            Logger instance.
        collector:         The UsageCollector instance driving this fetch.
        headers:           HTTP headers including authorization.
        start_time:        Start of collection window as a Unix timestamp.
        end_time:          End of collection window as a Unix timestamp.
        model_filter:      Optional allowlist of model IDs; None means all models.
        proxies:           Optional proxy dict for requests.
        omit_bucket_width: When True, the ``bucket_width`` param is not sent
                           (used by VectorStoresCollector).

    Returns:
        List of formatted event dicts.  Error dicts have ``status="error"``.
    """
    endpoint_type = collector.endpoint_type
    all_records: List[Dict] = []
    next_page = None
    page_count = 0

    while True:
        page_count += 1
        if page_count > MAX_PAGES:
            logger.warning(
                f"Reached max page limit ({MAX_PAGES}) for {endpoint_type}. "
                "Remaining pages will be collected on the next run."
            )
            break

        logger.info(f"Fetching page {page_count} from {endpoint_type} endpoint")

        params: Dict = {
            "start_time": start_time,
            "end_time": end_time,
            "limit": 100,
        }
        if not omit_bucket_width:
            params["bucket_width"] = "1d"
        if collector.group_by:
            params["group_by"] = collector.group_by
        if next_page:
            params["page"] = next_page

        try:
            response = requests.get(
                collector.url,
                headers=headers,
                params=params,
                timeout=30,
                proxies=proxies or {},
            )

            now_ts = int(datetime.now(timezone.utc).timestamp())

            if response.status_code == 401:
                logger.error("Invalid or insufficient API key permissions (admin key required)")
                return [{
                    "_time": now_ts,
                    "endpoint_type": endpoint_type,
                    "error": "Invalid or insufficient API key permissions - admin key required for usage API",
                    "status_code": 401,
                    "status": "error",
                }]

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "unknown")
                logger.error(f"Rate limit hit. Retry after: {retry_after} seconds")
                return [{
                    "_time": now_ts,
                    "endpoint_type": endpoint_type,
                    "error": f"Rate limit exceeded. Retry after: {retry_after}",
                    "retry_after": retry_after,
                    "status_code": 429,
                    "status": "error",
                }]

            if response.status_code != 200:
                response_detail = sanitize_error_detail(response.text)
                logger.error(
                    f"API request failed with status {response.status_code}. "
                    f"Details: {response_detail}"
                )
                return [{
                    "_time": now_ts,
                    "endpoint_type": endpoint_type,
                    "error": f"API request failed with status {response.status_code}. Details: {response_detail}",
                    "status_code": response.status_code,
                    "status": "error",
                }]

            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response: {str(e)}")
                return [{
                    "_time": now_ts,
                    "endpoint_type": endpoint_type,
                    "error": f"Invalid JSON response: {str(e)}",
                    "status": "error",
                }]

            records = data.get("data", [])
            logger.info(f"Received {len(records)} records in page {page_count}")

            for record in records:
                if collector.supports_model_filter and model_filter is not None:
                    if record.get("model", "") not in model_filter:
                        continue

                formatted = collector.format_record(record)
                if formatted is not None:
                    all_records.append(formatted)

            has_more = data.get("has_more", False)
            next_page = data.get("next_page")

            if not has_more or not next_page:
                logger.info(f"Pagination complete for {endpoint_type}. Total pages: {page_count}")
                break

            logger.info(f"More pages available. Next page cursor: {next_page}")

        except requests.exceptions.Timeout:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            logger.error(f"Request timeout after 30 seconds for {endpoint_type}")
            return [{
                "_time": now_ts,
                "endpoint_type": endpoint_type,
                "error": "Request timeout after 30 seconds",
                "error_type": "Timeout",
                "status": "error",
            }]

        except requests.exceptions.ConnectionError as e:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            sanitized_error = sanitize_error_detail(str(e))
            logger.error(f"Network connection error for {endpoint_type}: {sanitized_error}")
            return [{
                "_time": now_ts,
                "endpoint_type": endpoint_type,
                "error": f"Network connection error: {sanitized_error}",
                "error_type": "ConnectionError",
                "status": "error",
            }]

        except Exception as e:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            sanitized_error = sanitize_error_detail(str(e))
            logger.error(f"Unexpected error fetching {endpoint_type} data: {sanitized_error}")
            return [{
                "_time": now_ts,
                "endpoint_type": endpoint_type,
                "error": f"Unexpected error: {sanitized_error}",
                "error_type": type(e).__name__,
                "status": "error",
            }]

    return all_records


def get_openai_usage_data(
    logger: logging.Logger,
    api_key: str,
    start_time: int,
    end_time: int,
    organization_id: Optional[str] = None,
    models: Optional[str] = None,
    proxies: Optional[Dict[str, str]] = None,
) -> List[Dict]:
    """
    Collect usage data from all registered OpenAI usage collectors.

    Args:
        logger:          Logger instance.
        api_key:         OpenAI API key (requires admin permissions).
        start_time:      Start of collection window as a Unix timestamp (inclusive).
        end_time:        End of collection window as a Unix timestamp (exclusive).
        organization_id: Optional OpenAI organization ID.
        models:          Comma-separated model IDs, or '*' / empty for all models.
                         Model IDs not in the dropdown can be supplied here.
        proxies:         Optional proxy dict from get_proxy_settings().

    Returns:
        List of usage event dicts.  Events with ``status="error"`` indicate
        API or network failures for a specific collector; other collectors
        continue to run.
    """
    if requests is None:
        logger.error(
            "requests library is not installed. "
            "Please ensure requests>=2.31.0 is in requirements.txt"
        )
        return [{
            "_time": int(datetime.now(timezone.utc).timestamp()),
            "error": "requests library not available",
            "error_type": "ImportError",
            "status": "error",
        }]

    start_dt = datetime.fromtimestamp(start_time, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(end_time, tz=timezone.utc)
    logger.info(
        f"Fetching OpenAI usage data: {start_dt.isoformat()} to {end_dt.isoformat()} "
        f"(Unix: {start_time} to {end_time})"
    )

    model_filter: Optional[List[str]] = None
    if models and models.strip():
        candidates = [m.strip() for m in models.split(",") if m.strip()]
        if "*" not in candidates:
            model_filter = candidates

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if organization_id:
        headers["OpenAI-Organization"] = organization_id
        logger.info(f"Using organization ID: {organization_id}")

    all_usage_data: List[Dict] = []

    for collector in COLLECTOR_REGISTRY:
        logger.info(f"Fetching {collector.endpoint_type} usage data from {collector.url}")
        try:
            records = collector.collect(
                logger=logger,
                headers=headers,
                start_time=start_time,
                end_time=end_time,
                model_filter=model_filter,
                proxies=proxies,
            )
            all_usage_data.extend(records)
            logger.info(f"Collected {len(records)} {collector.endpoint_type} usage records")
        except Exception as e:
            sanitized_error = sanitize_error_detail(str(e))
            logger.error(f"Error fetching {collector.endpoint_type} usage data: {sanitized_error}")
            now_ts = int(datetime.now(timezone.utc).timestamp())
            all_usage_data.append({
                "_time": now_ts,
                "endpoint_type": collector.endpoint_type,
                "error": sanitized_error,
                "error_type": type(e).__name__,
                "status": "error",
            })

    if not all_usage_data:
        logger.warning("No usage data collected from any endpoint")
        now_ts = int(datetime.now(timezone.utc).timestamp())
        return [{
            "_time": now_ts,
            "status": "no_data",
            "message": "No usage data available for the specified time range",
            "start_time": start_time,
            "end_time": end_time,
        }]

    logger.info(f"Successfully collected {len(all_usage_data)} total usage records")
    return all_usage_data


# ---------------------------------------------------------------------------
# Splunk modular input entry points
# ---------------------------------------------------------------------------

def validate_input(definition: smi.ValidationDefinition):
    return


def stream_events(inputs: smi.InputDefinition, event_writer: smi.EventWriter):
    """
    Stream OpenAI usage events to Splunk.

    Time window logic (per input stanza):
      - First run, start_date configured : window begins at start_date (midnight UTC)
      - First run, no start_date         : window begins 24 hours ago
      - Subsequent runs                  : window begins where the last successful
                                           run ended (read from checkpoint file)
      - end_time is always "now" (UTC)

    The checkpoint is only advanced after at least one non-error event is
    successfully written.  If every API call returns an error the checkpoint
    stays unchanged so the same window is retried on the next poll cycle.
    """
    for input_name, input_item in inputs.inputs.items():
        normalized_input_name = input_name.split("/")[-1]
        logger = logger_for_input(normalized_input_name)
        try:
            session_key = inputs.metadata["session_key"]

            log_level = conf_manager.get_log_level(
                logger=logger,
                session_key=session_key,
                app_name=ADDON_NAME,
                conf_name="ta-openai-usage_settings",
            )
            logger.setLevel(log_level)
            log.modular_input_start(logger, normalized_input_name)

            # ----------------------------------------------------------------
            # Checkpoint setup
            # ----------------------------------------------------------------
            checkpoint_dir = inputs.metadata.get("checkpoint_dir", "")
            if not checkpoint_dir:
                checkpoint_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "var", "modinputs", ADDON_NAME,
                )
            os.makedirs(checkpoint_dir, exist_ok=True)

            ckpt = checkpointer.FileCheckpointer(checkpoint_dir)
            checkpoint_key = f"openai_usage_{normalized_input_name}"

            # ----------------------------------------------------------------
            # Determine collection window
            # ----------------------------------------------------------------
            now_utc = datetime.now(timezone.utc)
            end_time = int(now_utc.timestamp())

            last_end_time = ckpt.get(checkpoint_key)

            if last_end_time is not None:
                start_time = int(last_end_time)
                logger.info(
                    f"Resuming from checkpoint: "
                    f"{datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat()}"
                )
            else:
                start_date = input_item.get("start_date", "").strip()
                if start_date:
                    try:
                        start_time = int(
                            datetime.strptime(start_date, "%Y-%m-%d")
                            .replace(tzinfo=timezone.utc)
                            .timestamp()
                        )
                        logger.info(f"First run: using configured start_date {start_date}")
                    except ValueError:
                        logger.warning(
                            f"Invalid start_date '{start_date}'. Defaulting to last 24 hours."
                        )
                        start_time = int((now_utc - timedelta(days=1)).timestamp())
                else:
                    start_time = int((now_utc - timedelta(days=1)).timestamp())
                    logger.info(
                        "First run: no checkpoint or start_date found, defaulting to last 24 hours"
                    )

            if start_time >= end_time:
                logger.info(
                    "Collection window is zero-width (start_time >= end_time). "
                    "Skipping this run."
                )
                log.modular_input_end(logger, normalized_input_name)
                continue

            # ----------------------------------------------------------------
            # Account credentials and proxy
            # ----------------------------------------------------------------
            account_name = input_item.get("account")
            account_details = get_account_details(session_key, account_name)
            api_key = account_details.get("api_key")
            organization_id = account_details.get("organization_id")
            proxies = get_proxy_settings(session_key, logger)

            # Merge multiselect models with any additional free-text model IDs
            models = input_item.get("models", "")
            custom_models_str = input_item.get("custom_models", "").strip()
            if custom_models_str:
                extra_ids = [m.strip() for m in custom_models_str.split(",") if m.strip()]
                if extra_ids:
                    if models and models.strip() and models.strip() != "*":
                        models = f"{models},{','.join(extra_ids)}"
                    # If '*' (all models) is selected, custom_models has no further
                    # effect since the filter is already open — no action needed.
                    logger.info(f"Including additional model IDs from custom_models: {extra_ids}")

            logger.info(f"Fetching OpenAI usage data for account: {account_name}")
            if organization_id:
                logger.info(f"Using organization ID: {organization_id}")
            if models:
                logger.info(f"Tracking models: {models}")

            # ----------------------------------------------------------------
            # Fetch and write events
            # ----------------------------------------------------------------
            usage_data = get_openai_usage_data(
                logger=logger,
                api_key=api_key,
                start_time=start_time,
                end_time=end_time,
                organization_id=organization_id,
                models=models,
                proxies=proxies,
            )

            sourcetype = "openai:usage"
            events_written = 0
            for event_data in usage_data:
                event_data["input_name"] = normalized_input_name
                event_data["account"] = account_name

                event_writer.write_event(
                    smi.Event(
                        data=json.dumps(event_data, ensure_ascii=False, default=str),
                        index=input_item.get("index"),
                        sourcetype=sourcetype,
                        time=event_data.get("_time"),
                    )
                )

                if event_data.get("status") != "error":
                    events_written += 1

            # ----------------------------------------------------------------
            # Advance checkpoint only on (partial) success
            # ----------------------------------------------------------------
            if events_written > 0:
                ckpt.update(checkpoint_key, end_time)
                logger.info(
                    f"Checkpoint updated to "
                    f"{datetime.fromtimestamp(end_time, tz=timezone.utc).isoformat()}"
                )
            else:
                logger.warning(
                    "No successful events written; checkpoint NOT advanced. "
                    "The same window will be retried on the next run."
                )

            log.events_ingested(
                logger,
                input_name,
                sourcetype,
                events_written,
                input_item.get("index"),
                account=account_name,
            )
            log.modular_input_end(logger, normalized_input_name)

        except Exception as e:
            log.log_exception(
                logger,
                e,
                "openai_usage_error",
                msg_before=(
                    f"Exception raised while ingesting OpenAI usage data "
                    f"for {normalized_input_name}: "
                ),
            )
