# TA-openai-usage - OpenAI API Usage Monitor

A Splunk Technology Add-on for monitoring OpenAI API usage across all billing
dimensions, built using the UCC (Universal Configuration Console) framework.

## Overview

This add-on collects and indexes OpenAI organization-level usage data from
every billable endpoint, including:

- **Completions** — token usage and request counts for chat/text models
- **Embeddings** — token usage for embedding models
- **Images** — image generation counts and sizes (GPT Image 1, DALL-E)
- **Audio Transcription** — speech-to-text duration in seconds
- **Audio Speech** — TTS character counts
- **Moderations** — moderation token counts
- **Code Interpreter** — session counts
- **Web Search** — search call counts by context level
- **File Search** — search call counts by vector store
- **Vector Stores** — storage snapshots in bytes (GB-day billing)

It also collects **billed cost** from `/v1/organization/costs`, which is the
only endpoint that reports money rather than quantities.

Usage can be attributed by project, user, API key and vector store, not just
by model.  Those are the only dimensions OpenAI exposes, which means the
granularity of any later cost question is set by how projects and keys are
provisioned now.

## Version

**Version:** 1.1.0

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
- **Models:** (Optional) Comma-separated model IDs to restrict collection to,
  e.g. `gpt-4o, o3, text-embedding-3-small`. Sent to the API as its `models`
  filter; endpoints with no model dimension ignore it.

  **Leave this empty.** An allowlist in a monitoring tool is a silent data-loss
  mechanism: any model it does not name is absent from your cost data, and
  nothing tells you. A model released next month would simply not appear.

  There is no dropdown of known models, deliberately. Nobody can maintain an
  accurate list, including OpenAI: the `AssistantSupportedModels` enum in their
  own published OpenAPI spec still tops out at `gpt-5-2025-08-07`. A hardcoded
  list in a third-party add-on has no chance, and the previous release shipped
  one alongside a free-text override field, which was an admission that it did
  not work.

- **Attribution Dimensions:** (Optional) Break usage down by `project_id`,
  `user_id`, `api_key_id` and `vector_store_id` in addition to model.

  These four are the only handles OpenAI gives you for attributing spend to
  something inside your organisation. There is no way to tag a request with a
  cost centre, a team, or a customer after the fact, so whichever of these you
  can answer with is decided when projects and keys are provisioned, not when
  someone asks who spent the money.

  Each dimension multiplies the number of records returned, so selecting all
  four on a busy organisation means considerably more events. Dimensions an
  endpoint does not support are skipped for that endpoint rather than sent:
  `code_interpreter` and `vector_stores` accept only `project_id`, and
  `vector_store_id` applies only to `file_search`.

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
| `project_id` | OpenAI project ID (when requested via Attribution Dimensions) |
| `user_id` | OpenAI user ID (when requested via Attribution Dimensions) |
| `api_key_id` | OpenAI API key ID (when requested via Attribution Dimensions) |
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
| `source` | What produced the image (e.g. `image.generation`) |

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
| `num_requests` | Number of web search calls |
| `num_model_requests` | Number of API requests that made them |
| `context_level` | Search context size (`low`, `medium`, `high`); pricing varies by this |

#### `vector_stores`
| Field | Description |
|---|---|
| `bytes_stored` | Bytes of vector store data stored (snapshot, not request-based) |

#### `moderations`
| Field | Description |
|---|---|
| `input_tokens` | Tokens submitted for moderation |
| `num_model_requests` | Number of API requests |

#### `file_search`
| Field | Description |
|---|---|
| `num_requests` | Number of file search calls |
| `vector_store_id` | Vector store searched (when grouped by it) |

#### `costs`
| Field | Description |
|---|---|
| `cost_usd` | Amount OpenAI billed for this bucket |
| `currency` | ISO-4217 currency code, lowercase (e.g. `usd`) |
| `line_item` | Billing line item (e.g. `Image models`) |
| `quantity` | Billed quantity for the line item |

Error events include `"status": "error"` with `error`, `error_type`, and
optionally `status_code` and `retry_after` fields.  Successful events carry
no `status` field at all, so filter them with `NOT status=error` rather than
`status!=error` — an SPL field comparison does not match events where the
field is absent.

## Cost: Billed vs Estimated

There are two ways to get a cost number out of this add-on, and they are not
interchangeable.

**Billed cost** comes from `endpoint_type=costs`, collected from
`/v1/organization/costs`.  It is what OpenAI actually charged, in currency,
broken down by line item and project.  Use it for anything that reaches a
finance conversation.  It has no per-model breakdown, because the costs
endpoint does not provide one.

**Estimated cost** is computed in SPL by multiplying usage quantities by the
`lookups/openai_model_costs.csv` price list.  It gives you per-model
attribution, which is usually the question people actually have, at the price
of being a local copy of OpenAI's pricing that goes stale silently.

Run the `OpenAI Cost - Estimated vs Billed Reconciliation` saved search to see
the gap between the two.  A drift that grows over time means the CSV needs
updating.

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

The shipped file covers models whose pricing could be verified. Anything not
listed produces a null estimate, which reads as zero spend in a `sum()`. The
**Models With No Price Row** search reports those so the gap is visible rather
than silently wrong. Add rows as needed; the file is not overwritten on upgrade.

### Cost enrichment pattern

```spl
`openai_usage_ok` endpoint_type=completions
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


> **Note:** Pricing in `openai_model_costs.csv` reflects OpenAI list prices as
> of the TA release date.  Update the CSV when OpenAI changes pricing or
> releases new models.  The file is not overwritten during upgrades.

## Pre-Built Saved Searches

The following saved searches are included and run daily at 00:05 UTC
(covering the previous calendar day).  Enable them in Settings > Searches,
Reports, and Alerts.

| Search name | What it produces |
|---|---|
| OpenAI Cost - Billed Daily by Line Item | Actual billed cost by line item |
| OpenAI Cost - Billed Daily by Project | Actual billed cost by project |
| OpenAI Usage - Completions Daily Summary | Token counts and estimated cost by model |
| OpenAI Usage - Embeddings Daily Summary | Token counts and estimated cost by model |
| OpenAI Usage - Images Daily Summary | Image counts and estimated cost by model |
| OpenAI Usage - Audio Transcription Daily Summary | Duration (seconds/minutes) and estimated cost |
| OpenAI Usage - Audio Speech Daily Summary | Character counts and estimated cost by model |
| OpenAI Usage - Moderations Daily Summary | Moderation token counts by model |
| OpenAI Usage - Code Interpreter Daily Summary | Session counts |
| OpenAI Usage - Web Search Daily Summary | Search call counts by context level |
| OpenAI Usage - File Search Daily Summary | Search call counts by vector store |
| OpenAI Usage - Vector Store Storage Daily Summary | Peak bytes stored |
| OpenAI Cost - Estimated vs Billed Reconciliation | Drift between the local price list and the real bill |
| OpenAI Cost - Models With No Price Row | Models being used that have no price row, so estimate as null |

All searches read through the `openai_usage_index` macro.  Point that at your
index once in `default/macros.conf` instead of editing each search.

## Sample Searches

### View all usage events
```spl
`openai_usage_ok`
| table _time endpoint_type model input_tokens output_tokens num_model_requests
```

### What OpenAI actually billed
```spl
`openai_costs_ok`
| stats sum(cost_usd) as billed_cost_usd by line_item
| sort -billed_cost_usd
```

### Spend by project
Requires `project_id` in the input's Attribution Dimensions.
```spl
`openai_costs_ok`
| stats sum(cost_usd) as billed_cost_usd by project_id
| sort -billed_cost_usd
```

### Token usage trend for a specific model
```spl
`openai_usage_ok` endpoint_type=completions model=gpt-4o
| timechart span=1d sum(input_tokens) as input_tokens sum(output_tokens) as output_tokens
```

### Vector store storage trend (GB)
```spl
`openai_usage_ok` endpoint_type=vector_stores
| eval bytes_stored_gb = round(bytes_stored / 1073741824, 4)
| timechart span=1d max(bytes_stored_gb) as peak_gb_stored
```

### Audio transcription minutes per day
```spl
`openai_usage_ok` endpoint_type=audio_transcription
| eval input_minutes = round(input_seconds / 60, 2)
| timechart span=1d sum(input_minutes) as total_minutes by model
```

### Monitor errors and rate limits
```spl
`openai_usage_index` sourcetype="openai:usage" status=error
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
   - Some endpoints may return HTTP 404
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

## Development

The collectors are tested outside Splunk. Fixtures are shaped from OpenAI's
published OpenAPI schemas rather than from what the code happens to read,
which is what makes them worth running: the previous release passed its own
assumptions and collected nothing.

```bash
python3 -m venv .venv
.venv/bin/pip install pytest requests
.venv/bin/python -m pytest tests/ -q
```

`tests/conftest.py` stubs `import_declare_test`, `solnlib` and `splunklib` so
the helper imports without a Splunk installation. No API key is needed; the
tests never make a network call.

When adding a collector, check the path and the response field names against
`openai/openai-openapi` and add the path to `REAL_USAGE_PATHS` in
`tests/test_endpoints.py`.

## License

See LICENSE.txt in the LICENSES directory.

## Version History

### 1.1.0

Correctness release.  Version 1.0.0 was written against an assumed shape of
the Organization Usage API rather than the published one, and did not collect
anything.  Checked against `openai/openai-openapi`:

**Endpoints that did not exist**
- `audio_transcription` and `audio_speech` both requested `/usage/audio`.
  They are separate endpoints, `/usage/audio_transcriptions` and
  `/usage/audio_speeches`.  The model-prefix filter used to tell them apart
  is gone, and with it a bug that dropped all `gpt-4o-transcribe` usage.
- `code_interpreter` requested `/usage/code_interpreter`; the path is
  `/usage/code_interpreter_sessions`.
- `web_search` requested `/usage/web_search`; the path is
  `/usage/web_search_calls`.
- `fine_tuning` requested `/usage/fine_tuning`, which does not exist in any
  form.  The collector, its saved search, and its price rows are removed.
  Inference against a fine-tuned model is billed through `completions`.

**Requests the API rejected**
- `limit` was 100 on every request.  With `bucket_width=1d` the maximum is
  31, so every call returned HTTP 400.

**Fields that were read under the wrong name**, and so indexed as zero:
`images` (was `num_images`), `seconds` (was `input_seconds`), `characters`
(was `num_characters`), `num_requests` and `context_level` (were
`num_queries` and `context_tokens`).

**Searches that matched nothing**
- Every saved search and eventtype filtered on `status!=error`.  Successful
  events carry no `status` field, and an SPL field comparison does not match
  events where the field is absent.  Now `NOT status=error`.
- `index=*` is replaced by the `openai_usage_index` macro.

**The response was never unwrapped**
- `data` holds time buckets (`{object: "bucket", start_time, end_time,
  results: [...]}`); the metrics live on the nested `results`.  The add-on
  formatted the bucket itself, so even a request that succeeded produced an
  event with a correct timestamp and zero for every metric — indistinguishable
  from "this model was not used".

**Model filtering**
- Filtering happened client-side: fetch everything, discard non-matching rows.
  Same API calls, and any model the add-on had not heard of was dropped
  rather than counted.  The `models` filter is now sent as a query parameter
  on the seven endpoints that accept one.
- The model dropdown and its `custom_models` override field are replaced by a
  single optional free-text **Models** field, empty by default.  Maintaining a
  list of current models is not possible for a third-party add-on; OpenAI's own
  spec enum stops at `gpt-5-2025-08-07`.
- Price rows for models that could not be verified are removed rather than
  shipped with guessed numbers.  A wrong price yields a confident wrong total;
  a missing one yields a null the new **Models With No Price Row** search
  reports.

**New**
- `costs` collector reading `/v1/organization/costs`: what OpenAI actually
  billed, in currency, rather than a quantity multiplied by a local price
  list.  With an `Estimated vs Billed Reconciliation` search to show drift.
- `moderations` and `file_search` collectors, previously missing.
- **Attribution Dimensions** input setting.  Usage can now be grouped by
  `project_id`, `user_id`, `api_key_id` and `vector_store_id`, not just
  model.  These are the only handles OpenAI exposes for attributing spend
  inside an organisation.  Dimensions an endpoint does not support are
  dropped for that endpoint rather than sent and rejected.
- `tests/`, run with `pytest`.  Fixtures are shaped from the published
  OpenAPI schemas, not from what the collectors happen to read.

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
- Cost enrichment lookup (`openai_model_costs.csv`) with `transforms.conf`
- 10 pre-built daily summary saved searches
