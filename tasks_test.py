import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','veturilo.settings')

import django
django.setup()


import requests
import pandas as pd

from bs4 import BeautifulSoup
from celery.task.schedules import crontab
from celery.decorators import periodic_task
from datetime import datetime, timedelta, date
from django.db.models import Avg

from scraper.models import Snapshot, Location, Stat


def scrape(url='www.veturilo.waw.pl/mapa-stacji/'):
    """
    This function will extract the table from Veturilo website and create a
    pandas dataframe from it.
    """
    req = requests.get('https://' + url)
    table = BeautifulSoup(req.text).table
    dat=[]
    for row in table.find_all('tr'):
        cols = row.find_all('td')
        cols = [ele.text.strip() for ele in cols]
        dat.append([ele for ele in cols if ele])

    cols = ['Location', 'Bikes', 'Stands', 'Free stands', 'Coords']
    df = pd.DataFrame(dat, columns=cols)
    df.dropna(inplace=True)
    return df


# @periodic_task(run_every=crontab())
def take_snapshot():
    """
    Function that scrapes the veturilo website every 30 minutes and places
    the raw data in the DB.
    """
    df = scrape()
    for i in df.index:
        single = df.loc[i]
        # create or get locations
        loc, created = Location.objects.get_or_create(
                                name=single['Location'],
                                all_stands=single['Stands'],
                                coordinates=single['Coords']
                                )
        print('Location: ' + loc.name)
        # add a new snapshot
        obj = Snapshot(
            location = loc,
            avail_bikes = single['Bikes'],
            free_stands = single['Free stands'],
        )
        obj.save()
        print('Time: ' +  str(obj.timestamp))


# @periodic_task(run_every=crontab(minute=0, hour=0))
def delete_old():
    """
    Function that deletes snapshots >35 days old on the daily basis.
    """
    objs = (Snapshot
            .objects
            .filter(timestamp__lte=(datetime.now() - timedelta(days=35)))
            )
    objs.delete()


# @periodic_task(run_every=crontab(0, 0, day_of_month='1'))
def reduce_data():
    """
    Function averages data from every month and places it in a separate
    table.
    """
    snapshots = Snapshot.objects.all()
    locations = Location.objects.all()
    lst=[]
    for snapshot in snapshots:
        lst.append([snapshot.location.name, snapshot.avail_bikes,
                    snapshot.free_stands, snapshot.timestamp,
                    snapshot.weekend])
    cols = ['location', 'avail_bikes', 'free_stands', 'timestamp', 'weekend']
    df = pd.DataFrame(lst, columns=cols)
    df['time'] = df['timestamp'].dt.round('10min').dt.strftime('%H:%M')

    group = df.groupby(['location', 'time', 'weekend'])
    means = group.mean()
    sd = group.std()
    today = date.today()
    first = today.replace(day=1)
    last_month = first - timedelta(days=1)

    for name, time, weekend in means.index:
        subset_mean = means.xs((name, time, weekend), level=(0, 1, 2), axis=0)
        subset_sd = sd.xs((name, time, weekend), level=(0, 1, 2), axis=0)
        m = Stat.objects.get_or_create(
        location = locations.get(name=name),
        avail_bikes_mean = subset_mean['avail_bikes'],
        free_stands_mean = subset_mean['free_stands'],
        avail_bikes_sd = subset_sd['avail_bikes'],
        free_stands_sd = subset_sd['free_stands'],
        time = time,
        month = last_month,
        weekend = weekend
        )
        print(name + ' calculated' + 'weekend: ' + str(weekend))

if __name__ == '__main__':
    # for snapshot in Snapshot.objects.select_related():
    #     snapshot.save()
    #     print(snapshot.location.name +  ' changed')
    # print('-----------------')
    # Stat.objects.all().delete()
    # print('Stats deleted')
    # reduce_data()
    # locs = Location.objects.all()
    # for loc in locs:
    #     loc.save()
    #     print(loc.name + ' saved')
    #
    # stats = Stat.objects.select_related()
    #
    # for stat in stats:
    #     stat.avail_bikes_sd = 1
    #     stat.free_stands_sd = 2
    #     stat.save()
    #     print(stat.location.name)

    # snap = Snapshot.objects.first()
    # print(snap.timestamp.weekday())