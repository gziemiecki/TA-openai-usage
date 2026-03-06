# TA-openai-usage - OpenAI API Usage Monitor

A Splunk Technology Add-on for monitoring OpenAI API usage, built using the UCC (Universal Configuration Console) framework.

## Overview

This add-on collects and monitors OpenAI API usage data, tracking:
- API request counts
- Token usage (input/output) by model
- Cost data
- Request timestamps
- Error tracking

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
- **OpenAI API Key:** Your OpenAI API key (encrypted and stored securely)
- **Organization ID:** (Optional) Your OpenAI Organization ID if you're using organizations

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
  Model IDs are matched against the `model` field returned by the OpenAI Usage API,
  so selecting a specific model will only include usage records where the API reports
  that exact model ID. When in doubt, use **All Models** and filter in Splunk searches.

  | Model | Series |
  |---|---|
  | All Models (*) | — |
  | GPT-5.4 | GPT-5 Frontier |
  | GPT-5.4 Pro | GPT-5 Frontier |
  | GPT-5.2 | GPT-5 Frontier |
  | GPT-5.1 | GPT-5 Frontier |
  | GPT-5 | GPT-5 Frontier |
  | GPT-5 mini | GPT-5 Efficient |
  | GPT-5 nano | GPT-5 Efficient |
  | o3 | Reasoning |
  | o4-mini | Reasoning |
  | o3-mini | Reasoning |
  | o1 | Reasoning |
  | GPT-4.1 | GPT-4.1 |
  | GPT-4.1 mini | GPT-4.1 |
  | GPT-4.1 nano | GPT-4.1 |
  | GPT-4o | GPT-4o |
  | GPT-4o mini | GPT-4o |
  | text-embedding-3-large | Embeddings |
  | text-embedding-3-small | Embeddings |
  | text-embedding-ada-002 | Embeddings |
  | GPT-4 Turbo (Legacy) | Legacy |
  | GPT-4 (Legacy) | Legacy |
  | GPT-3.5 Turbo (Legacy) | Legacy |

## Data Collection

### Sourcetype

Events are indexed with sourcetype: `openai:usage`

### Event Structure

Each event represents one model's usage within a daily bucket returned by
the OpenAI Usage API.

```json
{
  "_time": 1741132800,
  "timestamp": "2026-03-05T00:00:00+00:00",
  "endpoint_type": "completions",
  "model": "gpt-5.4",
  "input_tokens": 84213,
  "output_tokens": 19047,
  "cached_tokens": 3200,
  "requests": 142,
  "project_id": "proj_abc123",
  "api_key_id": "key_xyz789",
  "bucket_start_time": 1741132800,
  "bucket_end_time": 1741219200,
  "input_name": "my_openai_input",
  "account": "my_openai_account"
}
```

Error events include `"status": "error"` with `error`, `error_type`, and
optionally `status_code` fields.

## Sample Searches

### View all usage events
```spl
index=main sourcetype="openai:usage" status!=error
| table _time model endpoint_type input_tokens output_tokens cached_tokens requests
```

### Total token usage by model
```spl
index=main sourcetype="openai:usage" status!=error
| stats sum(input_tokens) as input_tokens
        sum(output_tokens) as output_tokens
        sum(cached_tokens) as cached_tokens
        sum(requests) as requests by model
| eval total_tokens = input_tokens + output_tokens
| sort -total_tokens
```

### Compare completions vs embeddings usage
```spl
index=main sourcetype="openai:usage" status!=error
| stats sum(input_tokens) as input sum(output_tokens) as output sum(requests) as calls
        by endpoint_type
```

### Daily token trend for GPT-5.4
```spl
index=main sourcetype="openai:usage" model=gpt-5.4 status!=error
| timechart span=1d sum(input_tokens) as input_tokens sum(output_tokens) as output_tokens
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
│   └── openai_usage_helper.py    # Main data collection logic
├── default/                      # Configuration files
│   ├── app.conf
│   ├── inputs.conf
│   ├── restmap.conf
│   ├── server.conf
│   ├── web.conf
│   └── data/ui/                  # UI configuration
├── lib/                          # Python dependencies
│   ├── openai/                   # OpenAI SDK
│   ├── splunktaucclib/           # UCC library
│   ├── solnlib/                  # Splunk library
│   └── ...                       # Other dependencies
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

### Modifying Configuration

Edit `globalConfig.json` to customize:
- Account fields
- Input parameters
- Validation rules
- UI elements

After changes, rebuild using `ucc-gen build`.

## Dependencies

- `openai>=1.0.0` - OpenAI Python SDK
- `splunktaucclib` - UCC library for Splunk
- `splunk-sdk` - Splunk SDK for Python
- `solnlib` - Splunk library utilities

All dependencies are bundled in the `lib/` directory.

## Security Notes

- API keys are encrypted and stored securely using Splunk's credential management
- No credentials are logged or exposed in events
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
   - Verify API key is valid
   - Check interval setting
   - Review internal logs

2. **SSL/Connection errors:**
   - Verify network connectivity
   - Check firewall rules
   - Ensure OpenAI API is accessible

3. **Authentication errors:**
   - Verify API key is correct
   - Check organization ID if using organizations

## API Integration Notes

This add-on uses the OpenAI SDK (version 1.0+). The actual data collection logic in `openai_usage_helper.py` includes a template structure that can be extended to call specific OpenAI API endpoints for usage data.

**Note:** OpenAI's usage API endpoints may require specific parameters and authentication. Consult the [OpenAI API documentation](https://platform.openai.com/docs/api-reference) for the latest endpoints and data structures.

## Support

For issues, questions, or contributions:
- Review Splunk internal logs
- Check UCC framework documentation: https://splunk.github.io/addonfactory-ucc-generator/
- Consult OpenAI API documentation: https://platform.openai.com/docs/

## License

See LICENSE.txt in the LICENSES directory.

## Version History

### 1.0.0 (Initial Release)
- Account management with encrypted API key storage
- Configurable data inputs with multiple models support
- OpenAI SDK integration
- Flexible polling intervals
- Optional start date for historical data collection
- Multi-select model filtering
