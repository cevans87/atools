from setuptools import find_packages, setup

setup(
    name='atools',
    version='0.7.0',
    packages=find_packages(),
    python_requires='>=3.6',
    url='https://github.com/cevans87/atools',
    license='mit',
    author='cevans',
    author_email='c.d.evans87@gmail.com',
    description='Python 3.6+ async decorators and testing tools',
    tests_require=[
        'pytest',
        'pytest-asyncio',
        'pytest-cov',
    ],
)
