# AWS Cryptocurrency OHLC Data Aggregator

## Project Overview

This project is a cloud-native cryptocurrency market data collection and aggregation system built on AWS using Infrastructure as Code (CDK) principles. It scrapes market data from multiple sources (BTCMarkets and Binance), calculates spreads, and aggregates the data into OHLC (Open, High, Low, Close) candlestick patterns with spread statistics at multiple time intervals (1-minute, 1-hour, and daily).

## Architecture

The application follows a serverless, multi-tier architecture:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Frontend      │    │    API Gateway   │    │   Lambda API    │
│  (S3 + CF)      │────│   (REST API)     │────│   (Python)      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                          │
                                                          ↓ 
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  EventBridge    │    │  Lambda Scraper  │    │   DynamoDB      │
│  (1min sched)   │────│   (Python)       │────│  (OHLC Data)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                        ↑
                                                        │
┌─────────────────┐                            ┌──────────────────┐
│  EventBridge    │                            │Lambda Aggregator │
│ (Hourly/Daily)  │────────────────────────────│    (Python)      │
└─────────────────┘                            └──────────────────┘
```

### Component Details


- **S3 Bucket**: Static website hosting
- **CloudFront**: CDN for global distribution and caching
- **API Gateway**: REST API endpoint
- **Lambda Function**: Python-based API handlers
- **DynamoDB**: NoSQL database for OHLC candlestick and spread data
- **Data Format**: OHLC + spread quartiles [open, high, low, close, min, q1, q2, q3, max]
- **Scraper Lambda**: Python-based scraper for orderbook data (1-minute intervals)
- **Aggregator Lambda**: OHLC aggregation from 1m→1h and 1h→1d timeframes
- **EventBridge**: Multiple schedules for scraping (1min) and aggregation (hourly/daily)

## Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Frontend | S3 + CloudFront | Static web hosting & CDN |
| API | API Gateway + Lambda | Serverless REST API |
| Database | DynamoDB | NoSQL OHLC data storage |
| Scraping | Lambda + EventBridge | Automated data collection (1min) |
| Aggregation | Lambda + EventBridge | OHLC aggregation (1h, 1d) |
| Security | WAF + Secrets Manager | Application security & credential management |
| Infrastructure | AWS CDK (Python) | Infrastructure as Code |
| Runtime | Python 3.9 | Lambda functions |

## Project Structure

```
devscraper/
├── .venv/                          # Python virtual environment
├── app.py                          # CDK app entry point
├── requirements.txt                # CDK dependencies
├── cdk.json                        # CDK configuration
├── cdk/                           # CDK stack directory
│   ├── __init__.py
│   └── main_stack.py              # Main infrastructure definition
├── src/                           # Source code
│   ├── api/                       # API Lambda
│   │   ├── api_handler.py         # Market data API endpoints
│   │   └── requirements.txt
│   ├── scraper/                   # Scraper & Aggregator Lambdas
│       ├── scraper_handler.py     # Data scraping & OHLC aggregation
│       ├── btcm_api.py           # BTCMarkets API client
│       ├── binance_api.py        # Binance API client
│       ├── orderbook_logic.py    # Spread calculation logic
│       └── requirements.txt
├── frontend/                      # Static web assets
│   └── index.html
└── tests/                        # Unit tests
    └── scraper_tests.py
```

## Implementation Details

### Database Schema (DynamoDB)

The current implementation stores OHLC candlestick data with spread statistics:

```json
{
  "marketid": "BTC-AUD_1m",          // Partition Key (market + timeframe)
  "timestamp": "2024-01-01T12:00:00", // Sort Key (ISO-8601 datetime)
  "data": [                          // Array format: OHLC + spread quartiles
    95050.25,    // [0] Open price
    95200.00,    // [1] High price  
    95000.00,    // [2] Low price
    95150.75,    // [3] Close price
    99.75,       // [4] Min spread
    120.50,      // [5] Q1 spread (25th percentile)
    135.25,      // [6] Q2 spread (median)
    150.00,      // [7] Q3 spread (75th percentile)  
    180.25       // [8] Max spread
  ]
}
```

**Market ID Format:**
- `{MARKET}_{TIMEFRAME}` (e.g., `BTC-AUD_1m`, `BTC-AUD_1h`, `BTC-AUD_1d`)
- Supported markets: BTC-AUD, XRP-AUD, SOL-AUD, ETH-AUD, SUI-AUD, USDT-AUD, USDC-AUD, LTC-AUD, XLM-AUD, AVAX-AUD
- Supported timeframes: _1m (1-minute), _1h (1-hour), _1d (1-day)

### API Endpoints

| Method | Endpoint | Description | Response |
|--------|----------|-------------|----------|
| GET | `/data/{marketid}` | Get OHLC data for specific market+timeframe | Returns up to 100 most recent records |
| GET | `/markets` | List all available markets and timeframes | Returns array of market_timeframe combinations |

**Example API Usage:**
```bash
# Get 1-hour BTC-AUD data
GET /data/BTC-AUD_1h

# List all available markets
GET /markets
```

### Data Processing Flow

1. **Scraping (Every 1 minute)**:
   - Fetches orderbook data from BTCMarkets API
   - Calculates spread for $10,000 AUD volume
   - Stores as 1-minute OHLC record with spread as price proxy

2. **Hourly Aggregation (Every hour at minute 1)**:
   - Queries all 1-minute records from previous hour
   - Aggregates into OHLC format: first open, max high, min low, last close
   - Recalculates spread quartiles from all spread values
   - Stores as 1-hour record

3. **Daily Aggregation (Every day at 00:01)**:
   - Queries all 1-hour records from previous day
   - Aggregates into daily OHLC format
   - Recalculates spread quartiles
   - Stores as daily record

### Security Features
- **AWS Secrets Manager**: API credentials encrypted at rest using AWS KMS
- **IAM Access Control**: Only scraper Lambdas can read secrets
- **AWS Managed Web Application Firewall (WAF)**: Protection against OWASP Top 10 vulnerabilities 
- **Audit Trail**: All secret access logged in CloudTrail
- **Rate Limiting**: 2,000 requests per 5-minute window per IP
- **CloudWatch Integration**: Full metrics and monitoring for security events
- **Lambda functions**: Least privileges
- **S3 bucket**: Access via CloudFront OAI only
- **DynamoDB Encryption**: AWS-managed encryption at rest
- **Point-in-Time Recovery**: Enabled for data resilience

## Deployment Instructions

### Prerequisites
- Python 3.9+
- AWS CLI configured with appropriate credentials
- AWS CDK installed (`npm install -g aws-cdk`)

### Setup and Deployment
```bash
# Clone and setup the project
cd devscraper
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Bootstrap CDK (first time only)
cdk bootstrap

# Deploy infrastructure
cdk synth                    # Validate CloudFormation template
cdk deploy SpreadScraperStack # Deploy the stack

# Check deployment status
python3 deploy-checker.py    # Custom deployment verification script
```

### Post-Deployment Configuration
1. **Update API Credentials in Secrets Manager**:
   - Navigate to AWS Secrets Manager console
   - Find secret: `market-scraper/api-credentials`
   - Update JSON with real API keys:
   ```json
   {
     "btcmarkets_api_key": "your_btcmarkets_key",
     "btcmarkets_secret": "your_btcmarkets_secret", 
     "binance_api_key": "your_binance_key",
     "binance_secret": "your_binance_secret"
   }
   ```

2. **Update Frontend API URL**: 
   - Get API Gateway URL from CDK output or AWS Console
   - Update `API_BASE_URL` in `frontend/index.html` (line 210)
   - Upload to S3: `aws s3 cp frontend/index.html s3://webscraper-frontend-{account}-{region}/`

3. **Verify Security Deployment**:
   - Check WAF is attached to API Gateway in AWS Console
   - Test API rate limiting by making rapid requests
   - Monitor CloudWatch for WAF blocked requests
   - Verify Lambda functions can read secrets from CloudWatch logs

4. **Verify Data Collection**:
   - Check EventBridge rules are triggering
   - Monitor CloudWatch logs for Lambda execution
   - Test API endpoints manually

## Monitoring and Testing

### Available Testing Scripts
- `tests/scraper_tests.py`: Unit tests for scraper and aggregation functionality
- `deploy-checker.py`: Deployment status verification script

### CloudWatch Monitoring
- **Lambda Logs**: All Lambda functions log to CloudWatch
  - `/aws/lambda/SpreadScraperStack-ApiLambda-*`: API request logs
  - `/aws/lambda/SpreadScraperStack-ScraperLambda-*`: Scraping operation logs  
  - `/aws/lambda/SpreadScraperStack-AggregateLambda-*`: Aggregation process logs
- **API Gateway**: Request/response logging enabled
- **DynamoDB**: Read/write capacity and throttling metrics
- **EventBridge**: Rule execution and failure metrics
