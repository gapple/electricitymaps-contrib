#!/usr/bin/env python3

import json
import pprint
import re
from datetime import datetime, timedelta
from logging import Logger, getLogger
from typing import List, Optional, Tuple

import arrow
import pandas as pd
from bs4 import BeautifulSoup
from pytz import timezone
from requests import Session

from electricitymap.contrib.lib.models.event_lists import (
    ProductionBreakdownList,
    TotalConsumptionList,
)
from electricitymap.contrib.lib.models.events import ProductionMix, StorageMix
from electricitymap.contrib.lib.types import ZoneKey
from parsers.lib.config import refetch_frequency

TIMEZONE = timezone("Asia/Seoul")
REAL_TIME_URL = "https://new.kpx.or.kr/powerinfoSubmain.es?mid=a10606030000"
PRICE_URL = "https://new.kpx.or.kr/smpInland.es?mid=a10606080100&device=pc"
LONG_TERM_PRODUCTION_URL = (
    "https://new.kpx.or.kr/powerSource.es?mid=a10606030000&device=chart"
)
SOURCE = "new.kpx.or.kr"

pp = pprint.PrettyPrinter(indent=4)

#### Classification of New & Renewable Energy Sources ####
# Source: https://cms.khnp.co.kr/eng/content/563/main.do?mnCd=EN040101
# New energy: Hydrogen, Fuel Cell, Coal liquefied or gasified energy, and vacuum residue gasified energy, etc.
# Renewable: Solar, Wind power, Water power, ocean energy, Geothermal, Bio energy, etc.

# src: https://stackoverflow.com/questions/3463930/how-to-round-the-minute-of-a-datetime-object
def time_floor(time, delta, epoch=None):
    if epoch is None:
        epoch = datetime(1970, 1, 1, tzinfo=time.tzinfo)
    mod = (time - epoch) % delta
    return time - mod


def extract_realtime_production(
    raw_data, zone_key: ZoneKey, logger: Logger
) -> ProductionBreakdownList:
    """
    Extracts generation breakdown chart data from the source code of the page.
    """
    # Extract object with data
    data_source = re.search(r"var ictArr = (\[\{.+\}\]);", raw_data).group(1)
    # Un-quoted keys ({key:"value"}) are valid JavaScript but not valid JSON (which requires {"key":"value"}).
    # Will break if other keys than these are introduced. Alternatively, use a JSON5 library (JSON5 allows un-quoted keys)
    data_source = re.sub(
        r'"(localCoal|newRenewable|oil|once|gas|nuclearPower|coal|regDate|raisingWater|waterPower|seq)"',
        r'"\1"',
        data_source,
    )
    json_obj = json.loads(data_source)

    breakdowns = ProductionBreakdownList(logger)

    for item in json_obj:
        if item["regDate"] == "0":
            break

        date = datetime.strptime(item["regDate"], "%Y-%m-%d %H:%M")
        date = arrow.get(date, TIMEZONE).datetime
        breakdowns.append(
            zoneKey=zone_key,
            datetime=date,
            source=SOURCE,
            production=ProductionMix(
                coal=float(item["coal"]) + float(item["localCoal"]),
                gas=float(item["gas"]),
                hydro=float(item["waterPower"]),
                nuclear=float(item["nuclearPower"]),
                oil=float(item["oil"]),
                unknown=float(item["newRenewable"]),
            ),
            storage=StorageMix(
                hydro=-1 * float(item["raisingWater"]),
            ),
        )

    return breakdowns


@refetch_frequency(timedelta(minutes=5))
def fetch_consumption(
    zone_key: ZoneKey = ZoneKey("KR"),
    session: Optional[Session] = None,
    target_datetime: Optional[datetime] = None,
    logger: Logger = getLogger(__name__),
) -> List[dict]:
    """
    Fetches consumption.
    """

    if target_datetime:
        raise NotImplementedError("This parser is not yet able to parse past dates")

    r = session or Session()
    response = r.get(REAL_TIME_URL, verify=False)
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    consumption_val, consumption_date = extract_consumption_from_soup(soup)

    consumption = TotalConsumptionList(logger)
    consumption.append(
        zoneKey=zone_key,
        datetime=consumption_date,
        consumption=consumption_val,
        source=SOURCE,
    )

    return consumption.to_list()


def extract_consumption_from_soup(soup: BeautifulSoup) -> Tuple[float, datetime]:
    """
    Extracts consumption from the source code of the page.
    """
    consumption_title = soup.find("th", string=re.compile(r"\s*현재부하\s*"))
    consumption_val = float(
        consumption_title.find_next_sibling().text.split()[0].replace(",", "")
    )

    consumption_date_list = soup.find("p", {"class": "info_top"}).text.split(" ")[:2]
    consumption_date_list[0] = consumption_date_list[0].replace(".", "-").split("(")[0]
    consumption_date = TIMEZONE.localize(
        datetime.strptime(" ".join(consumption_date_list), "%Y-%m-%d %H:%M")
    )

    return consumption_val, consumption_date


@refetch_frequency(timedelta(hours=1))
def fetch_price(
    zone_key: str = "KR",
    session: Optional[Session] = None,
    target_datetime: Optional[datetime] = None,
    logger: Logger = getLogger(__name__),
):

    first_available_date = time_floor(
        arrow.now(TIMEZONE).shift(days=-6), timedelta(days=1)
    ).shift(hours=1)

    if target_datetime is not None and target_datetime < first_available_date:
        raise NotImplementedError(
            "This parser is not able to parse dates more than one week in the past."
        )

    if target_datetime is None:
        target_datetime = arrow.now(TIMEZONE).datetime

    r = session or Session()
    url = PRICE_URL

    response = r.get(url, verify=False)
    assert response.status_code == 200

    all_data = []
    table_prices = pd.read_html(response.text, header=0)[0]

    for col_idx in range(1, table_prices.shape[1]):
        for row_idx in range(24):

            day = col_idx
            hour = row_idx + 1

            if hour == 24:
                hour = 0
                day += 1

            arw_day = (
                arrow.now(TIMEZONE)
                .shift(days=-1 * (7 - day))
                .replace(hour=hour, minute=0, second=0, microsecond=0)
            )
            price_value = (
                table_prices.iloc[row_idx, col_idx] * 1000
            )  # Convert from Won/kWh to Won/MWh

            data = {
                "zoneKey": zone_key,
                "datetime": arw_day.datetime,
                "currency": "KRW",
                "price": price_value,
                "source": "new.kpx.or.kr",
            }

            all_data.append(data)

    return all_data


def get_long_term_prod_data(
    session: Session, target_datetime: Optional[datetime] = None
) -> List[dict]:
    target_datetime_formatted_daily = target_datetime.strftime("%Y-%m-%d")

    # CSRF token is needed to access the production data
    session.get(LONG_TERM_PRODUCTION_URL)
    cookies_dict = session.cookies.get_dict()

    payload = {
        "mid": "a10606030000",
        "device": "chart",
        "view_sdate": target_datetime_formatted_daily,
        "view_edate": target_datetime_formatted_daily,
        "_csrf": cookies_dict["XSRF-TOKEN"],
    }

    res = session.post(LONG_TERM_PRODUCTION_URL, payload)

    assert res.status_code == 200

    all_data = []

    soup = BeautifulSoup(res.text, "html.parser")
    table_rows = soup.find_all("tr")[1:]

    for row in table_rows:

        sanitized_date = [value[:-1] for value in row.find_all("td")[0].text.split(" ")]
        curr_prod_datetime_string = (
            "-".join(sanitized_date[:3]) + "T" + ":".join(sanitized_date[3:]) + ":00"
        )
        arw_datetime = arrow.get(
            curr_prod_datetime_string, "YYYY-MM-DDTHH:mm:ss", tzinfo=TIMEZONE
        ).datetime

        data = {
            "zoneKey": "KR",
            "datetime": arw_datetime,
            "capacity": {},
            "production": {},
            "storage": {},
            "source": "https://new.kpx.or.kr",
        }

        row_values = row.find_all("td")
        production_values = [
            int("".join(value.text.split(","))) for value in row_values[1:]
        ]

        # order of production_values
        # 0. other, 1. gas, 2. renewable, 3. coal, 4. nuclear
        # other can be negative as well as positive due to pumped hydro

        data["datetime"] = arw_datetime
        data["production"]["unknown"] = production_values[0] + production_values[2]
        data["production"]["gas"] = production_values[1]
        data["production"]["coal"] = production_values[3]
        data["production"]["nuclear"] = production_values[4]

        all_data.append(data)

    return all_data


@refetch_frequency(timedelta(minutes=5))
def fetch_production(
    zone_key: ZoneKey = ZoneKey("KR"),
    session: Optional[Session] = None,
    target_datetime: Optional[datetime] = None,
    logger: Logger = getLogger(__name__),
) -> List[dict]:
    if session is None:
        session = Session()
    if target_datetime is not None and target_datetime < datetime(
        2021, 12, 22, tzinfo=TIMEZONE
    ):
        raise NotImplementedError(
            "This parser is not able to parse dates before 2021-12-22."
        )
    production = ProductionBreakdownList(logger)
    if target_datetime is None:
        # Use real-time data
        target_datetime = datetime.now(TIMEZONE)

        response = session.get(REAL_TIME_URL, verify=False)
        production = extract_realtime_production(
            response.text, zone_key=zone_key, logger=logger
        )

        return production.to_list()

    all_data = get_long_term_prod_data(session=session, target_datetime=target_datetime)

    return all_data


if __name__ == "__main__":
    # Testing datetime on specific date
    target_datetime = arrow.get(2022, 2, 7, 16, 35, 0, tzinfo=TIMEZONE).datetime

    print("fetch_production() ->")
    # pp.pprint(fetch_production(target_datetime=target_datetime))
    pp.pprint(fetch_production())

    print("fetch_price() -> ")
    # pp.pprint(fetch_price(target_datetime=target_datetime))
    pp.pprint(fetch_price())

    print("fetch_consumption() -> ")
    pp.pprint(fetch_consumption())
