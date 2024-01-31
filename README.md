# Postcall Analytics with Genesys Contact Centre and Amazon Bedrock

Postcall Analytics with Genesys Contact Centre and Amazon Bedrock


## AWS Lambda - Genesys Trigger Load Call Records




## AWS Lambda - Genesys Load Call Records

The input from this function is an Amazon SQS queue event containing a list of Amazon S3 buckets and object keys referencing the .opus_metadata.json suffixed JSON file. The .opus_metadata.json is always returned by Genesys for a conversation and includes reference ids to the related files, some of which are optional depending on if a transcript was included or not.

This Lambda function aggregates the related Genesys call transcript and metadata files, passes the transcript to Amazon Bedrock with an array of prompts, then saves the responses to an Amazon S3 bucket.

```json
{
  "records_processed": 10
}
```


