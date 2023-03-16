import time
import logging
import logging.handlers
import json

import requests
import numpy as np

from io import BytesIO

from picamera import PiCamera
from PIL import Image, ImageChops, ImageFilter
from retry import retry

HF_API_TOKEN = ""
DISCORD_TOKEN = ""
MODEL_URL = "google/vit-base-patch16-224"
CHANNEL_ID = ""
DEBUG_CHANNEL_ID = ""
SLEEP_TIME = 5

# hand tuned based on minimal experimentation
MOTION_TIMESTEP = 0.5
IMG_THRESH_1 = 25
BLUR_RADIUS = 20
IMG_THRESH_2 = 100
DIFF_THRESH = 0.01

MODEL_THRESH = 0.01


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler("/home/pi/nomcam/nomcam.log", mode='a', maxBytes=1048576, backupCount=1)]
)
logger = logging.getLogger()


def _capture_pil_image(camera, resolution=(224, 224), mode="L") -> Image:

    camera.resolution = resolution

    stream = BytesIO()
    camera.capture(stream, format="jpeg")
    stream.seek(0)

    return Image.open(stream).convert(mode)


def detect_motion(camera: PiCamera) -> bool:
    """Detect motion based on image pixel differences"""

    image_1 = _capture_pil_image(camera)
    time.sleep(MOTION_TIMESTEP)
    image_2 = _capture_pil_image(camera)

    image = (
        ImageChops.difference(image_1, image_2)
        .point(lambda x: 255 if x > IMG_THRESH_1 else 0)
        .filter(ImageFilter.BoxBlur(BLUR_RADIUS))
        .point(lambda x: 255 if x > IMG_THRESH_2 else 0)
    )

    img_arr = np.asarray(image, dtype="int32")

    diff_value = ((img_arr / 255).sum() / img_arr.size)

    if diff_value > DIFF_THRESH:
        logger.info("motion detection value: %f" % diff_value)

    return diff_value > DIFF_THRESH


def send_notification(image: Image, message: str, channel_id=CHANNEL_ID):
    """POST a notification to the Discord API"""
    logger.info("sending notification")

    img_bin = BytesIO()
    image.save(img_bin, format="jpeg")
    img_hex = img_bin.getvalue()

    api_url = "https://discord.com/api/v9/channels/{CHANNEL_ID}/messages".format(CHANNEL_ID=channel_id)
    headers = {"Authorization": "Bot {DISCORD_TOKEN}".format(DISCORD_TOKEN=DISCORD_TOKEN)}
    data = {"content": message}
    files = {"file": ("image.jpeg", img_hex)}

    response = requests.post(
        api_url,
        headers=headers,
        data=data,
        files=files,
    )

    response.raise_for_status()


@retry(tries=5, delay=2, backoff=2)
def detect_squirrel(image: Image, model_url: str = MODEL_URL) -> bool:
    """Hit a HuggingFace API to check if the image contains a squirrel"""

    img_bin = BytesIO()
    image.save(img_bin, format="jpeg")
    data = img_bin.getvalue()

    api_url = "https://api-inference.huggingface.co/models/{MODEL_URL}".format(MODEL_URL=MODEL_URL)
    headers = {
        "Authorization": "Bearer {HF_API_TOKEN}".format(HF_API_TOKEN=HF_API_TOKEN)
    }

    response = requests.post(api_url, headers=headers, data=data)

    response.raise_for_status()

    logger.info(response.json())

    preds = {d["label"]: d["score"] for d in response.json()}
    squirrel_key = [key for key in preds if "squirrel" in key]

    if squirrel_key:
        return preds[squirrel_key.pop()] > MODEL_THRESH

    return False


def main():

    logger.info("initializing camera")
    camera = PiCamera()
    camera.start_preview()

    first_pic = True

    logger.info("starting loop")
    while True:
        logger.debug("next loop")

        snapshot = _capture_pil_image(camera, (1024, 1024), "RGB")

        if detect_motion(camera):
            logger.info("detected motion")

            if first_pic:
                send_notification(snapshot, "test", DEBUG_CHANNEL_ID)
                first_pic = False

            if detect_squirrel(snapshot):
                logger.info("detected squirrel")

                send_notification(snapshot, "He's heeeeeeere!!!")

                time.sleep(SLEEP_TIME)


if __name__ == "__main__":
    try:
        send_notification(Image.fromarray(np.ones((10,10), np.uint8)), "nomcam started", DEBUG_CHANNEL_ID)
        main()
    except Exception as e:
        send_notification(Image.fromarray(np.ones((10,10), np.uint8)), str(e), DEBUG_CHANNEL_ID)
        raise
