import json
import os
from boto3.dynamodb.conditions import Key
from decimal import Decimal
import boto3
from datetime import datetime, timezone
import re
from typing import Optional



#
INTERESTING_MARKETS: list[str] = ['BTC-AUD', 'XRP-AUD', 'SOL-AUD', 'ETH-AUD', 'SUI-AUD', 'USDT-AUD', 'USDC-AUD', 'LTC-AUD', 'XLM-AUD', 'AVAX-AUD']
INTERESTING_CANDLES: list[str] = ['_1d', '_1h', '_1m']


# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table_name = os.environ['DYNAMODB_TABLE_NAME']
table = dynamodb.Table(table_name)


class DecimalEncoder(json.JSONEncoder):
    """Helper class to convert DynamoDB Decimal types to JSON"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


def validate_market_id(market_id: str) -> bool:
    """Validate market ID against allowlist"""
    allowed_pattern = r'^[A-Z]{3,5}-[A-Z]{3}(_1[mhd])?$'
    return bool(re.match(allowed_pattern, market_id))


def handler(event, context):
    """
    Lambda function to handle API requests for scraped data
    """
    
    try:
        # Get HTTP method and path
        http_method = event['httpMethod']
        path = event['path']
        query_params = event.get('queryStringParameters') or {}
        
        print(f"Received {http_method} request to {path}")

        if http_method == 'GET' and path.startswith('/data/'):
            # Extract item ID from path
            market_id = path.split('/')[-1]
            if not validate_market_id(market_id):
                return {
                    'statusCode':400,
                    'body':json.dumps({'error':'Invalid market ID format'})
                }
            return get_market_data(market_id)
        elif http_method == 'GET' and path == '/markets':
            return get_available_markets()
        else:
            return {
                'statusCode': 404,
                'headers': get_cors_headers(),
                'body': json.dumps({
                    'error': 'Endpoint not found'
                })
            }
            
    except Exception as e:
        print(f"Error in API handler: {str(e)}")
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'error': 'Internal server error',
                'details': str(e)
            })
        }

def get_market_data(marketid: str):
    """
    Retrieve a specific market spread item by market_id
    Expected format: market_id, like BTC-AUD
    """
    try:
        # Get latest item for this market
        response = table.query(
            KeyConditionExpression=Key('marketid').eq(marketid),
            Limit=100,
            ScanIndexForward=False  # Get most recent
        )

        items = response.get('Items', [])

        if len(items) == 0:
            return {
                'statusCode': 404,
                'headers': get_cors_headers(),
                'body': json.dumps({
                    'error': 'Item not found'
                })
            }
        
        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'items': items
            }, cls=DecimalEncoder)
        }
        
    except Exception as e:
        print(f"Error retrieving item {marketid}: {str(e)}")
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'error': 'Failed to retrieve item',
                'details': str(e)
            })
        }

def get_cors_headers():
    """
    Return CORS headers for API responses
    """
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
    }

def get_available_markets():
    """
    Get list of all available markets
    """
    try:
        response = table.scan(
            ProjectionExpression="marketid"
        )

        markets = list()
        for market in INTERESTING_MARKETS:
            for candle in INTERESTING_CANDLES:
                markets.append(market + candle)

        #items = response.get('Items', [])
        #markets = list(set(item.get('marketid', '') for item in items if item.get('marketid')))
        markets.sort()
        
        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'markets': markets,
                'count': len(markets)
            })
        }
        
    except Exception as e:
        print(f"Error getting markets: {str(e)}")
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'error': 'Failed to get markets',
                'details': str(e)
            })
        }
