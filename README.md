# Postcall Analytics with Genesys Contact Centre and Amazon Bedrock

This solution shows a simple implementation for getting insights out of your Genesys Contact Centre call transcripts using generative AI.


## Introduction to Amazon Bedrock

[Amazon Bedrock](https://aws.amazon.com/bedrock/) is an AWS managed service used to build and scale generative AI applications with foundation models.

### Anthropic's Claude on Amazon Bedrock

[Anthropic's Claude Large Language Model](https://aws.amazon.com/bedrock/claude/) is a state of art model used for sophisticated dialogue, creative content generation, complex reasoning, coding, and detailed instruction. It can edit, rewrite, summarize, classify, extract structured data, do Q&A based on the content, and more.


## AWS Resources Required

* Create an Amazon S3 bucket for storing the Genesys conversations - a Genesys Trigger Load Call Records lambda function will read from this bucket
* Create an Amazon S3 bucket for storing output from Amazon Bedrock - a Genesys Load Call Records lambda function will write to this bucket - e.g. genesys-call-record-output - this will later be crawled with AWS Glue and used to show in a dashboard
* Create an Amazon SQS queue used for coordinating the processing of Genesys call centre records
* Setup Amazon Bedrock access


## Using Amazon Bedrock

### Using Boto3 to call Amazon Bedrock

In this project we are using the Python Boto3 library to call the Claude Instant v1 LLM hosted in Amazon Bedrock.

```python3
def invoke_amazon_bedrock(prompt):
    body = json.dumps({
        "prompt": prompt,
        "max_tokens_to_sample": 4096,
        "temperature": 0,
        "top_p": 1,
        "stop_sequences": [
          "\n\nHuman:"
        ],
        "anthropic_version": "bedrock-2023-05-31"
    })
    modelId = "anthropic.claude-instant-v1"
    accept = "application/json"
    contentType = "application/json"
    try:
        bedrock_response = bedrock_runtime.invoke_model(
            body=body, modelId=modelId, accept=accept, contentType=contentType
        )
        response_body = json.loads(bedrock_response.get("body").read())
        response_completion = response_body.get("completion")
        print(f"bedrock_response_completion: {response_completion}")
        return response_completion
```

## Define LLM Prompts

We define a list of prompts that we will send to the LLM to get insights out of the call transcript. This list can be refined over time as we define the insights that are most useful.

```python3
prompts = [
    { "key":"llm_intent", "value":"""Human: What was the customer intent for the call. Do not say anything else. Do not include any personal information. <br><transcript><br>{transcript}<br></transcript><br>Assistant:""" },
    { "key":"llm_summary", "value":"""Human: Summarise the call transcript. Do not include any personal information, only reply with the summary. <br><transcript><br>{transcript}<br></transcript><br>Assistant:""" },
    { "key":"llm_sentiment", "value":"""Human: what is the customer sentiment at the end of the call, only reply with 'postive', 'negative' or 'neutral'? Do not say anything else.<br><transcript><br>{transcript}<br></transcript><br>Assistant:""" },
    { "key":"llm_is_tocancel", "value":"""Human: Did the customer call to cancel an existing service? reply with "yes", "No". Do not say anything else.<br><transcript><br>{transcript}<br></transcript><br>Assistant:""" },
    { "key":"llm_is_newservice", "value":"""Human: Did the customer call to sign up to a new service? reply with "yes", "No". Do not say anything else.<br><transcript><br>{transcript}<br></transcript><br>Assistant:""" },
    { "key":"llm_is_discountoffered", "value":"""Human: Did the agent offer the customer a monthly recurring discount? reply with "yes", "No". Do not say anything else.<br><transcript><br>{transcript}<br></transcript><br>Assistant:""" },
]
```


## Genesys Trigger Load Call Records

An AWS Lambda function is used to trigger the processing of Genesys call records sitting in Amazon S3. The call centre records are normally organized by date prefixes in Amazon S3 and we will use this organization to process a subset of the call records.

### Create the AWS Lambda function

* Create a new AWS Lambda function - genesys-trigger-load-call-records - python3.11
* The function needs IAM permissions to:
  * read from an S3 bucket with the genesys conversations
  * write to an Amazon SQS queue

### AWS Lambda - Trigger Test JSON

```json
{
  "input_s3_bucket_name": "genesys-call-inputs-aws-accountid",
  "input_s3_object_key_prefix": "originalAudio/"
}
```



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
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockConsole",
      "Effect": "Allow",
      "Action": [
        "bedrock:*"
      ],
      "Resource": "*"
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

Records are saved into Amazon S3 bucket under a folder structure that it optimised for partitioning with AWS Glue and analytics querying such as with Amazon Athena. A .summary.json file is created for every conversation.

```
s3://genesys-call-record-output/summary/year=2023/month=08/day=29/recording-01e7279e-a65b-40d3-b807-ef6f3c0b2c0a.summary.json
```


## Amazon SQS Queue

Create a standard Amazon SQS queue that triggers the Genesys Load Call Records AWS Lambda

* Name: genesys-metadata-queue
* Type: standard
* Encryption: Amazon SQS key (SSE-SQS)
* Configure Lambda function trigger - choose the ARN of the Genesys Load Call Records AWS Lambda, e.g. arn:aws:lambda:ap-southeast-2:aws-accountid:function:genesys-load-call-records


## Example Summary Output

The aggregated output includes useful fields from the original metadata Genesys files and fields created from the Amazon Bedrock LLM response.

```json
{
  "s3_bucket_name": "genesys-call-inputs-190067120391",
  "s3_object_key_opus_metadata": "originalAudio/conversation_idea4303d8-014e-44f9-b770-5b15e6f86f1f/0261adc0-0618-4652-ac76-de176e1c431c.opus_metadata.json",
  "conversation_id": "ea4303d8-014e-44f9-b770-5b15e6f86f1f",
  "recording_id": "0261adc0-0618-4652-ac76-de176e1c431c",
  "start_time": "2023-08-29T23:19:04.873+0000",
  "end_time": "2023-08-29T23:19:30.493+0000",
  "duration_ms": 25620,
  "initial_direction": "outbound",
  "s3_object_key_opus_recording": "originalAudio/conversation_idea4303d8-014e-44f9-b770-5b15e6f86f1f/0261adc0-0618-4652-ac76-de176e1c431c.opus",
  "s3_object_key_transcript": "originalAudio/conversation_idea4303d8-014e-44f9-b770-5b15e6f86f1f/ea4303d8-014e-44f9-b770-5b15e6f86f1f-053fd4c8-85b7-473f-acbf-91cd183fefea.transcript.json",
  "s3_object_key_opus_call_metadata": "originalAudio/conversation_idea4303d8-014e-44f9-b770-5b15e6f86f1f/ea4303d8-014e-44f9-b770-5b15e6f86f1f.opus_call_metadata.json",
  "is_opus_recording_available": true,
  "is_opus_call_metadata_available": true,
  "is_transcript_available": true,
  "communication_id": "053fd4c8-85b7-473f-acbf-91cd183fefea",
  "media_type": "call",
  "transcript": "Hi, you. Please leave a message after a tone and I'll get back to you soon as I can thank you. Hi there. It is regarding your request activation and, uh, schedule a technician appointment. Please get in touch with the us. Thank you have a nice day.",
  "llm_intent": " Customer intent was to schedule a technician appointment for fibre installation.",
  "llm_summary": " This was a voicemail message from a telecommunications company regarding scheduling a technician appointment to activate a requested fibre internet service. The caller asked the recipient to contact the company's team to arrange the appointment.",
  "llm_sentiment": " positive",
  "llm_is_tocancel": " No",
  "llm_is_newservice": " No",
  "llm_is_discountoffered": " No"
}
```

## Supporting Resources

### Prompt Engineering

* [Prompt Engineering Guide](https://www.promptingguide.ai/)
* [AWS re:Invent 2023 - Prompt engineering best practices for LLMs on Amazon Bedrock (AIM377)](https://www.youtube.com/watch?v=jlqgGkh1wzY)

