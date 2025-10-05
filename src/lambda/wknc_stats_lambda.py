from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from io import StringIO
from logging import basicConfig, getLogger
from os import environ
from pathlib import Path
from time import sleep
from typing import Any, Final
from zoneinfo import ZoneInfo

from boto3 import client
from botocore.exceptions import ClientError
from jinja2 import StrictUndefined, Template
from pandas import DataFrame, read_csv, Series
from requests import Response, Session
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

basicConfig(level=environ.get("LOG_LEVEL", "INFO"))
logger = getLogger(__name__)

DAYS: Final = timedelta(days=30)
DATA_BUCKET: Final = environ.get("DATA_BUCKET", "wknc-stats-data")
DATA_KEY: Final = environ.get("DATA_KEY", "data/spins.csv")
WEBSITE_BUCKET: Final = environ.get("WEBSITE_BUCKET", "www.wkncstats.xyz")
WEBSITE_KEY: Final = environ.get("WEBSITE_KEY", "index.html")
REQUEST_DELAY_SECONDS: Final = float(environ.get("REQUEST_DELAY_SECONDS", 3))

s3 = client("s3")


@dataclass
class Spin:
    id: int
    start: datetime
    end: datetime
    artist: str
    song: str


def lambda_handler(event: dict[str, Any], context: dict[str, Any]) -> None:
    spins = load_records()
    spins = update_records(spins)
    update_s3_csv(spins)
    update_s3_website(spins)


def load_records() -> DataFrame:
    try:
        obj = s3.get_object(Bucket=DATA_BUCKET, Key=DATA_KEY)
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return DataFrame()
        else:
            raise
    body = obj["Body"].read().decode("utf-8")
    return read_csv(StringIO(body), index_col="id", parse_dates=["start", "end"])


def purge_old_records(spins: DataFrame, boundary: datetime) -> DataFrame:
    original_length = len(spins)
    spins = spins[spins["start"] > boundary]
    spins_removed = original_length - len(spins)
    logger.info("Removed %d old spins", spins_removed)
    return spins


def convert_utc_to_et(utc_dt: datetime) -> str:
    """Converts a UTC datetime object to an ET timestamp."""
    return utc_dt.astimezone(ZoneInfo("US/Eastern")).strftime("%Y-%m-%d %H:%M")


def parse_utc_string(utc_string: str) -> datetime:
    return datetime.strptime(utc_string, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc,
    )


def sanitize(raw: str) -> str:
    max_length: Final = 100
    return escape(raw)[:max_length]


def create_record(raw: dict[str, Any]) -> Spin:
    for col in ["id", "start", "end", "artist", "song"]:
        if not isinstance(raw[col], str):
            raise ValueError("Unexpected type for key=%s", col)
    return Spin(
        id=int(raw["id"]),
        start=parse_utc_string(raw["start"]),
        end=parse_utc_string(raw["end"]),
        artist=sanitize(raw["artist"]),
        song=sanitize(raw["song"]),
    )


def get_records(resp: Response) -> list[Spin]:
    json = resp.json()
    if not isinstance(json, list):
        raise ValueError(
            f"Could not parse response format. Expected list but was {type(json)}",
        )

    records = []
    for elem in json:
        try:
            records.append(create_record(elem))
        except (KeyError, ValueError) as e:
            logger.warning("Could not extract required key from record: %s", e)
    return records


def http():
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    http = Session()
    http.mount("https://", adapter)
    return http


def make_spin_request(
    start: datetime,
    end: datetime,
) -> list[Spin]:
    logger.info("Fetching spins from %s to %s...", start, end)

    params: dict[str, int | str] = {
        "station": 1,
        "start": convert_utc_to_et(start),
        "end": convert_utc_to_et(end),
    }
    response = http().get(
        "https://wknc.org/wp-json/wknc/v1/spins",
        params=params,
    )
    response.raise_for_status()

    spins = get_records(response)
    logger.info("Fetched %d spins from %s to %s", len(spins), start, end)
    return spins


def fetch_new_records(start: datetime, end: datetime) -> DataFrame:
    spins = make_spin_request(start, end)

    # The API returns a max of 100 records per request.
    MAX_RECORDS_PER_RESPONSE: Final = 100

    # Keep requesting a shorter time window until all of the records are returned.
    spins_in_response = len(spins)
    while spins_in_response == MAX_RECORDS_PER_RESPONSE:
        sleep(REQUEST_DELAY_SECONDS)
        earliest_time = min([spin.start for spin in spins])
        next_spins = make_spin_request(start, earliest_time)
        spins_in_response = len(next_spins)
        spins += next_spins

    df = DataFrame([asdict(s) for s in spins]).set_index("id")
    return df[~df.index.duplicated(keep="first")]  # Dedup by index


def update_records(spins: DataFrame) -> DataFrame:
    now = datetime.now(timezone.utc)
    boundary = now - DAYS

    if not spins.empty:
        spins = purge_old_records(spins, boundary)

    start = boundary if spins.empty else spins["start"].max()
    new_spins = fetch_new_records(start, now)
    return spins.combine_first(new_spins)


def find_trending_artists(spins: DataFrame, top_k: int) -> Series:
    middle = spins["start"].max() - DAYS / 2
    recent_artists = spins[spins["start"] > middle]["artist"].value_counts()
    old_artists = spins[spins["start"] < middle]["artist"].value_counts()
    return (
        recent_artists.sub(old_artists, fill_value=0)
        .astype("int64")
        .sort_values(ascending=False)
        .head(top_k)
    )


def update_s3_csv(spins: DataFrame) -> None:
    logger.info("Writing spins to s3...")
    csv_buffer = StringIO()
    spins.to_csv(csv_buffer)
    s3.put_object(
        Body=csv_buffer.getvalue(),
        Bucket=DATA_BUCKET,
        Key=DATA_KEY,
    )
    logger.info("Wrote %d spins to s3", len(spins))


def find_top_artists(spins: DataFrame, top_k: int) -> Series:
    return spins["artist"].value_counts().head(top_k)


def find_top_songs(spins: DataFrame, top_k: int) -> Series:
    return spins[["artist", "song"]].value_counts().head(top_k)


def update_s3_website(spins: DataFrame) -> None:
    logger.info("Updating website...")
    with open(Path("template/index.html.jinja")) as file:
        template = Template(file.read(), undefined=StrictUndefined)

    data = {
        "trending_artists": find_trending_artists(spins, 5).to_dict(),
        "top_artists": find_top_artists(spins, 10).to_dict(),
        "top_songs": find_top_songs(spins, 10).to_dict(),
    }
    html = template.render(data)

    s3.put_object(
        Body=html,
        Bucket=WEBSITE_BUCKET,
        Key=WEBSITE_KEY,
        ContentType="text/html",
    )
    logger.info("Updated website successfully!")


if __name__ == "__main__":
    lambda_handler({}, {})
