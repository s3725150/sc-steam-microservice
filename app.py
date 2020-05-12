from flask import Flask, jsonify, request
from flask_cors import CORS
import requests


# configuration
DEBUG = True

# instantiate the app
app = Flask(__name__)
app.config.from_object(__name__)

# enable CORS
CORS(app, resources={r'/*': {'origins': '*'}})

apiKey = "?key=62F5907DB2B29AB7265722A6AD958E32"

#hardcode test data
steamName = "autarchcosmos"
steamId = "76561198038149325"
#factorio app id
appId = "427520"

#Get all Apps on Steam
@app.route('/getAllApps', methods=['GET'])
def get_all_apps():
    url = "http://api.steampowered.com/ISteamApps/GetAppList/v2/"
    r = requests.get(url + apiKey)
    res = r.json()
    return jsonify(res)

#Get owned Apps from steamID
@app.route('/getOwnedApps', methods=['POST'])
def get_owned_apps():
    steamId = request.form.get("steamId")
    url = "http://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    r = requests.get(url + apiKey + "&steamid=" + steamId + "&include_appinfo=1")
    res = r.json()
    res = res['response']
    res['games'] = [dict(appid=key['appid'],img_logo_url=key['img_logo_url'],name=key['name']) for key in res['games']]
    return jsonify(res)

#Get player ID from username
@app.route('/getId', methods=['GET'])
def get_id():
    url = "http://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/"
    r = requests.get(url + apiKey + "&vanityurl=" + steamName)
    res = r.json()
    return jsonify(res["response"]["steamid"])


#Get app details from specific appID
@app.route('/getAppDetails', methods=['GET'])
def get_app_details():
    url = "https://store.steampowered.com/api/appdetails/"
    r = requests.get(url + "?appids=" + appId)
    res = r.json()
    return jsonify(res)

if __name__ == '__main__':
    app.run()
