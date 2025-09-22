import os
import uuid
from decimal import Decimal

from datetime import datetime, timezone, timedelta
import boto3
import logging
import json
from btcm_api import BTCMarketsClient
from orderbook_logic import calculate_spreads
from boto3.dynamodb.conditions import Key
import statistics

# Initialize AWS clients
secrets_client = boto3.client('secretsmanager')

INTERESTING_MARKETS: list[str] = ['BTC-AUD', 'XRP-AUD', 'SOL-AUD', 'ETH-AUD', 'SUI-AUD', 'USDT-AUD', 'USDC-AUD', 'LTC-AUD', 'XLM-AUD', 'AVAX-AUD']
INTERESTING_LEVELS = [100, 1000, 10000, 100000]

# initialise logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialise DynamoDB client
dynamodb = boto3.resource('dynamodb')
table_name = os.environ['DYNAMODB_TABLE_NAME']
table = dynamodb.Table(table_name)


def get_api_credentials():
    """
    Retrieve API credentials from AWS Secrets Manager
    Returns: dict containing API credentials
    """
    try:
        secrets_arn = os.environ.get('API_SECRETS_ARN')
        if not secrets_arn:
            logger.warning("API_SECRETS_ARN not set, using public API access only")
            return {}
        
        response = secrets_client.get_secret_value(SecretId=secrets_arn)
        credentials = json.loads(response['SecretString'])
        
        logger.info("Successfully retrieved API credentials from Secrets Manager")
        return credentials
        
    except Exception as e:
        logger.error(f"Failed to retrieve API credentials: {str(e)}")
        # Return empty dict to allow public API access
        return {}


def scrape_handler(event, context):
    """
    Lambda function to grab spread data and store them in DynamoDB
    """
    response = dict()
    for market_id in INTERESTING_MARKETS:
        try:
            market_data = scrape_market(market_id)
            store_in_dynamodb(market_data)
            response[market_id] = "Success"
        except Exception as e:
            logger.error("Market scrape exception: ")
            response[market_id] = f"Failure {e}"

    return {
        'statusCode': 200,
        'body': json.dumps(response)
    }

def scrape_market(market_str: str) -> dict:
    """ Scrape one market """
    try:
        # Load API credentials from Secrets Manager
        credentials = get_api_credentials()
        
        # Initialize API client (credentials will be passed but not used until BTCMarkets API is updated)
        if credentials and credentials.get('btcmarkets_api_key'):
            market_api = BTCMarketsClient(
                api_key=credentials.get('btcmarkets_api_key'),
                api_secret=credentials.get('btcmarkets_secret')
            )
            logger.info(f"Loaded credentials for authenticated API access for {market_str}")
        else:
            market_api = BTCMarketsClient()
            logger.info(f"Using public API access for {market_str}")
        
        market_orderbook = market_api.get_market_orderbook(market_str)
        return calculate_spreads(market_orderbook, INTERESTING_LEVELS)
        
    except Exception as e:
        logger.error(f"Error scraping market {market_str}: {str(e)}")
        raise


def aggregate_handler(event, context):
    """
    Lambda function to aggregate OHLC data from 1m to 1h or from 1h to 1d
    Event should contain:
    - aggregation_type: "1h" or "1d"
    - timezone: timezone string (e.g., "Australia/Melbourne")
    """

    aggregation_type = event.get('aggregation_type', '1h')
    timezone_str = event.get('timezone', 'UTC')

    # Convert timezone string to timezone object
    if timezone_str == 'UTC':
        tz = timezone.utc
    else:
        # For non-UTC timezones, use UTC as fallback
        # In production, you might want to handle specific timezones
        tz = timezone.utc

    try:
        if aggregation_type == '1h':
            result = aggregate_to_hourly(tz)
        elif aggregation_type == '1d':
            result = aggregate_to_daily(tz)
        else:
            raise ValueError(f"Invalid aggregation_type: {aggregation_type}")

        return {
            'statusCode':200,
            'body':json.dumps({
                'message':f'Successfully aggregated {aggregation_type} bars',
                'processed_items':result
            })
        }
    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        return {
            'statusCode':500,
            'body':json.dumps({
                'error':str(e)
            })
        }


def aggregate_to_hourly(tz):
    """Aggregate 1-minute bars to 1-hour bars"""
    # Get the current hour boundary
    now = datetime.now(tz)
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    previous_hour = current_hour - timedelta(hours=1)

    # Get all unique market IDs that have 1m data
    market_ids = []
    for market in INTERESTING_MARKETS:
        market_ids.append(market + '_1m')

    processed_items = 0

    for market_id in market_ids:
        base_market_id = market_id.replace('_1m', '')

        # Query 1-minute data for the previous hour
        one_minute_data = query_time_range(
            market_id,
            previous_hour,
            current_hour
        )

        if one_minute_data:
            # Aggregate the data
            hourly_bar = aggregate_bars(one_minute_data)

            # Store as 1-hour bar
            hourly_market_id = f"{base_market_id}_1h"
            hourly_timestamp = previous_hour.isoformat()

            store_aggregated_bar(hourly_market_id, hourly_timestamp, hourly_bar)
            processed_items += 1

    return processed_items


def aggregate_to_daily(tz):
    """Aggregate 1-hour bars to daily bars"""
    # Get the current day boundary

    now = datetime.now(tz)
    current_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    previous_day = current_day - timedelta(days=1)

    processed_items = 0

    for market_id in INTERESTING_MARKETS:
        market_id_1h = market_id + '_1h'
        print(f"market_id_1h: {market_id_1h}")

        # Query 1-hour data for the previous day
        hourly_data = query_time_range(
            market_id_1h,
            previous_day,
            current_day
        )

        if hourly_data:
            # Aggregate the data
            daily_bar = aggregate_bars(hourly_data)

            # Store as daily bar
            daily_market_id = f"{market_id}_1d"
            daily_timestamp = previous_day.isoformat()

            store_aggregated_bar(daily_market_id, daily_timestamp, daily_bar)
            processed_items += 1

    return processed_items


def query_time_range(market_id, start_time, end_time):
    """Query DynamoDB for data within a time range"""
    try:
        response = table.query(
            KeyConditionExpression=Key('marketid').eq(market_id) &
                                   Key('timestamp').between(
                                       start_time.isoformat(),
                                       end_time.isoformat()
                                   )
        )
        return response['Items']
    except Exception as e:
        print(f"Error querying data for {market_id}: {str(e)}")
        return []


def aggregate_bars(bars):
    """
    Aggregate multiple bars into a single bar
    Input bars format: [open, high, low, close, min, q1, q2, q3, max]
    """
    if not bars:
        return None

    # Extract OHLC and spread data
    opens = []
    highs = []
    lows = []
    closes = []
    spreads = []  # Will collect all spread values for recalculation

    for bar in bars:
        data = bar.get('data', [])
        if len(data) >= 9:  # Ensure we have all required fields
            opens.append(float(data[0]))
            highs.append(float(data[1]))
            lows.append(float(data[2]))
            closes.append(float(data[3]))

            # Collect all spread values for recalculation
            spreads.extend([
                float(data[4]),  # min
                float(data[5]),  # q1
                float(data[6]),  # q2
                float(data[7]),  # q3
                float(data[8])  # max
            ])

    if not opens:
        return None

    # Calculate aggregated OHLC
    aggregated_open = opens[0]  # First open
    aggregated_high = max(highs)
    aggregated_low = min(lows)
    aggregated_close = closes[-1]  # Last close

    # Calculate new spread quartiles from all spread data
    spreads.sort()
    aggregated_min = min(spreads)
    aggregated_q1 = statistics.quantiles(spreads, n=4)[0] if len(spreads) > 1 else spreads[0]
    aggregated_q2 = statistics.median(spreads)
    aggregated_q3 = statistics.quantiles(spreads, n=4)[2] if len(spreads) > 1 else spreads[0]
    aggregated_max = max(spreads)

    return [
        Decimal(str(aggregated_open)),
        Decimal(str(aggregated_high)),
        Decimal(str(aggregated_low)),
        Decimal(str(aggregated_close)),
        Decimal(str(aggregated_min)),
        Decimal(str(aggregated_q1)),
        Decimal(str(aggregated_q2)),
        Decimal(str(aggregated_q3)),
        Decimal(str(aggregated_max))
    ]


def store_aggregated_bar(market_id, timestamp, bar_data):
    """Store the aggregated bar in DynamoDB"""
    try:
        table.put_item(
            Item={
                'marketid':market_id,
                'timestamp':timestamp,
                'data':bar_data
            }
        )
        print(f"Stored aggregated bar for {market_id} at {timestamp}")
    except Exception as e:
        print(f"Error storing aggregated bar for {market_id}: {str(e)}")

def store_in_dynamodb(market_data) -> None:
    """
    Store a single item in DynamoDB
    """
    try:
        # Extract market summary
        market_summary = market_data.get('market_summary')
        market_id = market_summary.get('market_id') + '_1m'

        # Use provided timestamp or current time
        timestamp = datetime.now(timezone.utc).isoformat()

        volume = '10000_QUOTE'   # one of '100_QUOTE', '1000_QUOTE', '10000_QUOTE', '100000_QUOTE'
        mid_price = (market_data[volume]['buy_price'] - market_data['10000_QUOTE']['sell_price']) / 2
        spread = market_data[volume]['absolute_spread']
        # open, high, low, close, min, q1, q2(median), q3, max
        data = list()
        data.append(mid_price)  # open
        data.append(mid_price)  # high
        data.append(mid_price)  # low
        data.append(mid_price)  # close
        data.append(spread)  # min
        data.append(spread)  # q1
        data.append(spread)  # q2
        data.append(spread)  # q3
        data.append(spread)  # max

        # Prepare the item for DynamoDB
        item = {
            'marketid': market_id,
            'timestamp':timestamp,
            'data': data
        }

        # Store in DynamoDB
        response = table.put_item(Item=item)
        logger.info(f"Successfully stored data for {market_id} at {timestamp}")

    except Exception as e:
        logger.error(f"Error storing market spread data: {str(e)}")
        raise
