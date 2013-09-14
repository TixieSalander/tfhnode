import os
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))

requires = [
    'SQLAlchemy',
    'mako',
]

setup(name='tfhnode',
    version='0.0',
    description='tfhnode',
    packages=find_packages(),
    install_requires=requires,
)

