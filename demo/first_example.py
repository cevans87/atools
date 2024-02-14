import atools


@atools.CLI(__name__)
def entrypoint() -> None:
    print('haha')


if __name__ == '__main__':
    atools.CLI(__name__).run()
