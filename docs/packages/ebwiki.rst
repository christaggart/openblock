======
ebwiki
======

A basic wiki.

Caveat
=======

*This package is not actively maintained as of 10/2010.* It
was released as part of the original everyblock source code release,
and we're keeping it here for posterity, but the OpenBlock team has so
far not done anything with it.

Requirements
============

A recent Django release. It has been tested with Django revision 11079 from
Subversion. Django 1.1 should work as well.

Quickstart
==========

0. Install Django, PostgreSQL, and psycopg2. *(Does it really require postgres or would it work with other back ends?  Unknown.)*

1. Install the ebwiki package by putting it on your Python path.

2. Start a Django project. See the Django Book and
   Django docs for more:

       http://djangobook.com/en/2.0/
       http://docs.djangoproject.com/en/dev/

3. Update your settings file. It's probably easiest to just start with the
   file ebblog/settings.py and tweak that (or import from it in your own
   settings file). The application won't work until you set the following::

       DATABASE_USER
       DATABASE_NAME
       DATABASE_HOST
       DATABASE_PORT

   If you decide not to start with ebwiki.settings you'll also need to add
   ebwiki.wiki.urls to your urlconf and add the absolute path to
   ebwiki/templates to your TEMPLATE_DIRS setting.

4. Run ``django-admin.py syncdb`` to create all of the database tables.

5. Run ``django-admin.py runserver`` and go to http://127.0.0.1:8000/ in your
   Web browser to see the site in action.
