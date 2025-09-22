#!/usr/bin/env python3
"""
Script to test the webscraper deployment
Run this from your project root directory
"""

import boto3
import json
import requests
from datetime import datetime
import time


class WebscraperTester:
    def __init__(self, stack_name="SpreadScraperStack"):
        self.dynamodb = boto3.resource('dynamodb')
        self.dynamodb_client = boto3.client('dynamodb')
        self.lambda_client = boto3.client('lambda')
        self.logs_client = boto3.client('logs')
        self.cloudformation = boto3.client('cloudformation')
        self.secrets_client = boto3.client('secretsmanager')
        self.wafv2_client = boto3.client('wafv2')
        self.apigateway_client = boto3.client('apigateway')
        self.stack_name = stack_name
        
        # Get stack outputs
        self.api_url = None
        self.table_name = None
        self.scraper_function_name = None
        self.all_lambda_function_names = []
        self.frontend_bucket = None
        self.cloudfront_domain = None
        self.secret_arn = None
        self.waf_arn = None
        self.api_id = None
        self._get_stack_info()

    def _get_stack_info(self):
        """Get information from CloudFormation stack outputs"""
        try:
            response = self.cloudformation.describe_stacks(StackName=self.stack_name)
            stack = response['Stacks'][0]

            # Get outputs
            outputs = {output['OutputKey']: output['OutputValue']
                      for output in stack.get('Outputs', [])}

            print("📋 Stack Outputs:")
            for key, value in outputs.items():
                print(f"  {key}: {value}")

            # Try to find resources
            resources = self.cloudformation.describe_stack_resources(StackName=self.stack_name)

            for resource in resources['StackResources']:
                if resource['ResourceType'] == 'AWS::DynamoDB::Table':
                    self.table_name = resource['PhysicalResourceId']
                elif resource['ResourceType'] == 'AWS::Lambda::Function':
                    self.all_lambda_function_names = resource['PhysicalResourceId']
                    if 'Scraper' in resource['LogicalResourceId']:
                        self.scraper_function_name = resource['PhysicalResourceId']
                elif resource['ResourceType'] == 'AWS::ApiGateway::RestApi':
                    # Construct API URL
                    api_id = resource['PhysicalResourceId']
                    self.api_id = api_id
                    region = boto3.Session().region_name
                    self.api_url = f"https://{api_id}.execute-api.{region}.amazonaws.com/prod"
                elif resource['ResourceType'] == 'AWS::S3::Bucket':
                    self.frontend_bucket = resource['PhysicalResourceId']
                elif resource['ResourceType'] == 'AWS::CloudFront::Distribution':
                    # Get CloudFront domain
                    cf_client = boto3.client('cloudfront')
                    distribution = cf_client.get_distribution(Id=resource['PhysicalResourceId'])
                    self.cloudfront_domain = distribution['Distribution']['DomainName']
                elif resource['ResourceType'] == 'AWS::SecretsManager::Secret':
                    self.secret_arn = resource['PhysicalResourceId']
                elif resource['ResourceType'] == 'AWS::WAFv2::WebACL':
                    self.waf_arn = resource['PhysicalResourceId']

            print(f"\n🔍 Discovered Resources:")
            print(f"  Table: {self.table_name}")
            print(f"  Scraper Function: {self.scraper_function_name}")
            print(f"  API URL: {self.api_url}")
            print(f"  S3 Bucket: {self.frontend_bucket}")
            print(f"  CloudFront Domain: {self.cloudfront_domain}")
            print(f"  Secret ARN: {self.secret_arn}")
            print(f"  WAF ARN: {self.waf_arn}")

        except Exception as e:
            print(f"❌ Error getting stack info: {e}")
            print("You may need to manually set the resource names")
            raise

    def test_dynamodb_table(self):
        """Test DynamoDB table access and content"""
        print("\n" + "="*50)
        print("🗄️  TESTING DYNAMODB TABLE")
        print("="*50)
        
        if not self.table_name:
            print("❌ Table name not found")
            return False
        
        try:
            #table = self.dynamodb_client.Table(self.table_name)
            
            # Get table info
            response = self.dynamodb_client.describe_table(TableName=self.table_name)
            print(f"✅ Table exists: {self.table_name}")
            print(f"   Status: {response['Table']['TableStatus']}")
            print(f"   Item Count: {response['Table']['ItemCount']}")
            
            # Scan for recent items
            scan_response = self.dynamodb_client.scan(TableName=self.table_name, Limit=5)
            items = scan_response.get('Items', [])
            
            print(f"\n📊 Recent items ({len(items)}):")
            if items:
                for item in items:
                    print(f"marketid: {item.get("marketid", "MISSING")}")
                    print(f"timestamp: {item.get("timestamp", "MISSING")}")
                    print(f"buy/sell: {item['data']['L'][6]['N']} {item['data']['L'][7]['N']}")
                    print()
            else:
                print("  No items found - scraper may not have run yet")
            
            return True
            
        except Exception as e:
            print(f"❌ DynamoDB test failed: {e}")
            return False

    def test_scraper_lambda(self):
        """Test the scraper Lambda function"""
        print("\n" + "="*50)
        print("🕷️  TESTING SCRAPER LAMBDA")
        print("="*50)
        
        if not self.scraper_function_name:
            print("❌ Scraper function name not found")
            return False
        
        try:
            # Get function info
            func_info = self.lambda_client.get_function(FunctionName=self.scraper_function_name)
            print(f"✅ Function exists: {self.scraper_function_name}")
            print(f"   Runtime: {func_info['Configuration']['Runtime']}")
            print(f"   Timeout: {func_info['Configuration']['Timeout']}s")
            
            # Manual invoke
            print(f"\n🚀 Manually invoking scraper...")
            response = self.lambda_client.invoke(
                FunctionName=self.scraper_function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps({})
            )
            
            payload = json.loads(response['Payload'].read())
            print(f"   Status Code: {response['StatusCode']}")
            print(f"   Response: {json.dumps(payload, indent=2)}")
            
            return response['StatusCode'] == 200
            
        except Exception as e:
            print(f"❌ Scraper Lambda test failed: {e}")
            return False

    def test_api_lambda(self):
        """Test the API Lambda function via HTTP"""
        print("\n" + "="*50)
        print("🌐 TESTING API GATEWAY & LAMBDA")
        print("="*50)
        
        if not self.api_url:
            print("❌ API URL not found")
            return False
        
        try:
            # Test the /data endpoint
            data_url = f"{self.api_url}/data/BTC-AUD_1m"
            print(f"📡 Testing: {data_url}")
            
            response = requests.get(data_url, timeout=30)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Items returned: {len(data.get('items', []))}")
                print(f"   Sources: {data.get('sources', [])}")
                
                if data.get('items'):
                    print(f"\n📋 Sample item:")
                    print(f"market      :{data['items'][0]['marketid']}")
                    print(f"timestamp   :{data['items'][0]['timestamp']}")
                    print(f"buy  100000: {data['items'][0]['data'][6]}")
                    print(f"sell 100000: {data['items'][0]['data'][7]}")
                return True
            else:
                print(f"   Error: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ API test failed: {e}")
            return False

    def check_eventbridge_rule(self):
        """Check if EventBridge rule is properly configured"""
        print("\n" + "="*50)
        print("⏰ CHECKING EVENTBRIDGE SCHEDULE")
        print("="*50)
        
        try:
            events_client = boto3.client('events')
            
            # List rules to find our scraping rule
            rules = events_client.list_rules()
            scraper_rules = [rule for rule in rules['Rules'] 
                           if 'scraping' in rule['Name'].lower() or 
                              self.stack_name.lower() in rule['Name'].lower()]
            
            if scraper_rules:
                for rule in scraper_rules:
                    print(f"✅ Found rule: {rule['Name']}")
                    print(f"   Schedule: {rule.get('ScheduleExpression', 'Not scheduled')}")
                    print(f"   State: {rule['State']}")
                    
                    # Get targets
                    targets = events_client.list_targets_by_rule(Rule=rule['Name'])
                    print(f"   Targets: {len(targets['Targets'])}")
                return True
            else:
                print("❌ No EventBridge rules found")
                return False
                
        except Exception as e:
            print(f"❌ EventBridge check failed: {e}")
            return False

    def get_recent_logs(self, all_function_names, hours=1):
        """Get recent logs from a Lambda function"""
        print("\n" + "="*50)
        print("🔍 RECENT LOGS")
        print("="*50)
        for function_name in all_function_names:
            try:
                log_group = f"/aws/src/{function_name}"

                # Get log streams
                streams = self.logs_client.describe_log_streams(
                    logGroupName=log_group,
                    orderBy='LastEventTime',
                    descending=True,
                    limit=3
                )

                print(f"\n📜 Recent logs from {function_name}:")
                for stream in streams['logStreams'][:2]:  # Show 2 most recent streams
                    events = self.logs_client.get_log_events(
                        logGroupName=log_group,
                        logStreamName=stream['logStreamName'],
                        limit=10
                    )

                    print(f"\n  Stream: {stream['logStreamName']}")
                    for event in events['events'][-5:]:  # Show last 5 events
                        timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                        message = event['message'].strip()
                        print(f"    {timestamp}: {message}")

            except Exception as e:
                print(f"❌ Error getting logs: {e}")

    def get_s3_bucket_info(self):
        """Get S3 bucket information and upload commands"""
        print("\n" + "="*50)
        print("🪣 S3 BUCKET INFORMATION")
        print("="*50)
        
        if not self.frontend_bucket:
            print("❌ Frontend bucket not found in stack resources")
            return False
        
        try:
            s3_client = boto3.client('s3')
            
            # Check if bucket exists and get info
            try:
                bucket_info = s3_client.head_bucket(Bucket=self.frontend_bucket)
                print(f"✅ S3 Bucket: {self.frontend_bucket}")
                
                # Check if bucket has website configuration
                try:
                    website_config = s3_client.get_bucket_website(Bucket=self.frontend_bucket)
                    print(f"   Website hosting: Enabled")
                    print(f"   Index document: {website_config.get('IndexDocument', {}).get('Suffix', 'N/A')}")
                except:
                    print(f"   Website hosting: Not configured (using CloudFront)")
                
                # List current objects
                objects = s3_client.list_objects_v2(Bucket=self.frontend_bucket, MaxKeys=10)
                if 'Contents' in objects:
                    print(f"   Current objects ({len(objects['Contents'])}):")
                    for obj in objects['Contents']:
                        print(f"     • {obj['Key']} ({obj['Size']} bytes, {obj['LastModified']})")
                else:
                    print(f"   Current objects: Empty bucket")
                
            except s3_client.exceptions.NoSuchBucket:
                print(f"❌ Bucket {self.frontend_bucket} does not exist")
                return False
            
            return True
            
        except Exception as e:
            print(f"❌ Error getting bucket info: {e}")
            return False

    def show_upload_commands(self):
        """Display commands to upload frontend files"""
        print("\n" + "="*50)
        print("📤 FRONTEND UPLOAD COMMANDS")
        print("="*50)
        
        if not self.frontend_bucket:
            print("❌ Cannot generate upload commands - bucket name unknown")
            return
        
        print(f"🎯 Target S3 Bucket: {self.frontend_bucket}")
        if self.cloudfront_domain:
            print(f"🌐 CloudFront URL: https://{self.cloudfront_domain}")
        if self.api_url:
            print(f"🔗 API URL (update in frontend): {self.api_url}")
        
        print(f"\n📋 Upload Commands:")
        print(f"")
        print(f"# Upload single file:")
        print(f"aws s3 cp frontend/index.html s3://{self.frontend_bucket}/")
        print(f"")
        print(f"# Upload entire frontend directory:")
        print(f"aws s3 sync frontend/ s3://{self.frontend_bucket}/ --delete")
        print(f"")
        print(f"# Upload with public-read permissions (if needed):")
        print(f"aws s3 cp frontend/index.html s3://{self.frontend_bucket}/ --acl public-read")
        print(f"")
        print(f"# Verify upload:")
        print(f"aws s3 ls s3://{self.frontend_bucket}/")
        
        if self.cloudfront_domain:
            print(f"\n🔄 CloudFront Cache Invalidation (after upload):")
            print(f"# Get distribution ID first:")
            print(f"aws cloudformation describe-stack-resources \\")
            print(f"  --stack-name {self.stack_name} \\")
            print(f"  --query 'StackResources[?ResourceType==`AWS::CloudFront::Distribution`].PhysicalResourceId' \\")
            print(f"  --output text")
            print(f"")
            print(f"# Then invalidate cache (replace DISTRIBUTION_ID):")
            print(f"aws cloudfront create-invalidation \\")
            print(f"  --distribution-id DISTRIBUTION_ID \\")
            print(f"  --paths '/*'")
        
        print(f"\n⚠️  IMPORTANT REMINDERS:")
        print(f"1. Update API_BASE_URL in frontend/index.html to: {self.api_url}")
        print(f"2. Test your frontend locally before uploading")
        print(f"3. Invalidate CloudFront cache after uploads to see changes immediately")
        
        if self.cloudfront_domain:
            print(f"4. Access your app at: https://{self.cloudfront_domain}")


    def validate_frontend_file(self):
        """Check if frontend file exists and has correct API URL"""
        print("\n" + "="*50)
        print("🔍 FRONTEND FILE VALIDATION")
        print("="*50)
        
        frontend_file = "frontend/index.html"
        
        try:
            import os
            if not os.path.exists(frontend_file):
                print(f"❌ Frontend file not found: {frontend_file}")
                print(f"   Make sure you've created the frontend/index.html file")
                return False
            
            # Check file size
            file_size = os.path.getsize(frontend_file)
            print(f"✅ Frontend file exists: {frontend_file}")
            print(f"   File size: {file_size:,} bytes")
            
            # Check if API URL is configured
            with open(frontend_file, 'r') as f:
                content = f.read()
                
                if 'API_BASE_URL' in content:
                    print(f"✅ API_BASE_URL found in frontend")
                    
                    # Check if it's still the placeholder
                    if 'your-api-id.execute-api.your-region.amazonaws.com' in content:
                        print(f"⚠️  API_BASE_URL still contains placeholder!")
                        print(f"   Update it to: {self.api_url}")
                        return False
                    elif self.api_url and self.api_url.replace('https://', '') in content:
                        print(f"✅ API_BASE_URL appears to be correctly configured")
                        return True
                    else:
                        print(f"⚠️  API_BASE_URL may not match deployed API")
                        print(f"   Expected: {self.api_url}")
                        return False
                else:
                    print(f"❌ API_BASE_URL not found in frontend file")
                    return False

        except Exception as e:
            print(f"❌ Error validating frontend: {e}")
            return False

    def test_secrets_manager(self):
        """Test Secrets Manager configuration"""
        print("\n" + "="*50)
        print("🔐 TESTING SECRETS MANAGER")
        print("="*50)
        
        if not self.secret_arn:
            print("❌ Secret ARN not found in stack resources")
            return False
        
        try:
            # Get secret metadata
            secret_info = self.secrets_client.describe_secret(SecretId=self.secret_arn)
            print(f"✅ Secret exists: {secret_info['Name']}")
            print(f"   ARN: {secret_info['ARN']}")
            print(f"   Description: {secret_info.get('Description', 'No description')}")
            
            # Check if secret has a value
            try:
                secret_value = self.secrets_client.get_secret_value(SecretId=self.secret_arn)
                print(f"✅ Secret has value (length: {len(secret_value['SecretString'])} chars)")
                
                # Parse JSON to validate structure
                import json
                credentials = json.loads(secret_value['SecretString'])
                expected_keys = ['btcmarkets_api_key', 'btcmarkets_secret', 'binance_api_key', 'binance_secret']
                
                print(f"   Expected credential keys:")
                for key in expected_keys:
                    if key in credentials:
                        has_value = bool(credentials[key].strip()) if credentials[key] else False
                        status = "✅ Present" if has_value else "⚠️  Empty"
                        print(f"     {key}: {status}")
                    else:
                        print(f"     {key}: ❌ Missing")
                
                return True
                
            except self.secrets_client.exceptions.ResourceNotFoundException:
                print(f"❌ Secret value not found")
                return False
                
        except Exception as e:
            print(f"❌ Secrets Manager test failed: {e}")
            return False

    def test_waf_configuration(self):
        """Test WAF configuration and API Gateway association"""
        print("\n" + "="*50)
        print("🛡️  TESTING WAF CONFIGURATION")
        print("="*50)
        
        if not self.waf_arn:
            print("❌ WAF ARN not found in stack resources")
            return False
        
        try:
            # Parse WAF ARN to get ID and name
            # ARN format: arn:aws:wafv2:region:account:regional/webacl/name/id
            waf_id = self.waf_arn.split('/')[-1]
            
            # Get WAF information
            waf_info = self.wafv2_client.get_web_acl(
                Name="MarketScraperWAF",  # From our CDK implementation
                Id=waf_id,
                Scope="REGIONAL"
            )
            
            print(f"✅ WAF exists: {waf_info['WebACL']['Name']}")
            print(f"   ID: {waf_info['WebACL']['Id']}")
            print(f"   Default Action: {waf_info['WebACL']['DefaultAction']}")
            print(f"   Rules: {len(waf_info['WebACL']['Rules'])}")
            
            # List rules
            for i, rule in enumerate(waf_info['WebACL']['Rules'], 1):
                print(f"     {i}. {rule['Name']} (Priority: {rule['Priority']})")
            
            # Check if WAF is associated with API Gateway
            if self.api_id:
                try:
                    region = boto3.Session().region_name
                    stage = "prod"  # Default stage name
                    resource_arn = f"arn:aws:apigateway:{region}::/restapis/{self.api_id}/stages/{stage}"
                    
                    # Get associated resources
                    associations = self.wafv2_client.list_resources_for_web_acl(
                        WebACLArn=self.waf_arn,
                        ResourceType="API_GATEWAY"
                    )
                    
                    if resource_arn in associations['ResourceArns']:
                        print(f"✅ WAF is associated with API Gateway")
                    else:
                        print(f"⚠️  WAF association with API Gateway not found")
                        print(f"   Expected: {resource_arn}")
                        print(f"   Found: {associations['ResourceArns']}")
                        
                except Exception as e:
                    print(f"⚠️  Could not verify WAF association: {e}")
            
            return True
            
        except Exception as e:
            print(f"❌ WAF test failed: {e}")
            return False

    def test_waf_rate_limiting(self):
        """Test WAF rate limiting by making rapid requests"""
        print("\n" + "="*50)
        print("⚡ TESTING WAF RATE LIMITING")
        print("="*50)
        
        if not self.api_url:
            print("❌ API URL not found - cannot test rate limiting")
            return False
        
        print("🚀 Making rapid requests to test rate limiting...")
        print("   (This should trigger WAF blocking after 2000 requests per 5-min window)")
        
        success_count = 0
        blocked_count = 0
        error_count = 0
        
        try:
            # Make 10 rapid requests to test
            for i in range(10):
                try:
                    response = requests.get(f"{self.api_url}/markets", timeout=5)
                    if response.status_code == 200:
                        success_count += 1
                    elif response.status_code == 403:
                        blocked_count += 1
                        print(f"   Request {i+1}: ✅ BLOCKED by WAF (403)")
                    else:
                        error_count += 1
                        print(f"   Request {i+1}: Other status {response.status_code}")
                except requests.exceptions.RequestException as e:
                    error_count += 1
                    print(f"   Request {i+1}: Request failed - {e}")
                
                # Small delay between requests
                time.sleep(0.1)
            
            print(f"\n📊 Rate Limiting Test Results:")
            print(f"   Successful: {success_count}")
            print(f"   Blocked by WAF: {blocked_count}")
            print(f"   Errors: {error_count}")
            
            if success_count > 0:
                print(f"✅ API is accessible (WAF allows normal traffic)")
            
            if blocked_count > 0:
                print(f"✅ WAF rate limiting is working")
            else:
                print(f"ℹ️  No rate limiting triggered (normal with low request volume)")
            
            return True
            
        except Exception as e:
            print(f"❌ Rate limiting test failed: {e}")
            return False

    def run_full_test(self):
        """Run all tests"""
        print("🧪 WEBSCRAPER DEPLOYMENT TESTER")
        print("=" * 60)
        
        results = []
        results.append(("DynamoDB Table", self.test_dynamodb_table()))
        results.append(("Scraper Lambda", self.test_scraper_lambda()))
        results.append(("API Gateway", self.test_api_lambda()))
        results.append(("EventBridge Rule", self.check_eventbridge_rule()))
        results.append(("S3 Bucket Info", self.get_s3_bucket_info()))
        results.append(("Frontend File", self.validate_frontend_file()))
        results.append(("Secrets Manager", self.test_secrets_manager()))
        results.append(("WAF Configuration", self.test_waf_configuration()))
        results.append(("WAF Rate Limiting", self.test_waf_rate_limiting()))
        
        # Wait a moment after manual scraper invoke
        #if results[1][1]:  # If scraper test passed
        #    print("\n⏳ Waiting 5 seconds for scraper data to settle...")
        #    time.sleep(5)
        #    print("\n🔄 Re-checking DynamoDB for new data...")
        #    self.test_dynamodb_table()
        
        # Show logs if we have function names
        self.get_recent_logs(self.all_lambda_function_names)
        
        # Summary
        print("\n" + "="*60)
        print("📊 TEST SUMMARY")
        print("="*60)
        
        for test_name, passed in results:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status} {test_name}")
        
        all_passed = all(result[1] for result in results)
        if all_passed:
            print(f"\n🎉 All tests passed! Your API URL is:")
            print(f"   {self.api_url}")
            print(f"   API URL: {self.api_url}")
        else:
            print(f"\n⚠️  Some tests failed. Check the details above.")

if __name__ == "__main__":
    # You may need to adjust the stack name
    try:
        tester = WebscraperTester("SpreadScraperStack")
        tester.run_full_test()
        tester.show_upload_commands()
    except Exception as e:
        print("❌ Critical exception: ", e)
        raise
