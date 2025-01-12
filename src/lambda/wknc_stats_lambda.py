from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from json import dumps
from json import loads
from logging import getLogger
from os import environ
from pathlib import Path
from time import sleep
from typing import Any
from typing import Final
from zoneinfo import ZoneInfo

from boto3 import client
from botocore.exceptions import ClientError
from dataclass_wizard import asdict
from dataclass_wizard import fromdict
from dataclass_wizard.errors import JSONWizardError
from jinja2 import StrictUndefined
from jinja2 import Template
from requests import Session
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry


DAYS: Final = timedelta(days=30)
DATA_BUCKET: Final = environ.get("DATA_BUCKET", "wknc-stats-data")
DATA_KEY: Final = environ.get("DATA_KEY", "data/spins.json")
WEBSITE_BUCKET: Final = environ.get("WEBSITE_BUCKET", "www.wkncstats.xyz")
WEBSITE_KEY: Final = environ.get("WEBSITE_KEY", "index.html")
REQUEST_DELAY_SECONDS: Final = float(environ.get("REQUEST_DELAY_SECONDS", 3))

logger = getLogger(__name__)
logger.setLevel(environ.get("LOG_LEVEL", "INFO"))

s3 = client("s3")


def lambda_handler(event: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    spin_history = SpinHistory.load()
    spin_history.write_to_s3()
    update_s3_website(spin_history)
    return {"statusCode": 200}


@dataclass
class Spin:
    id_: str
    artist: str
    song: str
    start: datetime
    end: datetime

    @staticmethod
    def parse_utc_string(utc_string: str) -> datetime:
        return datetime.strptime(utc_string, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc,
        )

    @classmethod
    def from_dict(cls, spin: dict[str, Any]) -> Spin:
        return cls(
            id_=spin["id"],
            artist=spin["artist"],
            song=spin["song"],
            start=cls.parse_utc_string(spin["start"]),
            end=cls.parse_utc_string(spin["end"]),
        )


@dataclass
class SpinHistory:

    spins: dict[str, Spin] = field(default_factory=dict)

    @property
    def most_recent_spin(self) -> Spin:
        if not self.spins:
            raise ValueError("No spins exist")
        return max(self.spins.values(), key=lambda spin: spin.start)

    def purge_old_spins(self, boundary: datetime) -> None:
        original_length = len(self.spins)
        self.spins = {
            key: value for key, value in self.spins.items() if value.start > boundary
        }
        spins_removed = original_length - len(self.spins)
        logger.info("Removed %d old spins", spins_removed)

    def fetch_spins_from_api(self, start, end) -> None:
        new_spins = WkncApiClient().fetch_spins(start, end)
        self.spins = {**self.spins, **{spin.id_: spin for spin in new_spins}}

    def write_to_s3(self) -> None:
        logger.info("Writing spins to s3...")
        content = dumps(asdict(self), indent=2, default=str)
        s3.put_object(
            Body=content,
            Bucket=DATA_BUCKET,
            Key=DATA_KEY,
        )
        logger.info("Wrote %d spins to s3", len(self.spins))

    def find_trending_artists(self) -> list[tuple[str, int]]:
        middle = self.most_recent_spin.start - DAYS / 2
        scores = {spin.artist: 0 for spin in self.spins.values()}
        for spin in self.spins.values():
            if spin.start > middle:
                scores[spin.artist] += 1
            else:
                scores[spin.artist] -= 1
        sorted_scores = sorted(
            [(artist, score) for artist, score in scores.items()],
            key=lambda x: x[1],
            reverse=True,
        )
        return sorted_scores[:5]

    def find_top_artists(self) -> list[tuple[str, int]]:
        artists = [spin.artist for spin in self.spins.values()]
        return Counter(artists).most_common(10)

    def find_top_songs(self) -> list[tuple[str, str, int]]:
        songs = [(spin.song, spin.artist) for spin in self.spins.values()]
        top_songs = Counter(songs).most_common(10)
        return [(*song[0], song[1]) for song in top_songs]

    @classmethod
    def load_from_s3(cls) -> SpinHistory:
        logger.info("Loading spins from S3...")
        try:
            obj = s3.get_object(Bucket=DATA_BUCKET, Key=DATA_KEY)
            content = loads(obj["Body"].read().decode("utf-8"))
            spin_history = fromdict(SpinHistory, content)
            logger.info("Loaded %d spins from S3", len(spin_history.spins))
            return spin_history
        except (ClientError, JSONWizardError) as e:
            logger.warning("Could not load spin history from s3.", exc_info=e)
            return cls()

    @staticmethod
    def load() -> SpinHistory:
        spin_history = SpinHistory.load_from_s3()

        now = datetime.now(timezone.utc)
        spin_history.purge_old_spins(now - DAYS)
        start = (
            spin_history.most_recent_spin.start if spin_history.spins else now - DAYS
        )

        spin_history.fetch_spins_from_api(start, now)
        return spin_history


class WkncApiClient:

    @staticmethod
    def convert_utc_to_et(utc_dt: datetime) -> str:
        """Converts a UTC datetime object to an ET timestamp."""
        return utc_dt.astimezone(ZoneInfo("US/Eastern")).strftime("%Y-%m-%d %H:%M")

    def fetch_spins(self, start: datetime, end: datetime) -> list[Spin]:
        spins = self.make_spin_request(start, end)

        # The API returns a max of 100 records per request.
        # Keep requesting a shorter time window until all of the records are returned.
        spins_in_response = len(spins)
        while spins_in_response == 100:
            sleep(REQUEST_DELAY_SECONDS)
            earliest_time = min(spins, key=lambda spin: spin.start).start
            next_spins = self.make_spin_request(start, earliest_time)
            spins_in_response = len(next_spins)
            spins += next_spins
        return spins

    def make_spin_request(
        self,
        start: datetime,
        end: datetime,
        retries: int = 5,
    ) -> list[Spin]:
        logger.info("Fetching spins from %s to %s", start, end)
        retry_strategy = Retry(
            total=retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        http = Session()
        http.mount("https://", adapter)

        params: dict[str, int | str] = {
            "station": 1,
            "start": self.convert_utc_to_et(start),
            "end": self.convert_utc_to_et(end),
        }
        response = http.get(
            "https://wknc.org/wp-json/wknc/v1/spins",
            params=params,
        )

        spins = [Spin.from_dict(spin) for spin in loads(response.content)]
        logger.info("Fetched %d spins from %s to %s", len(spins), start, end)
        return spins


def update_s3_website(spin_history: SpinHistory):
    logger.info("Updating website...")
    with open(Path("template/index.html.jinja")) as file:
        template = Template(file.read(), undefined=StrictUndefined)

    data = {
        "trending_artists": spin_history.find_trending_artists(),
        "top_artists": spin_history.find_top_artists(),
        "top_songs": spin_history.find_top_songs(),
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
