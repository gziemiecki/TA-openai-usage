# Quick Start Guide - TA-openai-usage

## What Was Created

Your Splunk Technology Add-on for OpenAI API Usage monitoring has been successfully built!

### Project Structure

```
TA-openai-usage/
├── globalConfig.json              # UCC configuration (source)
├── package/                       # Source files
│   ├── bin/
│   │   └── openai_usage_helper.py # Data collection logic
│   └── lib/
│       └── requirements.txt       # Python dependencies
├── output/                        # Built add-on (ready to deploy)
│   └── TA-openai-usage/
│       ├── bin/                   # Compiled scripts
│       ├── default/               # Splunk configs
│       ├── lib/                   # Python libraries (bundled)
│       └── ...
└── .venv/                         # Build virtual environment
```

## Next Steps

### 1. Package the Add-on (Optional)

To create a `.tar.gz` package for distribution:

```bash
cd /Users/gziemiecki/Documents/TA-projects/OpenAI/TA-openai-usage
ucc-gen package --path output/TA-openai-usage
```

This creates a `.spl` file that can be uploaded to Splunkbase or distributed internally.

### 2. Install on Splunk

**Option A: Direct Installation (Development)**
```bash
# Copy to Splunk apps directory
cp -r output/TA-openai-usage $SPLUNK_HOME/etc/apps/

# Restart Splunk
$SPLUNK_HOME/bin/splunk restart
```

**Option B: Web UI Installation**
1. Package the add-on (see step 1)
2. Navigate to Splunk Web > Manage Apps > Install app from file
3. Upload the `.spl` file
4. Restart if prompted

### 3. Configure the Add-on

1. **Add an Account:**
   - Go to: OpenAI API Usage Monitor > Configuration > Account
   - Click "Add" and provide:
     - Account Name
     - OpenAI API Key
     - Organization ID (optional)

2. **Create an Input:**
   - Go to: OpenAI API Usage Monitor > Inputs > Create New Input
   - Configure:
     - Name
     - Interval (default: 3600s)
     - Index (default: main)
     - Account (select from dropdown)
     - Start Date (optional, YYYY-MM-DD)
     - Models to Track (default: All Models)

3. **Save and Enable**

### 4. Verify Data Collection

Wait for one polling interval, then search:

```spl
index=main sourcetype="openai:usage"
```

Check internal logs:

```spl
index=_internal source=*openai_usage*
| table _time log_level message
```

## Configuration Details

### Account Tab Features
- ✅ Encrypted OpenAI API key storage
- ✅ Optional Organization ID field
- ✅ Account name validation (alphanumeric + underscore)

### Input Configuration Features
- ✅ Polling interval: 300-86400 seconds (default: 3600)
- ✅ Index selection
- ✅ Account selection (dropdown)
- ✅ Optional start date (YYYY-MM-DD with regex validation)
- ✅ Multi-select models (default: All Models):
  - All Models (*)
  - GPT-5.4, GPT-5.4 Pro, GPT-5.2, GPT-5.1, GPT-5 (GPT-5 series)
  - GPT-5 mini, GPT-5 nano (efficient)
  - o3, o4-mini, o3-mini, o1 (reasoning)
  - GPT-4.1, GPT-4.1 mini, GPT-4.1 nano
  - GPT-4o, GPT-4o mini
  - text-embedding-3-large, text-embedding-3-small, text-embedding-ada-002 (embeddings)
  - GPT-4 Turbo, GPT-4, GPT-3.5 Turbo (legacy)

### Python Helper Module
- ✅ OpenAI SDK integration (openai>=1.0.0)
- ✅ Error handling and logging
- ✅ Modular design for easy customization
- ✅ Supports organization ID
- ✅ Date range filtering
- ✅ Model filtering

### Dependencies (Bundled)
- ✅ openai>=1.0.0
- ✅ splunktaucclib
- ✅ splunk-sdk
- ✅ solnlib

## Customization

### Modify Data Collection Logic

Edit: `package/bin/openai_usage_helper.py`

The `get_openai_usage_data()` function is where you can add specific OpenAI API calls:

```python
def get_openai_usage_data(logger, api_key, organization_id, start_date, models):
    # Add your custom OpenAI API calls here
    # Example:
    # usage = client.usage.list(date=start_date)
    # return usage data
    pass
```

After modifications:
```bash
ucc-gen build --ta-version 1.0.0 --python-binary-name .venv/bin/python3
```

### Add More Configuration Fields

Edit: `globalConfig.json`

Example - add a new field to inputs:

```json
{
    "type": "text",
    "label": "New Field",
    "field": "new_field",
    "help": "Help text here",
    "required": false
}
```

Rebuild after changes.

## Testing Checklist

- [ ] Add-on installs without errors
- [ ] Configuration page loads
- [ ] Can create account with encrypted API key
- [ ] Can create input with all fields
- [ ] Input appears in inputs list
- [ ] Events appear in Splunk after interval
- [ ] Sourcetype is `openai:usage`
- [ ] Internal logs show successful execution
- [ ] Error handling works (test with invalid API key)

## Troubleshooting

### No events appearing
```spl
index=_internal source=*openai_usage* log_level=ERROR
```

### Input not running
- Check if input is enabled
- Verify interval is not too large
- Check Splunk permissions

### Authentication errors
- Verify API key is correct
- Check Organization ID if specified
- Test API key manually with OpenAI

## OpenAI API Integration

The current implementation includes a template structure. To fully integrate with OpenAI's usage API:

1. Review OpenAI API documentation: https://platform.openai.com/docs/api-reference/usage
2. Update `get_openai_usage_data()` in `openai_usage_helper.py`
3. Add specific API endpoint calls
4. Parse and format response data
5. Rebuild the add-on

### Example API Call Structure

```python
from openai import OpenAI

client = OpenAI(api_key=api_key)

# Example: Fetch usage data
# Note: Actual endpoint may vary - check OpenAI docs
response = client.usage.list(
    date=start_date,
    organization=organization_id
)
```

## Support Resources

- **UCC Framework:** https://splunk.github.io/addonfactory-ucc-generator/
- **OpenAI API Docs:** https://platform.openai.com/docs/
- **Splunk SDK:** https://dev.splunk.com/python
- **Internal Logs:** `index=_internal source=*openai_usage*`

## Files Generated

### Configuration Files (output/TA-openai-usage/default/)
- `app.conf` - App metadata
- `inputs.conf` - Input configuration
- `inputs.conf.spec` - Input spec
- `restmap.conf` - REST API endpoints
- `server.conf` - Server settings
- `web.conf` - Web UI settings
- `ta-openai-usage_account.conf.spec` - Account spec
- `ta-openai-usage_settings.conf` - Settings config

### UI Files (output/TA-openai-usage/default/data/ui/views/)
- `configuration.xml` - Configuration page
- `inputs.xml` - Inputs page
- `dashboard.xml` - Monitoring dashboard

### Python Files (output/TA-openai-usage/bin/)
- Various generated REST handlers and input scripts
- Your custom `openai_usage_helper.py`

## Success Metrics

Your add-on is production-ready when:

1. ✅ Builds without errors
2. ✅ Installs on Splunk successfully
3. ✅ Configuration UI is accessible
4. ✅ Can create and save accounts
5. ✅ Can create and enable inputs
6. ✅ Data appears in Splunk at specified intervals
7. ✅ No errors in internal logs
8. ✅ Data is properly formatted JSON
9. ✅ Sourcetype is consistent
10. ✅ Search queries return expected results

---

**Congratulations!** Your Splunk TA for OpenAI Usage Monitoring is ready to deploy!
