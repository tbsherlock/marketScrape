import base64
import hashlib
import hmac
import json
from datetime import time
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

from requests import request

BASE_URL = 'https://api.btcmarkets.net'


class BTCMarketsClient:
    def __init__(self, api_key=None, api_secret=None):
        """
        Initialize BTCMarkets API client
        
        Args:
            api_key (str, optional): API key for authenticated requests
            api_secret (str, optional): API secret for authenticated requests
        """
        self.api_key = api_key
        self.api_secret = api_secret
        # Note: Authenticated requests not yet implemented, using public endpoints only
    def get_active_markets(self) -> dict:
        """ Retrieves list of active markets including configuration for each market. """
        path: str = f'/v3/markets'
        return self._make_pub_http_call('GET', path)

    def get_market_orderbook(self, market_id: str) -> dict:
        """ market_id; eg 'BTC-AUD' """
        path: str = f'/v3/markets/{market_id}/orderbook'
        return self._make_pub_http_call('GET', path)

    def _make_pub_http_call(self, method, path, data=None) -> dict:
        header = self._build_pub_headers(method, path)

        try:
            http_request = Request(BASE_URL + path, data, header)
            if method == 'POST' or method == 'PUT':
                response = urlopen(http_request, data = bytes(data, encoding="utf-8"))
            else:
                response = urlopen(http_request)

            return json.loads(str(response.read(), "utf-8"))
        except URLError as e:
            errObject = json.loads(e.read())
            if hasattr(e, 'code'):
                errObject['statusCode'] = e.code

            return errObject

    def _build_pub_headers(self, method, path):
        headers = {
            "Accept": "application/json",
            "Accept-Charset": "UTF-8",
            "Content-Type": "application/json",
        }
        return headers

    def _priv_post_request(self, path, postData):
        nowInMilisecond = str(int(time.time() * 1000))
        stringToSign = path + "\n" + nowInMilisecond + "\n" + postData

        signature = base64.b64encode(hmac.new(self.api_secret, stringToSign, digestmod=hashlib.sha512).digest())

        return request('post', self.api_key, signature, nowInMilisecond, path, postData)