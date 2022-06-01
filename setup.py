#!/usr/bin/env python
from setuptools import setup
from py3stratum import version

setup(name='py3stratum',
      version=version.VERSION,
      description='Stratum server implementation based on Twisted',
      author='0x000000000019b6',
      author_email='0x000000000019b6@gmail.com',
      url='https://github.com/0x000000000019b6/py3stratum',
      packages=['py3stratum',],
      py_modules=['distribute_setup',],
      zip_safe=False,
      install_requires=['setuptools-rust', 'twisted', 'ecdsa', 'cryptography>=35.0', 'pyopenssl', 'autobahn', 'pyasn1', 'service-identity',]
     )
