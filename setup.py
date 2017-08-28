"""setup.py file."""


import uuid

from pip.req import parse_requirements

from setuptools import find_packages, setup

__author__ = 'Ben Maddison <benm@workonline.co.za>'

install_reqs = parse_requirements('requirements.txt', session=uuid.uuid1())
reqs = [str(ir.req) for ir in install_reqs]

description = "Network Automation and Programmability Abstraction Layer with \
    Multivendor support"

setup(
    name="napalm-exaros",
    version="0.1.0",
    packages=find_packages(),
    author="Ben Maddison",
    author_email="benm@workonline.co.za",
    description=description,
    classifiers=[
        'Topic :: Utilities',
         'Programming Language :: Python',
         'Programming Language :: Python :: 2',
         'Programming Language :: Python :: 2.7',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS',
    ],
    url="https://github.com/wolcomm/napalm-exaros",
    include_package_data=True,
    install_requires=reqs,
)
