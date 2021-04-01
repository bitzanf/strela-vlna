#!/bin/bash
./manage.py makemigrations
read;
./manage.py migrate
