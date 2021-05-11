# AK Planning

## Description

AKPlanning is a tool used for modeling, submitting, scheduling and displaying AKs (German: Arbeitskreise), meaning workshops, talks or similar slot-based events.

It was built for KIF (German: Konferenz der deutschsprachigen Informatikfachschaften), refer to [the wiki](wiki.kif.rocks) for more Information.


## Structure

This repository contains a Django project called AKPlanning. The functionality is encapsulated into Django apps:

1. **AKModel**: This app contains the general Django models used to represent events, users, rooms, scheduling constraints etc. This app is a basic requirements for the other apps. Data Import/Export also goes here.
1. **AKDashboard**: This app provides a landing page for the project. Per Event it provides links to all relevant functionalities and views.
1. **AKSubmission**: This app provides forms to submit all kinds of AKs, edit or delete them, as well as a list of all submitted AKs for an event.
1. **AKScheduling**: This app allows organizers to schedule AKs, i.e. assigning rooms, slots, etc. It marks conflicts of all modeled constraints and assists in creating a suitable schedule.
1. **AKPlan**: This app displays AKs and where/when they will take place for each event. Views are optimised according to usage/purpose.


## Setup instructions

See [INSTALL.md](INSTALL.md) for detailed instructions on development and production setups.

To update the setup to the current version on the main branch of the repository use the update script ``Utils/update.sh`` or ``Utils/update.sh --prod`` in production.

Afterwards, you may check your setup by executing ``Utils/check.sh`` or ``Utils/check.sh --prod`` in production.



## Developer Notes
* to regenerate translations use ````python manage.py makemessages -l de_DE --ignore venv````
* to create a data backup use ````python manage.py dumpdata --indent=2 > db.json --traceback````
