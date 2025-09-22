import boto3
from aws_cdk import RemovalPolicy, aws_dynamodb
from boto3.dynamodb.conditions import Key
from datetime import datetime, timezone
import os


class MarketSpreadStorage:
    def __init__(self, table_name='market_spreads', region='ap-southeast-2'):
        """
        Initialize DynamoDB client and table reference

        Args:
            table_name: Name of the DynamoDB table
            region: AWS region for DynamoDB
        """



    def create_table_if_not_exists(self):
        """
        Create the DynamoDB table if it doesn't exist

        Table Schema:
        - Partition Key: market_id (e.g., 'ETH-AUD', 'BTC-AUD')
        - Sort Key: timestamp (ISO format string for sorting)
        """
        try:
            # Check if table exists
            self.table.load()
            print(f"Table {self.table_name} already exists")
        except aws_dynamodb.meta.client.exceptions.ResourceNotFoundException:
            # Create table
            table = aws_dynamodb.create_table(
                TableName=self.table_name,
                KeySchema=[
                    {
                        'AttributeName':'market_id',
                        'KeyType':'HASH'  # Partition key
                    },
                    {
                        'AttributeName':'timestamp',
                        'KeyType':'RANGE'  # Sort key
                    }
                ],
                AttributeDefinitions=[
                    {
                        'AttributeName':'market_id',
                        'AttributeType':'S'
                    },
                    {
                        'AttributeName':'timestamp',
                        'AttributeType':'S'
                    }
                ],
                BillingMode='PAY_PER_REQUEST'  # On-demand billing
            )

            # Wait for table to be created
            table.wait_until_exists()
            print(f"Table {self.table_name} created successfully")
            self.table = table

    def store_market_spread(self, market_data, timestamp=None):
        """
        Store market spread data in DynamoDB

        Args:
            market_data: Dictionary containing spread data for different levels
            timestamp: Optional timestamp (will use current time if not provided)

        Returns:
            bool: Success status
        """
        try:
            # Extract market summary
            market_summary = market_data.get('market_summary', {})
            market_id = market_summary.get('market_id', 'UNKNOWN')

            # Use provided timestamp or current time
            if timestamp is None:
                timestamp = datetime.now(timezone.utc)

            # Prepare the item for DynamoDB
            item = {
                'market_id':market_id,
                'timestamp':timestamp,
                'market_summary':market_summary,
                'spread_levels':{}
            }

            # Process each spread level (excluding market_summary)
            for level_key, level_data in market_data.items():
                if level_key != 'market_summary':
                    item['spread_levels'][level_key] = level_data

            # Store in DynamoDB
            response = self.table.put_item(Item=item)
            print(f"Successfully stored data for {market_id} at {timestamp}")
            return True

        except Exception as e:
            print(f"Error storing market spread data: {str(e)}")
            return False

    def batch_store_market_spreads(self, market_data_list):
        """
        Store multiple market spread records efficiently using batch writes

        Args:
            market_data_list: List of market data dictionaries

        Returns:
            int: Number of successfully stored records
        """
        success_count = 0

        # DynamoDB batch write can handle up to 25 items at once
        batch_size = 25

        for i in range(0, len(market_data_list), batch_size):
            batch = market_data_list[i:i + batch_size]

            try:
                with self.table.batch_writer() as batch_writer:
                    for market_data in batch:
                        market_summary = market_data.get('market_summary', {})
                        market_id = market_summary.get('market_id', 'UNKNOWN')
                        timestamp = market_summary.get('datetime', datetime.utcnow().isoformat())

                        item = {
                            'market_id':market_id,
                            'timestamp':timestamp,
                            'market_summary':market_summary,
                            'spread_levels':{k:v for k, v in market_data.items() if k != 'market_summary'}
                        }

                        batch_writer.put_item(Item=item)
                        success_count += 1

                print(f"Successfully stored batch of {len(batch)} records")

            except Exception as e:
                print(f"Error in batch write: {str(e)}")

        return success_count

    def get_market_spread(self, market_id, timestamp):
        """
        Retrieve a specific market spread record

        Args:
            market_id: Market identifier (e.g., 'ETH-AUD')
            timestamp: Timestamp of the record

        Returns:
            dict: Market spread data or None if not found
        """
        try:
            response = self.table.get_item(
                Key={
                    'market_id':market_id,
                    'timestamp':timestamp
                }
            )
            return response.get('Item')
        except Exception as e:
            print(f"Error retrieving market spread: {str(e)}")
            return None

    def query_market_spreads(self, market_id, start_time=None, end_time=None, limit=100):
        """
        Query market spreads for a specific market within a time range

        Args:
            market_id: Market identifier
            start_time: Start timestamp (ISO format)
            end_time: End timestamp (ISO format)
            limit: Maximum number of records to return

        Returns:
            list: List of market spread records
        """
        try:
            # Build the key condition
            key_condition = Key('market_id').eq(market_id)

            # Add time range conditions if provided
            if start_time and end_time:
                key_condition = key_condition & Key('timestamp').between(start_time, end_time)
            elif start_time:
                key_condition = key_condition & Key('timestamp').gte(start_time)
            elif end_time:
                key_condition = key_condition & Key('timestamp').lte(end_time)

            response = self.table.query(
                KeyConditionExpression=key_condition,
                Limit=limit,
                ScanIndexForward=False  # Sort in descending order (newest first)
            )

            return response.get('Items', [])
        except Exception as e:
            print(f"Error querying market spreads: {str(e)}")
            return []

