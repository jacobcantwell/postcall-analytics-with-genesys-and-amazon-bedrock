import boto3
import botocore
import datetime
import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SUFFIX_OPUS_RECORDING = ".opus"
SUFFIX_OPUS_CALL_METADATA_JSON = ".opus_call_metadata.json"
SUFFIX_TRANSCRIPT_JSON = ".transcript.json"
S3_OUTPUT_BUCKET = os.environ["S3_OUTPUT_BUCKET"]

s3_client = boto3.client("s3")

# Amazon Bedrock in us-east-1
bedrock_config = botocore.config.Config(
    region_name = 'us-east-1',
)
bedrock_runtime = boto3.client("bedrock-runtime", config=bedrock_config)

def load_s3_json(bucket_name, object_key):
    print(f"loading: s3://{bucket_name}/{object_key}")
    # Get the file inside the S3 Bucket
    s3_response = s3_client.get_object(
        Bucket=bucket_name,
        Key=object_key
    )
    # Get the Body object in the S3 get_object() response
    s3_object_body = s3_response.get("Body")
    # Read the data in bytes format
    content = s3_object_body.read()
    return json.loads(content)

# Define LLM Prompts
prompts = [
    { "key":"llm_intent", "value":"""Human: What was the customer intent for the call. Do not say anything else. Do not include any personal information. <br><transcript><br>{transcript}<br></transcript><br>Assistant:""" },
    { "key":"llm_summary", "value":"""Human: Summarise the call transcript. Do not include any personal information, only reply with the summary. <br><transcript><br>{transcript}<br></transcript><br>Assistant:""" },
    { "key":"llm_sentiment", "value":"""Human: what is the customer sentiment at the end of the call, only reply with 'postive', 'negative' or 'neutral'? Do not say anything else.<br><transcript><br>{transcript}<br></transcript><br>Assistant:""" },
    { "key":"llm_is_tocancel", "value":"""Human: Did the customer call to cancel an existing service? reply with "yes", "No". Do not say anything else.<br><transcript><br>{transcript}<br></transcript><br>Assistant:""" },
    { "key":"llm_is_newservice", "value":"""Human: Did the customer call to sign up to a new service? reply with "yes", "No". Do not say anything else.<br><transcript><br>{transcript}<br></transcript><br>Assistant:""" },
    { "key":"llm_is_discountoffered", "value":"""Human: Did the agent offer the customer a monthly recurring discount? reply with "yes", "No". Do not say anything else.<br><transcript><br>{transcript}<br></transcript><br>Assistant:""" },
]

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
    except botocore.exceptions.ClientError as error:
        if error.response['Error']['Code'] == 'AccessDeniedException':
               print(f"\x1b[41m{error.response['Error']['Message']}\
                    \nTo troubeshoot this issue please refer to the following resources.\
                     \nhttps://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot_access-denied.html\
                     \nhttps://docs.aws.amazon.com/bedrock/latest/userguide/security-iam.html\x1b[0m\n")
        else:
            raise error

# For every record:
# - load the opus_metadata.json
# - check the .opus recording exists
# - check and load the opus_call_metadata.json
# - check the transcript.json exists
def create_record_from_opus_metadata(bucket_name, object_key):
    
    s3_bucket_name = bucket_name
    s3_object_key_opus_metadata = object_key
    
    record = {}
    record["s3_bucket_name"] = s3_bucket_name
    record["s3_object_key_opus_metadata"] = s3_object_key_opus_metadata

    # Load .opus_metadata.json from Amazon S3
    opus_metadata_json = load_s3_json(bucket_name=s3_bucket_name, object_key=s3_object_key_opus_metadata)
    print(opus_metadata_json)
    start_time = opus_metadata_json["startTime"]
    record["conversation_id"] = opus_metadata_json["conversationId"]
    recording_id = opus_metadata_json["recordingId"]
    record["recording_id"] = recording_id
    record["start_time"] = start_time
    record["end_time"] = opus_metadata_json["endTime"]
    record["duration_ms"] = opus_metadata_json["durationMs"]
    record["initial_direction"] = opus_metadata_json["initialDirection"]
    
    # Get S3 object prefix used to load other files
    s3_prefix = s3_object_key_opus_metadata.partition(recording_id)[0]
    print(f"s3_prefix: {s3_prefix}")
    
    # Load keys of objects in this folder
    s3_response = s3_client.list_objects_v2(
        Bucket=s3_bucket_name,
        Prefix=s3_prefix,
        MaxKeys=5
    )
    print(f"s3_response: {s3_response}")
    genesys_objects = [i["Key"] for i in s3_response["Contents"]]

    # Load related Genesys files
    is_opus_recording_available = False
    is_opus_call_metadata_available = False
    is_transcript_available = False
    for s3_object in genesys_objects:
        # Check .opus recording exists
        if s3_object.endswith(SUFFIX_OPUS_RECORDING):
            is_opus_recording_available = True
            record["s3_object_key_opus_recording"] = s3_object
        # Check .opus_call_metadata.json
        elif s3_object.endswith(SUFFIX_OPUS_CALL_METADATA_JSON):
            is_opus_call_metadata_available = True
            record["s3_object_key_opus_call_metadata"] = s3_object
            # opus_call_metadata_json = load_s3_json(bucket_name=s3_bucket_name, object_key=s3_object)
        # Check and load .transcript.json
        elif s3_object.endswith(SUFFIX_TRANSCRIPT_JSON):
            is_transcript_available = True
            s3_object_key_transcript = s3_object
            record["s3_object_key_transcript"] = s3_object_key_transcript
            transcript_json = load_s3_json(bucket_name=s3_bucket_name, object_key=s3_object)
    record["is_opus_recording_available"] = is_opus_recording_available
    record["is_opus_call_metadata_available"] = is_opus_call_metadata_available
    record["is_transcript_available"] = is_transcript_available

    # Call Amazon Bedrock
    if is_transcript_available:
        # Extract a plain text transcript
        transcripts = transcript_json["transcripts"]
        record["communication_id"] = transcript_json["communicationId"]
        record["media_type"] = transcript_json["mediaType"]
        phrases_lst = []
        for obj_transcript in transcript_json["transcripts"]:
            obj_phrases = obj_transcript["phrases"]
            for j in obj_phrases:
                j_decoratedText = j["decoratedText"]
                # j_participantPurpose = j["participantPurpose"]
                phrases_lst.append(f"{j_decoratedText}")
        # Join the phrases with newline characters
        transcript = " ".join(phrases_lst)
        record["transcript"] = transcript
        
        # Summarize the transcript with Amazon Bedrock
        for each_prompt in prompts:
            input_text = each_prompt['value'].replace("{transcript}", transcript)
            # Call Amazon Bedrock
            query_response = invoke_amazon_bedrock(input_text)
            print(f"query_response: {query_response}")
            response_key = each_prompt["key"]
            record[response_key] = query_response
        print(f"record: {json.dumps(record)}")

    # Write record to Amazon S3
    dt = datetime.datetime.fromisoformat(start_time)
    print(dt)
    record_year = dt.strftime("%Y")
    record_month = dt.strftime("%m")
    record_day = dt.strftime("%d")
    data_string = json.dumps(record)
    output_s3_object_key = f"summary/year={record_year}/month={record_month}/day={record_day}/recording-{recording_id}.summary.json"
    s3_response = s3_client.put_object(
        Body=data_string,
        Bucket=S3_OUTPUT_BUCKET,
        Key=output_s3_object_key
    )
    return 1


def lambda_handler(event, context):
    print("genesys-load-call-records v21")
    logger.info(json.dumps(event))
    records_processed = 0
    # Load SQS messages
    for record in event["Records"]:
        print(f"record: {json.dumps(record)}")
        record_body = json.loads(record["body"])
        s3_bucket_name = record_body["s3_bucket_name"]
        s3_object_key = record_body["s3_object_key"]
        print(f"s3_bucket_name: {s3_bucket_name}")
        print(f"s3_object_key: {s3_object_key}")
        processed_count = create_record_from_opus_metadata(bucket_name=s3_bucket_name, object_key=s3_object_key)
        records_processed += processed_count 
    return {
        "records_processed": records_processed
    }
