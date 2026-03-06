TA-openai-usage - OpenAI API Usage Monitor
==========================================
Version: 1.0.0
Sourcetype: openai:usage

OVERVIEW
--------
This Technology Add-on (TA) collects API usage metrics from the OpenAI
Organization Usage API and indexes them into Splunk. It tracks token
consumption, request counts, and cached-token data broken down by model
and endpoint type (completions, embeddings) using daily buckets.

Supported OpenAI model families:
  - GPT-5 series    (gpt-5.4, gpt-5.4-pro, gpt-5.2, gpt-5.1, gpt-5,
                     gpt-5-mini, gpt-5-nano)
  - Reasoning       (o3, o4-mini, o3-mini, o1)
  - GPT-4.1 series  (gpt-4.1, gpt-4.1-mini, gpt-4.1-nano)
  - GPT-4o series   (gpt-4o, gpt-4o-mini)
  - Embeddings      (text-embedding-3-large, text-embedding-3-small,
                     text-embedding-ada-002)
  - Legacy          (gpt-4-turbo, gpt-4, gpt-3.5-turbo)

REQUIREMENTS
------------
  - Splunk Enterprise 9.x or Splunk Cloud
  - Python 3.7+
  - An OpenAI API key with admin/organization-level permissions
    (required to access the Organization Usage API)

INSTALLATION
------------
1. Extract or upload TA-openai-usage to $SPLUNK_HOME/etc/apps/
2. Restart Splunk
3. Navigate to Apps > OpenAI API Usage Monitor

CONFIGURATION
-------------
Step 1 - Add an Account (Configuration > Accounts tab):
  - Name:            A unique label for this credential set
  - OpenAI API Key:  Stored encrypted via Splunk's credential store
  - Organization ID: Optional - required if the key belongs to an org

Step 2 - Create an Input (Inputs > Create New Input):
  - Name:            Unique stanza identifier
  - Interval:        Polling frequency in seconds (300-86400, default 3600)
  - Index:           Destination Splunk index
  - Account:         Select from configured accounts
  - Start Date:      Optional historical backfill start (YYYY-MM-DD)
  - Models to Track: Multi-select filter; defaults to All Models (*)

CHECKPOINTING
-------------
The add-on persists the last successful collection end time to a
checkpoint file ($SPLUNK_HOME/var/lib/splunk/modinputs/TA-openai-usage/).
On subsequent runs the collection window starts exactly where the
previous run ended, preventing duplicate events. If a run fails
entirely the checkpoint is not advanced and the same window is retried.

DATA COLLECTED
--------------
Each Splunk event (sourcetype=openai:usage) represents one model's
usage within a daily bucket and includes:
  - _time               Unix timestamp of the bucket start
  - timestamp           ISO-8601 UTC timestamp
  - endpoint_type       "completions" or "embeddings"
  - model               Model ID (e.g. "gpt-5.4")
  - input_tokens        Input token count for the bucket
  - output_tokens       Output token count for the bucket
  - cached_tokens       Cached/prompt-cache token count
  - requests            Number of API requests in the bucket
  - project_id          OpenAI project ID (if available)
  - api_key_id          API key identifier (if available)
  - input_name          Splunk input stanza name
  - account             Configured account name

SAMPLE SEARCHES
---------------
All usage:
  index=main sourcetype="openai:usage" status!=error

Token usage by model:
  index=main sourcetype="openai:usage" status!=error
  | stats sum(input_tokens) as input sum(output_tokens) as output
          sum(requests) as calls by model
  | eval total_tokens=input+output | sort -total_tokens

Daily trend:
  index=main sourcetype="openai:usage" status!=error
  | timechart span=1d sum(input_tokens) as input sum(output_tokens) as output

Errors:
  index=main sourcetype="openai:usage" status=error
  | table _time endpoint_type error_type status_code error

TROUBLESHOOTING
---------------
Internal logs:
  index=_internal source=*ta-openai-usage* OR source=*openai_usage*

Common issues:
  401 error  - API key lacks admin/org-level permissions
  429 error  - Rate limit hit; the TA will retry on the next interval
  No data    - Verify the account is configured and the key is valid;
               check that the start_date is not in the future

LICENSE
-------
See LICENSES/LICENSE.txt

SUPPORT
-------
UCC framework docs : https://splunk.github.io/addonfactory-ucc-generator/
OpenAI API docs    : https://platform.openai.com/docs/api-reference/usage
Splunk dev docs    : https://dev.splunk.com
