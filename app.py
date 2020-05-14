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
    db_add_user(steamId)
    #db_add_friends(steamId)
    return jsonify("")

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

def db_add_user(steamId):
    summary = api_users_summary(steamId)
    summary = summary['response']
    summary['players'] = [dict(steamid=key['steamid'], personaname=key['personaname'], avatarmedium=key['avatarmedium']) for key in summary['players']]

    id = summary['players'][0]['steamid']
    name = summary['players'][0]['personaname']
    avatar_url = summary['players'][0]['avatarmedium']

    record_type = param_types.Struct([
        param_types.StructField('steamId', param_types.STRING),
        param_types.StructField('name', param_types.STRING),
        param_types.StructField('avatar_url', param_types.STRING)
    ])
    record_value = (id, name, avatar_url)

    def write_user(transaction):
        row_ct = transaction.execute_update(
            "INSERT Users (steamId, name, avatar_url) "
            "VALUES (@values.steamId, @values.name, @values.avatar_url)",
            params={'name': record_value},
            param_types={'name': record_type}
        )
        print("{} record(s) updated.".format(row_ct))

    global database
    database.run_in_transaction(write_user)

    return

def db_add_friends(steamId):
    friends = api_user_friends(steamId)
    steamIdList = friends #comma deli
    summary = api_users_summary(steamIdList)
    #db add steamId
    #db add name
    #db add avatar_url
    return

if __name__ == '__main__':
    app.run(host='0.0.0.0')
