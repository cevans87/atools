
def duration(parse: str) -> int:
    """Returns number of seconds in given 'parse' string.

    'parse' is given in days, hours, minutes, and seconds like '1d2h3m4s' for 1 day,
    2 hours, 3 minutes, and 4 seconds.
    """
    total = 0
    for suffix, mul in (('d', 24), ('h', 60), ('m', 60), ('s', 1)):
        try:
            token, parse = parse.split(suffix)
        except ValueError:
            value = 0
        else:
            value = int(token)

        total = (total + value) * mul

    return total
