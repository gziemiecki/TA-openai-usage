import json
import logging
import os
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
# Maximum pages to fetch per endpoint per run to bound execution time
MAX_PAGES = 50

def logger_for_input(input_name: str) -> logging.Logger:
    return log.Logs().get_logger(f"{ADDON_NAME.lower()}_{input_name}")


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
        "organization_id": account_data.get("organization_id", "")
    }


def get_proxy_settings(session_key: str, logger: logging.Logger) -> Optional[Dict[str, str]]:
    """
    Read proxy configuration written by UCC's proxyTab from the add-on
    settings conf file and return a dict suitable for passing as the
    ``proxies`` argument to ``requests.get()``.

    Returns None when the proxy is disabled or not configured, so callers
    can safely pass the result directly to requests without extra checks.
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
        logger.warning(f"Could not read proxy settings; proceeding without proxy: {e}")
        return None


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
    Fetch usage data from OpenAI Organization Usage API.

    Args:
        logger: Logger instance
        api_key: OpenAI API key (requires admin permissions)
        start_time: Start of collection window as a Unix timestamp (inclusive)
        end_time: End of collection window as a Unix timestamp (exclusive)
        organization_id: Optional OpenAI organization ID
        models: Comma-separated list of models to track, or '*' for all
        proxies: Optional dict of proxy URIs keyed by scheme, e.g.
                 {"http": "http://host:port", "https": "http://host:port"}.
                 Pass the return value of get_proxy_settings() directly.

    Returns:
        List of usage data dictionaries formatted for Splunk ingestion.
        Records with status="error" indicate API or network failures.
    """
    if requests is None:
        logger.error("requests library is not installed. Please ensure requests>=2.31.0 is in requirements.txt")
        return [{
            "_time": int(datetime.now(timezone.utc).timestamp()),
            "error": "requests library not available",
            "error_type": "ImportError",
            "status": "error"
        }]

    start_dt = datetime.fromtimestamp(start_time, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(end_time, tz=timezone.utc)
    logger.info(
        f"Fetching OpenAI usage data: {start_dt.isoformat()} to {end_dt.isoformat()} "
        f"(Unix: {start_time} to {end_time})"
    )

    # Parse models filter
    model_filter = None
    if models and models.strip():
        model_filter = [m.strip() for m in models.split(",") if m.strip()]
        if "*" in model_filter:
            model_filter = None  # All models
    
    # Prepare headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    if organization_id:
        headers["OpenAI-Organization"] = organization_id
        logger.info(f"Using organization ID: {organization_id}")
    
    all_usage_data = []
    
    # API endpoints to fetch from
    endpoints = [
        {
            "url": "https://api.openai.com/v1/organization/usage/completions",
            "type": "completions"
        },
        {
            "url": "https://api.openai.com/v1/organization/usage/embeddings",
            "type": "embeddings"
        }
    ]
    
    # Fetch data from each endpoint
    for endpoint_info in endpoints:
        endpoint_url = endpoint_info["url"]
        endpoint_type = endpoint_info["type"]
        
        logger.info(f"Fetching {endpoint_type} usage data from {endpoint_url}")
        
        try:
            usage_records = fetch_usage_with_pagination(
                logger=logger,
                url=endpoint_url,
                headers=headers,
                start_time=start_time,
                end_time=end_time,
                endpoint_type=endpoint_type,
                model_filter=model_filter,
                proxies=proxies,
            )
            
            all_usage_data.extend(usage_records)
            logger.info(f"Collected {len(usage_records)} {endpoint_type} usage records")
            
        except Exception as e:
            logger.error(f"Error fetching {endpoint_type} usage data: {str(e)}")
            # Add error event but continue with remaining endpoints
            now_ts = int(datetime.now(timezone.utc).timestamp())
            all_usage_data.append({
                "_time": now_ts,
                "endpoint_type": endpoint_type,
                "error": str(e),
                "error_type": type(e).__name__,
                "status": "error"
            })

    if not all_usage_data:
        logger.warning("No usage data collected from any endpoint")
        now_ts = int(datetime.now(timezone.utc).timestamp())
        return [{
            "_time": now_ts,
            "status": "no_data",
            "message": "No usage data available for the specified time range",
            "start_time": start_time,
            "end_time": end_time
        }]

    logger.info(f"Successfully collected {len(all_usage_data)} total usage records")
    return all_usage_data


def fetch_usage_with_pagination(
    logger: logging.Logger,
    url: str,
    headers: Dict[str, str],
    start_time: int,
    end_time: int,
    endpoint_type: str,
    model_filter: Optional[List[str]] = None,
    proxies: Optional[Dict[str, str]] = None,
) -> List[Dict]:
    """
    Fetch usage data with pagination support.

    Args:
        logger: Logger instance
        url: API endpoint URL
        headers: HTTP headers including authorization
        start_time: Start Unix timestamp
        end_time: End Unix timestamp
        endpoint_type: Type of endpoint (completions or embeddings)
        model_filter: Optional list of models to filter
        proxies: Optional proxy dict passed through to requests.get()

    Returns:
        List of formatted usage records
    """
    all_records = []
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
        
        # Build request parameters
        params = {
            "start_time": start_time,
            "end_time": end_time,
            "bucket_width": "1d",
            "group_by": ["model"],
            "limit": 100
        }
        
        # Add next_page cursor if available
        if next_page:
            params["page"] = next_page
        
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=30,
                proxies=proxies or {},
            )
            
            # Handle specific HTTP error codes
            now_ts = int(datetime.now(timezone.utc).timestamp())
            if response.status_code == 401:
                logger.error("Invalid or insufficient API key permissions (admin key required)")
                return [{
                    "_time": now_ts,
                    "endpoint_type": endpoint_type,
                    "error": "Invalid or insufficient API key permissions - admin key required for usage API",
                    "status_code": 401,
                    "status": "error"
                }]

            elif response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "unknown")
                logger.error(f"Rate limit hit. Retry after: {retry_after} seconds")
                return [{
                    "_time": now_ts,
                    "endpoint_type": endpoint_type,
                    "error": f"Rate limit exceeded. Retry after: {retry_after}",
                    "retry_after": retry_after,
                    "status_code": 429,
                    "status": "error"
                }]

            elif response.status_code != 200:
                logger.error(f"API request failed with status {response.status_code}: {response.text}")
                return [{
                    "_time": now_ts,
                    "endpoint_type": endpoint_type,
                    "error": f"API request failed: {response.text}",
                    "status_code": response.status_code,
                    "status": "error"
                }]

            # Parse response
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response: {str(e)}")
                return [{
                    "_time": now_ts,
                    "endpoint_type": endpoint_type,
                    "error": f"Invalid JSON response: {str(e)}",
                    "status": "error"
                }]
            
            # Extract usage records from response
            records = data.get("data", [])
            logger.info(f"Received {len(records)} records in page {page_count}")
            
            # Process each usage record
            for record in records:
                # Apply model filter if specified
                model_name = record.get("model", "unknown")
                if model_filter and model_name not in model_filter:
                    continue
                
                # Format record for Splunk ingestion
                now_ts = int(datetime.now(timezone.utc).timestamp())
                record_ts = record.get("start_time", now_ts)
                formatted_record = {
                    "_time": record_ts,
                    "timestamp": datetime.fromtimestamp(record_ts, tz=timezone.utc).isoformat(),
                    "endpoint_type": endpoint_type,
                    "model": model_name,
                    "input_tokens": record.get("input_tokens", 0),
                    "output_tokens": record.get("output_tokens", 0),
                    "cached_tokens": record.get("input_cached_tokens", 0),
                    "requests": record.get("num_model_requests", 0),
                }
                
                # Add optional fields if present
                if "project_id" in record:
                    formatted_record["project_id"] = record["project_id"]
                
                if "api_key_id" in record:
                    formatted_record["api_key_id"] = record["api_key_id"]
                
                if "model_id" in record:
                    formatted_record["model_id"] = record["model_id"]
                
                # Add bucket information
                if "bucket_start_time" in record:
                    formatted_record["bucket_start_time"] = record["bucket_start_time"]
                
                if "bucket_end_time" in record:
                    formatted_record["bucket_end_time"] = record["bucket_end_time"]
                
                all_records.append(formatted_record)
            
            # Check for pagination
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
                "status": "error"
            }]

        except requests.exceptions.ConnectionError as e:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            logger.error(f"Network connection error for {endpoint_type}: {str(e)}")
            return [{
                "_time": now_ts,
                "endpoint_type": endpoint_type,
                "error": f"Network connection error: {str(e)}",
                "error_type": "ConnectionError",
                "status": "error"
            }]

        except Exception as e:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            logger.error(f"Unexpected error fetching {endpoint_type} data: {str(e)}")
            return [{
                "_time": now_ts,
                "endpoint_type": endpoint_type,
                "error": f"Unexpected error: {str(e)}",
                "error_type": type(e).__name__,
                "status": "error"
            }]
    
    return all_records


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

            # Set log level from configuration
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
                # Fall back to a path alongside the add-on if Splunk doesn't
                # provide the directory (e.g. during local testing).
                checkpoint_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "var", "modinputs", ADDON_NAME,
                )
            os.makedirs(checkpoint_dir, exist_ok=True)

            ckpt = checkpointer.FileCheckpointer(checkpoint_dir)
            # Key is unique per input stanza so multiple inputs don't collide
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
                # First ever run for this input stanza
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
                    logger.info("First run: no checkpoint or start_date found, defaulting to last 24 hours")

            # Safety guard: never request a window where start >= end
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
            models = input_item.get("models")
            proxies = get_proxy_settings(session_key, logger)

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
            # Advance checkpoint only on (partial) success.
            # If every returned event is an error, leave the checkpoint alone
            # so the same window is retried on the next poll cycle.
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
                msg_before=f"Exception raised while ingesting OpenAI usage data for {normalized_input_name}: ",
            )
