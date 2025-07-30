# GGUF Models Data Pipeline

This directory contains the automated data pipeline for fetching and processing GGUF model data from Hugging Face, designed to run daily at exactly 23:59 UTC via GitHub Actions.

## Files

- `update_models.py` - Main script that fetches GGUF models from Hugging Face API
- `requirements.txt` - Python dependencies for the data pipeline
- `README.md` - This documentation file

## Features

- **Automated Daily Updates**: Runs at 23:59 UTC every day
- **Rate Limiting**: Respects Hugging Face API limits with intelligent throttling
- **Error Handling**: Robust retry logic and graceful failure handling
- **Progress Tracking**: Real-time progress bars and detailed logging
- **SEO Optimization**: Generates sitemaps and robots.txt for search engines
- **Multiple Output Formats**: Creates optimized JSON files for different use cases

## GitHub Actions Setup

The data pipeline runs automatically via GitHub Actions:

1. **Schedule**: Daily at exactly 23:59 UTC (`59 23 * * *`)
2. **Authentication**: Uses `HUGGINGFACE_TOKEN` secret for higher rate limits
3. **Output**: Generates optimized JSON files in the `data/` directory
4. **SEO**: Creates `sitemap.xml` and `robots.txt` files
5. **Verification**: Validates generated files before committing
6. **Commit**: Automatically commits changes with detailed messages

## Required Secrets

Add these secrets to your GitHub repository settings:

- `HUGGINGFACE_TOKEN` - Hugging Face API token for higher rate limits (optional but strongly recommended)

To get a token:
1. Go to https://huggingface.co/settings/tokens
2. Create a new token with "Read" permissions
3. Add it to your repository secrets

## Manual Execution

To run the script locally for testing:

```bash
# Install dependencies
pip install -r requirements.txt

# Set token (optional but recommended)
export HUGGINGFACE_TOKEN=your_token_here

# Run the pipeline
python update_models.py
```

## Generated Files

The pipeline generates the following files:

### Data Files (in `data/` directory)
- `models.json` - Complete model data with metadata and file information
- `search-index.json` - Optimized search index for fast client-side searching
- `statistics.json` - Model statistics, distributions, and analytics
- `families.json` - Models organized by family/organization

### SEO Files (in root directory)
- `sitemap.xml` - XML sitemap for search engine indexing
- `robots.txt` - Search engine crawling directives

## Data Structure

### models.json
```json
{
  "models": [
    {
      "id": "microsoft/DialoGPT-medium",
      "name": "DialoGPT Medium",
      "description": "Conversational AI model",
      "files": [...],
      "tags": ["conversational", "medium"],
      "downloads": 15420,
      "architecture": "GPT",
      "family": "microsoft",
      "quantizations": ["Q4_K_M", "Q8_0"],
      "totalSize": 2147483648
    }
  ],
  "metadata": {
    "totalModels": 1234,
    "lastUpdated": "2025-07-29T23:59:00Z",
    "nextUpdate": "2025-07-30T23:59:00Z"
  }
}
```

## Performance

- **Rate Limiting**: 1 req/sec (anonymous) or 1.5 req/sec (authenticated)
- **Processing Speed**: ~500-1000 models per hour depending on API limits
- **File Sizes**: Typically 5-20 MB for complete dataset
- **Update Time**: Usually completes within 30-60 minutes

## Monitoring

Check the GitHub Actions logs to monitor pipeline execution:
1. Go to your repository's "Actions" tab
2. Click on "Update GGUF Models Data" workflow
3. View the latest run for detailed logs and statistics

## Troubleshooting

### Common Issues

1. **Rate Limiting**: Add `HUGGINGFACE_TOKEN` secret for higher limits
2. **Large Files**: Pipeline automatically handles large datasets with pagination
3. **Network Errors**: Built-in retry logic handles temporary failures
4. **Memory Issues**: Uses streaming and async processing for efficiency

### Error Recovery

The pipeline is designed to be resilient:
- Failed model processing doesn't stop the entire pipeline
- Network errors trigger automatic retries with exponential backoff
- If the pipeline fails completely, existing data files remain unchanged
- Manual re-runs can be triggered via GitHub Actions interface