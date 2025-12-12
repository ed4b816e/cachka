from enum import IntEnum


class Intervals(IntEnum):
    ONE_MINUTE = 60
    FIVE_MINUTES = 60 * 5
    ONE_HOUR = 60 * 60
    ONE_DAY = 60 * 60 * 24
    TWO_DAY = 60 * 60 * 24 * 2
    THREE_MONTH = 60 * 60 * 24 * 90
    SIX_MONTH = 60 * 60 * 24 * 180
    ONE_YEAR = 60 * 60 * 24 * 365