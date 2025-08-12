import os
import io
import logging
from datetime import datetime
import boto3
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEST_BUCKET = "imgproc-processed"
DDB_TABLE = "ImageMetadata-Table" 


s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb") 

SIZES = {
    "thumb": (128, 128),
    "medium": (512, 512),
}

def lambda_handler(event, context):
    logger.info("Event: %s", event)
    for record in event.get("Records", []):
        src_bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        try:
            process_image(src_bucket, key)
        except Exception as e:
            logger.exception("Error processing %s/%s: %s", src_bucket, key, e)
    return {"status": "done"}

def process_image(src_bucket, key):
    resp = s3.get_object(Bucket=src_bucket, Key=key)
    content = resp["Body"].read()
    img = Image.open(io.BytesIO(content))
    img_format = img.format or "PNG"

    produced = []

    for label, size in SIZES.items():
        out = img.copy()
        out.thumbnail(size, Image.ANTIALIAS)

        # watermark : ZakariaeWatermark
        try:
            draw = ImageDraw.Draw(out)
            font = ImageFont.load_default()
            text = "© ZakariaeWatermark"
            tw, th = draw.textsize(text, font=font)
            draw.text((out.width - tw - 8, out.height - th - 8), text, font=font)
        except Exception:
            logger.warning("Watermark failed")

        buffer = io.BytesIO()
        if img_format.upper() == "JPEG":
            out = out.convert("RGB")
            out.save(buffer, format="JPEG", quality=85)
            content_type = "image/jpeg"
        else:
            out.save(buffer, format=img_format)
            content_type = f"image/{img_format.lower()}"
        buffer.seek(0)

        dest_key = f"{label}/{key}"
        s3.put_object(Bucket=DEST_BUCKET, Key=dest_key, Body=buffer, ContentType=content_type)
        produced.append(dest_key)

    if dynamodb and DDB_TABLE:
        table = dynamodb.Table(DDB_TABLE)
        table.put_item(Item={
            "image_key": key,
            "source_bucket": src_bucket,
            "processed_bucket": DEST_BUCKET,
            "processed": produced,
            "processed_at": datetime.utcnow().isoformat() + "Z"
        })
