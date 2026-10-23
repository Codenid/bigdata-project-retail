from setuptools import find_packages, setup

setup(
    name='retailsmart-streaming', version='1.0.0',
    packages=find_packages(include=('contracts*', 'pipelines*')),
    package_data={'contracts.streaming': ['*.schema.json']},
    install_requires=['jsonschema==4.25.1', 'referencing==0.37.0'],
)
