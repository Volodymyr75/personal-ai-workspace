"""Internal JSON primitives shared by fixed Google Ads evidence use cases."""

import re
from datetime import date
from decimal import Decimal

from paw.domain.files import InputError

_DECIMAL = re.compile(r"[0-9]{1,16}(?:\.[0-9]{1,18})?(?:E[+-]?[0-9]{1,2})?")


def _invalid() -> InputError:
    return InputError("invalid_evidence_input")


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise _invalid()
    return value


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise _invalid()
    return value


def _text(value: object, limit: int = 32768) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > limit
        or any(0xD800 <= ord(c) <= 0xDFFF for c in value)
    ):
        raise _invalid()
    return value


def _date(value: object) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise _invalid()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _invalid() from None


def _count(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 10**15:
        raise _invalid()
    return value


def _cost(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _DECIMAL.fullmatch(value):
        raise _invalid()
    number = Decimal(value)
    exponent = number.as_tuple().exponent
    if number > Decimal("1e15") or not isinstance(exponent, int) or exponent < -18:
        raise _invalid()
    return number


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid()
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise _invalid()


def _encode(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal) and value.is_finite():
        return format(value, "f")
    raise _invalid()
