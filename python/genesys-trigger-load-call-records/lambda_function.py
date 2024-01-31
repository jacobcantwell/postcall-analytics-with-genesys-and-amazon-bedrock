import boto3
import botocore
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

SUFFIX_OPUS_METADATA_JSON = ".opus_metadata.json"

s3_client = boto3.client("s3")
sqs_client = boto3.resource("sqs")

queue_name = "genesys-metadata-queue"

try:
    # create an SQS queue
    sqs_queue = sqs_client.get_queue_by_name(QueueName=queue_name)
except botocore.exceptions.ClientError as error:
    print(f"no sqs_queue")
    if (error.response["Error"]["Code"] != "AWS.SimpleQueueService.NonExistentQueue"):
        logger.exception("Cannot get queue: {}".format(queue_name))
    sqs_queue = sqs_client.create_queue(
        QueueName=queue_name,
        Attributes={
            "VisibilityTimeout": "120"
        }
    )


def lambda_handler(event, context):
    logger.debug(json.dumps(event))
    
    input_s3_bucket_name = event["input_s3_bucket_name"]
    input_s3_object_key_prefix = event["input_s3_object_key_prefix"]

    # Load keys of objects in this bucket with prefix
    s3_paginator = s3_client.get_paginator('list_objects_v2')
    operation_parameters = {
        'Bucket': input_s3_bucket_name,
        'Prefix': input_s3_object_key_prefix
    }
    page_iterator = s3_paginator.paginate(**operation_parameters)
    filtered_iterator = page_iterator.search(
        f"Contents[?Key.ends_with(@,`{SUFFIX_OPUS_METADATA_JSON}`)].Key"
    )
    key_list = list(filtered_iterator)
    
    # Send message to SQS queue
    for s3_object_key in key_list:
        message = {
            "s3_bucket_name": input_s3_bucket_name,
            "s3_object_key": s3_object_key
        }
        sqs_response = sqs_queue.send_message(
            MessageBody=json.dumps(message)
        )
    
    return {
        "input_s3_bucket_name": input_s3_bucket_name,
        "keys_length": len(key_list),
        "sqs_queue": queue_name
    }
