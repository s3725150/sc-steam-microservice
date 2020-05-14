from flask import Flask, jsonify, request
from flask_cors import CORS
from google.cloud import spanner
from google.cloud.spanner import param_types
import requests


# configuration
DEBUG = True

# instantiate the app
app = Flask(__name__)
app.config.from_object(__name__)

# enable CORS
CORS(app, resources={r'/*': {'origins': '*'}})

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


# Respond with the list {appid, logo, name}  games user owns
@app.route('/gameList', methods=['POST'])
def game_list():
    steamId = request.form.get("steamId")
    res = api_get_owned_games(steamId)
    res = res['response']
    res['games'] = [dict(appid=key['appid'],img_logo_url=key['img_logo_url'],name=key['name']) for key in res['games']]
    return jsonify(res)

# Res
@app.route('/addUser', methods=['POST'])
def add_user():
    steamId = request.form.get("steamId")
    db_add_user_and_games(steamId)
    stats = db_get_total_playtime(steamId)
    #db_add_friends_and_games(steamId)
    return jsonify(stats)

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

def db_get_total_playtime(steamId):
    name = ''
    avatar = ''
    playtime = 0

    with database.snapshot() as snapshot:
        query = "SELECT name, avatar_url FROM Users WHERE steamId =" + "'" + steamId + "'"
        results = snapshot.execute_sql(query)
        for row in results:
            name = row[0]
            avatar = row[1]

    with database.snapshot() as snapshot:
        query = "SELECT SUM(playtime) FROM Games WHERE steamId = " + "'" + steamId + "'"
        results = snapshot.execute_sql(query)
        for row in results:
            playtime = row[0]/60

    res = dict(name=name, avatar=avatar, playtime=playtime)
    return res


if __name__ == '__main__':
    app.run(host='0.0.0.0')
