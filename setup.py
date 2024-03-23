from pathlib import Path
from setuptools import find_packages, setup

setup(
    name='atools',
    version='0.14.2',
    packages=find_packages(),
    python_requires='>=3.12',
    url='https://github.com/cevans87/atools',
    license='mit',
    author='cevans',
    author_email='c.d.evans87@gmail.com',
    description='Python 3.9+ async/sync memoize and rate decorators',
    extras_require={
        'base': (base := ['pydantic']),
        'sql_cache': (sql_cache := base + ['sqlalchemy']),
        'sqlite_cache': (sqlite_cache := sql_cache + ['aiosqlite']),
        'requirements': (requirements := base + sql_cache + sqlite_cache),
        'test': (test := requirements + ['pytest', 'pytest-asyncio', 'pytest-cov']),
    },
    install_requires=base,
)
