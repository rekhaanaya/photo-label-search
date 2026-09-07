FROM public.ecr.aws/lambda/python:3.13

COPY label_photos.py ${LAMBDA_TASK_ROOT}

# boto3 is already included in the base Lambda Python image, so no extra
# dependencies need installing here.

CMD ["label_photos.lambda_handler"]
