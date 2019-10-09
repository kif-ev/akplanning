# AK Planning

## Description

AKPlanning is a tool used for modeling, submitting, scheduling and display AKs (German: Arbeitskreise), meaning workshops, talks or similar slot-based events.

It was built for KIF (German: Konferenz der deutschsprachigen Informatikfachschaften), refer to [the wiki](wiki.kif.rocks) for more Information.


## Setup

This repository contains a Django project with several apps.


### Requirements

AKPlanning has two types of requirements: System requirements are dependent on operating system and need to be installed manually beforehand. Python requirements will be installed inside a virtual environment (strongly recommended) during setup.


#### System Requirements

* Python 3.7
* Virtualenv


#### Python Requirements

Python requirements are listed in ``requirements.txt``. They can be installed with pip using ``-r requirements.txt``.


### Development Setup

* create a new directory that should contain the files in future, e.g. ``mkdir AKPlanning``
* change into that directory ``cd AKPlanning``
* clone this repository ``git clone URL .``

1. setup a virtual environment using the proper python version ``virtualenv env -p python3.7``
1. activate virtualenv ``source env/bin/activate``
1. install python requirements ``pip install -r requirements.txt``
1. setup necessary database tables etc. ``python manage.py migrate``
1. create a priviledged user, credentials are entered interactively on CLI ``python manage.py createsuperuser``
1. deactivate virtualenv ``deactivate``

To start the application for development use ``python manage.py runserver 0:8000`` from the root directory.
*Do not use this for deployment!*

In your browser, access ``http://127.0.0.1:8000/wannaDB/`` and continue from there.
