"""
Script posts tweets with the current NBA games ranking.
To be executed as cron process on a server.
Author: AI Geek Programmer
Date: Apr-2020
"""
import tweepy
import datetime
import pandas as pd
import pytz
import os
import random
from dotenv import load_dotenv, find_dotenv

# function that opens log file and write execution result
def write_to_log(log):
    with open(r"./log/twitter.log", 'a') as f:
        f.write(log)


# function to print specific number of yellow stars
def gen_stars(stars):
    str = ""
    for i in range(1, stars + 1):
        str = str + u'\u2B50'
    return str

# We always ask for yesterday's games.
yesterday = (datetime.date.today() - datetime.timedelta(days=1))
now = datetime.datetime.now()
utc = pytz.utc
eastern = pytz.timezone('US/Eastern')

# so the filename is:
file_name = "./scoring/scoring-" + yesterday.strftime('%Y-%m-%d') + ".csv"

# let's start logging event & info
log = now.strftime('%Y-%m-%d %H:%M:%S') + ": "

# we read cvs file using pandas. If failed we log error and exit
try:
    games = pd.read_csv(file_name)
except FileNotFoundError:
    log += "Unable to open file: " + file_name + ". Aborting. [100]\n"
    write_to_log(log)
    exit()

# we begin to built post
# get current time in UTC timezone and convert into Eastern timezone
time_utc = utc.localize(now)
time_et = time_utc.astimezone(eastern).strftime('%H:%M')

post_options = [
    "",
    "Tips welcome: https://ko-fi.com/nbagamesranked" + "\n\n",
    "Please support this service by retweet and like\n\n"
]
post = "Games for " + yesterday.strftime('%d, %b %Y') + "\n\n" + random.choice(post_options)


# to limit the length of a tweet we present the first LIMIT games only
LIMIT = 8
n_of_games = 0
for ind in games.index:
    # calculating no of stars. 1 - 15 (1), 16 - 27 (2), 28 - 40 (3), 41 - 56 (4), 57 - 100 (5)
    pts = int(games['SCORE: 0 - 100'][ind])
    stars = ""
    if pts <= 15:
        stars = gen_stars(1)
    elif 15 < pts <= 27:
        stars = gen_stars(2)
    elif 27 < pts <= 40:
        stars = gen_stars(3)
    elif 40 < pts <= 56:
        stars = gen_stars(4)
    elif pts > 56:
        stars = gen_stars(5)

    post = post + games['Visitor'][ind] + "-" + games['Host'][ind] + ": " + \
        stars + " (" + str(pts) + ")\n"
    n_of_games += 1
    if n_of_games == LIMIT:
        break
post = post + "#nba"

# If there are no game we do not send anything just logging
if n_of_games == 0:
    log += "No games in the ranking. [200]\n"
    write_to_log(log)
    exit()
else:
    log += "Posting ranking with " + str(n_of_games) + " games. "

# load authentication tokens
_ = load_dotenv(find_dotenv(filename='./.env'))
consumer_key = os.environ['CONSUMER_KEY']
consumer_secret = os.environ['CONSUMER_SECRET']
access_token = os.environ['ACCESS_TOKEN']
access_token_secret = os.environ['ACCESS_TOKEN_SECRET']

# authenticate
client = tweepy.Client(
    consumer_key=consumer_key,
    consumer_secret=consumer_secret,
    access_token=access_token,
    access_token_secret=access_token_secret
)

# posting
try:
    status = client.create_tweet(text=post)
    log += "Tweet successful. Post length: " + str(len(post)) + "\n"
    write_to_log(log)
except tweepy.errors.BadRequest as e:
    log += f"Bad Request. Unable to post tweet. Post length: {len(post)}. Aborting. [400]\nError: {e.response.text}\n"
    write_to_log(log)
    exit()
except tweepy.errors.Unauthorized as e:
    log += f"Unauthorized access. Post length: {len(post)}. Aborting. [401]\nError: {e.response.text}\n"
    write_to_log(log)
    exit()
except tweepy.errors.TweepyException as e:
    log += f"Some generic error occurred: {str(e)}\n"
    write_to_log(log)
    exit()
