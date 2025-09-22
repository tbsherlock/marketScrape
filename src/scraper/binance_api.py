import json
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
import urllib.parse


BASE_URL = 'https://api.binance.com'


class BinanceClient:
    def exchange_information(self) -> dict:
        """ Current exchange trading rules and symbol information """
        path: str = f'/api/v3/exchangeInfo'
        return self._make_pub_http_call('GET', path)

    def current_average_price(self, market_id: str) -> dict:
        """ Current average price for a symbol. """
        path: str = f'/api/v3/avgPrice'
        params = {'symbol': market_id}
        return self._make_pub_http_call(method='GET', path=path, params=params)

    def _make_pub_http_call(self, method, path, params=None, data=None) -> dict:
        if params is None:
            params = {}

        header = self._build_pub_headers(method, path)
        query_string = urllib.parse.urlencode(params)
        full_url = f"{BASE_URL}{path}?{query_string}"
        try:
            http_request = Request(full_url, data, header)
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
