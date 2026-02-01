import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import import_declare_test
from solnlib import conf_manager, log
from splunklib import modularinput as smi

try:
    import requests
except ImportError:
    requests = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


ADDON_NAME = "TA-openai-usage"

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


def get_openai_usage_data(
    logger: logging.Logger, 
    api_key: str, 
    organization_id: Optional[str] = None,
    start_date: Optional[str] = None,
    models: Optional[str] = None
) -> List[Dict]:
    """
    Fetch usage data from OpenAI Organization Usage API.
    
    Args:
        logger: Logger instance
        api_key: OpenAI API key (requires admin permissions)
        organization_id: Optional OpenAI organization ID
        start_date: Optional start date in YYYY-MM-DD format
        models: Comma-separated list of models to track, or '*' for all
        
    Returns:
        List of usage data dictionaries formatted for Splunk
    """
    if requests is None:
        logger.error("requests library is not installed. Please ensure requests>=2.31.0 is in requirements.txt")
        return [{
            "timestamp": datetime.now().isoformat(),
            "error": "requests library not available",
            "error_type": "ImportError",
            "status": "error"
        }]
    
    logger.info("Fetching OpenAI organization usage data")
    
    # Parse models filter
    model_filter = None
    if models and models.strip():
        model_filter = [m.strip() for m in models.split(",") if m.strip()]
        if "*" in model_filter:
            model_filter = None  # All models
    
    # Determine date range and convert to Unix timestamps
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            logger.warning(f"Invalid start_date format: {start_date}. Using last 24 hours.")
            start_dt = datetime.now() - timedelta(days=1)
    else:
        # Default to last 24 hours if no start date specified
        start_dt = datetime.now() - timedelta(days=1)
    
    end_dt = datetime.now()
    
    # Convert to Unix timestamps
    start_time = int(start_dt.timestamp())
    end_time = int(end_dt.timestamp())
    
    logger.info(f"Collecting usage data from {start_dt.date()} to {end_dt.date()} (Unix: {start_time} to {end_time})")
    
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
                model_filter=model_filter
            )
            
            all_usage_data.extend(usage_records)
            logger.info(f"Collected {len(usage_records)} {endpoint_type} usage records")
            
        except Exception as e:
            logger.error(f"Error fetching {endpoint_type} usage data: {str(e)}")
            # Add error event but continue with other endpoints
            error_event = {
                "_time": int(datetime.now().timestamp()),
                "timestamp": datetime.now().isoformat(),
                "endpoint_type": endpoint_type,
                "error": str(e),
                "error_type": type(e).__name__,
                "status": "error"
            }
            all_usage_data.append(error_event)
    
    if not all_usage_data:
        logger.warning("No usage data collected from any endpoint")
        # Return a status event
        return [{
            "_time": int(datetime.now().timestamp()),
            "timestamp": datetime.now().isoformat(),
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
    model_filter: Optional[List[str]] = None
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
        
    Returns:
        List of formatted usage records
    """
    all_records = []
    next_page = None
    page_count = 0
    
    while True:
        page_count += 1
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
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            # Handle specific HTTP error codes
            if response.status_code == 401:
                logger.error("Invalid or insufficient API key permissions (admin key required)")
                return [{
                    "_time": int(datetime.now().timestamp()),
                    "timestamp": datetime.now().isoformat(),
                    "endpoint_type": endpoint_type,
                    "error": "Invalid or insufficient API key permissions - admin key required for usage API",
                    "status_code": 401,
                    "status": "error"
                }]
            
            elif response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "unknown")
                logger.error(f"Rate limit hit. Retry after: {retry_after} seconds")
                return [{
                    "_time": int(datetime.now().timestamp()),
                    "timestamp": datetime.now().isoformat(),
                    "endpoint_type": endpoint_type,
                    "error": f"Rate limit exceeded. Retry after: {retry_after}",
                    "retry_after": retry_after,
                    "status_code": 429,
                    "status": "error"
                }]
            
            elif response.status_code != 200:
                logger.error(f"API request failed with status {response.status_code}: {response.text}")
                return [{
                    "_time": int(datetime.now().timestamp()),
                    "timestamp": datetime.now().isoformat(),
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
                    "_time": int(datetime.now().timestamp()),
                    "timestamp": datetime.now().isoformat(),
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
                formatted_record = {
                    "_time": record.get("start_time", int(datetime.now().timestamp())),
                    "timestamp": datetime.fromtimestamp(record.get("start_time", int(datetime.now().timestamp()))).isoformat(),
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
            logger.error(f"Request timeout after 30 seconds for {endpoint_type}")
            return [{
                "_time": int(datetime.now().timestamp()),
                "timestamp": datetime.now().isoformat(),
                "endpoint_type": endpoint_type,
                "error": "Request timeout after 30 seconds",
                "error_type": "Timeout",
                "status": "error"
            }]
        
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Network connection error for {endpoint_type}: {str(e)}")
            return [{
                "_time": int(datetime.now().timestamp()),
                "timestamp": datetime.now().isoformat(),
                "endpoint_type": endpoint_type,
                "error": f"Network connection error: {str(e)}",
                "error_type": "ConnectionError",
                "status": "error"
            }]
        
        except Exception as e:
            logger.error(f"Unexpected error fetching {endpoint_type} data: {str(e)}")
            return [{
                "_time": int(datetime.now().timestamp()),
                "timestamp": datetime.now().isoformat(),
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
    
    inputs.inputs is a Python dictionary object like:
    {
      "openai_usage://<input_name>": {
        "account": "<account_name>",
        "disabled": "0",
        "host": "$decideOnStartup",
        "index": "<index_name>",
        "interval": "<interval_value>",
        "start_date": "<YYYY-MM-DD>",  # Optional
        "models": "gpt-4,gpt-3.5-turbo",  # Optional
        "python.version": "python3",
      },
    }
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
            
            # Get account details (API key and organization ID)
            account_name = input_item.get("account")
            account_details = get_account_details(session_key, account_name)
            api_key = account_details.get("api_key")
            organization_id = account_details.get("organization_id")
            
            # Get optional configuration parameters
            start_date = input_item.get("start_date")
            models = input_item.get("models")
            
            logger.info(f"Fetching OpenAI usage data for account: {account_name}")
            if organization_id:
                logger.info(f"Using organization ID: {organization_id}")
            if start_date:
                logger.info(f"Start date: {start_date}")
            if models:
                logger.info(f"Tracking models: {models}")
            
            # Fetch usage data from OpenAI API
            usage_data = get_openai_usage_data(
                logger=logger,
                api_key=api_key,
                organization_id=organization_id,
                start_date=start_date,
                models=models
            )
            
            # Write events to Splunk
            sourcetype = "openai:usage"
            for event_data in usage_data:
                # Add metadata to each event
                event_data["input_name"] = normalized_input_name
                event_data["account"] = account_name
                
                event_writer.write_event(
                    smi.Event(
                        data=json.dumps(event_data, ensure_ascii=False, default=str),
                        index=input_item.get("index"),
                        sourcetype=sourcetype,
                    )
                )
            
            log.events_ingested(
                logger,
                input_name,
                sourcetype,
                len(usage_data),
                input_item.get("index"),
                account=account_name,
            )
            log.modular_input_end(logger, normalized_input_name)
            
        except Exception as e:
            log.log_exception(
                logger, 
                e, 
                "openai_usage_error", 
                msg_before=f"Exception raised while ingesting OpenAI usage data for {normalized_input_name}: "
            )
