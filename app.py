from flask import Flask, jsonify
from flask_cors import CORS
import requests


# configuration
DEBUG = True

# instantiate the app
app = Flask(__name__)
app.config.from_object(__name__)

# enable CORS
CORS(app, resources={r'/*': {'origins': '*'}})

apiKey = "62F5907DB2B29AB7265722A6AD958E32"

#hardcode test data
steamName = "autarchcosmos"
steamId = "76561198038149325"
#factorio app id
appId = "427520"

#Get all Apps on Steam
@app.route('/getAppList', methods=['GET'])
def get_applist():
    r = requests.get("http://api.steampowered.com/ISteamApps/GetAppList/v2/?key=" + apiKey)
    res = r.json()
    return jsonify(res)

#Get player ID from username
@app.route('/getId', methods=['GET'])
def get_id():
    r = requests.get("http://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/?key=" + apiKey + "&vanityurl=" + steamName)
    res = r.json()
    return jsonify(res["response"]["steamid"])

#Get owned Apps from player ID
@app.route('/getOwnedApps', methods=['GET'])
def get_owned():
    r = requests.get("http://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key=" + apiKey + "&steamid=" + steamId + "&include_appinfo=1")
    res = r.json()
    return jsonify(res)

#Get app details from specific appID
@app.route('/getAppDetails', methods=['GET'])
def get_app_details():
    r = requests.get("https://store.steampowered.com/api/appdetails/?appids=" + appId)
    res = r.json()
    return jsonify(res)

#Get recently played games with player Id
@app.route('/getRecent', methods=['GET'])
def get_recent():
    r = requests.get("http://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/?key=" + apiKey + "&steamid=" + steamId + "&count=20")
    res = r.json()
    return jsonify(res)

if __name__ == '__main__':
    app.run()
