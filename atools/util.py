
def seconds(parse: str) -> int:
    total = 0
    for suffix, mul in (('d', 24), ('h', 60), ('m', 60), ('s', 1)):
        try:
            token, parse = parse.split(suffix)
        except ValueError:
            value = 0.0
        else:
            value = int(token)

        total = (total + value) * mul

    return total
