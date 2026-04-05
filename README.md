# TA-openai-usage - OpenAI API Usage Monitor

A Splunk Technology Add-on for monitoring OpenAI API usage across all billing
dimensions, built using the UCC (Universal Configuration Console) framework.

## Overview

This add-on collects and indexes OpenAI organization-level usage data from
every billable endpoint, including:

- **Completions** — token usage and request counts for chat/text models
- **Embeddings** — token usage for embedding models
- **Images** — image generation counts and sizes (GPT Image 1, DALL-E)
- **Audio Transcription** — Whisper speech-to-text duration in seconds
- **Audio Speech** — TTS character counts
- **Code Interpreter** — session counts for Agents API usage
- **Web Search** — query counts and context tokens
- **Vector Stores** — storage snapshots in bytes (GB·day billing)
- **Fine-Tuning** — training token usage and job counts

## Version

**Version:** 1.0.0

## Installation

1. Copy the built add-on from `output/TA-openai-usage/` to your Splunk apps directory:
   - Splunk Cloud: Upload via the Splunk Web UI
   - Splunk Enterprise: `$SPLUNK_HOME/etc/apps/`

2. Restart Splunk:
   ```bash
   $SPLUNK_HOME/bin/splunk restart
   ```

## Configuration

### 1. Configure Account

Navigate to the add-on's configuration page and add an OpenAI account:

- **Account Name:** A unique identifier for this account
- **OpenAI API Key:** Your OpenAI API key (encrypted and stored securely).
  The key must have **admin-level** Organization API access to read usage data.
- **Organization ID:** (Optional) Your OpenAI Organization ID

### 2. Configure Input

Create a new data input with the following parameters:

- **Name:** Unique name for this input
- **Interval:** Polling interval in seconds (default: 3600)
  - Minimum: 300 seconds (5 minutes)
  - Maximum: 86400 seconds (24 hours)
- **Index:** Splunk index for storing usage data (default: main)
- **Account:** Select the configured OpenAI account
- **Start Date:** (Optional) Start date for collecting historical data (YYYY-MM-DD format)
- **Models to Track:** Select which models to monitor (default: All Models).
  Model IDs are matched against the `model` field returned by the OpenAI Usage
  API. When in doubt, use **All Models** and filter in Splunk searches.

  | Model | Series | Endpoint types |
  |---|---|---|
  | All Models (*) | — | All |
  | GPT-5.4 | GPT-5 Frontier | completions |
  | GPT-5.4 Pro | GPT-5 Frontier | completions |
  | GPT-5.2 | GPT-5 Frontier | completions |
  | GPT-5.1 | GPT-5 Frontier | completions |
  | GPT-5 | GPT-5 Frontier | completions |
  | GPT-5 mini | GPT-5 Efficient | completions |
  | GPT-5 nano | GPT-5 Efficient | completions |
  | o3 | Reasoning | completions |
  | o4-mini | Reasoning | completions |
  | o3-mini | Reasoning | completions |
  | o1 | Reasoning | completions |
  | GPT-4.1 | GPT-4.1 | completions |
  | GPT-4.1 mini | GPT-4.1 | completions |
  | GPT-4.1 nano | GPT-4.1 | completions |
  | GPT-4o | GPT-4o | completions, fine_tuning |
  | GPT-4o mini | GPT-4o | completions, fine_tuning |
  | text-embedding-3-large | Embeddings | embeddings |
  | text-embedding-3-small | Embeddings | embeddings |
  | text-embedding-ada-002 | Embeddings | embeddings |
  | GPT Image 1 | Images | images |
  | DALL-E 3 | Images | images |
  | DALL-E 2 | Images | images |
  | Whisper 1 | Audio | audio_transcription |
  | TTS-1 | Audio | audio_speech |
  | TTS-1 HD | Audio | audio_speech |
  | GPT-4 Turbo (Legacy) | Legacy | completions |
  | GPT-4 (Legacy) | Legacy | completions |
  | GPT-3.5 Turbo (Legacy) | Legacy | completions, fine_tuning |

- **Additional Model IDs:** Free-text field for model IDs not in the dropdown
  above (e.g. `gpt-4o-2024-11-20`, `ft:gpt-4o:my-org:my-model:abc123`).
  Enter as a comma-separated list. These are merged with the **Models to Track**
  selection. If **All Models** is selected this field has no effect (all models
  already pass through).

## Data Collection

### Sourcetype

All events are indexed with sourcetype `openai:usage`.

### Event Schema by Endpoint Type

Every event includes these common fields:

| Field | Description |
|---|---|
| `_time` | Bucket start time as a Unix timestamp |
| `timestamp` | Bucket start time in ISO 8601 format |
| `endpoint_type` | Which collector produced this event (see table below) |
| `model` | Model ID as returned by the API (present on model-grouped endpoints) |
| `input_name` | Name of the Splunk data input that collected this event |
| `account` | Name of the OpenAI account used |
| `project_id` | OpenAI project ID (when returned by the API) |
| `api_key_id` | OpenAI API key ID (when returned by the API) |
| `bucket_start_time` | Start of the daily bucket as a Unix timestamp |
| `bucket_end_time` | End of the daily bucket as a Unix timestamp |

Endpoint-specific fields:

#### `completions`
| Field | Description |
|---|---|
| `input_tokens` | Total input tokens consumed |
| `output_tokens` | Total output tokens generated |
| `cached_tokens` | Input tokens served from prompt cache |
| `num_model_requests` | Number of API requests |

#### `embeddings`
| Field | Description |
|---|---|
| `input_tokens` | Total tokens embedded |
| `num_model_requests` | Number of API requests |

#### `images`
| Field | Description |
|---|---|
| `num_images` | Number of images generated |
| `num_model_requests` | Number of API requests |
| `size` | Image dimensions (e.g. `1024x1024`) |
| `quality` | Image quality setting (e.g. `standard`, `hd`) |

#### `audio_transcription` (Whisper)
| Field | Description |
|---|---|
| `input_seconds` | Audio duration transcribed in seconds |
| `num_model_requests` | Number of API requests |

#### `audio_speech` (TTS)
| Field | Description |
|---|---|
| `num_characters` | Number of characters synthesized |
| `num_model_requests` | Number of API requests |

#### `code_interpreter`
| Field | Description |
|---|---|
| `num_sessions` | Number of Code Interpreter sessions |

#### `web_search`
| Field | Description |
|---|---|
| `num_queries` | Number of web search queries |
| `context_tokens` | Tokens consumed by search context |

#### `vector_stores`
| Field | Description |
|---|---|
| `bytes_stored` | Bytes of vector store data stored (snapshot, not request-based) |

#### `fine_tuning`
| Field | Description |
|---|---|
| `input_tokens` | Training input tokens consumed |
| `output_tokens` | Training output tokens generated |
| `num_model_requests` | Number of fine-tuning jobs |
| `training_steps` | Number of training steps (when returned by the API) |

Error events include `"status": "error"` with `error`, `error_type`, and
optionally `status_code` and `retry_after` fields.

## Cost Enrichment

This add-on ships with a cost lookup table at
`lookups/openai_model_costs.csv`.  Use it to estimate spend directly in
Splunk searches without leaving the platform.

### Lookup fields

| Column | Description |
|---|---|
| `model` | Model ID (matches the `model` event field; `*` for non-model endpoints) |
| `endpoint_type` | Endpoint type (matches the `endpoint_type` event field) |
| `input_unit` | The event field that represents the primary billable quantity |
| `cost_per_input_unit_usd` | USD cost per one unit of `input_unit` |
| `output_unit` | Secondary billable quantity field (output tokens; empty if not applicable) |
| `cost_per_output_unit_usd` | USD cost per one unit of `output_unit` |
| `notes` | Human-readable pricing note |

### Cost enrichment pattern

```spl
index=* sourcetype="openai:usage" endpoint_type=completions status!=error
| lookup openai_model_costs model endpoint_type
    OUTPUT cost_per_input_unit_usd cost_per_output_unit_usd
| eval estimated_cost_usd =
    round((input_tokens * cost_per_input_unit_usd) +
          (output_tokens * cost_per_output_unit_usd), 6)
| timechart span=1d sum(estimated_cost_usd) as daily_cost_usd by model
```

For other endpoint types, replace the metric field to match the billing unit:

| `endpoint_type` | Billable field | Cost expression |
|---|---|---|
| `completions` | `input_tokens`, `output_tokens` | `(input_tokens * cost_per_input_unit_usd) + (output_tokens * cost_per_output_unit_usd)` |
| `embeddings` | `input_tokens` | `input_tokens * cost_per_input_unit_usd` |
| `images` | `num_images` | `num_images * cost_per_input_unit_usd` |
| `audio_transcription` | `input_seconds` | `input_seconds * cost_per_input_unit_usd` |
| `audio_speech` | `num_characters` | `num_characters * cost_per_input_unit_usd` |
| `code_interpreter` | `num_sessions` | `num_sessions * 0.03` |
| `web_search` | `num_queries` | `num_queries * 0.03` |
| `vector_stores` | `bytes_stored` | `bytes_stored * 0.0000001` |
| `fine_tuning` | `input_tokens`, `output_tokens` | `(input_tokens * cost_per_input_unit_usd) + (output_tokens * cost_per_output_unit_usd)` |

> **Note:** Pricing in `openai_model_costs.csv` reflects OpenAI list prices as
> of the TA release date.  Update the CSV when OpenAI changes pricing or
> releases new models.  The file is not overwritten during upgrades.

## Pre-Built Saved Searches

The following saved searches are included and run daily at 00:05 UTC
(covering the previous calendar day).  Enable them in Settings > Searches,
Reports, and Alerts.

| Search name | What it produces |
|---|---|
| OpenAI Usage - Completions Daily Summary | Token counts and estimated cost by model |
| OpenAI Usage - Embeddings Daily Summary | Token counts and estimated cost by model |
| OpenAI Usage - Images Daily Summary | Image counts and estimated cost by model |
| OpenAI Usage - Audio Transcription Daily Summary | Duration (seconds/minutes) and estimated cost |
| OpenAI Usage - Audio Speech Daily Summary | Character counts and estimated cost by model |
| OpenAI Usage - Code Interpreter Daily Summary | Session counts and estimated cost |
| OpenAI Usage - Web Search Daily Summary | Query counts, context tokens, and estimated cost |
| OpenAI Usage - Vector Stores Daily Summary | Peak bytes stored and estimated GB·day cost |
| OpenAI Usage - Fine-Tuning Daily Summary | Training token counts and estimated cost by model |
| OpenAI Usage - Total Daily Cost by Endpoint | Cross-endpoint cost roll-up in a single timechart |

## Sample Searches

### View all usage events
```spl
index=main sourcetype="openai:usage" status!=error
| table _time endpoint_type model input_tokens output_tokens num_model_requests
```

### Full cost roll-up across all endpoints
```spl
index=main sourcetype="openai:usage" status!=error
| lookup openai_model_costs model endpoint_type
    OUTPUT input_unit cost_per_input_unit_usd output_unit cost_per_output_unit_usd
| eval estimated_cost_usd = case(
    endpoint_type="completions",         round((input_tokens * cost_per_input_unit_usd) + (output_tokens * cost_per_output_unit_usd), 6),
    endpoint_type="embeddings",          round(input_tokens * cost_per_input_unit_usd, 6),
    endpoint_type="images",              round(num_images * cost_per_input_unit_usd, 6),
    endpoint_type="audio_transcription", round(input_seconds * cost_per_input_unit_usd, 6),
    endpoint_type="audio_speech",        round(num_characters * cost_per_input_unit_usd, 6),
    endpoint_type="code_interpreter",    round(num_sessions * 0.03, 6),
    endpoint_type="web_search",          round(num_queries * 0.03, 6),
    endpoint_type="vector_stores",       round(bytes_stored * 0.0000001, 6),
    endpoint_type="fine_tuning",         round((input_tokens * cost_per_input_unit_usd) + (output_tokens * cost_per_output_unit_usd), 6),
    true(), 0)
| stats sum(estimated_cost_usd) as total_estimated_cost_usd by endpoint_type
| sort -total_estimated_cost_usd
```

### Token usage trend for a specific model
```spl
index=main sourcetype="openai:usage" endpoint_type=completions model=gpt-4o status!=error
| timechart span=1d sum(input_tokens) as input_tokens sum(output_tokens) as output_tokens
```

### Vector store storage trend (GB)
```spl
index=main sourcetype="openai:usage" endpoint_type=vector_stores status!=error
| eval bytes_stored_gb = round(bytes_stored / 1073741824, 4)
| timechart span=1d max(bytes_stored_gb) as peak_gb_stored
```

### Audio transcription minutes per day
```spl
index=main sourcetype="openai:usage" endpoint_type=audio_transcription status!=error
| eval input_minutes = round(input_seconds / 60, 2)
| timechart span=1d sum(input_minutes) as total_minutes by model
```

### Monitor errors and rate limits
```spl
index=main sourcetype="openai:usage" status=error
| table _time endpoint_type error_type status_code error
```

## File Structure

```
TA-openai-usage/
├── bin/                          # Input scripts and helpers
│   └── openai_usage_helper.py    # Collector registry and data collection logic
├── default/                      # Configuration files
│   ├── app.conf
│   ├── inputs.conf
│   ├── props.conf                # openai:usage sourcetype definition
│   ├── transforms.conf           # openai_model_costs lookup definition
│   ├── savedsearches.conf        # Pre-built daily summary searches
│   ├── restmap.conf
│   ├── server.conf
│   ├── web.conf
│   └── data/ui/                  # UI configuration
├── lookups/
│   └── openai_model_costs.csv    # Per-unit pricing for all known models
├── lib/                          # Python dependencies
│   ├── splunktaucclib/
│   ├── solnlib/
│   └── ...
├── static/                       # App icons
├── README/                       # Configuration specs
└── metadata/                     # Permissions
```

## Development

### Prerequisites

- Python 3.7+
- ucc-gen 6.1.0+
- Virtual environment recommended

### Building from Source

1. Clone or download the source code
2. Navigate to the project directory
3. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   ```

4. Build the add-on:
   ```bash
   ucc-gen build --ta-version 1.0.0 --python-binary-name .venv/bin/python3
   ```

5. Package the add-on:
   ```bash
   ucc-gen package --path output/TA-openai-usage
   ```

The built add-on will be in the `output/` directory.

### Adding a New Endpoint

To collect from a new OpenAI usage endpoint:

1. Add a new subclass of `UsageCollector` in `package/bin/openai_usage_helper.py`:
   - Set `endpoint_type`, `url`, `supports_model_filter`, and `group_by`
   - Implement `format_record()` to map API fields to Splunk event fields
   - Override `collect()` only if the endpoint needs non-standard request parameters

2. Append an instance to `COLLECTOR_REGISTRY`.

3. Add cost rows for the new endpoint to `package/lookups/openai_model_costs.csv`.

4. Add a saved search to `package/default/savedsearches.conf`.

5. Rebuild with `ucc-gen build`.

### Updating Model Pricing

Edit `package/lookups/openai_model_costs.csv` directly.  The file is copied
into the built add-on and is not overwritten by upgrades.  After editing,
rebuild and redeploy.

### Modifying Configuration UI

Edit `globalConfig.json` to customize account fields, input parameters,
validation rules, or UI elements.  After changes, rebuild using `ucc-gen build`.

## Dependencies

- `splunktaucclib` - UCC library for Splunk
- `splunk-sdk` - Splunk SDK for Python
- `solnlib` - Splunk library utilities
- `requests>=2.31.0` - HTTP client for OpenAI API calls

All dependencies are bundled in the `lib/` directory.

## Security Notes

- API keys are encrypted and stored securely using Splunk's credential management
- No credentials are logged or exposed in events
- URL credentials in proxy configuration are redacted from logs
- All network communication uses HTTPS
- Follow the principle of least privilege when configuring Splunk access

## Troubleshooting

### Check Input Status

```spl
index=_internal source=*openai_usage*
| table _time log_level message
```

### Verify Configuration

1. Navigate to Settings > Data Inputs > OpenAI Usage
2. Check that the input is enabled
3. Verify the account is configured correctly

### Common Issues

1. **No data appearing:**
   - Verify API key has admin-level Organization API permissions
   - Check interval setting and confirm the input is enabled
   - Review internal logs for error messages

2. **Partial data (some endpoint types missing):**
   - Some endpoints (e.g. `vector_stores`, `fine_tuning`) may return HTTP 404
     if your organization has never used that feature — this is expected and
     logged as a warning, not an error
   - Check internal logs for per-endpoint error messages

3. **SSL/Connection errors:**
   - Verify network connectivity to `api.openai.com`
   - Check proxy configuration if applicable

4. **Authentication errors (401):**
   - Verify the API key is correct and has admin permissions
   - Check the Organization ID if specified

5. **Cost lookup returning no match:**
   - Model IDs in the CSV must exactly match what the API returns
   - Use `| search model=*` to find the exact model string, then add it to the CSV

## Support

For issues, questions, or contributions:
- Review Splunk internal logs: `index=_internal source=*openai_usage*`
- Check UCC framework documentation: https://splunk.github.io/addonfactory-ucc-generator/
- Consult OpenAI API documentation: https://platform.openai.com/docs/api-reference/usage

## License

See LICENSE.txt in the LICENSES directory.

## Version History

### 1.0.0 (Initial Release)
- Account management with encrypted API key storage
- Configurable data inputs with multiple models support
- Polling interval from 5 minutes to 24 hours
- Optional start date for historical data collection
- Multi-select model filtering with free-text override field
- **Collector registry** with 9 endpoint types:
  - `completions` — chat/text token usage
  - `embeddings` — embedding token usage
  - `images` — image generation counts (GPT Image 1, DALL-E)
  - `audio_transcription` — Whisper speech-to-text duration
  - `audio_speech` — TTS character counts
  - `code_interpreter` — Agents API session counts
  - `web_search` — query counts and context tokens
  - `vector_stores` — RAG storage bytes (GB·day billing)
  - `fine_tuning` — training token usage and job counts
- Cost enrichment lookup (`openai_model_costs.csv`) with `transforms.conf`
- 10 pre-built daily summary saved searches
