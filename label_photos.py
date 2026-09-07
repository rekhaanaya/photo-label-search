"""
S3-triggered Lambda: whenever a photo lands in the bucket, run it through
Rekognition and store each detected label in DynamoDB.
"""

import os
import urllib.parse

import boto3

rekognition = boto3.client("rekognition")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ.get("TABLE_NAME", "PhotoLabels"))

MIN_CONFIDENCE = 80.0
MAX_LABELS = 15


def lambda_handler(event, context):
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        response = rekognition.detect_labels(
            Image={"S3Object": {"Bucket": bucket, "Name": key}},
            MaxLabels=MAX_LABELS,
            MinConfidence=MIN_CONFIDENCE,
        )

        labels_found = []
        for label in response["Labels"]:
            table.put_item(
                Item={
                    "label": label["Name"].lower(),
                    "s3_key": key,
                    "confidence": str(round(label["Confidence"], 2)),
                }
            )
            labels_found.append(label["Name"])

        print(f"Labeled {key}: {labels_found}")

    return {"statusCode": 200}
