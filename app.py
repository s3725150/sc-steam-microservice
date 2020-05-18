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
DEBUG = False

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
    steamId = api_get_steamId(request.form.get("steamId"))
    res = "error"
    if steamId != "err":
        res = api_get_owned_games(steamId)
        res = res['response']
        res['games'] = [dict(appid=key['appid'],img_logo_url=key['img_logo_url'],name=key['name']) for key in res['games']]
    return jsonify(res)

# Add user and games to DB then respond with user stats
@app.route('/myStats', methods=['POST'])
def my_stats():
    steamId = api_get_steamId(request.form.get("steamId"))
    stats = "error"
    if steamId != "err":
        db_add_user_and_games(steamId)
        stats = get_name_and_avatar(steamId)
        stats = merge(stats, get_total_playtime(steamId))
        stats = merge(stats, get_total_and_unplayed_games(steamId))
        stats = merge(stats, get_top_played_games(steamId))
    return jsonify(stats)

# Global Stats Leaderboard
@app.route('/globalStats', methods=['POST'])
def global_stats():
    steamId = api_get_steamId(request.form.get("steamId"))
    res = "error"
    if steamId != "err":
        myStats = get_name_and_avatar(steamId)
        myStats = merge(myStats, get_total_playtime_rank(steamId))
        myStats = merge(myStats, get_game_count_rank(steamId))
        myStats = merge(myStats, get_played_percent_rank(steamId))
        res = dict(user_stats=myStats)
        res = merge(res, get_global_top_playtime())
        res = merge(res, get_global_top_game_count())
        res = merge(res, get_global_top_played_percent())
    return jsonify(res)

# Most Popular Game among users
@app.route('/popularGame', methods=['GET'])
def popular_game():
    res = get_total_users()
    res = merge(res, get_global_most_popular_game())
    return jsonify(res)



"""
--------------------------------
Steam Web API calls
--------------------------------
"""
def api_get_steamId(data):
    steamId = "err"

    url = "http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
    r = requests.get(url + apiKey + "&steamids=" + data)
    r = r.json()
    r = r['response']
    r = r['players']
    if r:
        steamId = data

    url = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/"
    r = requests.get(url + apiKey + "&vanityurl=" + data)
    r = r.json()
    r=r['response']
    if r['success'] == 1:
        steamId = r['steamid']
    return steamId

def api_get_owned_games(steamId):
    url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    r = requests.get(url + apiKey + "&steamid=" + steamId + "&include_appinfo=1")
    return r.json()

def api_users_summary(steamIdList):
    url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
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

def db_add_games(steamId):
    summary = api_get_owned_games(steamId)
    summary = summary['response']
    if summary:
        summary['games'] = [dict(appid=key['appid'], name=key['name'], img_logo_url=key['img_logo_url'], playtime_forever=key['playtime_forever']) for key in summary['games']]

        length = len(summary['games'])
        data = []
        for i in range(length):
            appId = summary['games'][i]['appid']
            name = summary['games'][i]['name']
            img_logo_url = "http://media.steampowered.com/steamcommunity/public/images/apps/" + str(appId) +"/"+ str(summary['games'][i]['img_logo_url']) + ".jpg"
            playtime_forever = summary['games'][i]['playtime_forever']
            data += [(appId, steamId, name, img_logo_url, playtime_forever)]

        with database.batch() as batch:
            batch.insert_or_update(
                table='Games',
                columns=('appId', 'steamId', 'name', 'img_logo_url', 'playtime',),
                values=data)
        print('Inserted / Updated Games for ', steamId)
    return



"""
--------------------------------
Query DB & Analytics
--------------------------------
"""
def get_total_users():
    with database.snapshot() as snapshot:
        query = "SELECT COUNT(steamId) FROM Users"
        results = snapshot.execute_sql(query)

        total = 0
        for row in results:
            total = int(row[0])
        res = dict(total_users=total)
    return res

def get_name_and_avatar(steamId):
    name = ''
    avatar = ''

    with database.snapshot() as snapshot:
        query = "SELECT name, avatar_url FROM Users WHERE steamId =" + "'" + steamId + "'"
        results = snapshot.execute_sql(query)
        for row in results:
            name = row[0]
            avatar = row[1]

    res = dict(name=name, avatar_url=avatar)
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

def get_top_played_games(steamId):
    with database.snapshot() as snapshot:
        query = "SELECT name, playtime FROM Games WHERE steamId = " + "'" + steamId + "' ORDER BY playtime DESC LIMIT 10"
        results = snapshot.execute_sql(query)
        gameList = []
        for row in results:
            name = row[0]
            playtime = row[1]/60
            game = dict(name=name, playtime=int(playtime))
            gameList.append(game)
        res = dict(top_played=gameList)
    return res


def get_total_playtime_rank(steamId):
    playtime = 0
    with database.snapshot() as snapshot:
        query = "SELECT SUM(playtime) FROM Games WHERE steamId = " + "'" + steamId + "'"
        results = snapshot.execute_sql(query)
        for row in results:
            playtime = int(row[0])
    
    rank = 0
    with database.snapshot() as snapshot:
        query = ("SELECT COUNT(sid) "
                 "FROM( "
                 "SELECT g.steamId AS sid, SUM(playtime) AS sum_play "
                 "FROM Games g "
                 "GROUP BY steamId "
                 ") SUBQUERY "
                 "WHERE sum_play > " + str(playtime) + " ")
        results = snapshot.execute_sql(query)
        for row in results:
            rank = int(row[0]) + 1       

    resList=[dict(playtime=int(playtime/60), rank=rank)]
    res = dict(playtime_rank=resList)
    return res

def get_game_count_rank(steamId):
    count = 0
    with database.snapshot() as snapshot:
        query = "SELECT COUNT(appId) FROM Games WHERE steamId = " + "'" + steamId + "'"
        results = snapshot.execute_sql(query)
        for row in results:
            count = int(row[0])
    
    rank = 0
    with database.snapshot() as snapshot:
        query = ("SELECT COUNT(sid) "
                 "FROM( "
                 "SELECT g.steamId AS sid, COUNT(appId) AS count "
                 "FROM Games g "
                 "GROUP BY steamId "
                 ") SUBQUERY "
                 "WHERE count > " + str(count) + " ")
        results = snapshot.execute_sql(query)
        for row in results:
            rank = int(row[0]) + 1       

    resList=[dict(game_count=count, rank=rank)]
    res = dict(game_count_rank=resList)
    return res

def get_played_percent_rank(steamId):
    percent = 0
    with database.snapshot() as snapshot:
        query = ("SELECT (t1.played / t2.total)*100 AS percent "
                 "FROM( "
                 "SELECT g.steamId AS id1, COUNT(g.appId) AS played "
                 "FROM Games g "
                 "WHERE playtime >=10 "
                 "GROUP BY id1 "
                 ") t1 "
                 "LEFT JOIN ( "
                 "SELECT g.steamId AS id2, COUNT(g.appId) AS total "
                 "FROM Games g "
                 "GROUP BY id2 "
                 ") t2 "
                 "ON t2.id2 = t1.id1 "
                 "WHERE id1 = '" + steamId + "' ")
        results = snapshot.execute_sql(query)
        for row in results:
            percent = row[0]
    
    rank = 0
    with database.snapshot() as snapshot:
        query = ("SELECT COUNT(sid) "
                 "FROM( "
                 "SELECT id1 AS sid, (t1.played / t2.total)*100 AS percent  "
                 "FROM( "
                 "SELECT g.steamId AS id1, COUNT(g.appId) AS played "
                 "FROM Games g "
                 "WHERE playtime >=10 "
                 "GROUP BY id1 "
                 ") t1 "
                 "LEFT JOIN ( "
                 "SELECT g.steamId AS id2, COUNT(g.appId) AS total "
                 "FROM Games g "
                 "GROUP BY id2 "
                 ") t2 "
                 "ON t2.id2 = t1.id1 "
                 ") SUBQUERY "
                 "WHERE percent > " + str(percent) + " ")
        results = snapshot.execute_sql(query)
        for row in results:
            rank = int(row[0]) + 1       

    resList=[dict(play_percent=int(percent), rank=rank)]
    res = dict(play_percent_rank=resList)
    return res

def get_global_most_popular_game():
    with database.snapshot() as snapshot:
        query = ("SELECT name, img_logo_url, SUM(playtime) AS p, COUNT(*) AS c "
                 "FROM Games "
                 "GROUP BY name, img_logo_url "
                 "ORDER BY c DESC, p DESC LIMIT 1 ")
        results = snapshot.execute_sql(query)
        resList = []
        for row in results:
            name = row[0]
            img_logo_url = row[1]
            playtime = row[2]/60
            count = row[3]
            entry = dict(name=name, img_logo_url=img_logo_url, playtime=int(playtime), count=count)
            resList.append(entry)
        res = dict(popular_game=resList)
    return res

def get_global_top_playtime():
    with database.snapshot() as snapshot:
        query = ("SELECT t2.sname, t2.avatar, t1.playsum "
                 "FROM ( "
                 "SELECT g.steamId AS id1, SUM(g.playtime) AS playsum "
                 "FROM Games g "
                 "GROUP BY id1 "
                 " ) t1 "
                 "LEFT JOIN ( "
                 "SELECT u.steamId AS id2, u.name AS sname, u.avatar_url AS avatar "
                 "FROM Users u "
                 "GROUP BY id2, avatar, sname "
                 " ) t2 "
                 "ON t2.id2 = t1.id1 "
                 "ORDER BY t1.playsum DESC LIMIT 10 ")
        results = snapshot.execute_sql(query)
        resList = []
        for row in results:
            sid = row[0]
            avatar = row[1]
            playtime = row[2]/60
            entry = dict(steamId=sid, avatar_url=avatar, playtime=int(playtime))
            resList.append(entry)
        res = dict(global_playtime=resList)
    return res

def get_global_top_game_count():
    with database.snapshot() as snapshot:
        query = ("SELECT t2.sname, t2.avatar, t1.gamecount "
                 "FROM ( "
                 "SELECT g.steamId AS id1, COUNT(g.appId) AS gamecount "
                 "FROM Games g "
                 "GROUP BY id1 "
                 " ) t1 "
                 "LEFT JOIN ( "
                 "SELECT u.steamId AS id2, u.name AS sname, u.avatar_url AS avatar "
                 "FROM Users u "
                 "GROUP BY id2, avatar, sname "
                 " ) t2 "
                 "ON t2.id2 = t1.id1 "
                 "ORDER BY t1.gamecount DESC LIMIT 10 ")
        results = snapshot.execute_sql(query)
        resList = []
        for row in results:
            sid = row[0]
            avatar = row[1]
            count = row[2]
            entry = dict(steamId=sid, avatar_url=avatar, game_count=count)
            resList.append(entry)
        res = dict(global_game_count=resList)
    return res

def get_global_top_played_percent():
    with database.snapshot() as snapshot:
        query = ("SELECT t3.sname, t3.avatar, (t1.played / t2.total)*100 AS percent "
                 "FROM ( "
                 "SELECT g.steamId AS id1, COUNT(g.appId) AS played "
                 "FROM Games g "
                 "WHERE playtime >=10 "
                 "GROUP BY id1 "
                 " ) t1 "
                 "LEFT JOIN ( "
                 "SELECT g.steamId AS id2, COUNT(g.appId) AS total "
                 "FROM Games g "
                 "GROUP BY id2 "
                 " ) t2 "
                 "ON t2.id2 = t1.id1 "
                 "LEFT JOIN ( "
                 "SELECT u.steamId AS id3, u.name AS sname, u.avatar_url AS avatar "
                 "FROM Users u "
                 "GROUP BY id3, avatar, sname "
                 " ) t3 "
                 "ON t3.id3 = t2.id2 "
                 "ORDER BY percent DESC LIMIT 10")

        results = snapshot.execute_sql(query)
        resList = []
        for row in results:
            sid = row[0]
            avatar = row[1]
            percent = int(row[2])
            entry = dict(steamId=sid, avatar_url=avatar, played_percent=percent)
            resList.append(entry)
        res = dict(global_play_percent=resList)
    return res



def merge(dict1, dict2):
    res = dict(dict1, **dict2)
    return res

if __name__ == '__main__':
    app.run(host='0.0.0.0')
