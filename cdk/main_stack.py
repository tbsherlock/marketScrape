from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_apigateway as apigateway,
    aws_lambda as _lambda,
    aws_dynamodb as dynamodb,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_wafv2 as waf,
    aws_secretsmanager as secretsmanager,
    RemovalPolicy,
    Duration
)
from constructs import Construct

class SpreadScraperStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # DynamoDB Table for scraped data
        self.scraped_data_table = dynamodb.Table(
            self, "ScrapedDataTable",
            table_name="scraper-data",
            partition_key=dynamodb.Attribute(
                name="marketid",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=True,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.DESTROY
        )

        # DynamoDB Table for binance price feed data
        self.price_data_table = dynamodb.Table(
            self, "PriceDataTable",
            table_name="price-data",
            partition_key=dynamodb.Attribute(
                name="marketid",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=True,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Secrets Manager for API credentials
        self.api_secrets = secretsmanager.Secret(
            self, "ApiCredentials",
            secret_name="market-scraper/api-credentials",
            description="API credentials for cryptocurrency exchanges",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"btcmarkets_api_key": "", "btcmarkets_secret": "", "binance_api_key": "", "binance_secret": ""}',
                generate_string_key="placeholder",
                exclude_characters='"@/\\'
            )
        )

        # S3 bucket for frontend hosting
        self.frontend_bucket = s3.Bucket(
            self, "FrontendBucket",
            bucket_name=f"webscraper-frontend-{self.account}-{self.region}",
            website_index_document="index.html",
            public_read_access=False,  # CloudFront will handle access
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Lambda function for API
        self.api_lambda = _lambda.Function(
            self,"ApiLambda",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="api_handler.handler",
            code=_lambda.Code.from_asset("src/api"),
            environment={
                "DYNAMODB_TABLE_NAME": self.scraped_data_table.table_name,
                "LOG_LEVEL": "INFO",
                "POWERTOOLS_SERVICE_NAME": "market-scraper",  # For structured logging
                "API_SECRETS_ARN": self.api_secrets.secret_arn
            },
            reserved_concurrent_executions=5,  # Prevent resource exhaustion
            timeout=Duration.seconds(30),  # Reduce from default 3min
        )

        # Grant Lambda permission to read/write to DynamoDB
        self.scraped_data_table.grant_read_write_data(self.api_lambda)
        self.price_data_table.grant_read_write_data(self.api_lambda)
        
        # Grant Lambda permission to read API secrets
        self.api_secrets.grant_read(self.api_lambda)

        # API Gateway
        self.api = apigateway.RestApi(
            self, "SpreadScraperApi",
            rest_api_name="Spread Scraper API",
            description="API for spread scraper application",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS
            ),
            deploy_options = apigateway.StageOptions(
            throttling_rate_limit=100,
            throttling_burst_limit=200,
            logging_level=apigateway.MethodLoggingLevel.INFO
            )
        )

        # API Gateway integration
        api_integration = apigateway.LambdaIntegration(self.api_lambda)
        
        # API endpoints
        data_resource = self.api.root.add_resource("data")

        # Add a resource with a path parameter '{market_id}' under 'data'
        market_resource = data_resource.add_resource("{market_id}")
        market_resource.add_method("GET", api_integration)

        # Add markets endpoint
        markets_resource = self.api.root.add_resource("markets")
        markets_resource.add_method("GET", api_integration)

        # WAF for API Gateway protection
        self.waf = waf.CfnWebACL(
            self, "ApiGatewayWAF",
            scope="REGIONAL",  # For API Gateway REST API
            default_action=waf.CfnWebACL.DefaultActionProperty(
                allow=waf.CfnWebACL.AllowActionProperty()
            ),
            description="WAF for Market Scraper API Gateway",
            name="MarketScraperWAF",
            rules=[
                # AWS Managed Rule: Core Rule Set (OWASP Top 10)
                waf.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesCore",
                    priority=1,
                    override_action=waf.CfnWebACL.OverrideActionProperty(
                        none={}
                    ),
                    statement=waf.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesCommonRuleSet"
                        )
                    ),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="AWSManagedRulesCore",
                        sampled_requests_enabled=True
                    )
                ),
                # AWS Managed Rule: Known Bad Inputs
                waf.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesKnownBadInputs",
                    priority=2,
                    override_action=waf.CfnWebACL.OverrideActionProperty(
                        none={}
                    ),
                    statement=waf.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesKnownBadInputsRuleSet"
                        )
                    ),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="AWSManagedRulesKnownBadInputs",
                        sampled_requests_enabled=True
                    )
                ),
                # Rate limiting rule
                waf.CfnWebACL.RuleProperty(
                    name="RateLimitRule",
                    priority=3,
                    action=waf.CfnWebACL.RuleActionProperty(
                        block=waf.CfnWebACL.BlockActionProperty()
                    ),
                    statement=waf.CfnWebACL.StatementProperty(
                        rate_based_statement=waf.CfnWebACL.RateBasedStatementProperty(
                            limit=1000,  # Requests per 5-minute window
                            aggregate_key_type="IP"
                        )
                    ),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="RateLimitRule",
                        sampled_requests_enabled=True
                    )
                )
            ],
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="MarketScraperWAF",
                sampled_requests_enabled=True
            )
        )

        # Associate WAF with API Gateway
        self.waf_association = waf.CfnWebACLAssociation(
            self, "ApiGatewayWAFAssociation",
            resource_arn=f"arn:aws:apigateway:{self.region}::/restapis/{self.api.rest_api_id}/stages/{self.api.deployment_stage.stage_name}",
            web_acl_arn=self.waf.attr_arn
        )

        # Lambda function for web scraping
        self.scraper_lambda = _lambda.Function(
            self,
            "ScraperLambda",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="scraper_handler.scrape_handler",
            code=_lambda.Code.from_asset("src/scraper"),
            environment={
                "DYNAMODB_TABLE_NAME": self.scraped_data_table.table_name,
                "API_SECRETS_ARN": self.api_secrets.secret_arn
            },
            timeout=Duration.minutes(1)
        )

        # Grant scraper Lambda permission to write to DynamoDB
        self.scraped_data_table.grant_write_data(self.scraper_lambda)
        self.price_data_table.grant_write_data(self.scraper_lambda)
        
        # Grant scraper Lambda permission to read API secrets
        self.api_secrets.grant_read(self.scraper_lambda)

        # EventBridge rule to trigger scraping
        scraping_rule = events.Rule(
            self, "ScrapingSchedule",
            schedule=events.Schedule.rate(Duration.minutes(1))
        )

        # Add Lambda as target for the EventBridge rule
        scraping_rule.add_target(targets.LambdaFunction(self.scraper_lambda))

        # Lambda function for OHLC aggregation
        self.aggregation_lambda = _lambda.Function(
            self,
            "AggregateLambda",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="scraper_handler.aggregate_handler",
            code=_lambda.Code.from_asset("src/scraper"),
            environment={
                "DYNAMODB_TABLE_NAME": self.scraped_data_table.table_name,
            },
            timeout=Duration.minutes(2)
        )

        # Grant aggregation Lambda permission to read/write to DynamoDB
        self.scraped_data_table.grant_read_write_data(self.aggregation_lambda)
        
        # Grant aggregation Lambda permission to read API secrets
        self.api_secrets.grant_read(self.aggregation_lambda)


        # EventBridge rule for hourly aggregation (every hour at minute 0)
        hourly_rule = events.Rule(
            self, "HourlyAggregationRule",
            description="Trigger OHLC hourly aggregation every hour",
            schedule=events.Schedule.cron(
                minute="1",    # At minute 0
                hour="*",      # Every hour
                day="*",       # Every day
                month="*",     # Every month
                year="*"       # Every year
            )
        )

        # EventBridge rule for daily aggregation (every day at midnight)
        daily_rule = events.Rule(
            self, "DailyAggregationRule",
            description="Trigger OHLC daily aggregation every day at midnight",
            schedule=events.Schedule.cron(
                minute="1",    # At minute 0
                hour="0",      # At hour 0 (midnight)
                day="*",       # Every day
                month="*",     # Every month
                year="*"       # Every year
            )
        )

        # Add Lambda as target for hourly rule
        hourly_rule.add_target(targets.LambdaFunction(
            self.aggregation_lambda,
            event=events.RuleTargetInput.from_object({
                "aggregation_type": "1h",
                "timezone": "Australia/Melbourne"  # Adjust timezone as needed
            })
        ))

        # Add Lambda as target for daily rule
        daily_rule.add_target(targets.LambdaFunction(
            self.aggregation_lambda,
            event=events.RuleTargetInput.from_object({
                "aggregation_type": "1d",
                "timezone": "Australia/Melbourne"  # Adjust timezone as needed
            })
        ))

        # Grant EventBridge permission to invoke Lambda
        self.aggregation_lambda.add_permission(
            "AllowEventBridgeInvoke",
            principal=iam.ServicePrincipal("events.amazonaws.com")
        )


        # CloudFront Origin Access Identity
        origin_access_identity = cloudfront.OriginAccessIdentity(
            self, "FrontendOAI",
            comment="OAI for webscraper frontend"
        )

        # Grant CloudFront access to S3 bucket
        self.frontend_bucket.grant_read(origin_access_identity)

        # CloudFront distribution
        self.distribution = cloudfront.CloudFrontWebDistribution(
            self, "FrontendDistribution",
            origin_configs=[
                cloudfront.SourceConfiguration(
                    s3_origin_source=cloudfront.S3OriginConfig(
                        s3_bucket_source=self.frontend_bucket,
                        origin_access_identity=origin_access_identity
                    ),
                    behaviors=[
                        cloudfront.Behavior(
                            is_default_behavior=True,
                            compress=True,
                            allowed_methods=cloudfront.CloudFrontAllowedMethods.GET_HEAD_OPTIONS,
                            cached_methods=cloudfront.CloudFrontAllowedCachedMethods.GET_HEAD_OPTIONS
                        )
                    ]
                )
            ],
            default_root_object="index.html"
        )
