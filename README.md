# Postcall Analytics with Genesys Contact Centre and Amazon Bedrock

## AWS Resources Required

* Create an Amazon S3 bucket for storing the Genesys conversations - a Genesys Trigger Load Call Records lambda function will read from this bucket
* Create an Amazon S3 bucket for storing output from Amazon Bedrock - a Genesys Load Call Records lambda function will write to this bucket - e.g. genesys-call-record-output - this will later be crawled with AWS Glue and used to show in a dashboard



## Genesys Trigger Load Call Records

An AWS Lambda function is used to trigger the processing of Genesys call records sitting in Amazon S3. The call centre records are normally organized by date prefixes in Amazon S3 and we will use this organization to process a subset of the call records.

### Create the AWS Lambda function

* Create a new AWS Lambda function - genesys-trigger-load-call-records - python3.11
* The function needs IAM permissions to:
  * read from an S3 bucket with the genesys conversations
  * write to an Amazon SQS queue

### AWS Lambda - Trigger Test JSON

{
  "input_s3_bucket_name": "genesys-call-inputs-aws-accountid",
  "input_s3_object_key_prefix": "originalAudio/"
}




## Genesys Load Call Records

### Create the AWS Lambda function

* Create a new AWS Lambda function - genesys-load-call-records - python3.11
* The function needs IAM permissions to:
  * read from an S3 bucket with the genesys conversations
  * write to another S3 bucket with summary of the conversations
  * have an inline IAM policy for BedrockAccess ( https://docs.aws.amazon.com/bedrock/latest/userguide/security_iam_id-based-policy-examples.html )
* Add the latest python Boto3 library as a Lambda layer (required until Bedrock APIs are natively supported by AWS Lambda)

### Amazon IAM - Amazon Bedrock IAM policy 

```json
{
	“Version”: “2012-10-17",
	“Statement”: [
		{
			“Sid”: “BedrockConsole”,
			“Effect”: “Allow”,
			“Action”: [
				“bedrock:*”
			],
			“Resource”: “*”
		}
	]
}
```

### AWS Lambda Layer for Amazon Bedrock

The use of an AWS Lambda Layer for the latest Python Boto3 library is only required until the Amazon Bedrock APIs are added to the AWS Lambda python runtime by default.

In your local terminal or AWS CloudShell, create a boto3 Lamba Layer:

```bash
mkdir bedrock-lambda-layer
cd bedrock-lambda-layer
mkdir python
cd python
pip3 install boto3 -t .
cd ..
zip -r boto3_layer.zip .
```

In AWS Lambda, LHS menu -> Layers -> Create layer -> Name like Boto3Layer -> Select the same architecture/runtime as the above lambda layer





## AWS Lambda - Genesys Load Call Records

The input from this function is an Amazon SQS queue event containing a list of Amazon S3 buckets and object keys referencing the .opus_metadata.json suffixed JSON file. The .opus_metadata.json is always returned by Genesys for a conversation and includes reference ids to the related files, some of which are optional depending on if a transcript was included or not.

This Lambda function aggregates the related Genesys call transcript and metadata files, passes the transcript to Amazon Bedrock with an array of prompts, then saves the responses to an Amazon S3 bucket.

```json
{
  "records_processed": 10
}
```


