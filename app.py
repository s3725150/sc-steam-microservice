from flask import Flask, jsonify, request
from flask_cors import CORS
from google.cloud import spanner
import requests

"""
--------------------------------
Initialization
--------------------------------
"""
# configuration
DEBUG = True

# instantiate the app
app = Flask(__name__)
app.config.from_object(__name__)

# enable CORS
CORS(app, resources={r'/*': {'origins': '*'}})

# Steam Web API key
apiKey = "?key=62F5907DB2B29AB7265722A6AD958E32"

# Spanner Init
# Instantiate a client.
spanner_client = spanner.Client()

# Your Cloud Spanner instance ID.
instance_id = 'steam-chat'

# Get a Cloud Spanner instance by ID.
instance = spanner_client.instance(instance_id)

# Your Cloud Spanner database ID.
database_id = 'steam_data'

# Get a Cloud Spanner database by ID.
database = instance.database(database_id)




"""
--------------------------------
GET/POST Routes
--------------------------------
"""
# Respond with the list {appid, logo, name} games user owns
@app.route('/gameList', methods=['POST'])
def game_list():
    steamId = request.form.get("steamId")
    res = api_get_owned_games(steamId)
    res = res['response']
    res['games'] = [dict(appid=key['appid'],img_logo_url=key['img_logo_url'],name=key['name']) for key in res['games']]
    return jsonify(res)

# Add user and games to DB then respond with stats
@app.route('/myStats', methods=['POST'])
def my_stats():
    steamId = request.form.get("steamId")
    db_add_user_and_games(steamId)
    stats = get_name_and_avatar(steamId)
    stats = merge(stats, get_total_playtime(steamId))
    stats = merge(stats, get_total_and_unplayed_games(steamId))
    stats = merge(stats, get_top_played(steamId))
    return jsonify(stats)



"""
--------------------------------
Steam Web API calls
--------------------------------
"""
def api_get_owned_games(steamId):
    url = "http://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    r = requests.get(url + apiKey + "&steamid=" + steamId + "&include_appinfo=1")
    return r.json()

def api_user_friends(steamId):
    url = "http://api.steampowered.com/ISteamUser/GetFriendList/v0001/"
    r = requests.get(url + apiKey + "&steamid=" + steamId + "&relationship=friend")
    return r.json()

def api_users_summary(steamIdList):
    url = "http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
    r = requests.get(url + apiKey + "&steamids=" + steamIdList)
    return r.json()




"""
--------------------------------
Insert/Update Google Spanner DB
--------------------------------
"""
def db_add_user_and_games(steamId):
    summary = api_users_summary(steamId)
    summary = summary['response']
    summary['players'] = [dict(steamid=key['steamid'], personaname=key['personaname'], avatarmedium=key['avatarmedium']) for key in summary['players']]

    id = summary['players'][0]['steamid']
    name = summary['players'][0]['personaname']
    avatar_url = summary['players'][0]['avatarmedium']
    data = [(id, name, avatar_url)]

    with database.batch() as batch:
        batch.insert_or_update(
            table='Users',
            columns=('steamId', 'name', 'avatar_url',),
            values=data)
    print('Inserted / Updated User ', steamId)
    db_add_games(id)
    return

def db_add_friends_and_games(steamId):
    friendList = api_user_friends(steamId)
    friendList = friendList['friendslist']
    friendList['friends'] = [dict(steamid=key['steamid'])for key in friendList['friends']]
    length = len(friendList['friends'])
    steamIdList = ""
    for i in range(length):
        id = friendList['friends'][i]['steamid']
        steamIdList += id
        if i < length-1:
            id += ","

    summary = api_users_summary(steamIdList)
    summary = summary['response']
    summary['players'] = [dict(steamid=key['steamid'], personaname=key['personaname'], avatarmedium=key['avatarmedium']) for key in summary['players']]

    length = len(summary['players'])
    data = []
    for i in range(length):
        id = summary['players'][i]['steamid']
        name = summary['players'][i]['personaname']
        avatar_url = summary['players'][i]['avatarmedium']
        data += [(id, name, avatar_url)]

    with database.batch() as batch:
        batch.insert_or_update(
            table='Users',
            columns=('steamId', 'name', 'avatar_url',),
            values=data)
    print('Inserted / Updated Friends for ', steamId)

    for i in range(length):
        id = summary['players'][i]['steamid']
        db_add_games(id)
    return

def db_add_games(steamId):
    summary = api_get_owned_games(steamId)
    summary = summary['response']
    summary['games'] = [dict(appid=key['appid'], name=key['name'], playtime_forever=key['playtime_forever']) for key in summary['games']]

    length = len(summary['games'])
    data = []
    for i in range(length):
        appId = summary['games'][i]['appid']
        name = summary['games'][i]['name']
        playtime_forever = summary['games'][i]['playtime_forever']
        data += [(appId, steamId, name, playtime_forever)]

    with database.batch() as batch:
        batch.insert_or_update(
            table='Games',
            columns=('appId', 'steamId', 'name', 'playtime',),
            values=data)
    print('Inserted / Updated Games for ', steamId)
    return




"""
--------------------------------
Query DB & Analytics
--------------------------------
"""
def get_name_and_avatar(steamId):
    name = ''
    avatar = ''

    with database.snapshot() as snapshot:
        query = "SELECT name, avatar_url FROM Users WHERE steamId =" + "'" + steamId + "'"
        results = snapshot.execute_sql(query)
        for row in results:
            name = row[0]
            avatar = row[1]

    res = dict(name=name, avatar=avatar)
    return res

def get_total_playtime(steamId):
    playtime = 0

    with database.snapshot() as snapshot:
        query = "SELECT SUM(playtime) FROM Games WHERE steamId = " + "'" + steamId + "'"
        results = snapshot.execute_sql(query)
        for row in results:
            playtime = row[0]/60

    res = dict(playtime=int(playtime))
    return res

def get_total_and_unplayed_games(steamId):
    total = 0
    unplayed = 0

    with database.snapshot() as snapshot:
        query = "SELECT COUNT(appid) FROM Games WHERE steamId = " + "'" + steamId + "'"
        results = snapshot.execute_sql(query)
        for row in results:
            total = row[0]

    with database.snapshot() as snapshot:
        query = "SELECT COUNT(appid) FROM Games WHERE steamId = " + "'" + steamId + "' AND playtime < 10"
        results = snapshot.execute_sql(query)
        for row in results:
            unplayed = row[0]

    unplayed_percent = (unplayed/total)*100
    res = dict(total=total, unplayed=unplayed, unplayed_percent=int(unplayed_percent))
    return res

def get_top_played(steamId):

    with database.snapshot() as snapshot:
        query = "SELECT name, playtime FROM Games WHERE steamId = " + "'" + steamId + "' ORDER BY playtime DESC LIMIT 10"
        results = snapshot.execute_sql(query)
        gameList = []
        res = dict(game=[])
        for row in results:
            name = row[0]
            playtime = row[1]/60
            game = dict(name=name, playtime=int(playtime))
            gameList.append(game)
        res = dict(topPlayed=gameList)
    return res



def merge(dict1, dict2):
    res = dict(dict1, **dict2)
    return res

if __name__ == '__main__':
    app.run(host='0.0.0.0')
