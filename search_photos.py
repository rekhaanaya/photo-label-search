"""
Public-facing search Lambda: given a label (e.g. "beach"), query DynamoDB
for every photo tagged with it, and hand back short-lived presigned S3 URLs
so the browser can display the images without the bucket being public.
"""

import json
import os

import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ.get("TABLE_NAME", "PhotoLabels"))
s3 = boto3.client("s3")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "photo-label")


def _cors_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "content-type",
        },
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    if method == "OPTIONS":
        return _cors_response(200, {})

    params = event.get("queryStringParameters") or {}
    label = (params.get("label") or "").strip().lower()

    if not label:
        return _cors_response(400, {"error": "Missing 'label' query parameter"})

    response = table.query(KeyConditionExpression=Key("label").eq(label))
    items = response.get("Items", [])

    photos = []
    for item in items:
        key = item["s3_key"]
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": key},
            ExpiresIn=3600,
        )
        photos.append({"key": key, "url": url, "confidence": item.get("confidence")})

    return _cors_response(200, {"label": label, "count": len(photos), "photos": photos})
