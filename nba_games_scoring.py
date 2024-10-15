"""
nba_games_scoring.py

Collects games data from external APIs. 
Calculates a ranking.
Saves it in CSV files.

Script should be executed as a cron process.

Author: Szymon Manduk AI

Created: Feb-2020
"""
import datetime
import pandas as pd
import nbagames as nba  

playoff = False  

if __name__ == "__main__":
    calculator = nba.NBAGamesScoringCalculator(playoff)  

    # Because the API returns games for the date in UTC and games are played in ET, we need to first take all games
    # played on the date we are interested in, then all games from the day after
    # and filter games by start time in ET on the date we are interested in
    # "the date we are interested in" is the same date which is given on NBA.com
    date = datetime.date.today() - datetime.timedelta(days=1)  # "the date we are interested in" - here yesterday

    # get data from api-nba-v1.p.rapidapi.com. Returns number of games returned by the API
    no_of_games_1 = calculator.get_games_data(date)

    # get data from playoff file 
    calculator.get_playoff_data()

    # we need to initialize games DataFrame in case no_of_games is 0 and variable games will be never initialized
    games = pd.DataFrame()
    final_no_games_1 = 0
    if no_of_games_1 > 0:
        # get all data we need to calculate scoring
        final_no_games_1 = calculator.get_games_stats()

        if final_no_games_1 > 0:
            # calculate score and return a dataframe with data and scoring
            games = calculator.calculate_score()

    # Next the day after - here in this cron process, it will be today
    date_after = date + datetime.timedelta(days=1)
    no_of_games_2 = calculator.get_games_data(date_after)
    final_no_games_2 = 0
    if no_of_games_2 > 0:
        # get all data we need to calculate scoring
        final_no_games_2 = calculator.get_games_stats()

        if final_no_games_2 > 0:
            # calculate score and return a dataframe with data and scoring
            games_day_after = calculator.calculate_score()

            # Combine data collected in games and games_day_before. ignore_index to reset indexing after concatenating dataframes
            games = pd.concat([games, games_day_after], ignore_index=True)

    # Filter data to remove rows for games that took place before date we're asking for
    # We look for rows with "Start time ET" equal to "date"
    date_str = date.strftime('%Y-%m-%d')
    indexes = games[games['Start Time ET Date'] != date_str].index
    games.drop(indexes, inplace=True)

    # in case no games were played on the day we are interested in, print message and exit
    if len(games) == 0:
        print("No games to evaluate on", date)
        exit()

    # Print to csv file. There will be 2 files written on every cron execution.
    # One with the name that includes time scoring-yyyy-mm-dd-HH-MM.csv
    # And the other, that will be overwritten every time cron runs with the name scoring-yyyy-mm-dd.csv
    nba.print_scoring_csv(games, date_str, playoff_mode=False) 
