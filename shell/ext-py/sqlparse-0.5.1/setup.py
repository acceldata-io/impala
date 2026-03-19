#!/usr/bin/env ambari-python-wrap
# -*- coding: utf-8 -*-
#
# Copyright (C) 2009-2018 the sqlparse authors and contributors
# <see AUTHORS file>
#
# This setup script is part of python-sqlparse and is released under
# the BSD License: https://opensource.org/licenses/BSD-3-Clause

import re
  from setuptools import setup, find_packages

  def get_version():
      VERSIONFILE = 'sqlparse/__init__.py'
      VSRE = r'^__version__ = [\'"]([^\'"]*)[\'"]'
      with open(VERSIONFILE) as f:
          verstrline = f.read()
      mo = re.search(VSRE, verstrline, re.M)
      if mo:
          return mo.group(1)
      raise RuntimeError('Unable to find version in %s' % VERSIONFILE)

  setup(
      name='sqlparse',
      version=get_version(),
      author='Andi Albrecht',
      author_email='albrecht.andi@gmail.com',
      url='https://github.com/andialbrecht/sqlparse',
      description='A non-validating SQL parser.',
      license='BSD',
      python_requires='>=3.8',
      packages=find_packages(exclude=('tests',)),
      entry_points={
          'console_scripts': [
              'sqlformat = sqlparse.__main__:main',
          ]
      },
  )