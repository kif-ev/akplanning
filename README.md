# AK Planning

## Description

AKPlanning is a tool used for modeling, submitting, scheduling and displaying AKs (German: Arbeitskreise), meaning workshops, talks or similar slot-based events.

It was built for KIF (German: Konferenz der deutschsprachigen Informatikfachschaften), refer to [the wiki](wiki.kif.rocks) for more Information.


## Setup

This repository contains a Django project with several apps.


### Requirements

AKPlanning has two types of requirements: System requirements are dependent on operating system and need to be installed manually beforehand. Python requirements will be installed inside a virtual environment (strongly recommended) during setup.


#### System Requirements

* Python 3.7 incl. development tools
* Virtualenv
* for production using uwsgi:
  * C compiler e.g. gcc
  * uwsgi Python3 plugin
* for production using Apache (in addition to uwsgi)
  * the mod proxy uwsgi plugin for apache2


#### Python Requirements

Python requirements are listed in ``requirements.txt``. They can be installed with pip using ``-r requirements.txt``.


### Development Setup

* create a new directory that should contain the files in future, e.g. ``mkdir AKPlanning``
* change into that directory ``cd AKPlanning``
* clone this repository ``git clone URL .``


**Automatic Setup**

1. execute the setup bash script ``Utils/setup.sh``


**Manual Setup**

1. setup a virtual environment using the proper python version ``virtualenv env -p python3.7``
1. activate virtualenv ``source env/bin/activate``
1. install python requirements ``pip install -r requirements.txt``
1. setup necessary database tables etc. ``python manage.py migrate``
1. create a priviledged user, credentials are entered interactively on CLI ``python manage.py createsuperuser``
1. deactivate virtualenv ``deactivate``


**Development Server**

To start the application for development use ``python manage.py runserver 0:8000`` from the root directory.
*Do not use this for deployment!*

In your browser, access ``http://127.0.0.1:8000/`` and continue from there.


### Deployment Setup

This application can be deployed using a web server as any other Django application.
Remember to use a secret key that is not stored in any repository or similar, and disable DEBUG mode (``settings.py``).

**Step-by-Step Instructions**

1. log into your system with a sudo user
1. install system requirements
1. create a folder, e.g. ``mkdir /srv/AKPlanning/``
1. change to the new directory ``cd /srv/AKPlanning/``
1. clone this repository ``git clone URL .``
1. setup a virtual environment using the proper python version ``virtualenv env -p python3.7``
1. activate virtualenv ``source env/bin/activate``
1. update tools ``pip install --upgrade setuptools pip wheel``
1. install python requirements ``pip install -r requirements.txt``
1. install uwsgi ``pip install uwsgi``
1. create the file ``AKPlanning/settings_secrets.py`` (copy from ``settings_secrets.py.sample``) and fill it with the necessary secrets (e.g. generated by ``tr -dc 'a-z0-9!@#$%^&*(-_=+)' < /dev/urandom | head -c50``) (it is a good idea to restrict read permissions from others)
1. if necessary enable uwsgi proxy plugin for Apache e.g.``a2enmod proxy_uwsgi``
1. edit the apache config to serve the application and the static files, e.g. on a dedicated system in ``/etc/apache2/sites-enabled/000-default.conf`` within the ``VirtualHost`` tag add:

    ```
    Alias /static /srv/AKPlanning/static
    <Directory /srv/AKPlanning/static>
    Require all granted
    </Directory>

    ProxyPassMatch ^/static/ !
    ProxyPass / uwsgi://127.0.0.1:3035/
    ```

    or create a new config (.conf) file under ``/etc/apache2/sites-available``, fill it with something like:

    ````
    <VirtualHost *:80>

      ServerName $SUBDOMAIN

      ServerAdmin $MAILADDRESS

      ErrorLog ${APACHE_LOG_DIR}/error.log
      CustomLog ${APACHE_LOG_DIR}/access.log combined

      Alias /static /srv/AKPlanning/static
      <Directory /srv/AKPlanning/static>
      Require all granted
      </Directory>

      ProxyPassMatch ^/static/ !
      ProxyPass / uwsgi://127.0.0.1:3035/

      RewriteEngine on
      RewriteCond %{SERVER_NAME} =$SUBDOMAIN
      RewriteRule ^ https://%{SERVER_NAME}%{REQUEST_URI} [END,NE,R=permanent]
    </VirtualHost>
    ````

    replacing $SUBDOMAIN with the subdomain the system should be available under, and $MAILADDRESS with the e-mail address of your administrator. Then symlink it to ``sites-enabled`` e.g. by using ``ln -s /etc/apache2/sites-available/akplanning.conf /etc/apache2/sites-enabled/akplanning.conf``.
1. restart Apache ``sudo systemctl restart apache2.service``
1. create a dedicated user, e.g. ``adduser django``
1. transfer ownership of the folder to the new user ``chown -R django:django /srv/WannaDB``
1. change to the new user ``sudo su django``
1. change into the Django project folder ``cd WannaDB``
1. start uwsgi using the configuration file ``uwsgi --ini uwsgi-akplanning.ini``
1. execute the update script ``./Utils/update.sh --prod``


### Updates

To update the setup to the current version on the main branch of the repository use the update script ``Utils/update.sh`` or ``Utils/update.sh --prod`` in production.

Afterwards, you may check your setup by executing ``Utils/check.sh`` or ``Utils/check.sh --prod`` in production.


## Structure

This repository contains a Django project called AKPlanning. The functionality is encapsulated into Django apps:

1. **AKModel**: This app contains the general Django models used to represent events, users, rooms, scheduling constraints etc. This app is a basic requirements for the other apps. Data Import/Export also goes here.
1. **AKDashboard**: This app provides a landing page for the project. Per Event it provides links to all relevant functionalities and views.
1. **AKSubmission**: This app provides forms to submit all kinds of AKs, edit or delete them, as well as a list of all submitted AKs for an event.
1. **AKScheduling**: This app allows organizers to schedule AKs, i.e. assigning rooms, slots, etc. It marks conflicts of all modeled constraints and assists in creating a suitable schedule.
1. **AKPlan**: This app displays AKs and where/when they will take place for each event. Views are optimised according to usage/purpose.
