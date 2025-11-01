"""
Definition of 2 main classes for NBA Games Ranked app:
1) NBAGamesDataCollector: collects games data from RapidApi
2) NBAGamesScoringCalculator: calculates ranking
3) Plus some helper methods and functions outside of the classes.

Author: Szymon Manduk
"""

import datetime
import time
import pytz
import requests
import pandas as pd
import json
import os
from dotenv import load_dotenv, find_dotenv

# Class collects games data from external api provided by RapidAPI
class NBAGamesDataCollector:
    # We need to pause between API calls to avoid exceeding the limit of 10 calls per minute
    API_PAUSE_TIME = 8  # seconds

    def __init__(self, playoff_mode=False):  # if playoff mode we include additional scoring # PLAYOFF2021
        # read API key from .env file
        _ = load_dotenv(find_dotenv(filename='./.env'))
        self.API_KEY= os.getenv("API_KEY")
       
        self.HEADERS = {
            'x-rapidapi-host': "api-nba-v1.p.rapidapi.com",
            'x-rapidapi-key': self.API_KEY
        }
        self.request_games = None
        self.request_team = None
        self.url_games = "https://api-nba-v1.p.rapidapi.com/games/date/"
        self.url_team = "https://api-nba-v1.p.rapidapi.com/standings/standard/2025/teamId/"
        self.url_stats = "https://api-nba-v1.p.rapidapi.com/statistics/players/gameId/"
        self.games_df = pd.DataFrame()

        self.playoff_mode = playoff_mode  # PLAYOFF2021
        self.playoff_df = pd.DataFrame(columns=['Visitor', 'Host', 'Playoff_pts'])  # PLAYOFF2021

        # We need to use an additional API as the main API does not provide information about OTs
        self.HEADERS_API_BASKETBALL = {
	        "X-RapidAPI-Key": self.API_KEY,
	        "X-RapidAPI-Host": "api-basketball.p.rapidapi.com"
        }
        self.request_games_api_basketball = None
        self.url_games_api_basketball = "https://api-basketball.p.rapidapi.com/games"

    # getting games data in JSON
    def get_games_data(self, date: datetime.date = datetime.date.today()):
        self.request_games = requests.get(self.url_games + str(date), headers=self.HEADERS)
        # pause to avoid exceeding the limit of 10 calls per minute
        time.sleep(self.API_PAUSE_TIME)

        # We need to call another API to try te find out if there were any OTs in a game
        try:
            querystring = {"season":"2025-2026","league":"12","date":str(date)}

            response = requests.get(
                self.url_games_api_basketball, 
                headers=self.HEADERS_API_BASKETBALL, 
                params=querystring
            )
            self.request_games_api_basketball = response.json()

        except requests.RequestException as e:
            print(f"An error occurred: {e}")

        finally:
            # pause to avoid exceeding the limit of 10 calls per minute
            time.sleep(self.API_PAUSE_TIME)

        # checking number of games returned by the API
        data = self.request_games.json()
        return int(data['api']['results'])

    # collecting data we need to proceed with scoring and save it in Pandas DataFrame
    def get_games_stats(self, verbose=False):
        columns = ['Status', 'Start Time UTC', 'Start Time ET', 'Start Time ET Date', 'Start Time CET', 'End Time UTC', 'End Time ET', 'End Time CET',
                   'vTeamID', 'vPCT', 'vConfRank', 'Visitor', 'Visitor Pts', 'Host Pts', 'Host', 'hConfRank', 'hPCT', 'hTeamID',
                   'pointsDiff', 'OT', 'OT2', 'vLogoLink', 'hLogoLink', 'Playoff', 'GameId', 'Highest pts']
        lst = []

        data = self.request_games.json()
        for game in data['api']['games']:
            finished = (game['statusGame'] == 'Finished')
            # 31.08.2020
            # Around the end of August 2020 I encountered duplicate entries in games lists. One entry was finished
            # (correct). Other entries (usually additional one) were "scheduled" (duplicated). It might happened due to
            # BLM protest that forced games to be rescheduled. This all resulted in duplicates in the ranking.
            # To avoid this I remove all not finished games from further processing. Some code that comes after this
            # condition assumes that game might not be finished yet.
            # However there should be no more unfinished games in the processing engine after this line***.
            if not finished:
                no_OT = 0
                points_diff = 0
                continue  # *** added condition
            else:
                no_OT = int(game['currentPeriod'][0:1]) - 4
                points_diff = abs(int(game['vTeam']['score']['points']) - int(game['hTeam']['score']['points']))
                game_id = game['gameId']  # we add game ID to be able to collect game stats from another endpoint
                highest_pts = 0  # From game stats we want the highest scoring for a player
                no_OT2 = 0  # Number of OTs we take from another API call in case the main API call contains incorrect data

            if verbose:
                print(game['vTeam']['shortName'], "-", game['hTeam']['shortName'], ":",
                      game['vTeam']['score']['points'], game['hTeam']['score']['points'],
                      "finished:", game['statusGame'], game_id)

            # Sometimes, due to error in a response, there is an empty element in data['api']['games']
            # In that case we want to skip it
            v_team_id = game['vTeam']['teamId']
            if (v_team_id is None or v_team_id == ""): continue

            # for each team in a match-up we collect win PCT and ranking in its conference
            self.get_team_data(v_team_id)
            team_data = self.request_team.json()
            v_team_rank = int(team_data['api']['standings'][0]['conference']['rank'])
            v_team_pct = float(team_data['api']['standings'][0]['winPercentage'])

            # the same for the host team
            h_team_id = game['hTeam']['teamId']
            if (h_team_id is None or h_team_id == ""): continue

            self.get_team_data(h_team_id)
            team_data = self.request_team.json()
            h_team_rank = int(team_data['api']['standings'][0]['conference']['rank'])
            h_team_pct = float(team_data['api']['standings'][0]['winPercentage'])

            # Getting start time in UTC, ET and CET in the right format
            start_time_utc, start_time_et, start_time_et_date, start_time_cet = self.get_formatted_dates(game['startTimeUTC'])

            # Getting end time in UTC, ET and CET in the right format - only if gamed is finished
            if not finished:
                end_time_utc = None
                end_time_et = None
                end_time_cet = None
            else:
                end_time_utc, end_time_et, _, end_time_cet = self.get_formatted_dates(game['endTimeUTC'])

            # Getting points for a playoff game # PLAYOFF2021
            playoff_pts = 0
            if self.playoff_mode:
                # we are looking for the visiting team entry. If not found just leave playoff_pts at 0
                short_name = game['vTeam']['shortName']
                #if verbose:
                print("(", start_time_et, ") Looking for:", short_name)
                try:
                    playoff_pts = self.playoff_df.loc[self.playoff_df['Visitor'] == short_name]["Playoff_pts"].values[0]
                    # if verbose:
                    print("Found:", short_name, playoff_pts)
                except IndexError:
                    # if verbose:
                    print("Not found!", short_name)

            # checking the highest scoring for a player in a game
            highest_pts = self.get_the_highest_pts(game_id, verbose)

            # get the number of OTs from another API
            no_OT2 = self.calculate_OTs(game['hTeam']['fullName'], verbose)

            lst.append([
                game['statusGame'],
                start_time_utc,
                start_time_et,
                start_time_et_date,
                start_time_cet,
                end_time_utc,
                end_time_et,
                end_time_cet,
                game['vTeam']['teamId'],
                v_team_pct,
                v_team_rank,
                game['vTeam']['shortName'],
                game['vTeam']['score']['points'],
                game['hTeam']['score']['points'],
                game['hTeam']['shortName'],
                h_team_rank,
                h_team_pct,
                game['hTeam']['teamId'],
                points_diff,
                no_OT,
                no_OT2,
                game['vTeam']['logo'],
                game['hTeam']['logo'],
                playoff_pts,  # PLAYOFF2021
                game_id,  
                highest_pts,
            ])

        self.games_df = pd.DataFrame(lst, columns=columns)
        return len(self.games_df) # returns final games number

    # get playoff data from file to supplement scoring # PLAYOFF2021
    def get_playoff_data(self):
        if self.playoff_mode:
            self.playoff_df = pd.read_csv('./scoring/playoff.csv')

    # get team data in JSON to collect data like win PCT or current rank
    def get_team_data(self, team_id):
        # print("Team ID:", team_id)
        self.request_team = requests.get(self.url_team + team_id, headers=self.HEADERS)
        # pause to avoid exceeding the limit of 10 calls per minute
        time.sleep(self.API_PAUSE_TIME)

    def get_the_highest_pts(self, game_id, verbose=False):
        highest_pts = 0
        try:
            response = requests.get(self.url_stats + game_id, headers=self.HEADERS)

            data = response.json()
            
            for player in data['api']['statistics']:
                if int(player['points']) > highest_pts:
                    highest_pts = int(player['points'])
        except requests.RequestException as e:
            print(f"An error occurred: {e}")

        except json.JSONDecodeError:
            print("Failed to decode JSON response.")
        
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        finally:
            # pause to avoid exceeding the limit of 10 calls per minute
            time.sleep(self.API_PAUSE_TIME)
            if verbose:
                print(f"Highest pts for game id {game_id}: {highest_pts}")

        return highest_pts

    def calculate_OTs(self, home_team_name, verbose=False):
        no_OT2 = 0
        
        # data has been collected in self.request_games_api_basketball
        # game_name input parameter is the name of the home team from game['hTeam']['fullName']
        # we need to find the game in the list and then if points in OT are > 0, then assign no_OT2 = 1
        for game in self.request_games_api_basketball['response']:
            if game.get('teams', {}).get('home', {}).get('name') == home_team_name:
                over_time = game.get('scores', {}).get('home', {}).get('over_time')
                if over_time is not None:
                    no_OT2 = 1
                break                           

        return no_OT2

    # getting list of seasons in JSON 
    def get_seasons(self):
        url = "https://api-nba-v1.p.rapidapi.com/seasons/"
        response = requests.get(url, headers=self.HEADERS)
        # pause to avoid exceeding the limit of 10 calls per minute
        time.sleep(self.API_PAUSE_TIME)        

    # converting datetime returned from the API as string, into a time-zoned, formatted datetime object
    def get_formatted_dates(self, date):
        # date format in API: 2019-12-04T02:09:00.000Z
        utc = pytz.utc
        eastern = pytz.timezone('US/Eastern')
        warsaw = pytz.timezone('Europe/Warsaw')
        fmt = '%Y-%m-%d %H:%M'
        fmt2 = '%Y-%m-%d'

        # Converting datetime returned from the API as string into a timezone-naive datetime object
        # Date format is usually '%Y-%m-%dT%H:%M:%S.%fZ'. However sometimes it's only '%Y-%m-%d',
        # hence first we try to convert from a full format and if failed to convert from a date only
        try:
            dt = datetime.datetime.strptime(date, '%Y-%m-%dT%H:%M:%S.%fZ')
        except ValueError:
            try:
                dt = datetime.datetime.strptime(date, '%Y-%m-%d')
            except ValueError:
                return None, None, None, None

        # Making it less naive by assigning UTC timezone
        time_utc = utc.localize(dt)
        # Converting into Eastern timezone for displaying purposes in the USA
        time_et = time_utc.astimezone(eastern).strftime(fmt)
        time_et_date = time_utc.astimezone(eastern).strftime(fmt2)
        # Converting into Central European timezone for displaying purposes in Poland
        time_cet = time_utc.astimezone(warsaw).strftime(fmt)
        time_utc = time_utc.strftime(fmt)
        return time_utc, time_et, time_et_date, time_cet


# Class that calculates scoring for collected games data
class NBAGamesScoringCalculator(NBAGamesDataCollector):
    def __init__(self, playoff_mode=False):  # PLAYOFF2021
        super().__init__(playoff_mode)

    # Calculating score for pandas dataframe. We function calculate to each individual row
    def calculate_score(self):
        self.games_df['SCORE: 0 - 100'] = self.games_df.apply(self.calculate, axis=1)
        return self.games_df

    # Method calculates scoring for a row (a game) in pandas dataset
    # All parameters are here
    def calculate(self, row):
        scoring = 0
        # If game didn't finish we do not calculate a scoring
        if row['Status'] != 'Finished':
            return scoring

        points_diff = int(row['pointsDiff'])
        
        # number of OTS
        no_OT = int(row['OT'])
        no_OT2 = int(row['OT2'])  # number of OTs from another API call
        if no_OT2 > no_OT:  # we take the higher number of OTs
            no_OT = no_OT2
        
        # increase scoring if game went to OT or was very close
        if no_OT >= 3:
            scoring += 30
        elif no_OT == 2:
            scoring += 29
        elif no_OT == 1:
            scoring += 27
        elif points_diff == 1:
            scoring += 27
        elif points_diff > 1 and points_diff <= 3:
            scoring += 25
        elif points_diff > 3 and points_diff <= 6:
            scoring += 19
        elif points_diff > 6 and points_diff <= 10:
            scoring += 8
        elif points_diff > 10 and points_diff <= 15:
            scoring += 1

        # if visiting team has a better win PCT the game may be more leveled
        if row['vPCT'] > row['hPCT']:
            scoring += 3

        # We add score depending on combined ranking of teams
        combined_rank = row['vConfRank'] + row['hConfRank']
        if combined_rank <= 5:
            scoring += 10
        elif combined_rank > 5 and combined_rank <= 10:
            scoring += 8
        elif combined_rank > 10 and combined_rank <= 16:
            scoring += 4

        # we add score if winning PCT of both teams is close to each other
        PCT_diff = abs(row['vPCT'] - row['hPCT'])
        if PCT_diff <= 0.02:
            scoring += 7
        elif PCT_diff > 0.02 and PCT_diff <= 0.04:
            scoring += 5
        elif PCT_diff > 0.04 and PCT_diff <= 0.1:
            scoring += 4
        elif PCT_diff > 0.1 and PCT_diff <= 0.2:
            scoring += 2
        elif PCT_diff > 0.2 and PCT_diff <= 0.3:
            scoring += 1

        # we add score for interesting playoff series - max 4 pts # PLAYOFF2021
        if self.playoff_mode:
            scoring += int(row['Playoff'])

        # We add some point if there was exception indivudual scoring
        if row['Highest pts'] >= 55:
            scoring += 15
        elif row['Highest pts'] >= 48:
            scoring += 10
        elif row['Highest pts'] >= 45:
            scoring += 5
        elif row['Highest pts'] >= 40:
            scoring += 3

        # maximum score is max_scoring. We want to normalize it to get 0 - 100 score easily to understand
        # PLAYOFF2021
        if self.playoff_mode:
            max_scoring = 69    # PLAYOFF_MODE can add up to 4 points that we need to account for during normalization
        else:
            max_scoring = 65
        scoring = round((scoring / max_scoring)*100)

        return scoring

    # printing JSON
    def print_games_json(self):
        print(json.dumps(self.request_games.json(), sort_keys=False, indent=3))

    # dumping games in JSON to a file
    def write_games_to_file(self, file_name):
        with open(file_name, "w") as p:
            p.write(json.dumps(self.request_games.json(), sort_keys=False, indent=3))


# this function returns styled html for the limited scope of columns
def print_scoring_html_styled(games):
    score_df = games[['Start Time ET', 'End Time ET', 'Start Time UTC', 'End Time UTC', 'Visitor',
                      'Host', 'Playoff', 'SCORE: 0 - 100']].copy().sort_values(by=['SCORE: 0 - 100'], ascending=False) # PLAYOFF2021

    html_string_start = '''
    <html>
      <head><title>Games Scoring</title></head>
      <link rel="stylesheet" type="text/css" href="greenTable.css"/>
      <body>
    '''
    html_string_end = '''
      </body>
    </html>
    '''

    with open(r"c:\tmp\scoring_styled.html", "w") as f:
        f.write(html_string_start)
        f.write(r'<table class="greenTable"><thead><tr>')
        for header in score_df.columns.values:
            f.write('<th>' + str(header) + '</th>')
        f.write('</tr></thead><tbody>')
        for i in range(len(score_df)):
            f.write('<tr>')
            for col in score_df.columns:
                value = score_df.iloc[i][col]
                f.write('<td>' + str(value) + '</td>')
            f.write('</tr>')
        f.write('</tbody></table>')
        f.write(html_string_end)


# this function returns simple html with all data
def print_scoring_html_plain(games):
    with open(r"c:\tmp\scoring.html", "w") as p:
        p.write(games.sort_values(by=['SCORE: 0 - 100'], ascending=False).to_html())


# this function saves calculated ranking into 2 CSV files
def print_scoring_csv(games, date: str = "", playoff_mode = False):  # PLAYOFF2021
    # We want print only a subset of columns from games dataframe. We also want present only games that were Finished
    # And finally we want to sort data starting from the highest scoring
    score_df = games[['Visitor', 'Host', 'SCORE: 0 - 100']]\
        .loc[games['Status'] == "Finished"]\
        .sort_values(by=['SCORE: 0 - 100'], ascending=False)

    if playoff_mode: # PLAYOFF2021
        po = "-po"
    else:
        po = ""

    # First, we write a file with the name that includes time scoring-yyyy-mm-dd-HH-MM.csv
    time = datetime.datetime.now().strftime('%H%M')
    with open(r"./scoring/scoring-" + date + " " + time + po + ".csv", "w+") as file: # PLAYOFF2021
        file.write(score_df.sort_values(by=['SCORE: 0 - 100'], ascending=False).to_csv(index=False))

    # The we write to a file that will be overwritten every time cron runs with the name scoring-yyyy-mm-dd.csv
    with open(r"./scoring/scoring-" + date + po + ".csv", "w+") as file: # PLAYOFF2021
        file.write(score_df.sort_values(by=['SCORE: 0 - 100'], ascending=False).to_csv(index=False))


# this function dumps data in a json format
def print_scoring_json(games):
    games[['Visitor', 'Host', 'SCORE: 0 - 100']].copy()\
        .sort_values(by=['SCORE: 0 - 100'], ascending=False) \
        .to_json(r'c:\tmp\scoring.json', orient='records', lines=True)