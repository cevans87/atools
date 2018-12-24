from atools import util
import unittest


class TestUtil(unittest.TestCase):

    def test_util_time(self) -> None:
        for parse, result in (
            ('1s', 1),
            ('1m', 60),
            ('1h', 3600),
            ('1d', 86400),
            ('1d1h1m1s', 90061),
            ('10d10h10m10s', 900610),
        ):
            self.assertEqual(util.seconds(parse), result)


if __name__ == '__main__':
    unittest.main()
