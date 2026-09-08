# Photo Label Search

A AWS pipeline that labels photos with Amazon Rekognition as they land in S3, stores the labels in DynamoDB, and lets you search for photos by label through a simple web UI.


## Architecture

```
Upload photo               Rekognition detects labels        Query by label
      │                              │                              │
      ▼                              ▼                              ▼
   S3 bucket  ──(S3 event)──>  label_photos Lambda  ──>  DynamoDB   <──  search_photos Lambda  <── API Gateway (HTTP API)  <── gallery.html
  (photos/*)                  (Docker container)        (PhotoLabels                (zip package)
                                                           table)
```

1. A photo is uploaded to the S3 bucket under `photos/`.
2. That upload fires an S3 event notification, which invokes `label_photos.py` (packaged as a Docker container Lambda).
3. `label_photos.py` calls Rekognition's `detect_labels` on the image and writes one DynamoDB item per detected label (partition key `label`, sort key `s3_key`), so "give me every photo tagged X" is a fast `Query`, not a table scan.
4. `search_photos.py` (a plain zip-based Lambda, no special dependencies) sits behind an API Gateway HTTP API. It takes a `label` query-string parameter, queries DynamoDB, and returns presigned S3 URLs for each matching photo so the browser can display them without the bucket being public.
5. `gallery.html` is a static, single-file frontend: type a label, hit search, see a photo grid.

## Files

| File | Purpose |
|---|---|
| `label_photos.py` | S3-triggered Lambda. Runs Rekognition on the uploaded image and writes labels to DynamoDB. |
| `Dockerfile` | Container image definition for `label_photos.py` (deployed via ECR, since it's the labeling side of the pipeline). |
| `search_photos.py` | Public-facing Lambda behind API Gateway. Queries DynamoDB by label and returns presigned photo URLs. |
| `gallery.html` | Search UI — a search box and a responsive photo grid, calling `search_photos.py` via `fetch()`. |

## Deploying it yourself

### 1. S3 bucket + sample data

```bash
aws s3 mb s3://YOUR-BUCKET-NAME
aws s3 cp --no-sign-request s3://fast-ai-coco/coco_tiny.tgz .
tar -xzf coco_tiny.tgz
aws s3 cp coco_tiny/train/000000005906.jpg s3://YOUR-BUCKET-NAME/photos/
# repeat for a handful of test images — avoid --recursive on a large folder,
# it can trigger an AWS CLI segfault on some machines
```

### 2. DynamoDB table

```bash
aws dynamodb create-table \
  --table-name PhotoLabels \
  --attribute-definitions AttributeName=label,AttributeType=S AttributeName=s3_key,AttributeType=S \
  --key-schema AttributeName=label,KeyType=HASH AttributeName=s3_key,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST
```

### 3. Labeling Lambda (container image via ECR)

```bash
docker build --provenance=false --platform linux/arm64 -t photo-labeler .
# tag, push to ECR, then:
aws lambda create-function \
  --function-name label-photos \
  --package-type Image \
  --code ImageUri=<your-ecr-image-uri> \
  --role <your-lambda-execution-role-arn> \
  --architectures arm64 \
  --environment "Variables={TABLE_NAME=PhotoLabels}"
```

Wire up the S3 trigger (`put-bucket-notification-configuration` + `lambda add-permission` for `s3.amazonaws.com`) so new uploads to `photos/` invoke this function. Note: S3 event notifications only fire for objects uploaded *after* the trigger is configured — anything already in the bucket won't retroactively trigger it.

### 4. Search Lambda (zip)

```bash
zip search_photos.zip search_photos.py
aws lambda create-function \
  --function-name search-photos \
  --runtime python3.13 \
  --role <your-lambda-execution-role-arn> \
  --handler search_photos.lambda_handler \
  --zip-file fileb://search_photos.zip \
  --environment "Variables={TABLE_NAME=PhotoLabels,BUCKET_NAME=YOUR-BUCKET-NAME}"
```

### 5. API Gateway (HTTP API)

Create an HTTP API with a `GET /search` route targeting `search-photos`. **Important gotcha:** if you enable CORS in the API Gateway console, API Gateway *ignores* the CORS headers `search_photos.py` already returns and enforces its own config instead — and if that config isn't filled in correctly (an empty "Allow Origins" field, for instance), it silently strips all CORS headers, which looks like a network error in the browser even though the API itself returns 200. The simplest fix, since the Lambda already sets its own CORS headers correctly, is to remove API Gateway's CORS layer entirely and let the Lambda's headers pass through:

```bash
aws apigatewayv2 delete-cors-configuration --api-id <your-api-id>
```

### 6. Frontend

Open `gallery.html`, set `SEARCH_ENDPOINT` to your API Gateway invoke URL + `/search`, and open the file in a browser.

## Notes

- This uses a public sample dataset rather than personal photos, so there's no dependency on Google Photos API access (which no longer supports broad background/library-wide read access as of April 2025).
- Presigned photo URLs expire after 1 hour by design — that's intentional, not a bug, so the S3 bucket doesn't need to be public.
- Labels are stored lowercase; searches are lowercased before querying, so casing doesn't matter.
