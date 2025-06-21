# AK Planning

## Description

AKPlanning is a tool used for modeling, submitting, scheduling and displaying AKs (German: Arbeitskreise), meaning
workshops, talks or similar slot-based events.

It was built for the KIF (German: Konferenz der deutschsprachigen Informatikfachschaften), refer
to [the wiki](https://wiki.kif.rocks) for more Information.

## Structure

This repository contains a Django project called AKPlanning. The functionality is encapsulated into Django apps:

1. **AKModel**: This app contains the general Django models used to represent events, users, rooms, scheduling
   constraints etc. This app is a basic requirements for the other apps. Data Import/Export also goes here.
2. **AKDashboard**: This app provides a landing page for the project. Per event, it provides links to all relevant
   functionalities and views.
3. **AKSubmission**: This app provides forms to submit all kinds of AKs, edit or delete them, as well as a list of all
   submitted AKs for an event.
4. **AKScheduling**: This app allows organizers to schedule AKs, i.e. assigning rooms, slots, etc. It marks conflicts of
   all modeled constraints and assists in creating a suitable schedule.
5. **AKPlan**: This app displays AKs and where/when they will take place for each event. Views are optimised according
   to usage/purpose.
6. **AKOnline**: This app contains functionality for online/hybrid events, such as online rooms (links for video or
   audio calls).
7. **AKPreference**: This apps facilitates the submission of preferences for AKs, so each participants can mark which
   AKs they would like to visit, to facilitate better scheduling.
8. **AKSolverInterface**: This app provides an interface to an automatic solver, a tool that can be used to generate
   schedules based on the submitted AKs and preferences.

## Setup instructions

See [INSTALL.md](INSTALL.md) for detailed instructions on development and production setups.

To update the setup to the current version on the main branch of the repository use the update script
``Utils/update.sh`` or ``Utils/update.sh --prod`` in production.

Afterward, you may check your setup by executing ``Utils/check.sh`` or ``Utils/check.sh --prod`` in production.

## Developer Notes

* to regenerate translations use ````python manage.py makemessages -l de_DE --ignore venv````
* to create a data backup use ````python manage.py dumpdata --indent=2 > db.json --traceback````
* to export all database items belonging to a certain event use
  ````./Utils/json_export.sh <event_id> <export_prefix>  [--prod]````. The results will be saved in
  ````backups/<export_prefix>.json````
