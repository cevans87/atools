from typing import Union


def duration(parse: Union[int, float, str]) -> float:
    """Returns number of seconds in given 'token'.

    If 'token' is a str, it is given in days, hours, minutes, and seconds like '1d2h3m4s' for 1 day,
    2 hours, 3 minutes, and 4 seconds.
    """
    if isinstance(parse, (float, int)):
        return float(parse)

    total = 0
    remainder = parse
    for suffix, mul in (('d', 24), ('h', 60), ('m', 60), ('s', 1)):
        try:
            value, remainder = remainder.split(suffix)
        except ValueError:
            value = 0
        else:
            value = int(value)

        total = (total + value) * mul

    if remainder:
        raise ValueError(f"Invalid parse token '{parse}'")

    return float(total)
